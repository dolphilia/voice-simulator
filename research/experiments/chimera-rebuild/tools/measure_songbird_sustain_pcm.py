"""鳴禽の持続音と停止を、公開レンダーと独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import firwin, lfilter

from measure_songbird_syrinx import CLI, compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-sustain-pcm.json'
PROBE = WORKSPACE / 'tools/upstream_songbird_voice_probe.rs'
PARAMS = ('pitch_hz', 'interval_semitones', 'voices', 'drive', 'tension',
          'pressure_kpa', 'purity', 'oec_cm3', 'gape')
FIELDS = ('frame', 'internal_sample', 'gate', *PARAMS, 'sac_pressure_dyn_cm2',
          'left_opening', 'right_opening', *(f'radiation_{i}' for i in range(4)),
          'decimated', 'dc_removed', 'pcm_f32')


def control_reference(case, m):
    frames = case['frames']
    dt = m['control_frames'] / case['sample_rate_hz']
    times = m['parameter_time_constants_seconds']
    log = set(m['logarithmic_parameters'])
    target = case['controls'].copy()
    state = target.copy()
    expected = {key: np.empty(frames) for key in ('gate', *PARAMS, 'sac_pressure_dyn_cm2')}
    gate, goal = 0.0, 0.0
    events = iter(case['events'])
    event = next(events, None)
    for start in range(0, frames, m['control_frames']):
        while event is not None and event['frame'] <= start:
            target.update(event.get('controls', {}))
            goal = event.get('gate', goal)
            event = next(events, None)
        take = slice(start, start + m['control_frames'])
        tau = m['attack_seconds'] if goal > gate else m['release_seconds']
        gate = goal + (gate - goal) * np.exp(-dt / tau)
        expected['gate'][take] = gate
        for key in PARAMS:
            goal_value = target[key]
            retention = np.exp(-dt / times[key])
            old = state[key]
            if key in log:
                state[key] = np.exp(np.log(goal_value) + (np.log(old) - np.log(goal_value)) * retention)
            else:
                state[key] = goal_value + (old - goal_value) * retention
            expected[key][take] = state[key]
        expected['sac_pressure_dyn_cm2'][take] = state['pressure_kpa'] * gate * 1e4
    return expected


def columns(path, frames):
    header, values = shared.read_trace(path, frames, len(FIELDS))
    if tuple(header) != FIELDS:
        raise ValueError('観測列が一致しません')
    return dict(zip(header, values.T, strict=True))


def waveform(path, case):
    rate, pcm = wavfile.read(path)
    if rate != case['sample_rate_hz'] or pcm.dtype != np.dtype('<f4') or pcm.ndim != 1 or not np.isfinite(pcm).all():
        raise ValueError(f'{path.name} は指定レートの有限なモノラルf32ではありません')
    return pcm


def internal(trace, factor):
    return np.column_stack([trace[f'radiation_{index}'] for index in range(factor)]).ravel()


def independent_output(raw, case, factor, m):
    fir = firwin(24 * factor + 1, 0.92 / factor, window=('kaiser', 8.5))
    decimated = lfilter(fir, [1], raw)[factor - 1::factor]
    input_ = decimated * (m['nominal_gain'] * case['level'])
    pole = np.exp(-2 * np.pi * m['dc_cutoff_hz'] / case['sample_rate_hz'])
    filtered = lfilter([1, -1], [1, -pole], input_)
    threshold = m['limiter_threshold']
    margin = 1 - threshold
    magnitude = np.abs(filtered)
    clipped = np.sign(filtered) * (threshold + margin * np.tanh((magnitude - threshold) / margin))
    bounded = np.where(magnitude > threshold, clipped, filtered)
    return {'decimated': decimated, 'dc_removed': filtered, 'pcm_f32': bounded.astype(np.float32)}


def fir_tolerance(values, m):
    return np.max(np.abs(values)) * m['fir_peak_relative_tolerance'] + m['fir_absolute_floor']


def evaluate_wave(pcm, trace, case, m):
    rate = case['sample_rate_hz']
    onset, = [event['frame'] for event in case['events'] if event.get('gate') == 1.0]
    stop, = [event['frame'] for event in case['events'] if event.get('gate') == 0.0]
    block = m['control_frames']
    begins, release = (((frame + block - 1) // block) * block for frame in (onset, stop))
    lo, hi = [release - round(rate * dt) for dt in m['steady_window_before_release_seconds']]
    tail = pcm[-round(rate * m['tail_window_seconds']):].astype(float)
    rms = lambda values: float(np.sqrt(np.mean(values.astype(float)**2)))
    steady_rms = rms(pcm[lo:hi])
    reported = {
        'onset_command_frame': onset,
        'onset_control_frame': begins,
        'gate_after_onset': float(trace['gate'][begins]),
        'first_nonzero_pcm_frame': int(np.flatnonzero(pcm != 0)[0]) if np.any(pcm != 0) else None,
        'release_command_frame': stop,
        'release_control_frame': release,
        'gate_before_release': float(trace['gate'][release - 1]),
        'gate_after_release': float(trace['gate'][release]),
        'steady_rms': steady_rms,
        'tail_rms': rms(tail),
        'tail_to_steady_rms_ratio': rms(tail) / max(steady_rms, np.finfo(float).tiny),
        'peak_pcm': float(np.max(np.abs(pcm))),
        'peak_dc_removed': float(np.max(np.abs(trace['dc_removed']))),
        'limited_frames': int(np.count_nonzero(np.abs(trace['dc_removed']) > m['limiter_threshold'])),
    }
    checks = {
        'silent_before_gate': bool(np.all(pcm[:begins] == 0)),
        'gate_updates_on_absolute_boundaries': bool(np.all(trace['gate'][:begins] == 0)
            and trace['gate'][begins] > 0 and trace['gate'][release] < trace['gate'][release - 1]),
        'steady_rms': steady_rms >= m['minimum_steady_rms'],
        'tail_rms': reported['tail_to_steady_rms_ratio'] <= m['maximum_tail_to_steady_rms_ratio'],
        'bounded': reported['peak_pcm'] <= 1.0,
    }
    return reported, checks


def capture(case, out, execute, probe, m, official):
    out.mkdir()
    case_path = out / 'case.json'
    case_path.write_text(json.dumps({'songbird_voice': case}, ensure_ascii=False, indent=2) + '\n')
    settings, upstream_csv = (out / name for name in ('settings.json', 'upstream.csv'))
    execute([*CLI, 'inspect', str(case_path)], stdout=settings)
    execute([str(probe), str(case_path)], cwd=UPSTREAM, stdout=upstream_csv)
    products = {}
    for block in m['host_block_frames']:
        paths = out / f'pcm-{block}.wav', out / f'pcm-{block}.csv'
        execute([*CLI, 'render-pcm', str(case_path), *map(str, paths), str(block)])
        products[block] = paths
    wave, trace = products[m['host_block_frames'][0]]
    pcm = waveform(wave, case)
    frames, rate = case['frames'], case['sample_rate_hz']
    candidate, upstream = (columns(path, frames) for path in (trace, upstream_csv))
    factor = 2 if rate > 60000 else 4
    info = read(settings)
    checks = {
        'layout': (info['decimation_factor'], info['internal_rate_hz'], info['control_frames'], info['filter_taps'])
                  == (factor, factor * rate, m['control_frames'], 24 * factor + 1),
        'frame_count': len(pcm) == frames,
        'wave_matches_csv': np.array_equal(pcm.view('u4'), candidate['pcm_f32'].astype(np.float32).view('u4')),
        'host_blocks': all(sha256(other_wave) == sha256(wave) and sha256(other_trace) == sha256(trace)
                           for other_wave, other_trace in products.values()),
    }
    for label, data in (('candidate', candidate), ('upstream', upstream)):
        checks[f'{label}.internal_index'] = np.array_equal(data['internal_sample'], factor * (np.arange(frames) + 1) - 1)
        checks[f'{label}.unused_phases'] = all(np.all(data[f'radiation_{i}'] == 0) for i in range(factor, 4))
    raw, upper_raw = (internal(data, factor) for data in (candidate, upstream))
    checks['pcm_finite'] = bool(np.isfinite(pcm).all())
    agreement = {
        'radiation_internal_samples': compare(raw, upper_raw, np.max(np.abs(upper_raw)) *
            m['acoustic_peak_relative_tolerance'] + m['acoustic_absolute_floor']),
        'decimated': compare(candidate['decimated'], upstream['decimated'], fir_tolerance(upstream['decimated'], m)),
        'dc_removed': compare(candidate['dc_removed'], upstream['dc_removed'], m['dc_absolute_tolerance']),
        'pcm_f32': compare(pcm, upstream['pcm_f32'].astype(np.float32), m['pcm_absolute_tolerance']),
    }
    for field in ('gate', *PARAMS, 'sac_pressure_dyn_cm2', 'left_opening', 'right_opening'):
        agreement[field] = compare(candidate[field], upstream[field], m['control_absolute_tolerance'])
    checks.update({f'upstream.{key}': value['passed'] for key, value in agreement.items()})
    ctrl = control_reference(case, m)
    independent = {}
    for label, observed, signal in (('candidate', candidate, raw), ('upstream', upstream, upper_raw)):
        ideal = independent_output(signal, case, factor, m)
        independent[label] = {
            'decimated': compare(observed['decimated'], ideal['decimated'], fir_tolerance(ideal['decimated'], m)),
            'dc_removed': compare(observed['dc_removed'], ideal['dc_removed'], m['dc_absolute_tolerance']),
            'pcm_f32': compare(observed['pcm_f32'].astype(np.float32), ideal['pcm_f32'], m['pcm_absolute_tolerance']),
            **{key: compare(observed[key], expected, m['control_absolute_tolerance']) for key, expected in ctrl.items()},
        }
        checks.update({f'independent.{label}.{key}': value['passed'] for key, value in independent[label].items()})
    events, event_checks = evaluate_wave(pcm, candidate, case, m)
    checks.update(event_checks)
    if case['level'] > 1:
        checks['limiter_applied'] = events['limited_frames'] >= m['minimum_limited_frames_loud']
    if official is not None:
        samples = waveform(official, case)[:frames]
        if len(samples) != frames:
            raise ValueError('固定上流のCLIに指定された持続区間がありません')
        agreement['official_cli_prefix'] = compare(pcm, samples, m['pcm_absolute_tolerance'])
        checks['upstream.official_cli_prefix'] = agreement['official_cli_prefix']['passed']
        checks['probe_matches_official_cli_prefix'] = np.array_equal(
            samples.view('u4'), upstream['pcm_f32'].astype(np.float32).view('u4'))
    return checks, {'samples': frames, 'rate_hz': rate, 'factor': factor, 'agreement': agreement,
                    'independent': independent, 'events': events}


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    target = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render',
             'creature', 'songbird', str(target), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, results = {}, {}
    for entry in config['measurement']['variants']:
        name = entry['id']
        case = config['songbird_voice'] | entry['overrides']
        official = target / 'songbird.wav' if name == 'upper-cli-prefix' else None
        flags, results[name] = capture(case, artifacts / name, execute, probe, config['measurement'], official)
        checks.update({f'{name}.{key}': value for key, value in flags.items()})
    return {'checks': checks, 'variants': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    references = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/creatures/voice.rs',
                  'crates/chimera/src/creatures/songbird.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera/src/airway/decimator.rs', 'crates/chimera/tests/golden_creatures.rs',
                  'crates/chimera/tests/creature_realtime.rs')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in references}}
    inputs = [CASE, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              WORKSPACE / 'tools/measure_songbird_syrinx.py', WORKSPACE / 'tools/upstream_baseline.py',
              *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
