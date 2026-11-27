"""ゾウの trumpet の指数補間、所有値の復帰、弁と公式PCMを照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_elephant_fixed_voice as fixed
from measure_elephant_rumble import reference_controls
from measure_elephant_valve import compare_state
from measure_songbird_syrinx import compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/elephant-trumpet.json'
FREE = ('pitch_hz', 'trunk')
OWNED = ('mode', 'lip_pitch_hz', 'pressure_cm_h2o', 'chaos')


def replacement_checks(trace, case, variant):
    events = {e['frame']: e for e in case['events']}
    replace, = [n for n, e in events.items() if e.get('play_call', {}).get('id') == 'trumpet']
    old, edit = [e for e in events.values() if 'params' in e]
    stopped = variant['end_frame']
    checks = {
        'replaces_rumble': trace['call_id'][replace - 1] == 1 and trace['call_id'][replace] == 2,
        'rumble_targets_return_at_replacement': all(trace['target_' + k][replace] == old['params'][k]
                                                   for k in FREE),
        'free_targets_update_at_request': all(trace['target_' + k][edit['frame']] == edit['params'][k]
                                               for k in FREE),
        'owned_targets_wait': all(trace['target_' + k][edit['frame']] == trace['target_' + k][edit['frame'] - 1]
                                  and trace['target_' + k][edit['frame']] != edit['params'][k] for k in OWNED),
        'targets_return_at_stop': all(trace['target_' + k][stopped] == value for k, value in edit['params'].items()),
        'smoothed_values_wait_after_stop': all(trace[k][stopped] == trace[k][stopped - 1] for k in (*OWNED, *FREE)),
    }
    return {name: bool(passed) for name, passed in checks.items()}


def observe(trace, case, variant, spec):
    launch, = [e for e in case['events'] if e.get('play_call', {}).get('id') == 'trumpet']
    request, start = launch['frame'], variant['first_control']
    end = variant['end_frame']
    stop = case['frames'] if end is None else end
    act = np.flatnonzero(trace['call_id'] == 2)
    tol = spec['tolerances']['control']
    gate_limit = launch['play_call'].get('amplitude', 1.0)
    checks = {
        'ownership_period': np.array_equal(act, np.arange(request, stop)),
        'first_control_takes_call_targets': all(
            abs(trace['target_' + name][start] - spec['trumpet_keys'][name][0][1]) <= tol for name in OWNED),
        'gate_envelope_scaled': bool(np.max(trace['gate_goal'][start:stop]) <= gate_limit + tol
                                     and np.max(trace['gate_goal'][start:stop]) > 0.99 * gate_limit),
    }
    if variant.get('replacement_and_stop'):
        checks.update(replacement_checks(trace, case, variant))
    elif end is not None:
        checks['check_natural_release'] = bool(trace['gate_goal'][end] == 0
                                               and 0 < trace['gate'][end] < trace['gate'][end - 1])
    reed = compare_state(trace, case, spec)
    checks.update({f'reed_reference.{key}': diff['passed'] for key, diff in reed.items()})
    rate = case['sample_rate_hz']
    windows = []
    for seconds in variant['windows_seconds']:
        first, last = (start + round(rate * t) for t in seconds)
        interval = slice(first, last)
        windows.append({'seconds': seconds, 'mode_mean': float(np.mean(trace['mode'][interval])),
                        'lip_pitch_mean_hz': float(np.mean(trace['lip_pitch_hz'][interval])),
                        'reed_peak_to_peak_cm2': float(np.ptp(trace['reed_opening_cm2'][interval])),
                        'nasal_ac_rms_cm3_s': float(np.std(trace['nasal_cm3_s'][interval])),
                        'pcm_rms': fixed.rms(trace['pcm_f32'][interval])})
    checks['nasal_radiation_measured'] = all(w['nasal_ac_rms_cm3_s'] > 0.0 and w['pcm_rms'] > 0.0 for w in windows)
    columns = ('call_id', 'control_clock_seconds', 'gate_goal', 'gate', 'lung_pressure_dyn_cm2',
               'reed_opening_cm2', 'trunk_valve_area_cm2', *OWNED, *FREE,
               *('target_' + name for name in (*OWNED, *FREE)))
    return checks, {
        'request_frame': request, 'first_control_frame': start, 'end_frame': end, 'windows': windows,
        'frames': {str(i): {key: float(trace[key][i]) for key in columns} for i in variant['curve_frames']},
        'reed_reference': reed,
    }


def definition_matches(definition, keys):
    aliases = {'gate': 'gate', 'mode': 'mode', 'lip_pitch_hz': 'lipPitch', 'pressure_cm_h2o': 'pressure', 'chaos': 'chaos'}
    points = {}
    for field, name in aliases.items():
        for at, value in keys.get(field, ()):
            points.setdefault(at, {})[name] = value
    exponential = keys.get('exponential_into_seconds', ())
    expected = [{'t': at, 'v': points[at], **({'curve': 'exp'} if at in exponential else {})}
                for at in sorted(points)]
    return definition['pitchRef'] == keys['pitch_reference_hz'] and definition['keys'] == expected


def check_pitch_request(case, spec, artifacts):
    match = spec['matched_pitch_request']
    test, control = (artifacts / match[name] for name in ('case', 'control'))
    block = spec['host_block_frames'][0]
    def csv_prefix(name):
        with (test / name).open('rb') as candidate, (control / name).open('rb') as reference:
            return all(candidate.readline() == line for line in reference)
    prefix = fixed.waveform(test / f'pcm-{block}.wav', case)[:match['frames']]
    unpitched = fixed.waveform(control / f'pcm-{block}.wav', case)
    return {'candidate_csv': csv_prefix(f'pcm-{block}.csv'), 'upstream_csv': csv_prefix('upstream.csv'),
            'pcm': np.array_equal(prefix.view('u4'), unpitched.view('u4'))}


def measure_call(config, spec, artifacts, execute, call, observe_call):
    probe, official_path = fixed.prepare(artifacts, execute)
    definition = artifacts / f'{call}-definition.json'
    execute([str(probe), f'--{call}-definition'], cwd=UPSTREAM, stdout=definition)
    checks = {f'upstream_{call}_definition': definition_matches(read(definition), spec[call + '_keys'])}
    variants = {}
    source = config['elephant_voice']
    for variant in spec['variants']:
        case = source | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
        case['shape'] = case['shape'] | variant.get('shape', {})
        name = variant['id']
        folder = artifacts / name
        result = fixed.capture(case, variant, spec, folder, probe, official_path, execute,
                               control_model=reference_controls, observe=observe_call)
        if variant.get('official_prefix'):
            start = result['observations']['request_frame']
            pcm = fixed.waveform(folder / f"pcm-{spec['host_block_frames'][0]}.wav", case)[start:]
            official = fixed.waveform(official_path, case)[start:case['frames']]
            region = compare(pcm.astype(float), official.astype(float), spec['tolerances']['pcm'])
            result['checks'][f'official_{call}_segment'] = region['passed']
            result['observations'][f'official_{call}_segment'] = region | {
                'frames': len(pcm), 'different_pcm_bits': int(np.count_nonzero(pcm.view('u4') != official.view('u4')))}
        checks.update({f'{name}.{key}': value for key, value in result['checks'].items()})
        variants[name] = result
    return checks, variants


def measure(config, spec, artifacts, execute):
    checks, variants = measure_call(config, spec, artifacts, execute, 'trumpet', observe)
    pair = check_pitch_request(config['elephant_voice'] | {'sample_rate_hz': 96000}, spec, artifacts)
    checks.update({f'matched_pitch_request.{key}': value for key, value in pair.items()})
    return {'checks': checks, 'variants': variants, 'matched_pitch_frames': spec['matched_pitch_request']['frames']}


def run_call_measurement(case_path, baseline_run, evaluate, script, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(case_path)
    parents = [WORKSPACE / 'cases' / name for name in config['inherits_measurement']]
    spec = {}
    for path in (*parents, case_path):
        spec.update(read(path)['measurement'])
    valve_case = next(path for path in parents if path.name == 'elephant-valve.json')
    spec['reed_parameters'] = read(valve_case)['lip_reed']['parameters']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs' / baseline_run / 'manifest.json'
    before = read(baseline)
    if before['status'] != 'pass' or before['upstream_revision'] != revision:
        raise SystemExit('ゾウの比較基準が確認できません')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in before['upstream_source_sha256']}}
    tools = ('upstream_baseline.py', 'measure_uniform_tube.py', 'measure_seal_sustain_pcm.py',
             'measure_songbird_sustain_pcm.py', 'measure_songbird_syrinx.py', 'measure_elephant_fixed_voice.py',
             'measure_elephant_rumble.py', 'measure_elephant_valve.py')
    paths = [case_path, *parents, fixed.PROBE, baseline, Path(__file__).resolve(), script, WORKSPACE / 'LICENSE-CHIMERA',
             *(WORKSPACE / 'tools' / name for name in tools), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, case_path, paths, details,
                                     lambda artifacts, execute: evaluate(config, spec, artifacts, execute), command=None)


def main():
    return run_call_measurement(CASE, 'elephant-valve-before-trumpet-1', measure, Path(__file__).resolve(), __doc__)


if __name__ == '__main__':
    raise SystemExit(main())
