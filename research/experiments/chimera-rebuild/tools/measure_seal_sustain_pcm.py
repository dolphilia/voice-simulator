"""アザラシの持続音と停止を、上流PCMと独立した出力計算に照合する。"""

import argparse
import json
from math import exp
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import firwin, lfilter

from measure_songbird_sustain_pcm import waveform
from measure_songbird_syrinx import CLI, compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/seal-sustain-pcm.json'
PROBE = WORKSPACE / 'tools/upstream_seal_voice_probe.rs'
COMPONENTS = ('wall', 'oral', 'nasal', 'radiation')
RAW_FIELDS = tuple(f'{key}_{phase}' for phase in range(2) for key in COMPONENTS)
COMMON_FIELDS = ('gate', 'lung_pressure_dyn_cm2', *RAW_FIELDS)
CANDIDATE = ('frame', 'internal_sample', 'gate_target', *COMMON_FIELDS, 'decimated', 'dc_removed', 'pcm_f32')
UPPER = ('frame', 'internal_sample', *COMMON_FIELDS, 'pcm_f32')


def columns(path, frames, fields):
    header, values = shared.read_trace(path, frames, len(fields))
    if tuple(header) != fields:
        raise ValueError(f'{path.name} の観測列が一致しません')
    return dict(zip(fields, values.T, strict=True))


def internal(trace, factor):
    return {key: np.column_stack([trace[f'{key}_{phase}'] for phase in range(factor)]).ravel()
            for key in COMPONENTS}


def first_nonzero(values):
    positions = np.flatnonzero(values)
    return int(positions[0]) if positions.size else None


def gate_reference(breath, limits):
    frames, stride = breath['frames'], limits['control_frames']
    dt = stride / breath['sample_rate_hz']
    keep = {key: exp(-dt / limits[f'{key}_seconds']) for key in ('attack', 'release')}
    targets, states = np.empty(frames), np.empty(frames)
    state = target = 0.0
    changes = iter(event for event in breath['events'] if 'gate' in event)
    change = next(changes, None)
    for start in range(0, frames, stride):
        while change is not None and change['frame'] <= start:
            target = min(1.5, max(0.0, change['gate']))
            change = next(changes, None)
        state = target + (state - target) * keep['attack' if target > state else 'release']
        part = slice(start, start + stride)
        states[part], targets[part] = state, target
    return states, targets


def independent_output(raw, rate, factor, level, limits):
    if factor == 1:
        decimated = raw
    else:
        taps = limits['taps_per_phase'] * factor + 1
        fir = firwin(taps, limits['normalized_cutoff'] / factor, window=('kaiser', limits['kaiser_beta']))
        decimated = lfilter(fir, [1], raw)[factor - 1::factor]
    pole = exp(-2 * np.pi * limits['dc_cutoff_hz'] / rate)
    filtered = lfilter([1, -1], [1, -pole], decimated * (limits['gain'] * level))
    threshold = limits['limiter_threshold']
    margin = 1 - threshold
    magnitude = np.abs(filtered)
    saturating = threshold + margin * np.tanh((magnitude - threshold) / margin)
    pcm = np.where(magnitude > threshold, np.copysign(saturating, filtered), filtered).astype(np.float32)
    return decimated, filtered, pcm


