"""同じMFAでTSP録音・両合成を整列し、語と音素の区間を照合する。"""

import argparse
import csv
import gzip
from hashlib import sha256 as digest
from itertools import groupby, zip_longest
import math
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import numpy as np
from scipy.io import wavfile

import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-phone-boundaries-calibration.json'
PROBE = WORKSPACE / 'tools/upstream_english_probe.rs'
CMUDICT = UPSTREAM / 'public/data/cmudict.txt.gz'
TSP = UPSTREAM / 'tools/tsp'
ARPABET = dict(zip('ɑ æ ʌ ɔ aʊ aɪ ɛ ɝ eɪ ɪ i oʊ ɔɪ ʊ u'.split(),
                   'AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW'.split(), strict=True))
CONSONANTS = dict(zip('b tʃ d ð f g h dʒ k l m n ŋ p ɹ s ʃ t θ v w j z ʒ'.split(),
                      'B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH'.split(), strict=True))
SILENCE = {'', 'sil', 'sp', '<eps>'}


def arpa(phone):
    ipa = phone['ipa']
    if ipa == 'ɫ':
        return 'L'
    if ipa in ARPABET:
        return f"{ARPABET[ipa]}{phone.get('stress') or 0}"
    if ipa == 'ə':
        return 'AH0'
    if ipa == 'ɚ':
        return 'ER0'
    if ipa not in CONSONANTS:
        raise ValueError(f'発音辞書へ変換できない音素があります ({ipa})')
    return CONSONANTS[ipa]


def registered_transcripts(case):
    if 'transcripts' in case:
        return case['transcripts']
    return [{'id': 'sentence', 'recording_ids': case['recording_ids'], 'words': case['words']}]


def pronunciation(transcripts, folder, execute, single_sentence):
    path = folder / 'english-input.json'
    timing.write(path, {'english_text': {
        'inputs': [{key: row[key] for key in ('id', 'text')} for row in transcripts],
        'words': list(dict.fromkeys(word for row in transcripts for word in row['words'])),
    }})
    dict_data = folder / 'cmudict.tsv'
    dict_data.write_bytes(gzip.decompress(CMUDICT.read_bytes()))
    probe = shared.build_upstream_probe(PROBE, folder, execute, extra_libraries=('serde_json',))
    out = folder / 'upstream-english.json'
    execute([str(probe), str(path), str(dict_data)], stdout=out)
    dict_data.unlink()
    fixed = timing.read(out)
    dictionary = {word['w']: [arpa(p) for p in word['dict']['reduce']] for word in fixed['words']}
    lines = ''.join(f"{word}\t{' '.join(dictionary[word])}\n" for word in sorted(dictionary))
    (folder / 'synth.dict').write_text(lines)
    results = {}
    for transcript, upper in zip(transcripts, fixed['entries'], strict=True):
        uid, words = transcript['id'], transcript['words']
        if upper['id'] != uid:
            raise ValueError(f'固定上流の本文IDが登録順と一致しません ({uid})')
        filename = 'candidate-english.json' if single_sentence else f'candidate-english-{uid}.json'
        native_path = folder / filename
        execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--',
                 'english', transcript['text']], stdout=native_path)
        native = timing.read(native_path)
        expected = [phoneme for word in words for phoneme in dictionary[word]]
        upper_phrases = [row['phrase'] for row in upper['phrases']]
        for phrases in (upper_phrases, native['phrases']):
            if ([word for phrase in phrases for word in phrase['words']] != words or
                    [arpa(phone) for phrase in phrases for phone in phrase['segments']] != expected):
                raise ValueError(f'語と音素の順序が固定上流の発音辞書と一致しません ({uid})')
        upper_timing = [[part['t0'], part['t1'], part['ipa']]
                        for row in upper['phrases'] for part in row['segments']]
        results[uid] = (expected, upper_timing)
    return results


