"""連続母音列と固定発声の /ɔ/ に同じLPC条件を適用する。"""

import argparse
import csv
from itertools import product
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import resample_poly

from measure_fan_crossing_allocations import run_manifest, verified_path
import measure_vowel_benchmark as benchmark
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/vowel-open-o-lpc-matched.json'
ROOT = WORKSPACE.parents[2]
WAVES = {'sequence': 'upstream-vowel-sequence.wav', 'fixed': 'fixed.wav'}
AXES = ('start_frame', 'duration_frames', 'analysis_rate_hz', 'decimator', 'order')


def read(path):
    return json.loads(path.read_text())


def archived_inputs(study):
    definitions, paths = {}, {}
    outputs = {'sequence': ('artifacts/upstream-vowel-sequence.wav', 'summary.json'),
               'fixed': ('artifacts/block-128.wav', 'artifacts/upstream-voice.wav',
                         'artifacts/upstream-lpc-window.f64', 'summary.json')}
    for name, files in outputs.items():
        ref = study[name]
        run, manifest = run_manifest(ref['run'], ref['case'], study['upstream_revision'])
        manifest_path = run / 'manifest.json'
        if manifest['status'] != 'pass' or sha256(manifest_path) != ref['manifest_sha256']:
            raise ValueError(f'保存済みの実験が事前登録の記録と一致しません ({name})')
        entry, = (row for row in manifest['inputs'] if row['path'] == f'cases/{ref["case"]}.json')
        case = run / manifest['source_snapshot'] / entry['path']
        if sha256(case) != entry['sha256']:
            raise ValueError(f'保存済みのケースを照合できません ({name})')
        definitions[name] = case
        paths[name] = {'manifest': manifest_path, **{Path(file).name: verified_path((run, manifest), file) for file in files}}
    return definitions, paths


def condition_grid(cfg):
    short, long = cfg['durations_frames']
    low, high = cfg['analysis_rates_hz']
    small, large = cfg['orders']
    anchor = cfg['common_starts_frames'][0]
    original_sequence = (anchor, short, low, 'box', small)
    original_fixed = (cfg['legacy_fixed_start_frame'], long, high, 'polyphase', large)
    pairs = list(product(cfg['common_starts_frames'], cfg['durations_frames'], cfg['analysis_rates_hz'],
                         cfg['decimators'], cfg['orders']))
    rows = [(voice, key) for voice, key in product(WAVES, pairs)] + [('fixed', original_fixed)]
    return dict(enumerate(rows)), (original_sequence, original_fixed)


def read_wave(path, cfg, voice):
    rate, data = wavfile.read(path)
    if rate != cfg['source_rate_hz'] or data.dtype != np.float32 or data.shape != (cfg['source_frames'][voice],):
        raise ValueError(f'PCMのレート・フレーム数・標本形式が登録値と異なります ({path.name})')
    if not np.isfinite(data).all():
        raise ValueError(f'PCMに非有限値があります ({path.name})')
    return data


def reconstruct_frame(wave, voice, settings, cfg):
    start, duration, rate, decimator, _ = settings
    offset = cfg['sequence_vowel_index'] * cfg['vowel_segment_frames'] if voice == 'sequence' else 0
    raw = wave[offset+start:offset+start+duration].astype(np.float64)
    if len(raw) != duration or (voice == 'sequence' and start+duration > cfg['sequence_gate_end_frame']):
        raise ValueError(f'登録した有声区間から測定窓が外れました ({voice}, {settings})')
    source_rate = cfg['source_rate_hz']
    ratio, remainder = divmod(source_rate, rate)
    if ratio < 2 or remainder or duration % ratio:
        raise ValueError('元のサンプルを整数比で分割できません')
    if decimator == 'box':
        groups = raw.reshape(-1, ratio)
        totals = groups[:, 0].copy()
        for column in groups.T[1:]:
            totals += column
        processed = totals / ratio
    elif decimator == 'polyphase':
        processed = resample_poly(raw, rate, source_rate)
    else:
        raise ValueError(f'未対応の間引き方式です ({decimator})')
    return raw, processed


