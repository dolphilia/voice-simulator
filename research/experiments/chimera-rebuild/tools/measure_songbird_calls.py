"""周期コールのタイミング、重なるキー、コールの切り替えを照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_uniform_tube as shared
from measure_songbird_flute import CALL_CODES, PROBE, capture, control_reference
from measure_songbird_sustain_pcm import waveform
from measure_songbird_syrinx import read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-calls.json'


def event_verifier(definitions):
    sorted_definitions = definitions | {'chirps': definitions['chirps'] | {
        'keys': sorted(definitions['chirps']['keys'], key=lambda key: key['t'])
    }}

    def evaluate(name, candidate, pcm, source, sustain, m):
        rate = source['sample_rate_hz']
        block = sustain['control_frames']
        ids = candidate['call_id'].astype(int)
        frames = np.flatnonzero(np.diff(ids, prepend=0))
        transitions = [[int(frame), int(ids[frame])] for frame in frames]
        details = {'call_transitions': transitions, 'peak_pcm': float(np.max(np.abs(pcm)))}
        checks = {'pcm_has_a_signal': details['peak_pcm'] >= m['minimum_pcm_peak']}
        first = next(event for event in source['events'] if 'play_call' in event)
        start = math.ceil(first['frame'] / block) * block
        tolerance = m['control_and_target_absolute_tolerance']
        if name in ('trill', 'buzz-96000'):
            feature = 'trill' if name == 'trill' else 'buzz'
            limits = m[feature]
            gate = candidate['gate_target']
            high = gate >= limits['gate_threshold']
            rising = np.flatnonzero(high & ~np.r_[False, high[:-1]])
            intervals = np.diff(rising)
            details.update({'pulse_rises': rising.tolist(), 'pulse_intervals': intervals.tolist(),
                            'first_pitch_target_hz': float(candidate['target_pitch_hz'][start])})
            checks['pulse_count'] = len(rising) == limits['expected_pulses']
            if feature == 'buzz' and 'buzz_startup' in m and intervals.size:
                startup = m['buzz_startup']
                level = limits['gate_threshold'] / first['play_call'].get('amplitude', 1.0)
                end_gate = startup['rise_end_gate']
                def crossing(times, low):
                    start_sec, end_sec = times
                    return start_sec + (end_sec - start_sec) * (level - low) / (end_gate - low)
                first_cross = crossing(startup['first_rise_seconds'], startup['first_rise_start_gate'])
                second_cross = crossing(startup['second_rise_seconds'], startup['second_rise_start_gate'])
                predicted = (second_cross - first_cross) * rate
                details['first_interval_prediction_frames'] = predicted
                checks['startup_pulse_interval'] = bool(abs(intervals[0] - predicted) <= block)
                intervals = intervals[1:]
            checks['pulse_period'] = bool(intervals.size and np.all(
                abs(intervals - limits['period_seconds'] * rate) <= block))
            checks['first_pitch_target'] = abs(details['first_pitch_target_hz'] -
                                               limits['first_pitch_target_hz']) <= tolerance
        if name == 'chirps-44100':
            limits = m['chirps']
            lo, hi = limits['overlap_window_seconds']
            frame = start + math.ceil(lo * rate / block) * block
            elapsed = (frame - start) / rate
            sorted_track = control_reference(source, sorted_definitions, sustain)
            observed = float(candidate['gate_target'][frame])
            counterfactual = float(sorted_track['gate_target'][frame])
            details.update({'overlap_frame': frame, 'overlap_elapsed_seconds': elapsed,
                            'observed_gate': observed, 'sorted_gate': counterfactual,
                            'observed_pitch_hz': float(candidate['target_pitch_hz'][frame]),
                            'sorted_pitch_hz': float(sorted_track['target_pitch_hz'][frame])})
            checks['overlap_in_window'] = lo <= elapsed <= hi
            checks['overlap_gate'] = abs(observed - limits['gate_in_overlap']) <= tolerance
            checks['key_order_effect'] = abs(observed - counterfactual) >= limits['minimum_order_effect_on_gate']
        if name == 'switch':
            limits = m['switch']
            switch, control = limits['frame'], limits['control_frame']
            performer = next(event['controls'] for event in source['events'] if 'controls' in event)
            details['restored'] = {}
            for field in limits['released_fields']:
                obs, goal = candidate[field], candidate[f'target_{field}']
                details['restored'][field] = {
                    'target_before': float(goal[switch - 1]), 'target_on_switch': float(goal[switch]),
                    'smoothed_before': float(obs[switch - 1]), 'smoothed_at_control': float(obs[control]),
                }
                checks[f'{field}.target_restored'] = bool(goal[switch - 1] != goal[switch]
                    and np.all(goal[switch:] == performer[field]))
                checks[f'{field}.smoothed_at_boundary'] = bool(np.all(obs[switch:control] == obs[switch - 1])
                    and abs(obs[control] - performer[field]) < abs(obs[switch] - performer[field]))
            checks['call_switch'] = bool(ids[switch - 1] == CALL_CODES['buzz']
                                         and ids[switch] == CALL_CODES['trill'])
            details['first_target_in_new_call_hz'] = float(candidate['target_pitch_hz'][control])
            checks['new_call_uses_own_pitch'] = abs(details['first_target_in_new_call_hz'] -
                                                    m['trill']['first_pitch_target_hz']) <= tolerance
        return details, checks

    return evaluate


def measure(case, sustain, out, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    official = out / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render',
             'creature', 'songbird', str(official), '--float'], cwd=UPSTREAM, stdout=out / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    definition_path = out / 'definitions.json'
    execute([str(probe), '--songbird-definitions'], cwd=UPSTREAM, stdout=definition_path)
    definitions = {definition['id']: definition for definition in read(definition_path)}
    limits = case['measurement']
    counts = {name: len(definition['keys']) for name, definition in definitions.items()}
    checks = {'key_counts': counts == limits['expected_key_counts']}
    variants = {}
    for entry in limits['variants']:
        name = entry['id']
        source = case['songbird_voice'] | entry['overrides']
        wav = official / 'songbird.wav' if name == 'upper-cli' else None
        if wav is not None:
            checks['official_frame_count'] = len(waveform(wav, source)) == source['frames']
        variants[name], flags = capture(name, source, out / name, execute, probe, definitions, sustain,
                                        limits, wav, event_verifier=event_verifier(definitions))
        checks.update({f'{name}.{key}': value for key, value in flags.items()})
    return {'checks': checks, 'variants': variants, 'key_counts': counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--revision', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read(CASE)
    case_inputs = [CASE]
    if args.revision == 2:
        amendment = CASE.with_name('songbird-calls-v2.json')
        revision = read(amendment)
        if revision['base_case'] != CASE.name or revision['upstream_revision'] != case['upstream_revision']:
            raise ValueError('事前登録と改訂の参照先が一致しません')
        case['revision'] = revision['revision']
        case['measurement']['buzz_startup'] = revision['buzz_startup']
        case_inputs.append(amendment)
    sustain = CASE.with_name(case['measurement']['output_reference'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    references = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/creatures/songbird.rs',
                  'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/types.rs',
                  'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    info = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
            'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
            'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in references}}
    inputs = [*case_inputs, sustain, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_songbird_flute',
                   'measure_songbird_sustain_pcm', 'measure_songbird_syrinx', 'upstream_baseline')),
              *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, info,
        lambda artifacts, execute: measure(case, read(sustain)['measurement'], artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
