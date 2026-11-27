"""IPAの字句・発話分割・診断、および原文のUTF-8バイト範囲を照合する。"""

import json
from pathlib import Path
import re
import subprocess
import sys

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/ipa-tokenization.json'
PROBE = WORKSPACE / 'tools/upstream_ipa_probe.rs'
DATA = WORKSPACE / 'crates/vocal-core/src/phonetics/ipa'
UPSTREAM_NFC = UPSTREAM / 'crates/chimera/src/phonetics/ipaNfc.generated.json'
DIAGNOSTIC_KEYS = {'unknown': 'unknown', 'no_sound': 'noSound', 'ignored_mark': 'ignoredMarks'}


def read(path):
    return json.loads(path.read_text())


def compatible(report):
    return {
        'known_symbols': report['known_symbols'],
        'entries': [
            {**{key: item[key] for key in ('id', 'segments', 'skipped')},
             'utterances': [{key: utterance[key] for key in ('text', 'segments')}
                            for utterance in item['utterances']]}
            for item in report['entries']
        ],
    }


def difference(actual, expected, path=()):
    if type(actual) != type(expected):
        return {'path': path, 'candidate': actual, 'reference': expected}
    if isinstance(actual, dict):
        if actual.keys() != expected.keys():
            return {'path': path, 'candidate_keys': sorted(actual), 'reference_keys': sorted(expected)}
        for key in sorted(actual):
            if mismatch := difference(actual[key], expected[key], (*path, key)):
                return mismatch
    elif isinstance(actual, list):
        if len(actual) != len(expected):
            return {'path': path, 'candidate_length': len(actual), 'reference_length': len(expected)}
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            if mismatch := difference(left, right, (*path, index)):
                return mismatch
    elif actual != expected:
        return {'path': path, 'candidate': actual, 'reference': expected}
    return None


def span(record):
    return [record['start_byte'], record['end_byte']]


def check_ranges(text, entry):
    offsets = {0}
    index = 0
    for char in text:
        index += len(char.encode('utf-8'))
        offsets.add(index)

    def valid(item, low=0, high=index):
        start, end = span(item)
        return start in offsets and end in offsets and low <= start < end <= high

    def ordered_spans(row, low=0, high=index):
        spans = row['segment_spans']
        return (len(row['segments']) == len(spans)
                and all(valid(item, low, high) for item in spans)
                and all(a['end_byte'] <= b['start_byte'] for a, b in zip(spans, spans[1:])))

    if not ordered_spans(entry) or not all(valid(row['span']) for row in entry['diagnostics']):
        return False
    selected = []
    start = 0
    for chunk in text.split('/'):
        trimmed = chunk.strip()
        lower = start + len(chunk[:len(chunk) - len(chunk.lstrip())].encode())
        if trimmed:
            selected.append((trimmed, [lower, lower + len(trimmed.encode())]))
        start += len(chunk.encode()) + 1
    actual = [(utterance['text'], span(utterance['span'])) for utterance in entry['utterances']]
    if actual != selected:
        return False
    return all(ordered_spans(u, *span(u['span'])) for u in entry['utterances'])


def check_registered(input_, output):
    expected = input_['expected']
    segments = output['segments']
    details = []
    actual = {
        'symbols': [segment['ipa'] for segment in segments],
        'skipped': output['skipped'],
        'utterance_count': len(output['utterances']),
    }
    for name in actual:
        if actual[name] != expected[name]:
            details.append({'field': name, 'actual': actual[name], 'expected': expected[name]})
    for requirement in expected.get('segment_fields', []):
        index = requirement['index']
        segment = segments[index] if index < len(segments) else {}
        fields = requirement['fields']
        if (any(segment.get(name) != value for name, value in fields.items())
                or any(name in segment for name in requirement.get('absent', []))):
            details.append({'field': 'segment_fields', 'actual': segment, 'expected': requirement})
    if 'utterance_symbols' in expected:
        symbols = [[s['ipa'] for s in u['segments']] for u in output['utterances']]
        if symbols != expected['utterance_symbols']:
            details.append({'field': 'utterance_symbols', 'actual': symbols,
                            'expected': expected['utterance_symbols']})
    for item in expected.get('segment_spans', []):
        index = item['index']
        spans = output['segment_spans']
        value = span(spans[index]) if index < len(spans) else None
        if value != item['bytes']:
            details.append({'field': 'segment_spans', 'actual': value, 'expected': item})
    diagnostics = [(row['kind'], row['symbol'], span(row['span'])) for row in output['diagnostics']]
    for item in expected.get('diagnostic_spans', []):
        if (item['kind'], item['symbol'], item['bytes']) not in diagnostics:
            details.append({'field': 'diagnostic_spans', 'expected': item})
    return details


