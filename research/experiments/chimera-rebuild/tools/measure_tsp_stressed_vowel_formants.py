"""TSP確認用の強勢付き単母音で、窓位置を変えたときのF1・F2を照合する。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.linalg import toeplitz

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-stressed-vowel-formants-held-out.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_formant_probe.rs'
TSP_SOURCE = Path('crates/chimera-cli/src/compare/tsp.rs')


def read(path):
    return json.loads(path.read_text())


def open_run(spec, revision):
    run = run_manifest(spec['run'], spec['case'], revision)
    if run[1]['status'] != 'pass' or sha256(run[0] / 'manifest.json') != spec['manifest_sha256']:
        raise ValueError(f"入力の計測が登録済みの実行と一致しません ({spec['run']})")
    return run


def load_inputs(case, alignment, render):
    observed = read(verified_path(alignment, 'summary.json'))
    original = read(verified_path(render, 'summary.json'))['splits']['held_out']
    data = {}
    for uid in case['recording_ids']:
        source = {}
        for voice in ('recording', 'upstream', 'candidate'):
            tag = uid if voice == 'recording' else f'{uid}-{voice}'
            if voice == 'recording':
                wave = verified_path(alignment, f'artifacts/corpus/recording/{uid}/{uid}.wav')
                if sha256(wave) != original[uid]['recording_sha256']:
                    raise ValueError(f'元の録音と一致しません ({uid})')
            else:
                wave = verified_path(render, f'artifacts/{uid}/{voice}.wav')
            source[voice] = {'wave': wave, **observed['intervals'][tag]}
        pairs, stressed = {}, {}
        for voice in ('upstream', 'candidate'):
            rows = observed['pairs'][uid][voice]['phones_recording_to_synth']
            pairs[voice] = [[row['recording_index'], row['synth_index']] for row in rows]
            for row, (i, j) in zip(rows, pairs[voice], strict=True):
                if (source['recording']['phones'][i] != row['recording'] or
                        source[voice]['phones'][j] != row['synth']):
                    raise ValueError(f'対応表の音素区間が元の整列結果と一致しません ({uid}/{voice})')
            stressed[voice] = [[i, j, case['arpabet_to_ipa'][phone]]
                               for i, j in pairs[voice]
                               if (phone := source[voice]['phones'][j][2]) in case['arpabet_to_ipa']]
        candidate_for_human = {i: (j, ipa) for i, j, ipa in stressed['candidate']}
        tokens = [{'ipa': ipa, 'recording': i, 'upstream': j, 'candidate': candidate_for_human[i][0]}
                  for i, j, ipa in stressed['upstream']
                  if i in candidate_for_human and candidate_for_human[i][1] == ipa]
        if len(tokens) != case['matched_vowels_per_utterance'][uid]:
            raise ValueError(f'共通の強勢付き単母音数が事前登録と一致しません ({uid})')
        data[uid] = {'source': source, 'pairs': pairs, 'stressed': stressed, 'tokens': tokens}
    return data


def filtered_wave(path, voice, cfg):
    fs, samples = wavfile.read(path)
    dtype = np.int16 if voice in ('recording', 'control') else np.float32
    if fs != cfg['sample_rate_hz'] or samples.dtype != dtype or samples.ndim != 1 or not np.isfinite(samples).all():
        raise ValueError(f'計測対象の波形形式が一致しません ({path})')
    x = samples.astype(float)
    if dtype == np.int16:
        x /= 32768
    return analysis_downsample(x, cfg)


def analysis_downsample(x, cfg):
    fs = cfg['sample_rate_hz']
    taps, dec = cfg['low_pass_taps'], cfg['decimation']
    half = (taps - 1) // 2
    fc = cfg['low_pass_hz'] / fs
    kernel = 2 * fc * np.sinc(2 * fc * np.arange(-half, half + 1)) * np.blackman(taps)
    filtered = np.convolve(x, kernel)
    return filtered[half:half + (len(x) // dec) * dec:dec]


def independent_roots(frame, fs, order, cfg):
    emphasized = np.r_[frame[0], frame[1:] - cfg['pre_emphasis'] * frame[:-1]]
    shaped = emphasized * np.hamming(len(frame))
    corr = np.correlate(shaped, shaped, mode='full')[len(shaped) - 1:len(shaped) + order]
    corr *= np.exp(-0.5 * (2 * np.pi * cfg['lag_window_hz'] * np.arange(order + 1) / fs)**2)
    matrix = toeplitz(corr[:order])
    matrix.flat[::order + 1] = corr[0] * (1 + 1e-9) + 1e-30
    coefficients = np.r_[1., np.linalg.solve(matrix, -corr[1:])]
    return np.roots(coefficients)


def independent_poles(frame, fs, order, cfg):
    roots = independent_roots(frame, fs, order, cfg)
    upper = roots[roots.imag > 0]
    frequency = np.angle(upper) * fs / (2 * np.pi)
    bandwidth = -np.log(abs(upper)) * fs / np.pi
    poles = sorted([float(fr), float(bw)] for fr, bw in zip(frequency, bandwidth, strict=True)
                   if fr >= cfg['pole_min_frequency_hz'] and bw <= cfg['pole_max_bandwidth_hz'])
    real_roots = [float(root.real) for root in roots if root.imag == 0 and root.real < 0]
    return poles, real_roots


def window(lo, interval, q, order, cfg):
    a, b, _ = interval
    fs = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(cfg['frame_seconds'] * fs)
    start = int((a + q * (b - a)) * fs) - length // 2
    end = start + length
    outside = 1000 * (max(0, a - start / fs) + max(0, end / fs - b))
    result = {'center': q, 'start_sample': start, 'outside_phone_ms': outside,
              'poles': [], 'negative_real_roots': [], 'f1_f2_hz': None, 'reason': 'outside_wave'}
    if start < 0 or end > len(lo):
        return result
    poles, real_roots = independent_poles(lo[start:end], fs, order, cfg)
    result.update(poles=poles, negative_real_roots=real_roots, reason='no_f1')
    f1 = next((fr for fr, bw in poles
               if fr < cfg['f1_max_frequency_hz'] and bw < cfg['f1_max_bandwidth_hz']), None)
    if f1 is not None:
        f2 = next((fr for fr, _ in poles
                   if f1 + cfg['f2_min_gap_hz'] < fr < cfg['f2_max_frequency_hz']), None)
        result.update(f1_f2_hz=[f1, f2] if f2 is not None else None, reason='no_f2' if f2 is None else None)
    return result


def measure_fixed(case, data, centers, artifacts, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-golden-analysis.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tsp-tests.log')
    with TemporaryDirectory(prefix='fixed-tsp-', dir=artifacts) as directory:
        scratch = Path(directory)
        archive, copy = scratch / 'upstream.tar', scratch / 'upstream'
        copy.mkdir()
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(copy)])
        tsp = copy / TSP_SOURCE
        probe = tsp.with_name(PROBE.name)
        probe.write_bytes(PROBE.read_bytes())
        with tsp.open('a') as stream:
            stream.write(f'\ninclude!("{probe.name}");\n')
        entry = copy / 'crates/chimera-cli/src/main.rs'
        source = entry.read_text()
        anchor = '        ["compare", "tsp", ..]'
        if source.count(anchor) != 1:
            raise ValueError('固定上流のCLIの照合入口が1つに定まりません')
        entry.write_text(source.replace(anchor, '        ["research-formants", path] => '
                                        'compare::tsp::research_formants(path),\n' + anchor))
        voices = {uid: [uid.startswith('F'), {
            voice: [str(values['wave']), values['phones'], [token[voice] for token in row['tokens']]]
            for voice, values in row['source'].items()}] for uid, row in data.items()}
        # 先頭の母音では3窓が波形外。残る窓も無音のため採用極がない。
        control_wave = scratch / 'silence.wav'
        cfg = case['measurement']
        wavfile.write(control_wave, cfg['sample_rate_hz'], np.zeros(4800, dtype=np.int16))
        intervals = [[0.0, 0.02, 'IY1']]
        voices['control'] = [False, {'control': [str(control_wave), intervals, [0]]}]
        request = scratch / 'request.json'
        request.write_text(json.dumps([centers, voices], ensure_ascii=False))
        output = artifacts / 'upstream-formants.json'
        execute(['cargo', 'run', '--locked', '--offline', '--release', '--target-dir', str(scratch / 'target'),
                 '-p', 'chimera-cli', '--', 'research-formants', str(request)], cwd=copy, stdout=output)
        lo = filtered_wave(control_wave, 'control', cfg)
        control = [window(lo, intervals[0], q, cfg['order']['M'], cfg) for q in centers]
    return read(output), control


def max_error(a, b):
    if a is None or b is None:
        return 0.0 if a is b else None
    if len(a) != len(b):
        return None
    return float(np.max(np.abs(np.asarray(a) - np.asarray(b)))) if len(a) else 0.0


def compare_poles(window_row, fixed, cfg):
    poles = fixed['poles']
    raw_error = max_error(window_row['poles'], poles)
    limit = cfg['frequency_bandwidth_agreement_hz']
    if raw_error is not None and raw_error <= limit:
        return raw_error, raw_error, []
    fs = cfg['sample_rate_hz'] / cfg['decimation']
    on_axis, remaining = [], []
    negative_roots = window_row['negative_real_roots'].copy()
    for frequency, bandwidth in poles:
        if abs(frequency - fs / 2) <= cfg['nyquist_axis_agreement_hz']:
            match = next((root for root in negative_roots
                          if abs(-np.log(-root) * fs / np.pi - bandwidth) <= limit), None)
            if match is not None:
                on_axis.append({'fixed_pole_hz': [frequency, bandwidth], 'negative_real_root': match,
                                'independent_bandwidth_hz': float(-np.log(-match) * fs / np.pi)})
                negative_roots.remove(match)
                continue
        remaining.append([frequency, bandwidth])
    return raw_error, max_error(window_row['poles'], remaining), on_axis


def compare_windows(windows, reference, cfg):
    rows = []
    limit = cfg['frequency_bandwidth_agreement_hz']
    for window_row, fixed in zip(windows, reference, strict=True):
        raw_error, pole_error, axial_poles = compare_poles(window_row, fixed, cfg)
        errors = {'raw_poles_hz': raw_error, 'poles_hz': pole_error, 'nyquist_axis_matches': axial_poles,
                  'pair_hz': max_error(window_row['f1_f2_hz'], fixed['f1_f2_hz'])}
        stages = {'window_start': fixed['start_sample'] == window_row['start_sample'],
                  'filtered_poles': errors['poles_hz'] is not None and errors['poles_hz'] <= limit,
                  'selection': (errors['pair_hz'] is not None and errors['pair_hz'] <= limit
                                and fixed['reason'] == window_row['reason'])}
        rows.append({**errors, 'first_different_stage': next((name for name, ok in stages.items() if not ok), None)})
    return rows


def token_measurement(lo, interval, order, centers, fixed, cfg):
    windows = [window(lo, interval, q, order, cfg) for q in centers]
    comparison = compare_windows(windows, fixed['windows'], cfg)
    selected = [row['f1_f2_hz'] for row in windows
                if row['center'] in cfg['reference_centers'] and row['f1_f2_hz'] is not None]
    baseline = np.median(selected, axis=0).tolist() if selected else [None, None]
    if baseline == [None, None] or fixed['baseline_hz'] == [None, None]:
        difference = 0.0 if baseline == fixed['baseline_hz'] else None
    else:
        difference = max_error(baseline, fixed['baseline_hz'])
    return {'interval': interval, 'windows': windows, 'window_comparison': comparison,
            'baseline_hz': baseline, 'baseline_error_hz': difference, 'baseline_support': len(selected)}


def report_windows(rows, cfg):
    by_voice = {}
    for voice in ('recording', 'upstream', 'candidate'):
        values = [token[voice] for tokens in rows.values() for token in tokens]
        bins = {}
        for q in sorted(cfg['boundary_centers'] + cfg['reference_centers']):
            classified = {'crosses_phone': [], 'inside_phone': []}
            missing = Counter()
            shifts = []
            for token in values:
                by_q = {row['center']: row for row in token['windows']}
                row = by_q[q]
                center_pair = by_q[0.5]['f1_f2_hz']
                pair = row['f1_f2_hz']
                key = 'crosses_phone' if row['outside_phone_ms'] > 1e-9 else 'inside_phone'
                classified[key].append(pair is not None)
                if row['reason'] is not None:
                    missing[row['reason']] += 1
                if pair is not None and center_pair is not None:
                    shifts.append([abs(after - center) for after, center in zip(pair, center_pair, strict=True)])
            bins[str(q)] = {'windows': {key: {'total': len(flags), 'pair': sum(flags)}
                                       for key, flags in classified.items()}, 'missing': dict(missing),
                            'compared_to_midpoint': len(shifts),
                            'median_abs_shift_hz': np.median(shifts, axis=0).tolist() if shifts else None,
                            'max_abs_shift_hz': np.max(shifts, axis=0).tolist() if shifts else None,
                            'large_shift_count': sum(max(row) > cfg['boundary_large_shift_hz'] for row in shifts)}
        by_voice[voice] = bins
    return by_voice


def describe_f2_candidates(window, cfg):
    poles = window['poles']
    first = next((i for i, (frequency, width) in enumerate(poles)
                  if frequency < cfg['f1_max_frequency_hz'] and width < cfg['f1_max_bandwidth_hz']), None)
    f1 = poles[first][0] if first is not None else None
    lower = f1 + cfg['f2_min_gap_hz'] if f1 is not None else None
    rank = 0
    trace = []
    for i, (frequency, width) in enumerate(poles):
        candidate_rank = None
        if lower is None:
            decision = 'no_f1'
        elif frequency <= lower:
            decision = 'at_or_below_f1_gap'
        elif frequency >= cfg['f2_max_frequency_hz']:
            decision = 'at_or_above_f2_ceiling'
        else:
            rank += 1
            candidate_rank = rank
            decision = 'selected' if rank == 1 else 'later_in_frequency_order'
        trace.append({'frequency_hz': frequency, 'bandwidth_hz': width, 'selected_f1': i == first,
                      'f2_rank': candidate_rank, 'f2_decision': decision})
    return {'f1_hz': f1, 'f2_hz': window['f1_f2_hz'][1] if window['f1_f2_hz'] is not None else None,
            'missing_reason': window['reason'], 'poles': trace}


def write_f2_candidates(path, tokens, fixed, control, cfg):
    windows = []
    for uid, utterance in tokens.items():
        for voice, entries in fixed[uid]['sources'].items():
            for token, entry in zip(utterance, entries, strict=True):
                observed = token[voice]
                for local, upstream in zip(observed['windows'], entry['windows'], strict=True):
                    q = local['center']
                    windows.append({'utterance': uid, 'source': voice, 'phone_index': entry['index'],
                                    'ipa': token['ipa'], 'word': observed['word'],
                                    'interval_seconds': observed['interval'][:2], 'center': q,
                                    'start_sample': upstream['start_sample'], 'outside_phone_ms': local['outside_phone_ms'],
                                    'used_in_median': q in cfg['reference_centers'] and upstream['reason'] is None,
                                    **describe_f2_candidates(upstream, cfg)})
    for local, upstream in zip(control, fixed['control']['sources']['control'][0]['windows'], strict=True):
        windows.append({'utterance': 'control', 'source': 'control', 'phone_index': 0,
                        'center': local['center'], 'start_sample': upstream['start_sample'],
                        'outside_phone_ms': local['outside_phone_ms'], 'used_in_median': False,
                        **describe_f2_candidates(upstream, cfg)})
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    report = {'schema_version': 1, 'sample_rate_hz': rate, 'frame_samples': int(rate * cfg['frame_seconds']),
              'windows': windows}
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def measure(case, data, artifacts, execute, *, f2_candidates=False):
    cfg = case['measurement']
    centers = sorted(cfg['boundary_centers'] + cfg['reference_centers'])
    fixed, control = measure_fixed(case, data, centers, artifacts, execute)
    fixed_control = fixed['control']['sources']['control'][0]
    control_comparison = compare_windows(control, fixed_control['windows'], cfg)
    checks = {
        'upstream_matches_saved_phone_alignment': all(fixed[uid]['matching'][voice] == {
            'pairs': row['pairs'][voice], 'stressed': row['stressed'][voice]}
            for uid, row in data.items() for voice in ('upstream', 'candidate')),
        'silent_and_wave_edge_control': [r['reason'] for r in control] ==
        ['outside_wave', 'outside_wave', 'outside_wave', 'no_f1', 'no_f1']
        and fixed_control['baseline_hz'] == [None, None]
        and all(r['first_different_stage'] is None for r in control_comparison),
    }
    rows, compared, baselines = {}, [], []
    for uid, group in data.items():
        lo = {voice: filtered_wave(value['wave'], voice, cfg) for voice, value in group['source'].items()}
        order = cfg['order'][uid[0]]
        rows[uid] = []
        for offset, token in enumerate(group['tokens']):
            result = {'ipa': token['ipa'], 'indexes': {voice: token[voice] for voice in lo}}
            for voice, values in group['source'].items():
                i = token[voice]
                reference = fixed[uid]['sources'][voice][offset]
                if reference['index'] != i:
                    raise ValueError(f'固定上流の出力が登録順と一致しません ({uid}/{voice})')
                observed = token_measurement(lo[voice], values['phones'][i], order, centers, reference, cfg)
                mid = sum(observed['interval'][:2]) / 2
                observed['word'] = next((word for start, end, word in values['words'] if start <= mid < end), None)
                compared.extend({'utterance': uid, 'voice': voice, 'phone_index': i, 'center': q, **row}
                                for q, row in zip(centers, observed['window_comparison'], strict=True))
                baselines.append(observed['baseline_error_hz'])
                result[voice] = observed
            human = result['recording']['baseline_hz']
            result['synth_minus_recording_hz'] = {}
            for voice in ('upstream', 'candidate'):
                synth = result[voice]['baseline_hz']
                result['synth_minus_recording_hz'][voice] = (
                    [s - h for s, h in zip(synth, human, strict=True)] if None not in human + synth else None)
            rows[uid].append(result)
    checks['window_indices_and_poles'] = all(r['first_different_stage'] is None for r in compared)
    limit = cfg['frequency_bandwidth_agreement_hz']
    checks['fixed_token_medians'] = all(v is not None and v <= limit for v in baselines)
    comparisons = {'windows': len(compared), 'token_medians': len(baselines),
                   'max_pole_delta_hz': max((r['poles_hz'] for r in compared if r['poles_hz'] is not None), default=None),
                   'max_median_delta_hz': max((v for v in baselines if v is not None), default=None),
                   'nyquist_axis_match_count': sum(len(r['nyquist_axis_matches']) for r in compared),
                   'first_raw_pole_difference': next((r for r in compared
                                                      if r['raw_poles_hz'] is None or r['raw_poles_hz'] > limit), None),
                   'first_different_window': next((r for r in compared if r['first_different_stage'] is not None), None)}
    if f2_candidates:
        write_f2_candidates(artifacts / 'f2-candidates.json', rows, fixed, control, cfg)
    return {'checks': checks, 'scipy': scipy.__version__, 'comparison': comparisons,
            'control': {'windows': control, 'window_comparison': control_comparison},
            'window_statistics': report_windows(rows, cfg), 'tokens': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--f2-candidates', action='store_true', help='各窓の公開極とF2の採択順をJSONに保存する')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if actual != revision or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    alignment, render = (open_run(case[key], revision) for key in ('alignment', 'render'))
    data = load_inputs(case, alignment, render)
    inputs = [CASE, PROBE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/upstream_baseline.py',
              UPSTREAM / TSP_SOURCE, UPSTREAM / 'crates/chimera-cli/src/compare.rs',
              UPSTREAM / 'crates/chimera-cli/src/main.rs', UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/src/phonetics/english.rs', UPSTREAM / 'Cargo.lock']
    for root, _ in (alignment, render):
        inputs.extend(root / name for name in ('manifest.json', 'summary.json'))
    inputs.extend(values['wave'] for row in data.values() for values in row['source'].values())
    return record_measurement(args.run_id, CASE, inputs, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'alignment_run': alignment[0].name, 'render_run': render[0].name,
    }, lambda artifacts, execute: measure(case, data, artifacts, execute, f2_candidates=args.f2_candidates),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
