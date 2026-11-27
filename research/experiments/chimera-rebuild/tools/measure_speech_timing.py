"""発話区間を固定上流、独立した手計算、上流CLIのマークと照合する。"""

import argparse
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/speech-timing.json'
PROBE = WORKSPACE / 'tools/upstream_speech_timing_probe.rs'
CANDIDATE = WORKSPACE / 'crates/vocal-core/src/phonetics'
UPPER = UPSTREAM / 'crates/chimera/src/phonetics'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def compare(actual, reference, tolerance):
    maximum = 0.0

    def first(left, right, path):
        nonlocal maximum
        if type(left) in (float, int) and type(right) in (float, int):
            delta = abs(left - right)
            maximum = max(maximum, delta)
            if math.isfinite(delta) and delta <= tolerance:
                return None
        elif isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
            return next((mismatch for key in sorted(left)
                         if (mismatch := first(left[key], right[key], [*path, key]))), None)
        elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            return next((mismatch for i, (a, b) in enumerate(zip(left, right, strict=True))
                         if (mismatch := first(a, b, [*path, i]))), None)
        elif left == right and type(left) is type(right):
            return None
        return {'path': path, 'candidate': left, 'reference': right}

    mismatch = first(actual, reference, [])
    return mismatch, maximum


def kind(part):
    return part['manner'] or '?'


def upper_view(entry):
    utterances = []
    for row in entry['utterances']:
        parts = []
        for part in row['segments']:
            value = {'ipa': part['segment']['ipa'], 'kind': kind(part),
                     't0': part['start_seconds'], 't1': part['end_seconds']}
            if value['kind'] == 'vowel':
                value['stress'] = part['segment'].get('stress', 0)
            parts.append(value)
        utterances.append({**{key: row[key] for key in ('text', 'input_segments', 'start_seconds',
                                                        'end_seconds', 'durations_seconds')},
                           'segments': parts})
    return {**entry, 'utterances': utterances}


def registered(entry, expected):
    rows = entry['utterances']
    pick = {
        'duration_rows': lambda row: row['durations_seconds'],
        'kind_rows': lambda row: [kind(part) for part in row['segments']],
        'symbol_rows': lambda row: [part['segment']['ipa'] for part in row['segments']],
        'part_durations': lambda row: [part['end_seconds'] - part['start_seconds']
                                       for part in row['segments']],
    }
    actual = {key: {idx: get(rows[int(idx)]) for idx in expected[key]}
              for key, get in pick.items() if key in expected}
    if 'first_start_seconds' in expected:
        actual['first_start_seconds'] = rows[0]['segments'][0]['start_seconds']
    if 'utterances' in expected:
        actual['utterances'] = len(rows)
    if 'render_end_seconds' in expected:
        actual['render_end_seconds'] = entry['render_end_seconds']
    return actual


def valid_mapping(example, entry, expansions, tolerance):
    raw = example.get('text', '').encode('utf-8')
    for row in entry['utterances']:
        source = row['input_segments']
        if 'text' in example:
            span = row['source_span']
            begin, end = span['start_byte'], span['end_byte']
            if raw[begin:end].decode('utf-8') != row['text'] or len(row['input_spans']) != len(source):
                return False
            for span in row['input_spans']:
                start, stop = span['start_byte'], span['end_byte']
                if not begin <= start < stop <= end or not raw[start:stop].decode('utf-8'):
                    return False
        spans = [[] for _ in source]
        previous_end = row['start_seconds'] + 0.06
        last_index = -1
        for part in row['segments']:
            index = part['input_index']
            if (not 0 <= index < len(source) or index < last_index
                    or part['glide_from_previous'] != bool(spans[index])
                    or abs(part['start_seconds'] - previous_end) > tolerance):
                return False
            segment = part['segment']
            original = source[index]
            raw_length = segment['dur']
            scheduled_length = part['end_seconds'] - part['start_seconds']
            if abs(scheduled_length - raw_length / entry['rate']) > tolerance:
                return False
            if original['ipa'] in expansions:
                kept = ('stress', 'f0', 'nasalized', 'breathy')
                expected = {key: original[key] for key in kept if key in original}
            else:
                expected = {key: value for key, value in original.items() if key not in ('ipa', 'dur')}
            if expected != {key: value for key, value in segment.items() if key not in ('ipa', 'dur')}:
                return False
            spans[index].append(raw_length)
            previous_end = part['end_seconds']
            last_index = index
        if abs(previous_end - row['end_seconds']) > tolerance or any(
                not parts or abs(math.fsum(parts) - raw_length) > tolerance
                for parts, raw_length in zip(spans, row['durations_seconds'], strict=True)):
            return False
    return True


