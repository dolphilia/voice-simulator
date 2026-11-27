"""FK61_02の整列用PCM16を50 msで入れ替え、tallの境界とF2を照合する。"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import wave

import numpy as np
from scipy.io import wavfile

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_tall_output_gain_mfa import measure_formants
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-tall-mfa-preroll.json'
SOURCES = {
    'control': ('control', 'control'),
    'old_tip': ('old_tip', 'old_tip'),
    'old_preroll': ('old_tip', 'control'),
    'old_remainder': ('control', 'old_tip'),
}


def pcm_bytes(path, rate, frames):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) != (rate, 1, 2, frames):
            raise ValueError(f'整列用PCM16の形式または長さが登録値と違います ({path.name})')
        result = wav.readframes(frames)
    if len(result) != frames * 2:
        raise ValueError(f'整列用PCM16のデータが不足しています ({path.name})')
    return result


def make_corpus(case, paths, corpus):
    cfg = case['measurement']
    rate, frames, cut = (cfg[key] for key in ('sample_rate_hz', 'frames', 'cut_frame'))
    if not 0 < cut < frames:
        raise ValueError('PCM16を分ける標本番号が有効範囲外です')
    original = {name: aligned.wave_samples(paths[f'{name}_pcm'], rate, np.int16) for name in ('control', 'old_tip')}
    reference = {name: pcm_bytes(paths[f'{name}_pcm'], rate, frames) for name in original}
    labels = paths['lab'].read_bytes()
    tags, tapes, byte_checks = {}, {}, {}
    for mode, (first, second) in SOURCES.items():
        tag = f"{case['utterance']}-{mode}"
        folder = corpus / tag
        folder.mkdir(parents=True)
        (folder / f'{tag}.lab').write_bytes(labels)
        wav = folder / f'{tag}.wav'
        samples = np.concatenate((original[first][:cut], original[second][cut:]))
        wavfile.write(wav, rate, samples)
        byte_checks[mode] = pcm_bytes(wav, rate, frames) == reference[first][:2 * cut] + reference[second][2 * cut:]
        tags[mode], tapes[mode] = tag, samples
    return tags, tapes, byte_checks


def measure(case, align_case, analysis_case, paths, out, execute):
    cfg, config = case['measurement'], align_case['aligner']
    corpus = out / 'corpus'
    tags, tapes, byte_checks = make_corpus(case, paths, corpus)
    dictionary = out / 'synth.dict'
    shutil.copyfile(paths['dictionary'], dictionary)
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    target = out / 'aligned'
    with TemporaryDirectory(prefix='tall-preroll-', dir=out.parent / 'tmp') as directory:
        mfa.mfa_run(root, config, corpus, dictionary, model, target, Path(directory), execute)
    tiers = {name: mfa.tiers(target / tag / f'{tag}.json') for name, tag in tags.items()}
    indices = {name: single.phone_at_word(tier, cfg) for name, tier in tiers.items()}
    intervals = {name: tier['phones'][indices[name]] for name, tier in tiers.items()}
    routes = {name: ('clean', name) for name in SOURCES}
    rows = measure_formants(case, analysis_case, {'clean': paths['clean']}, tiers, indices, out, execute, routes=routes)
    control, old = tapes['control'], tapes['old_tip']
    changed = np.flatnonzero(control != old)
    begin, end = cfg['local_frames']
    begin_changes = int(np.count_nonzero(changed < cfg['cut_frame']))
    end_changes = int(changed.size) - begin_changes
    checks = {
        'pcm16_byte_partition_exact': all(byte_checks.values()),
        'same_transcript': paths['lab'].read_bytes() == paths['old_lab'].read_bytes(),
        'registered_parent_pcm_differences': changed.size == cfg['parent_pcm16_differences']
            and int(changed[0]) == cfg['parent_pcm16_first_difference']
            and int(changed[-1]) == cfg['parent_pcm16_last_difference'] and min(begin_changes, end_changes) > 0,
        'untouched_local_pcm': all(np.array_equal(tape[begin:end], control[begin:end]) for tape in tapes.values()),
        'whole_control_alignment_replayed': tiers['control'] == mfa.tiers(paths['control_tier'])
            and intervals['control'][1] == cfg['control_end_seconds'],
        'whole_old_tip_alignment_replayed': tiers['old_tip'] == mfa.tiers(paths['old_tip_tier'])
            and intervals['old_tip'][1] == cfg['old_tip_end_seconds'],
        'fixed_and_independent_formants_agree': all(row['agrees'] for values in rows.values() for row in values),
    }
    return {
        'checks': checks,
        'predictions': {'preroll_only_recovers_old_boundary': intervals['old_preroll'][1] == cfg['old_tip_end_seconds'],
                        'remainder_only_keeps_control_boundary': intervals['old_remainder'][1] == cfg['control_end_seconds']},
        'pcm16_differences_by_region': {'preroll': begin_changes, 'remainder': end_changes},
        'tall_vowel_intervals': intervals,
        'alignment_vs_control': {name: aligned.compare_intervals(tiers['control'], tier) for name, tier in tiers.items()},
        'last_window': {name: values[-1] for name, values in rows.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = formants.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    parent, archive, report = (formants.open_run(case[key], revision) for key in ('parent', 'alignment_settings', 'formants'))
    align_case, align_snapshot = saved_case(archive, CASE.with_name(f"{case['alignment_settings']['case']}.json"))
    analysis, analysis_snapshot = saved_case(report, formants.CASE)
    if parent[1]['aligner'] != align_case['aligner']:
        parser.error('前回のMFA設定と登録済み設定が一致しません')
    uid = case['utterance']
    control, old = f'{uid}-candidate', f'{uid}-old_tip'
    paths = {name: formants.verified_path(parent, 'artifacts/' + item) for name, item in (
        ('dictionary', 'synth.dict'), ('clean', 'matched-clean.wav'),
        ('control_pcm', f'corpus/{control}/{control}.wav'), ('old_tip_pcm', f'corpus/{old}/{old}.wav'),
        ('control_tier', f'aligned/{control}/{control}.json'), ('old_tip_tier', f'aligned/{old}/{old}.json'),
        ('lab', f'corpus/{control}/{control}.lab'), ('old_lab', f'corpus/{old}/{old}.lab'))}
    helpers = ('measure_tsp_again_initial_tip_mfa.py', 'measure_tsp_f2_bandwidth_held_out.py',
               'measure_tsp_matched_speech_mfa.py', 'measure_tsp_phone_boundaries.py',
               'measure_tsp_stressed_vowel_formants.py', 'measure_tsp_tall_output_gain_mfa.py')
    source = (formants.TSP_SOURCE, 'crates/chimera-cli/src/wav.rs', 'crates/chimera-cli/src/main.rs',
              'crates/chimera/src/analysis/lpc.rs', 'crates/chimera/tests/golden_analysis.rs',
              align_case['aligner']['configuration'])
    inputs = [CASE, Path(__file__).resolve(), align_snapshot, analysis_snapshot, *paths.values(),
              *(run[0] / 'manifest.json' for run in (parent, archive, report)), formants.PROBE,
              *(WORKSPACE / 'tools' / name for name in helpers), *(UPSTREAM / name for name in source)]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'aligner': align_case['aligner']}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, align_case, analysis, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
