"""音源をそろえた合成4組で、MFA入力と再整列後の境界を照合する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_tsp_phone_boundaries as mfa
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_stressed_vowel_formants import TSP_SOURCE, open_run, read, verified_path
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-matched-speech-mfa.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_mfa_probe.rs'
ENTRY = Path('crates/chimera-cli/src/main.rs')
VOICES = ('upstream', 'candidate')


def describe_delta(left, right):
    if left.shape != right.shape or left.dtype != right.dtype:
        raise ValueError('比較する波形の長さまたは標本形式が一致しません')
    delta = right.astype(np.float64 if left.dtype == np.float32 else np.int32) - left
    changed = np.flatnonzero(delta)
    first = int(changed[0]) if len(changed) else None
    return {'frames': len(left), 'changed_frames': len(changed),
            'max_absolute_delta': np.max(np.abs(delta)).item(),
            'first_changed_sample': first,
            'values_at_first_change': None if first is None else [left[first].item(), right[first].item()]}


def wave_samples(path, rate, dtype):
    actual_rate, samples = wavfile.read(path)
    if actual_rate != rate or samples.ndim != 1 or samples.dtype != dtype or not len(samples):
        raise ValueError(f'比較音声の形式が一致しません ({path.name})')
    return samples


def fixed_mfa_input(revision, request, scratch, artifacts, execute):
    archive, copy = scratch / 'upstream.tar', scratch / 'upstream'
    copy.mkdir()
    execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=archive)
    execute(['tar', '-xf', str(archive), '-C', str(copy)])
    tsp = copy / TSP_SOURCE
    shutil.copyfile(PROBE, tsp.with_name(PROBE.name))
    with tsp.open('a') as stream:
        stream.write(f'\ninclude!("{PROBE.name}");\n')
    entry = copy / ENTRY
    source = entry.read_text()
    anchor = '        ["compare", "tsp", ..]'
    if source.count(anchor) != 1:
        raise ValueError('固定上流のCLIの照合入口が1つに定まりません')
    entry.write_text(source.replace(anchor, '        ["research-mfa-input", request] => '
                                    'compare::tsp::research_mfa_input(request),\n' + anchor))
    target = scratch / 'target'
    cargo_options = ['--locked', '--offline', '--target-dir', str(target), '-p', 'chimera-cli']
    execute(['cargo', 'test', *cargo_options, 'compare::tsp::tests'], cwd=copy,
            stdout=artifacts / 'upstream-tsp-tests.log')
    execute(['cargo', 'run', '--release', *cargo_options, '--', 'research-mfa-input', str(request)], cwd=copy)


def compare_waves(files, rate):
    waves = {}
    for tag, paths in files.items():
        clean, noisy, native, prepared, prior = paths
        waves[tag] = {
            'clean': wave_samples(clean, rate, np.float32),
            'noisy': wave_samples(noisy, rate, np.float32),
            'native': wave_samples(native, rate, np.int16),
            'prepared': wave_samples(prepared, rate, np.int16),
            'prior': wave_samples(prior, rate, np.int16),
        }
    return waves


def compare_intervals(before, after):
    result = {}
    for tier in ('words', 'phones'):
        left, right = before[tier], after[tier]
        same_labels = [row[2] for row in left] == [row[2] for row in right]
        deltas = [max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(left, right)] if same_labels else []
        result[tier] = {'counts': [len(left), len(right)], 'same_labels': same_labels,
                        'changed_intervals': sum(delta > 0 for delta in deltas) if same_labels else None,
                        'max_absolute_delta_seconds': max(deltas) if same_labels else None}
    return result


def compare_windows(case, previous, current, report):
    cfg = case['measurement']
    rate, length = cfg['analysis_sample_rate_hz'], cfg['frame_samples']
    if [rate, length] != [report['sample_rate_hz'], report['frame_samples']]:
        raise ValueError('保存済み窓の標本周波数または長さが事前登録と一致しません')
    windows = {}
    for row in report['windows']:
        uid, voice, center = row['utterance'], row['source'], row['center']
        if uid not in case['utterances'] or voice not in VOICES:
            continue
        tag = f'{uid}-{voice}'
        phones = previous[tag]['phones']
        before = phones[row['phone_index']]
        after = current[tag]['phones']
        if [phone[2] for phone in phones] != [phone[2] for phone in after]:
            # 音素列が変われば旧インデックスから新しい窓を決められない。
            return None
        new = after[row['phone_index']]
        start = int((new[0] + center * (new[1] - new[0])) * rate) - length // 2
        old_start = int((before[0] + center * (before[1] - before[0])) * rate) - length // 2
        if before[:2] != row['interval_seconds'] or old_start != row['start_sample']:
            raise ValueError(f'保存済み音素区間から以前の窓開始位置を再現できません ({tag})')
        key = (uid, row['phone_index'], row['word'], row['ipa'], center)
        pair = windows.setdefault(key, {})
        if voice in pair:
            raise ValueError(f'同じ音素・中心が重複しています ({tag})')
        pair[voice] = {'intervals_seconds': [before[:2], new[:2]], 'start_samples': [old_start, start]}
    result = []
    for (uid, index, word, ipa, center), voices in windows.items():
        if set(voices) != set(VOICES):
            raise ValueError(f'両版に同じ音素の測定窓がありません ({uid}/{index})')
        upper, candidate = (voices[voice]['start_samples'] for voice in VOICES)
        result.append({'utterance': uid, 'phone_index': index, 'word': word, 'ipa': ipa, 'center': center,
                       **voices, 'candidate_minus_upstream_samples': [b - a for a, b in zip(upper, candidate)]})
    return result


def window_summary(windows):
    if windows is None:
        return None
    result = {}
    for index, name in enumerate(('prior', 'realigned')):
        offsets = [abs(row['candidate_minus_upstream_samples'][index]) for row in windows]
        result[name] = {'different_starts': sum(delta > 0 for delta in offsets),
                        'maximum_start_delta_samples': max(offsets, default=None)}
    result['windows'] = len(windows)
    return result


def measure(case, config, sources, out, execute):
    cfg = case['measurement']
    rate = cfg['sample_rate_hz']
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    corpus = out / 'corpus'
    corpus.mkdir()
    dictionary = out / 'synth.dict'
    shutil.copyfile(sources['dictionary'], dictionary)
    noise, files = {}, {}
    with (TemporaryDirectory(prefix='matched-mfa-', dir=out.parent / 'tmp') as directory,
          np.load(sources['pcm'], allow_pickle=False) as pcm):
        scratch = Path(directory)
        for uid in case['utterances']:
            for voice in VOICES:
                tag = f'{uid}-{voice}'
                lab, prior, _ = sources['prior'][tag]
                folder = corpus / tag
                folder.mkdir()
                shutil.copyfile(lab, folder / lab.name)
                prepared = folder / f'{tag}.wav'
                clean = scratch / f'{tag}-clean.wav'
                wavfile.write(clean, rate, pcm[f'{uid}_{voice}'])
                noise[tag] = mfa.alignment_wav(clean, prepared, config, rate)
                files[tag] = (clean, scratch / f'{tag}-noisy.wav', scratch / f'{tag}-native.wav', prepared, prior)
        request = scratch / 'files.json'
        request.write_text(json.dumps([[str(path) for path in paths[:3]] for paths in files.values()]))
        fixed_mfa_input(case['upstream_revision'], request, scratch, out, execute)
        waves = compare_waves(files, rate)
        target = out / 'aligned'
        mfa_run_tmp = scratch / 'mfa'
        mfa_run_tmp.mkdir()
        mfa.mfa_run(root, config, corpus, dictionary, model, target, mfa_run_tmp, execute)
    previous = {tag: mfa.tiers(paths[2]) for tag, paths in sources['prior'].items()}
    current = {tag: mfa.tiers(target / tag / f'{tag}.json') for tag in previous}
    windows = compare_windows(case, previous, current, read(sources['formants']))
    stats = window_summary(windows)
    rows = {}
    for uid in case['utterances']:
        tags = [f'{uid}-{voice}' for voice in VOICES]
        left, right = (waves[tag] for tag in tags)
        rows[uid] = {
            'paired_pcm': {key: describe_delta(left[key], right[key]) for key in ('clean', 'noisy', 'prepared', 'prior')},
            'conversion': {tag: describe_delta(waves[tag]['native'], waves[tag]['prepared']) for tag in tags},
            'input_vs_prior': {tag: describe_delta(waves[tag]['prior'], waves[tag]['prepared']) for tag in tags},
            'paired_boundaries': compare_intervals(*(current[tag] for tag in tags)),
            'boundaries_vs_prior': {tag: compare_intervals(previous[tag], current[tag]) for tag in tags},
        }
    equal_pcm = sum(not row['paired_pcm']['prepared']['changed_frames'] for row in rows.values())
    max_pcm = max(row['paired_pcm']['prepared']['max_absolute_delta'] for row in rows.values())
    checks = {
        'native_pcm16_matches': all(not row['changed_frames'] for uid in rows.values()
                                    for row in uid['conversion'].values()),
        'unchanged_upstream_pcm16_and_boundaries': all(
            not rows[uid]['input_vs_prior'][f'{uid}-upstream']['changed_frames']
            and previous[f'{uid}-upstream'] == current[f'{uid}-upstream'] for uid in rows),
        'noise_floor': all(abs(row['noise_ratio_db'] - config['noise_db']) <= cfg['noise_tolerance_db']
                           and not row['pcm16_clipped_frames'] for row in noise.values()),
        'registered_prior_windows': stats is None or (
            stats['windows'] == cfg['vowels'] * len(cfg['centers']) and stats['prior'] == {
                'different_starts': cfg['old_different_starts'],
                'maximum_start_delta_samples': cfg['old_maximum_start_delta_samples']}),
    }
    predictions = {
        'pcm16_rounding': equal_pcm >= cfg['minimum_equal_pcm_pairs'] and max_pcm <= cfg['maximum_pcm_step'],
        'paired_boundaries_agree': all(current[f'{uid}-upstream'] == current[f'{uid}-candidate'] for uid in rows),
        'prior_window_offsets_disappear': stats is not None and stats['realigned'] == {
            'different_starts': 0, 'maximum_start_delta_samples': 0},
    }
    (out / 'window-comparisons.json').write_text(json.dumps(windows, ensure_ascii=False, indent=2) + '\n')
    return {'checks': checks, 'predictions': predictions, 'same_pcm16_pairs': equal_pcm,
            'max_pcm16_delta': max_pcm, 'windows': stats, 'utterances': rows, 'noise': noise}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    alignment, pcm, formants = (open_run(case[key], revision) for key in ('alignment', 'matched_pcm', 'formants'))
    original, snapshot = saved_case(alignment, CASE.with_name(f"{case['alignment']['case']}.json"))
    config = original['aligner']
    prior = {}
    for uid in case['utterances']:
        for voice in VOICES:
            tag = f'{uid}-{voice}'
            prior[tag] = tuple(verified_path(alignment, f'artifacts/{folder}/{tag}/{tag}.{extension}')
                               for folder, extension in (('corpus/synth', 'lab'), ('corpus/synth', 'wav'),
                                                         ('aligned-1-synth', 'json')))
    sources = {'pcm': verified_path(pcm, 'artifacts/matched-pcm.npz'),
               'formants': verified_path(formants, 'artifacts/f2-candidates.json'),
               'dictionary': verified_path(alignment, 'artifacts/synth.dict'), 'prior': prior}
    inputs = [CASE, snapshot, Path(__file__).resolve(), PROBE, sources['pcm'], sources['formants'], sources['dictionary'],
              *(path for paths in prior.values() for path in paths),
              *(run[0] / 'manifest.json' for run in (alignment, pcm, formants)),
              WORKSPACE / 'tools/measure_tsp_phone_boundaries.py',
              *(UPSTREAM / path for path in (TSP_SOURCE, ENTRY, config['configuration'],
                                             'crates/chimera-cli/src/compare.rs', 'crates/chimera-cli/src/wav.rs',
                                             'crates/chimera/src/math.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, config, sources, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