def compare_cases(examples, candidate, upper, expansions, tolerance):
    rows = []
    for example, actual, reference in zip(examples, candidate['entries'], upper['entries'], strict=True):
        if actual['id'] != example['id'] or reference['id'] != example['id']:
            raise ValueError('入力IDの順序がケースと異なります')
        first, maximum = compare(upper_view(actual), reference, tolerance)
        expected = example.get('expected', {})
        prereg, _ = compare(registered(actual, expected), expected, tolerance)
        mapping = valid_mapping(example, actual, expansions, tolerance)
        rows.append({'id': example['id'], 'maximum_checked_difference_seconds': maximum,
                     'first_upstream_difference': first, 'first_registered_difference': prereg,
                     'mapping_valid': mapping, 'passed': first is None and prereg is None and mapping})
    return rows


def parse_catalog_request():
    rules = (UPPER/'planner.rs').read_text().split('pub fn expand(', 1)[1].split('/// A rising nucleus', 1)[0]
    durations = (UPPER/'durations.rs').read_text().split('fn table(', 1)[1].split('const NUCLEUS_VOWEL_MIN', 1)[0]
    symbols = re.findall(r'^\s*"([^"]+)" => &\[', rules, re.M)
    pairs = re.findall(r'^\s*"([^"]+)" => \((\d+\.0), (\d+\.0)\),', durations, re.M)
    return {'expansion_candidates': symbols,
            'klatt_milliseconds': {ipa: [float(a), float(b)] for ipa, a, b in pairs}}


def matrix_case(case, catalog, vowels):
    examples = []
    contexts = {
        'alone': lambda s: [s],
        'between_vowels': lambda s: [{'ipa': 'ɑ'}, s, {'ipa': 'ɑ', 'stress': 2}],
        'after_stop': lambda s: [{'ipa': 'p'}, {**s, 'stress': 1}],
        'before_voiced_fricative': lambda s: [{**s, 'stress': 1}, {'ipa': 'z', 'wordEnd': True}],
        'explicit_and_rate': lambda s: [{**s, 'dur': .17, 'stress': 2, 'nasalized': True}, {'ipa': 'ɹ'}],
    }
    symbols = sorted(set(vowels).union(*(table.keys() for table in catalog.values())))
    for i, symbol in enumerate(symbols):
        for name in case['measurement']['matrix_contexts']:
            rate = 1.6 if name == 'explicit_and_rate' else 1.0
            examples.append({'id': f'{i:03d}-{name}', 'rate': rate,
                             'segments': contexts[name]({'ipa': symbol})})
    return {**case, 'id': 'speech-timing-matrix', 'speech_timing': {'inputs': examples}}


def independent(entries):
    vcv = entries['vcv']['utterances']
    cues = entries['word-final-cue']['utterances']
    # 秒で計算する。元のミリ秒表を読み込まず、ノートの値から展開する。
    d = Decimal
    effects = tuple(map(d, ('0.7', '1.2', '1', '1.6', '0.85')))
    raw_vcv = [
        float(d('.050') + d('.190') * d('.6') * d('.85') * d('.8') * d('.7') * (d('.7') + d('.3') * f))
        for f in effects
    ]
    final_vcv = float(d('.050') + d('.190') * d('1.4') * d('.8') * d('.7'))
    raw_cues = [float(d('.080') + d('.150') * d('1.4') * f) for f in effects]
    actual = [[row['durations_seconds'][0] for row in vcv],
              [row['durations_seconds'][2] for row in vcv],
              [row['durations_seconds'][1] for row in cues]]
    expected = [raw_vcv, [final_vcv] * len(effects), raw_cues]

    # 話速は区間長を変え、先頭のリードは一定に保つ。
    slow = entries['falling']['utterances'][0]
    fast = entries['fast']['utterances'][0]
    actual.extend([fast['durations_seconds'],
                   [s['end_seconds'] - s['start_seconds'] for s in fast['segments']]])
    expected.extend([slow['durations_seconds'],
                     [(s['end_seconds'] - s['start_seconds']) / 1.6 for s in slow['segments']]])
    return actual, expected


def native_cli(artifacts, execute, text, entry, measurement):
    log = artifacts/'upstream-native.log'
    stem = artifacts/'upstream-native'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--',
             'render', 'speech', str(stem), text, 'male', '--float'], cwd=UPSTREAM, stdout=log)
    fields = [token.rsplit('@', 1) for token in log.read_text().splitlines()[-1].split()]
    sample_rate, wave = wavfile.read(stem.with_suffix('.wav'))
    parts = [part for row in entry['utterances'] for part in row['segments']]
    symbols_match = [key for key, seconds in fields] == [part['segment']['ipa'] for part in parts]
    maximum = max(abs(float(seconds) - part['start_seconds'])
                  for (_, seconds), part in zip(fields, parts, strict=True))
    frames = math.floor(entry['render_end_seconds'] * sample_rate + 0.5)
    return {'symbols_match': symbols_match,
            'max_marker_error_seconds': maximum,
            'sample_rate_hz': sample_rate, 'frames': len(wave), 'expected_frames': frames,
            'passed': symbols_match and maximum <= measurement['native_marker_tolerance_seconds']
            and sample_rate == measurement['native_sample_rate_hz'] and len(wave) == frames
            and bool(np.isfinite(wave).all())}