def capture(study, definitions, out, execute):
    cfg = study['measurement']
    sequence_def = read(definitions['sequence'])
    fixed_def = read(definitions['fixed'])
    block = fixed_def['measurement']['voice']['host_block_sizes'][0]
    native = benchmark.native_reference(sequence_def, out, execute)
    (out / 'native-vowel-report.json').write_text(json.dumps(native, ensure_ascii=False, indent=2) + '\n')
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--',
             'render-pcm', str(definitions['fixed']), str(out / WAVES['fixed']), '--no-trace', str(block)])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'upstream-golden-analysis.log')
    probe = vowel.shared.build_upstream_probe(vowel.PROBE, out, execute, cargo_args=('--offline',))
    waves = {voice: read_wave(out / name, cfg, voice) for voice, name in WAVES.items()}
    versions, _ = condition_grid(cfg)
    frames, measured = {}, {}
    with TemporaryDirectory(prefix='lpc-windows-', dir=out) as tmp:
        scratch = Path(tmp)
        pcm_path, frame_path, report, root_path = (scratch / name for name in ('raw', 'lpc', 'analysis.csv', 'roots.csv'))
        for index, (voice, settings) in versions.items():
            raw, frame = reconstruct_frame(waves[voice], voice, settings, cfg)
            frames[f'raw_{index}'], frames[f'lpc_{index}'] = raw, frame
            raw.astype('<f8').tofile(pcm_path)
            frame.astype('<f8').tofile(frame_path)
            rate, order = settings[2], settings[4]
            args = (pcm_path, cfg['source_rate_hz'], cfg['pitch_min_hz'], cfg['pitch_max_hz'], cfg['yin_threshold'],
                    frame_path, rate, order, cfg['pre_emphasis'], cfg['lpc_min_hz'], cfg['lpc_max_bandwidth_hz'],
                    report, root_path)
            execute([str(probe), 'analyze', *map(str, args)], cwd=UPSTREAM)
            with report.open(newline='') as stream:
                pitch, *formants = csv.DictReader(stream)
            with root_path.open(newline='') as stream:
                roots = [[float(row['real']), float(row['imaginary'])] for row in csv.DictReader(stream)]
            measured[index] = {'pitch_hz': float(pitch['frequency_hz']) if pitch['frequency_hz'] else None,
                               'pitch_aperiodicity': float(pitch['aperiodicity_or_bandwidth_hz']),
                               'formants': [[float(row['frequency_hz']), float(row['aperiodicity_or_bandwidth_hz'])]
                                            for row in formants],
                               'roots': roots}
            report.unlink()
            root_path.unlink()
    np.savez_compressed(out / 'analysis-windows.npz', **frames)
    (out / 'upstream-analysis.json').write_text(json.dumps(measured, indent=2, allow_nan=False) + '\n')


def inspect_condition(pcm, settings, cfg, probe):
    rate, order = settings[2], settings[4]
    lpc_cfg = cfg | {'lpc_sample_rate_hz': rate, 'lpc_order': order}
    cutoff = rate / 2 - cfg['lpc_nyquist_guard_hz']
    independent = vowel.independent_lpc(pcm, lpc_cfg)
    upper = np.asarray(probe['formants'], dtype=float).reshape(-1, 2)
    independent = independent[independent[:, 0] < cutoff]
    retained = upper[upper[:, 0] < cutoff]
    errors = abs(independent - retained).max(axis=0).tolist() if len(independent) and independent.shape == retained.shape else None
    raw_peaks = []
    for re_part, im_part in probe['roots']:
        if im_part <= 0.0:
            continue
        root = complex(re_part, im_part)
        frequency = float(np.angle(root) * rate / (2 * np.pi))
        bandwidth = float(-np.log(abs(root)) * rate / np.pi)
        accepted = cfg['lpc_min_hz'] <= frequency < cutoff and bandwidth <= cfg['lpc_max_bandwidth_hz']
        raw_peaks.append({'frequency_hz': frequency, 'bandwidth_hz': bandwidth, 'included': accepted})
    candidates = np.array(sorted((p['frequency_hz'], p['bandwidth_hz']) for p in raw_peaks if p['included'])).reshape(-1, 2)
    filter_matches = candidates.shape == retained.shape and np.allclose(candidates, retained, rtol=0, atol=1e-7)
    return {'formants_hz_and_bw_hz': independent.tolist(), 'upstream_formants_hz_and_bw_hz': retained.tolist(),
            'upstream_nyquist_reported': upper[upper[:, 0] >= cutoff].tolist(), 'error_hz_and_bw_hz': errors,
            'raw_peak_filter_matches': bool(filter_matches),
            'raw_peaks': sorted(raw_peaks, key=lambda p: p['frequency_hz'])}