def alignment_wav(source, target, config, rate):
    actual_rate, raw = wavfile.read(source)
    if actual_rate != rate or raw.ndim != 1 or raw.dtype != np.float32 or not np.isfinite(raw).all():
        raise ValueError('合成の入力は有限な48 kHzモノラルfloat32が必要です')
    x = raw.astype(float)
    width = config['noise_window_frames']
    windows = x[:x.size // width * width].reshape(-1, width)
    power = float(np.percentile(np.mean(windows**2, axis=1), 95))
    amplitude = math.sqrt(3 * power * 10**(config['noise_db'] / 10))
    state = int(config['seed_hex'], 16)
    noise = np.empty(len(x))
    for i in range(len(x)):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        noise[i] = amplitude * (state / 2147483648 - 1)
    # 固定上流と同じく一度float32を通してから、Math.round相当でPCM16へ量子化する。
    blended = (x + noise).astype(np.float32).astype(float)
    quantized = np.floor(np.clip(blended, -1, 1) * 32767 + .5).astype(np.int16)
    wavfile.write(target, rate, quantized)
    return {'frames': len(x), 'p95_window_power': power, 'noise_ratio_db': float(10 * np.log10(np.mean(noise**2) / power)),
            'pcm16_clipped_frames': int(np.count_nonzero(np.abs(blended) > 1)),
            'tape_sha256': sha256(target), 'clean_sha256': sha256(source)}


def tiers(path):
    output = timing.read(path)['tiers']
    result = {}
    for kind in ('words', 'phones'):
        rows = [[a, b, label] for a, b, label in output[kind]['entries'] if label not in SILENCE]
        if not rows or any(not 0 <= a < b or not math.isfinite(b) for a, b, _ in rows):
            raise ValueError(f'整列結果に不正な {kind} 区間があります ({path.name})')
        if any(left[1] > right[0] + 1e-9 for left, right in zip(rows, rows[1:])):
            raise ValueError(f'整列区間が時間順に並んでいません ({path.name})')
        result[kind] = rows
    return result


def saved_tiers(ids):
    result = {uid: {'words': [], 'phones': []} for uid in ids}
    with gzip.open(TSP / 'alignment.tsv.gz', 'rt', newline='') as stream:
        for uid, tier, start, end, label in csv.reader(stream, delimiter='\t'):
            if uid in result:
                result[uid][tier + 's'].append([float(start), float(end), label])
    return result


def compare_tiers(observed, reference, limit):
    result = {}
    for kind, rows in observed.items():
        wanted = reference[kind]
        labels = [row[2] for row in rows] == [row[2] for row in wanted]
        delta = [[1000 * (actual - source) for actual, source in zip(a[:2], b[:2], strict=True)]
                 for a, b in zip(rows, wanted)] if labels else []
        maximum = max((abs(x) for row in delta for x in row), default=None)
        result[kind] = {'passed': labels and maximum is not None and maximum <= limit * 1000,
                        'labels_match': labels, 'maximum_boundary_difference_ms': maximum,
                        'first_label_difference': next(({'i': i, 'observed': a, 'saved': b}
                            for i, (a, b) in enumerate(zip_longest([r[2] for r in rows], [r[2] for r in wanted]))
                            if a != b), None),
                        'first_nonzero_difference': next(({'i': i, 'label': rows[i][2], 'start_end_difference_ms': d}
                                                         for i, d in enumerate(delta) if any(d)), None)}
    return result


def span_decomposition(words):
    total = words[-1][1] - words[0][0]
    duration = math.fsum(b-a for a, b, _ in words)
    gaps = math.fsum(b[0]-a[1] for a, b in zip(words, words[1:]))
    return {'duration_ms': total * 1000, 'words_ms': duration * 1000, 'gaps_ms': gaps * 1000,
            'constructed_duration_matches': abs(total - duration - gaps) <= 1e-9}


def plan_phones(path, upper_timing, expected):
    intervals = []
    candidate_timing = []
    for phrase in timing.read(path)['speech']['phrases']:
        segments = phrase['timing']['segments']
        candidate_timing.extend([p['start_seconds'], p['end_seconds'], p['segment']['ipa']] for p in segments)
        for index, pieces in groupby(segments, key=lambda p: p['input_index']):
            pieces = list(pieces)
            intervals.append([pieces[0]['start_seconds'], pieces[-1]['end_seconds'], arpa(phrase['segments'][index])])
    if [row[2] for row in intervals] != expected:
        raise ValueError('計画の区間を登録済みの音素へ戻せません')
    diff, error = timing.compare(candidate_timing, upper_timing, 1e-12)
    return intervals, {'first_difference': diff, 'maximum_time_difference_seconds': error}


def normalized_phone(label):
    return label if label in ('AH0', 'ER0') else label.rstrip('012')


def match_phones(recording, synth):
    a, b = ([normalized_phone(row[2]) for row in x] for x in (recording, synth))
    grid = [list(range(len(b) + 1))] + [[i] + [0] * len(b) for i in range(1, len(a) + 1)]
    for i, left in enumerate(a, 1):
        for j, right in enumerate(b, 1):
            grid[i][j] = min(grid[i-1][j]+1, grid[i][j-1]+1, grid[i-1][j-1]+(left != right))
    i, j = len(a), len(b)
    pairs = []
    while i and j:
        equal = a[i-1] == b[j-1]
        if grid[i][j] == grid[i-1][j-1] + (not equal):
            if equal:
                pairs.append((i-1, j-1))
            i, j = i-1, j-1
        elif grid[i][j] == grid[i-1][j] + 1:
            i -= 1
        else:
            j -= 1
    return list(reversed(pairs))


def interval_pairs(recording, synth, pairs):
    rows = []
    for i, j in pairs:
        a, b = recording[i], synth[j]
        rows.append({'recording_index': i, 'synth_index': j, 'recording': a, 'synth': b,
                     'start_end_delta_ms': [1000 * (b[k]-a[k]) for k in (0, 1)],
                     'duration_delta_ms': 1000 * ((b[1]-b[0])-(a[1]-a[0]))})
    return rows


def versions(root, config, artifacts, execute):
    model = root / 'downloads/english_us_arpa.zip'
    dictionary = root / 'downloads/english_us_arpa.dict'
    if sha256(model) != config['model_sha256'] or sha256(dictionary) != config['dictionary_sha256']:
        raise ValueError('音響モデルまたは辞書が固定上流の版と一致しません')
    execute([str(root / 'downloads/micromamba-osx-arm64'), '--no-rc', '--root-prefix', str(root / 'root'), 'list', '--explicit',
             '--prefix', str(root / 'env')], stdout=artifacts / 'conda-explicit.txt')
    return model, dictionary


def mfa_run(root, config, corpus, dictionary, model, result, temp, execute, *, entry=None):
    env = ['/usr/bin/env', f"PATH={root / 'env/bin'}:/usr/bin:/bin:/usr/sbin:/sbin", f'MFA_ROOT_DIR={temp}',
           f"XDG_CACHE_HOME={temp / 'cache'}",
           'OMP_NUM_THREADS=1', 'OPENBLAS_NUM_THREADS=1']
    bin = str(root / 'env/bin/mfa')
    v = result.parent / 'mfa-version.txt'
    if not v.exists():
        execute([*env, bin, 'version'], stdout=v)
        if v.read_text().strip() != config['version']:
            raise ValueError('MFAが登録した版と一致しません')
    invoke = [bin] if entry is None else entry
    execute([*env, *invoke, 'align', '--clean', '-c', str(UPSTREAM / config['configuration']),
             '-j', str(config['jobs']), '--output_format', 'json', str(corpus), str(dictionary),
             str(model), str(result)])


def measurement(case, transcripts, baseline, archive_path, artifacts, execute):
    config = case['aligner']
    root = Path(config['environment_root'])
    model, dictionary = versions(root, config, artifacts, execute)
    by_recording = {uid: row for row in transcripts for uid in row['recording_ids']}
    ids = list(by_recording)
    with (TSP / 'sentences.tsv').open(newline='') as stream:
        saved_texts = {uid: text for uid, _, text in csv.reader(stream, delimiter='\t') if uid in by_recording}
    resolved = []
    for row in transcripts:
        texts = {saved_texts.get(uid) for uid in row['recording_ids']}
        if len(texts) != 1 or None in texts or ('text' in row and texts != {row['text']}):
            raise ValueError(f"本文がTSPの収録内容と一致しません ({row['id']})")
        resolved.append({**row, 'text': texts.pop()})
    single_sentence = 'transcripts' not in case
    pronunciations = pronunciation(resolved, artifacts, execute, single_sentence)
    sources = timing.read(baseline / 'summary.json')['splits'][case.get('split', 'calibration')]
    original_hashes = {row['path']: row['sha256'] for row in timing.read(baseline / 'manifest.json')['outputs']}
    inputs = {'recording': [], 'synth': []}
    noise = {}
    plan = {}
    for uid in ids:
        expected, fixed_timing = pronunciations[by_recording[uid]['id']]
        path = baseline / 'artifacts' / uid / 'inspect.json'
        if sha256(path) != original_hashes[path.relative_to(baseline).as_posix()]:
            raise ValueError(f'発話計画が元のマニフェストと一致しません ({uid})')
        plan[uid] = plan_phones(path, fixed_timing, expected)
    words_by_tag = {}
    expected_by_tag = {}
    with ZipFile(archive_path) as archive:
        for uid in ids:
            row = by_recording[uid]
            words = row['words']
            folder = artifacts / 'corpus' / 'recording' / uid
            folder.mkdir(parents=True)
            raw = archive.read(sources[uid]['recording_archive_member'])
            if digest(raw).hexdigest() != sources[uid]['recording_sha256']:
                raise ValueError(f'録音が保存済みのデータと一致しません ({uid})')
            (folder / f'{uid}.wav').write_bytes(raw)
            (folder / f'{uid}.lab').write_text(saved_texts[uid] + '\n')
            inputs['recording'].append(uid)
            words_by_tag[uid] = words
            for voice in ('upstream', 'candidate'):
                tag = f'{uid}-{voice}'
                folder = artifacts / 'corpus' / 'synth' / tag
                folder.mkdir(parents=True)
                wave = baseline / 'artifacts' / uid / f'{voice}.wav'
                if sha256(wave) != original_hashes[wave.relative_to(baseline).as_posix()]:
                    raise ValueError(f'合成WAVが元のマニフェストと一致しません ({tag})')
                (folder / f'{tag}.lab').write_text(' '.join(words) + '\n')
                noise[tag] = alignment_wav(wave, folder / f'{tag}.wav', config, case['measurement']['sample_rate_hz'])
                inputs['synth'].append(tag)
                words_by_tag[tag] = words
                expected_by_tag[tag] = pronunciations[row['id']][0]
    rounds = []
    temporary_roots = []
    for attempt in (1, 2):
        parsed = {}
        for kind, names in inputs.items():
            out = artifacts / f'aligned-{attempt}-{kind}'
            temp = artifacts.parent / 'tmp' / f'mfa-{attempt}-{kind}'
            temp.mkdir()
            temporary_roots.append(temp)
            mfa_run(root, config, artifacts / 'corpus' / kind, dictionary if kind == 'recording' else artifacts / 'synth.dict',
                    model, out, temp, execute)
            parsed.update({tag: tiers(out / tag / f'{tag}.json') for tag in names})
        rounds.append(parsed)
    observed = rounds[0]
    saved = saved_tiers(ids)
    comparison = {uid: compare_tiers(observed[uid], saved[uid], case['measurement']['saved_boundary_tolerance_seconds'])
                  for uid in ids}
    decomposition = {tag: span_decomposition(value['words']) for tag, value in observed.items()}
    words_agree = all([p[2] for p in row['words']] == words_by_tag[tag] for tag, row in observed.items())
    matched = {}
    for uid in ids:
        recorded = observed[uid]
        planned, diff = plan[uid]
        words = words_by_tag[uid]
        matched[uid] = {'planned': planned, 'candidate_plan_to_upstream': diff}
        if not single_sentence:
            matched[uid]['candidate_alignment_to_upstream'] = compare_tiers(
                observed[f'{uid}-candidate'], observed[f'{uid}-upstream'], 0,
            )
        for source in ('upstream', 'candidate'):
            aligned = observed[f'{uid}-{source}']
            phone_pairs = match_phones(recorded['phones'], aligned['phones'])
            plan_pairs = match_phones(planned, aligned['phones'])
            matched[uid][source] = {
                'words_recording_to_synth': interval_pairs(recorded['words'], aligned['words'],
                                                          ((i, i) for i in range(len(words)))) if words_agree else [],
                'phones_recording_to_synth': interval_pairs(recorded['phones'], aligned['phones'], phone_pairs),
                'phones_plan_to_alignment': interval_pairs(planned, aligned['phones'], plan_pairs),
            }
    checks = {
        'reproducible_alignment': observed == rounds[1],
        'word_labels_and_order': words_agree,
        'synth_phone_sequence': all([p[2] for p in observed[tag]['phones']] == expected_by_tag[tag]
                                    for tag in inputs['synth']),
        'candidate_plan_to_upstream': all(diff['first_difference'] is None for _, diff in plan.values()),
        'noise_floor': all(abs(row['noise_ratio_db'] - config['noise_db']) <= case['measurement']['noise_tolerance_db']
                           and not row['pcm16_clipped_frames'] for row in noise.values()),
        'saved_human_boundaries': all(row['passed'] for group in comparison.values() for row in group.values()),
        'word_and_gap_duration': all(row['constructed_duration_matches'] for row in decomposition.values()),
    }
    expected_phones = pronunciations['sentence'][0] if single_sentence else {
        uid: value[0] for uid, value in pronunciations.items()
    }
    if all(checks.values()):
        # 確定した入力と整列結果は artifacts にあり、MFAの展開モデルや中間特徴量は再生成できる。
        for temp in temporary_roots:
            shutil.rmtree(temp)
    return {'checks': checks, 'hypothesis_comparison': comparison, 'expected_synth_phones': expected_phones,
            'intervals': observed, 'noise_floor': noise, 'word_duration_and_gaps': decomposition, 'pairs': matched}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case_path = args.case.resolve()
    case = timing.read(case_path)
    transcripts = registered_transcripts(case)
    ids = [uid for row in transcripts for uid in row['recording_ids']]
    baseline = WORKSPACE / 'runs' / case['baseline_run']
    reference_case = CASE.parent / case['baseline_case']
    reference = timing.read(reference_case)['reference']
    split_ids = case.get('split', 'calibration') + '_ids'
    registered = reference
    scope_inputs = []
    if scope_id := case.get('baseline_scope'):
        manifest = timing.read(baseline / 'manifest.json')
        relative = (CASE.parent / f'{scope_id}.json').relative_to(WORKSPACE.parents[2])
        hashes = [row['sha256'] for row in manifest['inputs'] if row['path'] == relative.as_posix()]
        snapshot = baseline / manifest['source_snapshot'] / relative
        if (manifest['status'] != 'pass' or manifest['case_id'] != scope_id
                or manifest['upstream_revision'] != case['upstream_revision'] or hashes != [sha256(snapshot)]):
            parser.error('先行実行が保存した対象範囲を照合できません')
        registered = timing.read(snapshot)
        scope_inputs.append(snapshot)
    if len(ids) != len(set(ids)) or not set(ids) <= set(registered[split_ids]):
        parser.error('録音IDが元の比較で登録した区分と一致しません')
    archive = Path(reference['archive_path'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    if sha256(archive) != reference['sha256'] or sha256(CMUDICT) != sha256(WORKSPACE / 'data/cmudict.txt.gz'):
        parser.error('録音または発音辞書が登録済みの版と一致しません')
    inputs = [case_path, reference_case, Path(__file__).resolve(), PROBE, TSP / 'sentences.tsv', TSP / 'alignment.tsv.gz',
              TSP / 'mfa.yaml', CMUDICT, baseline / 'manifest.json', baseline / 'summary.json', *scope_inputs]
    inputs.extend(baseline / 'artifacts' / uid / f'{source}.wav' for uid in ids
                  for source in ('upstream', 'candidate'))
    inputs.extend(baseline / 'artifacts' / uid / 'inspect.json' for uid in ids)
    return shared.record_measurement(args.run_id, case_path, inputs, {'case_id': case['id'], 'revision': case['revision'],
        'upstream_revision': revision, 'archive_sha256': reference['sha256'], 'aligner': case['aligner']},
        lambda out, execute: measurement(case, transcripts, baseline, archive, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