def compare_reports(cases, candidate, reference):
    records = []
    expected_ids = [example['id'] for example in cases]
    if ([row['id'] for row in candidate['entries']] != expected_ids
            or [row['id'] for row in reference['entries']] != expected_ids):
        raise ValueError('観測された入力IDの数または順序がケースと異なります')
    normalized = compatible(candidate)['entries']
    for item, output, simple, upper in zip(cases, candidate['entries'], normalized, reference['entries'], strict=True):
        registered = check_registered(item, output) if 'expected' in item else []
        first = difference(simple, upper)
        ranges = check_ranges(item['text'], output)
        diagnostics = {}
        for kind, field in DIAGNOSTIC_KEYS.items():
            symbols = [row['symbol'] for row in output['diagnostics'] if row['kind'] == kind]
            diagnostics[field] = set(symbols) == set(output['skipped'][field])
        records.append({'id': item['id'], 'segments': len(output['segments']),
                        'utterances': len(output['utterances']), 'diagnostic_occurrences': len(output['diagnostics']),
                        'first_upstream_difference': first, 'registered_differences': registered,
                        'source_ranges_valid': ranges, 'diagnostic_groups_valid': all(diagnostics.values()),
                        'passed': first is None and not registered and ranges and all(diagnostics.values())})
    return records


def generate_matrix(case, known):
    config = case['measurement']['pair_matrix']
    examples = [
        {'id': f'ipa-{index:03d}-{suffix_index:02d}',
         'text': config['prefix'] + symbol + config['suffix_separator'] + suffix + config['tail']}
        for index, symbol in enumerate(known) for suffix_index, suffix in enumerate(config['suffixes'])
    ]
    return {**case, 'id': 'ipa-tokenization-matrix', 'ipa': {'inputs': examples}}


def measure(case, artifacts, execute):
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*prefix, 'inspect', str(CASE)], stdout=artifacts/'settings.json')
    actual_path = artifacts/'tokenization.json'
    execute([*prefix, 'render', str(CASE), str(actual_path)])
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'skipped_ipa', '--test',
             'sound_marks', '--test', 'aspiration', '--test', 'affricates'],
            cwd=UPSTREAM, stdout=artifacts/'upper-tests.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    upper_path, catalog_path = (artifacts/name for name in ('upstream-tokenization.json', 'upstream-catalog.json'))
    execute([str(probe), str(CASE)], cwd=UPSTREAM, stdout=upper_path)
    execute([str(probe), '--catalog'], cwd=UPSTREAM, stdout=catalog_path)
    actual, upper = read(actual_path), read(upper_path)
    entries = compare_reports(case['ipa']['inputs'], actual, upper)
    expected_symbol_count = case['measurement']['known_symbol_count']

    single = case['ipa']['inputs'][5]
    path = artifacts/'single-input.json'
    execute([*prefix, 'ipa', single['text']], stdout=path)
    expected = next(item for item in actual['entries'] if item['id'] == single['id'])

    matrix = generate_matrix(case, upper['known_symbols'])
    matrix_case = artifacts/'matrix-case.json'
    matrix_case.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + '\n')
    matrix_out, upper_matrix = (artifacts/name for name in ('matrix-tokenization.json', 'upstream-matrix.json'))
    execute([*prefix, 'render', str(matrix_case), str(matrix_out)])
    execute([str(probe), str(matrix_case)], cwd=UPSTREAM, stdout=upper_matrix)
    matrix_results = compare_reports(matrix['ipa']['inputs'], read(matrix_out), read(upper_matrix))
    failures = [row for row in matrix_results if not row['passed']]

    catalog = read(catalog_path)
    checks = {
        'exact_known_symbols': actual['known_symbols'] == upper['known_symbols']
        and len(actual['known_symbols']) == expected_symbol_count,
        'catalog_matches_fixed_reference': catalog == read(DATA/'catalog.generated.json')
        and {key: len(values) for key, values in catalog.items()} == case['measurement']['catalog_counts'],
        'same_ipa_normalization_data': sha256(DATA/'nfc.generated.json') == sha256(UPSTREAM_NFC),
        'registered_cases': all(row['passed'] for row in entries),
        'single_input_cli_matches_case': read(path) == {key: value for key, value in expected.items() if key != 'id'},
        'all_symbols_with_modifiers': not failures,
    }
    return {'checks': checks, 'known_symbol_count': len(actual['known_symbols']), 'inputs': entries,
            'matrix_count': len(matrix_results), 'matrix_failures': failures}


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', sys.argv[1]):
        raise SystemExit('英数字で始まる実行IDをひとつ指定してください')
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [CASE, PROBE, Path(__file__).resolve(), Path(shared.__file__),
               WORKSPACE/'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'],
               'upstream_ipa_nfc_data_sha256': sha256(UPSTREAM_NFC)}
    return shared.record_measurement(sys.argv[1], CASE, sources, details,
                                     lambda artifacts, execute: measure(case, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