def aggregate(rows, cfg, legacy):
    table = {(row['wave'], tuple(row[key] for key in AXES)): row['upstream_formants_hz_and_bw_hz'][0][0]
             for row in rows if row['upstream_formants_hz_and_bw_hz']}
    source_preset, fixed_preset = legacy
    start = cfg['common_starts_frames'][0]
    baseline_settings = (source_preset, (start, *fixed_preset[1:]))
    matrix = [[table[wave, settings] for settings in baseline_settings] for wave in WAVES]
    (a, b), (c, d) = matrix
    original_fixed = table['fixed', fixed_preset]
    original_difference = original_fixed - a
    waveform = ((c-a) + (d-b)) / 2
    analysis = ((b-a) + (d-c)) / 2
    start_effect = original_fixed - d
    pairs = {settings: table['fixed', settings] - value for (wave, settings), value in table.items()
             if wave == 'sequence' and ('fixed', settings) in table}
    matched_reference = {str(anchor): [pairs[(anchor, *method[1:])] for method in baseline_settings]
                         for anchor in cfg['common_starts_frames']}
    levels = (cfg['common_starts_frames'], cfg['durations_frames'], cfg['analysis_rates_hz'],
              cfg['decimators'], cfg['orders'])
    factor_effects = {}
    for wave in WAVES:
        factor_effects[wave] = {}
        for i, (axis, (before, after)) in enumerate(zip(AXES, levels, strict=True)):
            deltas = [table[wave, key[:i] + (after,) + key[i+1:]] - table[wave, key]
                      for key in pairs if key[i] == before]
            factor_effects[wave][axis] = {'from': before, 'to': after, 'count': len(deltas),
                                         'median_hz': float(np.median(deltas)), 'min_hz': min(deltas), 'max_hz': max(deltas)}
    return {'anchor_frame': start, 'waves': list(WAVES), 'settings_at_common_anchor': [list(key) for key in baseline_settings],
            'crossed_first_peaks_hz': matrix, 'matched_reference_differences_hz': matched_reference,
            'all_matched_differences_hz': {'count': len(pairs), 'minimum': min(pairs.values()),
                                           'maximum': max(pairs.values()), 'median': float(np.median(list(pairs.values())))},
            'legacy_unrounded_difference_hz': original_difference, 'waveform_effect_hz': waveform,
            'analysis_effect_hz': analysis, 'fixed_legacy_start_effect_hz': start_effect,
            'decomposition_residual_hz': original_difference - waveform - analysis - start_effect,
            'paired_factor_effects_hz': factor_effects}


