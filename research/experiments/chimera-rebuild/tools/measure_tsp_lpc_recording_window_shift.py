"""実録音の同じ母音区間内で窓をずらし、LPCのF2候補を照合する。"""

import argparse
from collections import Counter
import math
from pathlib import Path
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_lpc_order_recordings as recording_order
import measure_tsp_lpc_pre_emphasis_recordings as pre_emphasis
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-lpc-recording-window-shift.json'


def direct_decimation(path, start, end, cfg):
    fs, data = wavfile.read(path)
    x = [float(n) / 32768 for n in data]
    taps, dec = cfg['low_pass_taps'], cfg['decimation']
    half = (taps - 1) // 2
    fc = cfg['low_pass_hz'] / fs
    kernel = []
    for j in range(taps):
        m = j - half
        sinc = math.sin(2 * math.pi * fc * m) / (math.pi * m) if m else 2 * fc
        phase = 2 * math.pi * j / (taps - 1)
        kernel.append(sinc * (0.42 - 0.5 * math.cos(phase) + 0.08 * math.cos(2 * phase)))
    return np.array([sum(coefficient * x[i] for j, coefficient in enumerate(kernel)
                         if 0 <= (i := position * dec + j - half) < len(x))
                     for position in range(start, end)])


def classify_window(case, cfg, observed):
    picked = observed['selected']
    eligible = recording_order.eligible_f2(observed['public_poles_hz'], picked['f1'], cfg)
    bands = {}
    for name in ('low', 'high'):
        lower, upper = case[f'{name}_band_hz']
        bands[name] = {label: [pole for pole in poles if lower <= pole[0] <= upper]
                       for label, poles in (('raw', observed['raw_poles_hz']),
                                            ('public', observed['public_poles_hz']), ('eligible', eligible))}
    selected = picked['f2']
    category = picked['reason'] if selected is None else next(
        (name for name, candidates in bands.items() if selected in candidates['eligible']), 'other')
    low = bands['low']
    low_gaps = [pole[0] - picked['f1'][0] for pole in low['public'] if picked['f1'] is not None]
    first_difference = None
    if category != 'low':
        if not low['raw']:
            first_difference = 'pole_estimation'
        elif not low['public']:
            first_difference = ('bandwidth_filter' if all(pole[1] > cfg['pole_max_bandwidth_hz'] for pole in low['raw'])
                                else 'public_pole_filter')
        elif not low['eligible']:
            first_difference = 'f1_or_f2_eligibility'
        else:
            first_difference = 'f2_candidate_order'
    return {'bands': bands, 'category': category, 'low_public_gaps_from_f1_hz': low_gaps,
            'first_difference_from_baseline_low_choice': first_difference}