def measure(case, artifacts, execute):
    measurement = case['measurement']
    tolerance = measurement['absolute_tolerance_seconds']
    examples = case['speech_timing']['inputs']
    actual_path, upper_path = artifacts/'speech-timing.json', artifacts/'upstream-speech-timing.json'
    execute([*CLI, 'inspect', str(CASE)], stdout=artifacts/'settings.json')
    execute([*CLI, 'render', str(CASE), str(actual_path)])
    for suite, test in (
        ('golden_planning', 'klatt_durations_match_typescript'),
        ('nasal_spans', 'a_vowel_and_its_coda_r_share_the_vowels_span'),
        ('speech_quality', 'phrase_final_lengthening_and_stress_contrast'),
    ):
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', suite, test],
                cwd=UPSTREAM, stdout=artifacts/f'upstream-test-{suite}.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(CASE)], cwd=UPSTREAM, stdout=upper_path)
    request, reference_catalog = artifacts/'catalog-request.json', artifacts/'upstream-timing-catalog.json'
    write(request, parse_catalog_request())
    execute([str(probe), '--catalog', str(request)], cwd=UPSTREAM, stdout=reference_catalog)
    catalog = read(reference_catalog)
    vowels = read(CANDIDATE/'ipa/catalog.generated.json')['calibrated_vowels']
    upper_vowels = read(UPPER/'vowelTargets.generated.json')

    matrix = matrix_case(case, catalog, vowels)
    matrix_path = artifacts/'matrix-case.json'
    matrix_out, matrix_upper = artifacts/'matrix-speech-timing.json', artifacts/'upstream-matrix.json'
    write(matrix_path, matrix)
    execute([*CLI, 'render', str(matrix_path), str(matrix_out)])
    execute([str(probe), str(matrix_path)], cwd=UPSTREAM, stdout=matrix_upper)
    expansions = catalog['expansions']
    matrix_checks = compare_cases(matrix['speech_timing']['inputs'], read(matrix_out), read(matrix_upper),
                                  expansions, tolerance)
    actual = read(actual_path)
    cases = compare_cases(examples, actual, read(upper_path), expansions, tolerance)
    entries = {row['id']: row for row in actual['entries']}
    decimal_difference, decimal_max = compare(*independent(entries), tolerance)
    native_example = next(row for row in examples if row['id'] == measurement['native_cli_input'])
    native_entry = entries[native_example['id']]
    single_path = artifacts/'single-input.json'
    execute([*CLI, 'plan', native_example['text']], stdout=single_path)
    native = native_cli(artifacts, execute, native_example['text'], native_entry, measurement)
    matrix_failures = [row for row in matrix_checks if not row['passed']]
    checks = {
        'registered_cases': all(row['passed'] for row in cases),
        'matrix_matches_upstream': not matrix_failures,
        'catalog_matches_upper': catalog == read(CANDIDATE/'timing.generated.json')
        and {key: len(values) for key, values in catalog.items()} == measurement['catalog_counts'],
        'body_presets_have_same_vowels': len(upper_vowels) == 3
        and all(set(profile) == set(vowels) for profile in upper_vowels.values()),
        'independent_calculations': decimal_difference is None,
        'native_upper_cli': native['passed'],
        'single_input_cli_matches_case': read(single_path) == {**native_entry, 'id': 'ipa'},
    }
    return {'checks': checks, 'cases': cases, 'matrix_count': len(matrix_checks),
            'matrix_failures': matrix_failures, 'independent_difference': decimal_difference,
            'independent_max_error_seconds': decimal_max,
            'maximum_checked_upstream_difference_seconds': max(
                row['maximum_checked_difference_seconds'] for row in [*cases, *matrix_checks]),
            'native_cli': native}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [CASE, PROBE, Path(__file__), Path(shared.__file__),
               WORKSPACE/'tools/upstream_baseline.py', *shared.candidate_sources()]
    upper_files = ['durations.rs', 'planner.rs', 'inventory.rs', 'vowelTargets.generated.json']
    details = {'upstream_revision': revision, 'case_id': case['id'],
               'upper_source_sha256': {name: sha256(UPPER/name) for name in upper_files}}
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(case, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