def audio_observations(variant, breath, trace, pcm, raw, limits):
    name = variant['id']
    onset = {key: first_nonzero(raw[key]) for key in COMPONENTS}
    onset['pcm'] = first_nonzero(pcm)
    checks = {'nasal_remains_quiet': onset['nasal'] is None, 'bounded_pcm': bool(np.max(np.abs(pcm)) <= 1)}
    stats = {'onsets': onset}
    if name == 'silent-96000':
        checks['silent'] = all(sample is None for sample in onset.values())
        return checks, stats
    checks['wall_onset'] = onset['radiation'] == onset['wall'] == variant['wall_first_internal']
    checks['oral_onset'] = onset['oral'] == variant['oral_first_internal']
    checks['pcm_onset'] = onset['pcm'] == variant['first_pcm']
    events = [event for event in breath['events'] if 'gate' in event]
    stride = limits['control_frames']
    boundaries = [((event['frame'] + stride - 1) // stride) * stride for event in events]
    observed = np.flatnonzero(np.diff(trace['gate_target'], prepend=0.0))
    checks['gate_boundaries'] = observed.tolist() == boundaries
    stop = boundaries[-1]
    rate = breath['sample_rate_hz']
    low, high = (stop - round(rate * seconds) for seconds in limits['steady_window_before_release_seconds'])
    tail = pcm[-round(rate * limits['tail_window_seconds']):]
    steady_rms = float(np.sqrt(np.mean(pcm[low:high].astype(float)**2)))
    tail_rms = float(np.sqrt(np.mean(tail.astype(float)**2)))
    tail_ratio = tail_rms / max(steady_rms, np.finfo(float).tiny)
    limited = int(np.count_nonzero(np.abs(trace['dc_removed']) > limits['limiter_threshold']))
    stats.update({'gate_control_frames': boundaries, 'steady_rms': steady_rms, 'tail_rms': tail_rms,
                  'tail_to_steady_ratio': tail_ratio, 'limited_frames': limited,
                  'peak_pcm': float(np.max(np.abs(pcm))),
                  'peak_before_limit': float(np.max(np.abs(trace['dc_removed'])))})
    checks['steady_rms'] = steady_rms >= limits['minimum_steady_rms']
    checks['tail_decay'] = tail_ratio <= limits['maximum_tail_to_steady_rms_ratio']
    if name == 'loud':
        checks['limiter_engages'] = limited >= limits['minimum_limited_frames_loud']
    return checks, stats


def capture(variant, source, folder, execute, probe, limits, official):
    folder.mkdir()
    case, settings, upper = (folder / name for name in ('case.json', 'inspect.json', 'upstream.csv'))
    case.write_text(json.dumps({'seal_voice': source}, indent=2) + '\n')
    execute([*CLI, 'inspect', str(case)], stdout=settings)
    execute([str(probe), str(case)], cwd=UPSTREAM, stdout=upper)
    variants = []
    for block in limits['host_block_frames']:
        wave, trace = folder / f'pcm-{block}.wav', folder / f'pcm-{block}.csv'
        execute([*CLI, 'render-pcm', str(case), str(wave), str(trace), str(block)])
        variants.append((wave, trace))
    wave, trace = variants[0]
    breath = source['breath']
    rate, frames = breath['sample_rate_hz'], breath['frames']
    pcm = waveform(wave, breath)
    candidate, upstream = columns(trace, frames, CANDIDATE), columns(upper, frames, UPPER)
    factor = 2 if rate <= 60000 else 1
    info = read(settings)
    taps = 1 if factor == 1 else factor * limits['taps_per_phase'] + 1
    checks = {
        'layout': (info['decimation_factor'], info['internal_rate_hz'], info['control_frames'], info['filter_taps'])
        == (factor, rate * factor, limits['control_frames'], taps),
        'wav_size': len(pcm) == frames,
        'wav_matches_csv': np.array_equal(pcm.view('u4'), candidate['pcm_f32'].astype(np.float32).view('u4')),
        'block_invariant': all(sha256(other_wav) == sha256(wave) and sha256(other_csv) == sha256(trace)
                               for other_wav, other_csv in variants),
    }
    expected_index = (np.arange(frames) + 1) * factor - 1
    gate, gate_target = gate_reference(breath, limits)
    gate_tolerance = limits['gate_absolute_tolerance']
    pressure_tolerance = limits['pressure_absolute_tolerance_dyn_cm2']
    component_tolerance = limits['component_absolute_tolerance_cm3_s']
    raw_tolerance = limits['radiation_absolute_tolerance_cm3_s2']
    pcm_tolerance = limits['pcm_absolute_tolerance']
    dc_tolerance = limits['dc_absolute_tolerance']
    upper_pcm = upstream['pcm_f32'].astype(np.float32)
    comparisons = {'gate': compare(candidate['gate'], upstream['gate'], gate_tolerance),
                   'lung_pressure': compare(candidate['lung_pressure_dyn_cm2'], upstream['lung_pressure_dyn_cm2'],
                                            pressure_tolerance),
                   'pcm': compare(pcm, upper_pcm, pcm_tolerance)}
    results = {}
    for label, trace, samples in (('candidate', candidate, pcm), ('upstream', upstream, upper_pcm)):
        checks[f'{label}.sample_index'] = np.array_equal(trace['internal_sample'], expected_index)
        checks[f'{label}.unused_slots_zero'] = factor == 2 or all(np.all(trace[f'{key}_1'] == 0) for key in COMPONENTS)
        raw = internal(trace, factor)
        combined = raw['wall'] + raw['oral'] + raw['nasal']
        decimated, dc_filtered, expected_pcm = independent_output(raw['radiation'], rate, factor, source['level'], limits)
        independence = {
            'gate': compare(trace['gate'], gate, gate_tolerance),
            'components_recombine': compare(raw['radiation'], np.diff(combined, prepend=0.0) * rate * factor, raw_tolerance),
            'independent_pcm': compare(samples, expected_pcm, pcm_tolerance),
        }
        if label == 'candidate':
            independence.update({'decimated': compare(trace['decimated'], decimated, raw_tolerance),
                                 'dc_removed': compare(trace['dc_removed'], dc_filtered, dc_tolerance),
                                 'gate_target': compare(trace['gate_target'], gate_target, gate_tolerance)})
        checks.update({f'{label}.{key}': diff['passed'] for key, diff in independence.items()})
        results[label] = {'independent': independence, 'raw': raw, 'output': (decimated, dc_filtered)}
    comparisons.update({
        key: compare(results['candidate']['raw'][key], results['upstream']['raw'][key],
                     raw_tolerance if key == 'radiation' else component_tolerance)
        for key in COMPONENTS
    })
    upper_decimated, upper_dc = results['upstream']['output']
    comparisons.update({'decimated': compare(candidate['decimated'], upper_decimated, raw_tolerance),
                        'dc_removed': compare(candidate['dc_removed'], upper_dc, dc_tolerance)})
    if variant['id'] == 'official-prefix-48000':
        prefix = waveform(official, breath)[:frames]
        checks['probe_agrees_with_official_cli'] = np.array_equal(prefix.view('u4'), upper_pcm.view('u4'))
        comparisons['official_cli'] = compare(pcm, prefix, pcm_tolerance)
    checks.update({f'upstream.{key}': diff['passed'] for key, diff in comparisons.items()})
    wave_checks, observations = audio_observations(variant, breath, candidate, pcm, results['candidate']['raw'], limits)
    checks.update(wave_checks)
    pcm_difference = pcm.view('u4') != upper_pcm.view('u4')
    return {'checks': checks, 'frames': frames, 'internal_rate_hz': rate * factor, 'factor': factor,
            'observations': observations, 'upstream_comparison': comparisons,
            'candidate_pcm_different_bits': int(np.count_nonzero(pcm_difference)),
            'first_pcm_different_bits': first_nonzero(pcm_difference),
            'independent_comparison': {key: value['independent'] for key, value in results.items()}}


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    dest = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'seal', str(dest), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    base, limits = config['seal_voice'], config['measurement']
    checks, variants = {}, {}
    for variant in limits['variants']:
        name = variant['id']
        source = base | {'breath': base['breath'] | variant['breath'],
                         'level': variant.get('level', base['level'])}
        result = capture(variant, source, artifacts / name, execute, probe, limits, dest / 'seal.wav')
        variants[name] = result
        checks.update({f'{name}.{key}': passed for key, passed in result['checks'].items()})
    return {'checks': checks, 'limits': {key: value for key, value in limits.items() if key != 'variants'},
            'variants': variants}


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
    baseline = WORKSPACE / 'runs/seal-airway-before-pcm-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('アザラシの気道の基準ケースが不合格です')
    references = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/creatures/seal.rs',
                  'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera/src/airway/decimator.rs', 'crates/chimera-cli/src/render.rs',
                  'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {file: sha256(UPSTREAM / file) for file in references}}
    inputs = [CASE, PROBE, baseline, Path(__file__).resolve(), Path(shared.__file__),
              *(WORKSPACE / 'tools' / file for file in ('upstream_baseline.py', 'measure_songbird_syrinx.py',
                                                       'measure_songbird_sustain_pcm.py')),
              WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