def analyze(study, definitions, archived, out):
    cfg = study['measurement']
    versions, legacy = condition_grid(cfg)
    probes = read(out / 'upstream-analysis.json')
    waves = {name: read_wave(out / file, cfg, name) for name, file in WAVES.items()}
    old = {'sequence': read_wave(archived['sequence'][WAVES['sequence']], cfg, 'sequence'),
           'fixed': read_wave(archived['fixed']['block-128.wav'], cfg, 'fixed')}
    old_upper = read_wave(archived['fixed']['upstream-voice.wav'], cfg, 'fixed')
    archived_report = read(archived['sequence']['summary.json'])['native_reference']
    current_report = read(out / 'native-vowel-report.json')
    fixed_definition = read(definitions['fixed'])['measurement']['voice']
    sequence_cfg = read(definitions['sequence'])['measurement']['native_vowel_sequence']
    checks = {
        'sequence_full_pcm_and_cli_report': bool(np.array_equal(waves['sequence'].view('<u4'), old['sequence'].view('<u4')))
        and current_report == archived_report,
        'fixed_full_pcm_against_both_archives': all(
            np.array_equal(waves['fixed'].view('<u4'), saved.view('<u4')) for saved in (old['fixed'], old_upper)),
        'historical_clock_settings': sequence_cfg['vowel_seconds'] * cfg['source_rate_hz'] == cfg['vowel_segment_frames']
        and sequence_cfg['gate_end_seconds'] * cfg['source_rate_hz'] == cfg['sequence_gate_end_frame']
        and current_report['rows'][cfg['sequence_vowel_index']]['ipa'] == fixed_definition['ipa'] == cfg['ipa']
        and all(fixed_definition[key] == expected for key, expected in
                zip(('start_frame', 'frame_count', 'lpc_sample_rate_hz', 'lpc_order'),
                    (legacy[1][0], legacy[1][1], legacy[1][2], legacy[1][4]), strict=True)),
    }
    exposed, voiced, result = [], [], []
    with np.load(out / 'analysis-windows.npz', allow_pickle=False) as saved:
        for index, (voice, settings) in versions.items():
            raw, frame = reconstruct_frame(waves[voice], voice, settings, cfg)
            exposed.append(np.array_equal(saved[f'raw_{index}'], raw) and np.array_equal(saved[f'lpc_{index}'], frame))
            probe = probes[str(index)]
            lo, hi = cfg['voiced_pitch_hz']
            voiced.append(probe['pitch_hz'] is not None and lo <= probe['pitch_hz'] <= hi)
            info = inspect_condition(frame, settings, cfg, probe)
            result.append({'index': index, 'wave': voice, **dict(zip(AXES, settings, strict=True)),
                           'probe_pitch_hz': probe['pitch_hz'], 'raw_rms': float(np.sqrt(np.mean(raw*raw))), **info})
        fixed_original_index = next(index for index, (voice, settings) in versions.items()
                                    if voice == 'fixed' and settings == legacy[1])
        fixed_input = np.fromfile(archived['fixed']['upstream-lpc-window.f64'], dtype='<f8')
        checks['legacy_fixed_input'] = bool(np.array_equal(saved[f'lpc_{fixed_original_index}'].view('<u8'),
                                                         fixed_input.view('<u8')))
    first = next(row for row in result if row['wave'] == 'sequence'
                 and tuple(row[key] for key in AXES) == legacy[0])
    archived_poles = read(archived['fixed']['summary.json'])['acoustic']['lpc_formants_frequency_bandwidth_hz']
    fixed_row = result[fixed_original_index]
    fixed_poles = np.asarray(fixed_row['formants_hz_and_bw_hz'])
    expected = np.asarray(archived_poles)
    checks.update({
        'raw_and_resampled_inputs_replayed': all(exposed) and len(probes) == len(versions),
        'windows_are_voiced_and_have_first_peaks': all(voiced) and all(row['upstream_formants_hz_and_bw_hz'] for row in result),
        'independent_lpc_frequencies_bandwidths': all(row['error_hz_and_bw_hz'] is not None
                                                     and max(row['error_hz_and_bw_hz']) < cfg['maximum_probe_independent_error_hz']
                                                     for row in result),
        'raw_peak_selection_matches_public_lpc': all(row['raw_peak_filter_matches'] for row in result),
        'legacy_sequence_three_reported_peaks': [int(np.floor(f + 0.5)) for f, _ in first['upstream_formants_hz_and_bw_hz'][:3]]
        == archived_report['rows'][cfg['sequence_vowel_index']]['lpc_hz'],
        'legacy_fixed_public_peaks': fixed_poles.shape == expected.shape and np.max(abs(fixed_poles - expected))
        < cfg['legacy_fixed_error_hz'],
    })
    stats = aggregate(result, cfg, legacy) if all(row['upstream_formants_hz_and_bw_hz'] for row in result) else {}
    if not stats:
        return {'checks': {key: bool(value) for key, value in checks.items()}, 'hypotheses': {},
                'statistics': stats, 'conditions': result}
    errors = [max(row['error_hz_and_bw_hz']) for row in result if row['error_hz_and_bw_hz'] is not None]
    stats['largest_independent_error_hz'] = max(errors, default=None)
    stats['conditions_with_fewer_than_three_peaks'] = [
        row['index'] for row in result if len(row['upstream_formants_hz_and_bw_hz']) < 3]
    m = stats['crossed_first_peaks_hz']
    hypotheses = {
        'fixed_peak_remains_higher_with_matched_choices': all(x >= cfg['minimum_reference_matched_difference_hz']
                                                               for values in stats['matched_reference_differences_hz'].values()
                                                               for x in values),
        'analysis_choices_change_a_single_wave': max(abs(b-a) for a, b in m) >= cfg['minimum_explicit_analysis_effect_hz'],
        'the_waveform_accounts_for_most_of_the_legacy_difference': stats['waveform_effect_hz']
        >= stats['legacy_unrounded_difference_hz'] / 2,
    }
    checks['crossed_effects_reconstruct_legacy_difference'] = len(result) == 65 and abs(stats['decomposition_residual_hz']) < 1e-9
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'hypotheses': hypotheses, 'statistics': stats, 'conditions': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    definitions, archived = archived_inputs(study)

    def measure(out, execute):
        capture(study, definitions, out, execute)
        return analyze(study, definitions, archived, out)

    inputs = [CASE, *definitions.values(), *(path for entries in archived.values() for path in entries.values()),
              Path(__file__), Path(vowel.__file__), Path(benchmark.__file__), Path(vowel.shared.__file__), vowel.PROBE,
              UPSTREAM / 'crates/chimera-cli/src/render.rs', UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', *vowel.shared.candidate_sources()]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'scipy_version': scipy.__version__}
    return vowel.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
