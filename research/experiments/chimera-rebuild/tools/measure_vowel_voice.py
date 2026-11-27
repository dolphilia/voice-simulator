"""較正した固定母音を発声し、上流のPCMと独立のF0・LPC計測に照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.linalg import solve_toeplitz
from scipy.signal import correlate, lfilter, resample_poly

import measure_pcm_output as pcm
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


PROBE = WORKSPACE / 'tools/upstream_vowel_voice_probe.rs'
TABLE = UPSTREAM / 'crates/chimera/src/phonetics/vowelTargets.generated.json'
CASES = tuple(p.stem for p in sorted((WORKSPACE / 'cases').glob('vowel-voice-*.json')))
TRACE = ('frame', 'internal_sample', 'gate', 'lung_boundary_dyn_cm2', 'pressure_sub_dyn_cm2',
         'pressure_supra_dyn_cm2', 'glottal_area_cm2', 'glottal_flow_cm3_s', 'glottal_phase',
         'glottal_voicing', 'glottal_f0_hz', 'lip_flow_cm3_s', 'nose_flow_cm3_s', 'radiation_derivative_cm3_s2')


def independent_yin(wave, rate, cfg):
    low = max(2, int(rate / cfg['pitch_max_hz']))
    high = min(len(wave)//2, int(rate / cfg['pitch_min_hz']))
    width = len(wave) - high
    base = wave[:width]
    distances = np.array([np.sum((base-wave[lag:lag+width])**2) for lag in range(1, high+1)])
    cumulative = np.cumsum(distances)
    normalized = np.ones(high+1)
    np.divide(distances*np.arange(1, high+1), cumulative, out=normalized[1:], where=cumulative>0)
    found = np.flatnonzero(normalized[low:] < cfg['yin_threshold'])
    if not len(found):
        return None, float(normalized[low:].min())
    i = int(found[0]+low)
    while i < high and normalized[i+1] < normalized[i]:
        i += 1
    lag = float(i)
    if 1 < i < high:
        a,b,c = normalized[i-1:i+2]
        curvature = a-2*b+c
        if abs(curvature) > 1e-12:
            lag += (a-c)/(2*curvature)
    return float(rate/lag), float(normalized[i])


def independent_lpc(wave, cfg):
    if not np.any(wave):
        return np.empty((0,2))
    order = cfg['lpc_order']
    rate = cfg['lpc_sample_rate_hz']
    emphasized = np.r_[wave[0], wave[1:]-cfg['pre_emphasis']*wave[:-1]] * np.hamming(len(wave))
    start = len(emphasized)-1
    correlation = correlate(emphasized, emphasized, method='direct')[start:start+order+1]
    correlation *= np.exp(-0.5*(2*np.pi*40*np.arange(order+1)/rate)**2)
    correlation[0] = correlation[0]*(1+1e-9)+1e-30
    coefficients = solve_toeplitz(correlation[:-1], -correlation[1:])
    roots = np.roots(np.r_[1, coefficients])
    roots = roots[roots.imag > 0]
    frequency = np.angle(roots)*rate/(2*np.pi)
    bandwidth = -np.log(abs(roots))*rate/np.pi
    keep = (frequency >= cfg['lpc_min_hz']) & (bandwidth <= cfg['lpc_max_bandwidth_hz'])
    return np.column_stack((frequency[keep], bandwidth[keep]))[np.argsort(frequency[keep])]


def cycle_f0(phase, rate):
    i = np.flatnonzero(np.diff(phase)<0)
    crossings = i + (1-phase[i])/(1+phase[i+1]-phase[i])
    return float(rate*(len(crossings)-1)/(crossings[-1]-crossings[0])) if len(crossings)>1 else None


def analyze(case, window, reference_window, phase, probe, artifacts, execute):
    cfg = case['measurement']['voice']
    rate = case['voice']['output_sample_rate_hz']
    lpc_rate = cfg['lpc_sample_rate_hz']
    lpc_window = resample_poly(window, lpc_rate, rate)
    raw, raw_lpc = (artifacts / name for name in ('upstream-window.f64', 'upstream-lpc-window.f64'))
    reference_window.astype('<f8').tofile(raw)
    resample_poly(reference_window, lpc_rate, rate).astype('<f8').tofile(raw_lpc)
    table = artifacts / 'upstream-analysis.csv'
    roots_path = artifacts / 'upstream-lpc-roots.csv'
    args = [raw, rate, cfg['pitch_min_hz'], cfg['pitch_max_hz'], cfg['yin_threshold'], raw_lpc,
            lpc_rate, cfg['lpc_order'], cfg['pre_emphasis'], cfg['lpc_min_hz'], cfg['lpc_max_bandwidth_hz'],
            table, roots_path]
    execute([str(probe), 'analyze', *map(str,args)], cwd=UPSTREAM)
    with table.open(newline='') as stream:
        reader = csv.DictReader(stream)
        pitch_row = next(reader)
        upper_f0 = float(pitch_row['frequency_hz']) if pitch_row['frequency_hz'] else None
        upper_aperiodicity = float(pitch_row['aperiodicity_or_bandwidth_hz'])
        upper_raw_lpc = np.array([[float(row['frequency_hz']), float(row['aperiodicity_or_bandwidth_hz'])]
                                  for row in reader], dtype=float).reshape(-1, 2)

    f0, aperiodicity = independent_yin(window, rate, cfg)
    lpc = independent_lpc(lpc_window, cfg)
    # ナイキスト境界の実根は、数値解の微小な虚部で正の半平面へ入ることがある。
    limit = lpc_rate / 2 - cfg['lpc_nyquist_guard_hz']
    upper_lpc = upper_raw_lpc[upper_raw_lpc[:, 0] < limit]
    excluded = upper_raw_lpc[upper_raw_lpc[:, 0] >= limit]
    lpc = lpc[lpc[:, 0] < limit]
    with roots_path.open(newline='') as stream:
        roots = [complex(float(row['real']), float(row['imaginary'])) for row in csv.DictReader(stream)]
    boundary_roots = [root for root in roots if root.real < 0.0 and root.imag > 0.0
                      and np.angle(root) * lpc_rate / (2 * np.pi) >= limit]
    # 上流の推定器は根を周波数だけでなく帯域幅でも選別してからピークとして返す。
    boundary_bandwidths = [-np.log(abs(root)) * lpc_rate / np.pi for root in boundary_roots]
    kept_boundary_count = sum(width <= cfg['lpc_max_bandwidth_hz'] for width in boundary_bandwidths)
    cycles = cycle_f0(phase, rate)
    expected_f0 = cfg['f0_interval_hz']
    f0_error = abs(f0-upper_f0) if f0 is not None and upper_f0 is not None else None
    formant_errors = abs(lpc-upper_lpc).max(axis=0).tolist() if lpc.shape==upper_lpc.shape and len(lpc) else None
    intervals = cfg['formant_intervals_hz']
    pitch_matches = f0 is None and upper_f0 is None if f0_error is None else f0_error < cfg['upstream_f0_error_lt_hz']
    cycle_tolerance = cfg['independent_cycle_f0_error_lt_hz']
    checks = {
        'registered_pitch': f0 is None if expected_f0 is None else f0 is not None and expected_f0[0] <= f0 <= expected_f0[1],
        'upstream_pitch': pitch_matches and abs(aperiodicity - upper_aperiodicity) < 1e-6,
        'independent_glottal_cycle_rate': (
            cycles is not None and abs(cycles - case['voice']['f0_hz']) < cycle_tolerance
            and (f0 is None or abs(cycles - f0) < cycle_tolerance)),
        'registered_first_formants': (not len(lpc) if not intervals else len(lpc)>=len(intervals) and all(
            lo<=f<=hi for f,(lo,hi) in zip(lpc[:len(intervals),0],intervals,strict=True))),
        'registered_nyquist_only_roots': len(excluded) == kept_boundary_count == cfg['upstream_nyquist_only_count'],
        'upstream_lpc_frequencies_and_bandwidths': (len(lpc)==len(upper_lpc)==0 if formant_errors is None
                                                  else max(formant_errors)<cfg['upstream_formant_error_lt_hz']),
    }
    diagnostics = {
        'pcm_f0_hz': f0, 'upstream_pcm_f0_hz': upper_f0, 'glottal_cycle_rate_hz': cycles,
        'aperiodicity': aperiodicity, 'upstream_aperiodicity': upper_aperiodicity, 'f0_error_hz': f0_error,
        'lpc_formants_frequency_bandwidth_hz': lpc.tolist(),
        'upstream_lpc_formants_frequency_bandwidth_hz': upper_lpc.tolist(),
        'upstream_excluded_nyquist_frequency_bandwidth_hz': excluded.tolist(),
        'upstream_nyquist_roots_real_imaginary': [[root.real, root.imag] for root in boundary_roots],
        'upstream_max_lpc_frequency_and_bandwidth_errors_hz': formant_errors,
    }
    if kept_boundary_count < len(boundary_roots):
        diagnostics['nyquist_roots_rejected_by_bandwidth_hz'] = [
            float(width) for width in boundary_bandwidths if width > cfg['lpc_max_bandwidth_hz']
        ]
    return checks, diagnostics


def measure(case, case_path, linear, artifacts, execute):
    voice, cfg = case['voice'], case['measurement']['voice']
    rate, internal = voice['output_sample_rate_hz'], case['fixed_airway']['sample_rate_hz']
    settings = json.loads((artifacts / 'settings.json').read_text())['voice']
    frames, factor = settings['frames'], settings['decimation_factor']
    first, length = cfg['start_frame'], cfg['frame_count']
    if first<0 or length<2 or first+length>frames or voice['f0_hz']!=110:
        raise ValueError('固定上流比較には有効な計測窓と110 Hzが必要です')
    window = slice(first, first+length)

    for test, name in [('engine','output_does_not_depend_on_the_host_block_size'),
                       ('golden_analysis','analysis_matches_typescript')]:
        execute(['cargo','test','--locked','-p','chimera','--test',test,name,'--','--nocapture'],
                cwd=UPSTREAM, stdout=artifacts/f'upstream-{test}.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    args = [cfg['ipa'],internal,rate,frames,*(voice[key] for key in
            ('pressure_cm_h2o','gate','breathiness','tension','output_gain')),artifacts]
    execute([str(probe),'render',*map(str,args)], cwd=UPSTREAM)

    reference = np.fromfile(artifacts/'upstream-voice.f32',dtype='<f4')
    wavfile.write(artifacts/'upstream-voice.wav', rate, reference)
    blocks = pcm.render_blocks(case_path, {'block_frames':cfg['host_block_sizes']},artifacts,execute)
    paths = next(iter(blocks.values()))
    observed_rate, output = wavfile.read(paths[0])
    if output.dtype != np.float32 or output.shape != (frames,) or reference.shape != output.shape:
        raise ValueError('候補または上流のPCMサンプル型・フレーム数が不正です')
    if not np.isfinite(output).all() or not np.isfinite(reference).all():
        raise ValueError('候補または上流のPCMに非有限値があります')
    out_keys, out_trace = pcm.read_columns(paths[1], frames, len(pcm.OUTPUT_COLUMNS))
    if out_keys != pcm.OUTPUT_COLUMNS:
        raise ValueError('PCM出力段の観測列が不正です')

    tracks = []
    for path in (artifacts/'trace.csv',artifacts/'upstream-trace.csv'):
        keys, track = pcm.read_columns(path,frames,len(TRACE))
        if tuple(keys)!=TRACE or not np.array_equal(track['internal_sample'],factor*np.arange(1,frames+1)-1):
            raise ValueError(f'{path.name} の観測列または内部サンプルが不正です')
        tracks.append(track)
    actual,upper = tracks
    components = {key:shared.compare_series(actual[key],upper[key],cfg['upstream_component_peak_relative_error_lt'])
                  for key in TRACE[2:]}
    wave_error = abs(output-reference)
    onset = np.flatnonzero(abs(output)>cfg['onset_amplitude_threshold'])
    onset_frame = int(onset[0]) if onset.size else None
    rms = float(np.sqrt(np.mean(output[window].astype(float)**2)))
    lo, hi = cfg['rms_interval']
    gain = voice['output_gain']
    dc = lfilter([gain,-gain],[1,-np.exp(-2*np.pi*25/rate)],out_trace['decimated'])
    _, _, independent_pcm = pcm.independent_limiter(dc, rate)
    active = voice['gate']>0
    checks = {
        'registered_rates_and_frames': rate==observed_rate and frames*factor==case['fixed_airway']['sample_count'],
        'native_upstream_pcm': float(wave_error.max())<cfg['upstream_pcm_max_error_lt'],
        'upstream_internal_components': all(result['status'] for result in components.values()),
        'registered_onset': onset_frame==cfg['onset_frame'],
        'registered_steady_rms': lo<=rms<=hi,
        'bounded_pcm': float(abs(output).max())<=cfg['max_pcm_peak'],
        'registered_voicing_or_complete_silence': (
            float(actual['glottal_voicing'][window].min())>=cfg['steady_voicing_min'] if active
            else not np.any(output) and all(not np.any(actual[key]) for key in
                  ('lung_boundary_dyn_cm2','glottal_voicing','glottal_flow_cm3_s','radiation_derivative_cm3_s2'))),
        'pcm_trace_matches_wave': np.array_equal(out_trace['pcm_f32'].astype(np.float32),output),
        'host_block_invariance': all(sha256(paths[0])==sha256(wav) and sha256(paths[1])==sha256(csv_path)
                                     for wav,csv_path in blocks.values()),
        'independent_output_after_decimation': float(abs(independent_pcm-output).max())<cfg['upstream_pcm_max_error_lt'],
    }
    acoustic_checks, acoustic = analyze(
        case, output[window].astype(float), reference[window].astype(float), actual['glottal_phase'][window],
        probe, artifacts, execute)
    checks.update(acoustic_checks)
    acoustic['fixed_linear_peaks_hz'] = linear['peaks']['peaks_hz'][:3]
    lpc = acoustic['lpc_formants_frequency_bandwidth_hz']
    acoustic['first_three_lpc_minus_linear_hz'] = [row[0]-peak for row,peak in zip(lpc[:3],acoustic['fixed_linear_peaks_hz'])] if len(lpc)>=3 else None
    failed = np.flatnonzero(wave_error>=cfg['upstream_pcm_max_error_lt'])
    return {'checks':{k:bool(v) for k,v in checks.items()}, 'pcm_peak':float(abs(output).max()),
            'steady_rms':rms,'onset_frame':onset_frame,'maximum_pcm_absolute_error':float(wave_error.max()),
            'pcm_sample_bytes_equal': output.astype('<f4').tobytes() == reference.tobytes(),
            'first_pcm_frame_over_tolerance':int(failed[0]) if failed.size else None,
            'components':components,'acoustic':acoustic}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case',choices=CASES)
    parser.add_argument('--linear-run', help='同じ姿勢で実行した線形伝達関数の実行ID')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*',args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    path = WORKSPACE/'cases'/f'{args.case}.json'
    case = json.loads(path.read_text())
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise ValueError('変更のない固定上流版が必要です')
    cfg = case['measurement']['voice']
    linear_run = args.linear_run or cfg['linear_reference_run']
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', linear_run):
        parser.error('線形伝達関数の実行IDが不正です')
    run = WORKSPACE/'runs'/linear_run
    manifest_path, linear_path = run/'manifest.json',run/'summary.json'
    manifest = json.loads(manifest_path.read_text())
    archived_case_name = f"cases/{manifest['case_id']}.json"
    archived = run / manifest['source_snapshot'] / archived_case_name
    reference_case = json.loads(archived.read_text())
    linear = json.loads(linear_path.read_text())
    if (manifest['status']!='pass' or manifest['upstream_revision']!=revision
            or case['posture']!=reference_case['posture']
            or cfg['ipa']!=reference_case['measurement']['transfer']['ipa'] or not all(linear['checks'].values())
            or not any(x['path']==archived_case_name and x['sha256']==sha256(archived) for x in manifest['inputs'])
            or not any(x['path']=='summary.json' and x['sha256']==sha256(linear_path) for x in manifest['outputs'])):
        raise ValueError('同じ固定姿勢で検証済みの線形伝達関数が必要です')
    sources = [path,PROBE,Path(__file__).resolve(),Path(pcm.__file__),Path(shared.__file__),
               WORKSPACE/'tools/upstream_baseline.py', WORKSPACE/'tools/measure_junction.py',
               manifest_path,linear_path,archived,*shared.candidate_sources()]
    details = {'upstream_revision':revision,'case_id':case['id'],
               'upstream_vowel_table_sha256':sha256(TABLE),'scipy':scipy.__version__}
    return shared.record_measurement(args.run_id,path,sources,details,
        lambda artifacts, execute: measure(case,path,linear,artifacts,execute))


if __name__=='__main__':
    raise SystemExit(main())