def measure(case, prior, cfg, wave_path, anchor, anchor_probe, out, execute):
    target = case['target']
    order, length, start = (target[name] for name in ('order', 'frame_samples', 'start_sample'))
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    interval = anchor['interval_seconds']
    left, right = case['offset_samples']
    offsets = range(left, right + 1)
    wave = tsp.filtered_wave(wave_path, 'recording', cfg)
    first, last = start + left, start + right + length
    window_center = interval[0] + target['center'] * (interval[1] - interval[0])
    if (not left <= 0 <= right or not 0 <= first < last <= len(wave)
            or first / rate < interval[0] or last / rate > interval[1]
            or order != cfg['order'][target['utterance'][0]]
            or cfg['pre_emphasis'] != prior['pre_emphasis']
            or int(window_center * rate) - length // 2 != start or length != int(cfg['frame_seconds'] * rate)):
        raise ValueError('音素区間、窓の標本位置、または固定LPC設定が一致しません')
    frames = [wave[start + shift:start + shift + length] for shift in offsets]
    segment = wave[first:last]
    decimated_error = float(np.max(abs(segment - direct_decimation(wave_path, first, last, cfg))))
    np.savez_compressed(out / 'decimated-segment.npz', first_sample=first, samples=segment)
    fixed = envelope.fixed_spectra(frames, np.empty(0), out, execute, orders=[order] * len(offsets), include_roots=True)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = []
    for shift, frame, probe in zip(offsets, frames, fixed, strict=True):
        observed = recording_order.observe(frame, rate, order, probe, cfg)
        rows.append({'offset_samples': shift, 'start_sample': start + shift, **observed,
                     **classify_window(case, cfg, observed)})
    zero, zero_probe = rows[-left], fixed[-left]
    same_recording = all(zero_probe[name] == value for name, value in anchor_probe.items() if name != 'lpc_envelope_db')
    same_selection = (zero['selected'] == anchor['by_order'][str(order)]['selected']
                      and zero['category'] == 'low' and bool(zero['bands']['high']['eligible']))
    root_limit = prior['raw_complex_distance_tolerance']
    pole_limit = cfg['frequency_bandwidth_agreement_hz']
    checks = {
        'registered_windows_inside_phone_and_finite':
            len(rows) == len(offsets) and all(len(frame) == length and np.isfinite(frame).all() for frame in frames),
        'zero_offset_matches_archived_probe_and_selection': same_recording and same_selection,
        'decimation_matches_direct_tap_sum': decimated_error <= case['decimation_absolute_tolerance'],
        'independent_raw_roots': all(row['errors_hz']['raw'] <= prior['raw_root_comparison_hz']
            and row['raw_complex_max_distance'] <= root_limit
            and all(abs(entry[side][1]) <= root_limit for entry in row['real_axis_matches']['raw']
                    for side in ('fixed', 'independent')) for row in rows),
        'independent_public_poles_and_selection':
            all(row['errors_hz'][name] is not None and row['errors_hz'][name] <= pole_limit
                for row in rows for name in ('public', 'public_filter', 'selected')),
    }
    transitions = [{'offsets_samples': [a['offset_samples'], b['offset_samples']],
                    'categories': [a['category'], b['category']],
                    'first_differences': [a['first_difference_from_baseline_low_choice'],
                                          b['first_difference_from_baseline_low_choice']]}
                   for a, b in zip(rows, rows[1:]) if a['category'] != b['category']]
    predictions = {
        'high_band_remains_eligible': all(row['bands']['high']['eligible'] for row in rows),
        'low_band_stays_above_gap_while_public': all(
            not row['bands']['low']['public'] or (row['low_public_gaps_from_f1_hz']
            and min(row['low_public_gaps_from_f1_hz']) > cfg['f2_min_gap_hz']) for row in rows),
        'window_shift_changes_selection_at_bandwidth_filter':
            any(row['category'] == 'high' and row['first_difference_from_baseline_low_choice'] == 'bandwidth_filter'
                for row in rows),
    }
    return {'checks': checks, 'predictions': predictions, 'target': target, 'interval_seconds': interval,
            'decimation_max_absolute_error': decimated_error, 'selection_counts': dict(Counter(r['category'] for r in rows)),
            'transitions': transitions, 'windows': rows}


def verify_annotation(case, cfg, wave, key_path, clip_path, result):
    target, association = case['target'], case['annotation']
    key = tsp.read(key_path)
    trial = key['trials'][association['trial']]
    start, length = target['start_sample'], target['frame_samples']
    analysis_rate = cfg['sample_rate_hz'] / cfg['decimation']
    rate, pcm = wavfile.read(wave)
    clip_rate, clip = wavfile.read(clip_path)
    first, count = trial['clip_start_sample'], trial['clip_frames']
    focus = [(sample / analysis_rate - first / rate) * 1000 for sample in (start, start + length)]
    result['checks']['annotation_uses_registered_window_and_pcm'] = (
        key['packet_id'] == association['packet_id'] and trial['kind'] == 'recording'
        and all(trial[name] == target[name] for name in ('utterance', 'word', 'center'))
        and trial['phone_seconds'] == result['interval_seconds'] and trial['analysis_samples'] == [start, start + length]
        and trial['wave_sha256'] == sha256(clip_path) and rate == clip_rate == trial['sample_rate_hz']
        and clip.dtype == pcm.dtype == np.int16 and clip.shape == (count,)
        and np.array_equal(clip, pcm[first:first + count])
        and tsp.max_error(focus, trial['focus_ms']) <= 1e-9
    )
    zero = result['windows'][-case['offset_samples'][0]]['selected']['f2']
    result['checks']['annotation_baseline_f2_replayed'] = (
        zero is not None and abs(zero[0] - trial['held_out_lpc_f2_hz'][0]) <= cfg['frequency_bandwidth_agreement_hz'])
    result['predictions']['low_band_remains_selected'] = result['selection_counts'] == {'low': len(result['windows'])}
    result['annotation'] = {'packet_id': key['packet_id'], 'trial': association['trial'],
                            'analysis_samples': trial['analysis_samples'], 'focus_ms': focus,
                            'clip_sha256': trial['wave_sha256']}
    ranges = {}
    for name in ('low', 'high'):
        candidates = [p for row in result['windows'] for p in row['bands'][name]['eligible']]
        ranges[name] = {'eligible_windows': sum(bool(row['bands'][name]['eligible']) for row in result['windows']),
                        'frequency_hz': [min(p[0] for p in candidates), max(p[0] for p in candidates)] if candidates else None,
                        'bandwidth_hz': [min(p[1] for p in candidates), max(p[1] for p in candidates)] if candidates else None}
    result['candidate_ranges'] = ranges
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = tsp.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archived = tsp.open_run(case['order_reference'], revision)
    prior, prior_path = saved_case(archived, recording_order.CASE)
    prep = tsp.open_run(prior['recording_reference'], revision)
    source, source_path = saved_case(prep, pre_emphasis.CASE)
    registered = tsp.open_run(source['baseline'], revision)
    definition, cfg_path = saved_case(registered, tsp.CASE)
    alignment = tsp.open_run(definition['alignment'], revision)
    reference = tsp.verified_path(archived, 'summary.json')
    probes_path = tsp.verified_path(archived, 'artifacts/upstream-envelopes.json')
    align_path = tsp.verified_path(alignment, 'summary.json')
    target = case['target']
    uid = target['utterance']
    wave_path = tsp.verified_path(alignment, f'artifacts/corpus/recording/{uid}/{uid}.wav')
    input_root = WORKSPACE.parents[2]
    original_hash, = (entry['sha256'] for entry in archived[1]['inputs']
                      if entry['path'] == wave_path.relative_to(input_root).as_posix())
    index, = (i for i, row in enumerate(tsp.read(reference)['windows']) if all(row[k] == v for k, v in target.items()))
    anchor = tsp.read(reference)['windows'][index]
    probe = tsp.read(probes_path)[index * len(prior['orders']) + prior['orders'].index(target['order'])]
    phone = tsp.read(align_path)['intervals'][uid]['phones'][target['phone_index']]
    if sha256(wave_path) != original_hash or phone != [*anchor['interval_seconds'], target['arpabet']]:
        parser.error('録音または音素境界が先行の次数比較と一致しません')
    tools = ('measure_tsp_lpc_order_recordings', 'measure_tsp_lpc_pre_emphasis_recordings',
             'measure_tsp_f2_bandwidth_envelope', 'measure_tsp_f2_bandwidth_held_out', 'measure_tsp_f2_harmonic_bandwidth',
             'measure_tsp_stressed_vowel_formants', 'measure_uniform_tube', 'upstream_baseline')
    inputs = [case_path, Path(__file__).resolve(), prior_path, source_path, cfg_path, reference, probes_path,
              align_path, wave_path, envelope.PROBE, *(run[0] / 'manifest.json' for run in (archived, prep, registered, alignment)),
              *(WORKSPACE / f'tools/{name}.py' for name in tools), UPSTREAM / tsp.TSP_SOURCE,
              UPSTREAM / 'crates/chimera/src/analysis/lpc.rs', UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    annotation_paths = None
    if association := case.get('annotation'):
        packet = tsp.open_run(association, revision)
        annotation_paths = (tsp.verified_path(packet, 'artifacts/reference.json'),
                            tsp.verified_path(packet, f"artifacts/review/{association['trial']}.wav"))
        inputs.extend((packet[0] / 'manifest.json', *annotation_paths))

    def run(out, execute):
        cfg = definition['measurement']
        result = measure(case, prior, cfg, wave_path, anchor, probe, out, execute)
        return verify_annotation(case, cfg, wave_path, *annotation_paths, result) if annotation_paths else result

    return record_measurement(args.run_id, case_path, inputs, details, run, command=None, input_root=input_root)


if __name__ == '__main__':
    raise SystemExit(main())
