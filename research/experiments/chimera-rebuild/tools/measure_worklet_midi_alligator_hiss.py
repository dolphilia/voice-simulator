"""HissのMIDI再発音、音番号の交換、離鍵後の乱流を比較する。"""

import json
from pathlib import Path

import numpy as np

from measure_alligator_bellow import CALL_IDS, NOISE_FIELDS, OWNERSHIP
from measure_alligator_hiss import GLOTTAL_PRESSURE, ORAL_LEVEL, hiss_definition_matches, measure_noise
from measure_wasm_fixed import read_json
from measure_worklet_midi_alligator_call import acoustic_window, main
from measure_worklet_midi_songbird import read_trace, rms
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-alligator-hiss.json'


def bounds(candidate, pcm, voice, events, starts, pitches, factor, config, spec):
    rate = voice['sample_rate_hz']
    keys = spec['hiss_keys']
    fields = ('call_id', 'gate_target', 'gate', 'target_pitch_hz', 'pitch_hz', 'target_mouth', 'mouth', 'target_hiss',
              'hiss', 'oral_tip_area_cm2', 'oral_noise', 'glottis_area_cm2', 'glottis_flow_cm3_s',
              'glottis_voicing', GLOTTAL_PRESSURE, ORAL_LEVEL, 'radiation_cm3_s2')
    transitions = []
    for frame in starts:
        sample = frame * factor
        transitions.append({'frame': frame, 'before': {key: float(candidate[key][sample - 1]) for key in fields},
                            'after': {key: float(candidate[key][sample]) for key in fields}})
    before, after = (transitions[-1][side] for side in ('before', 'after'))

    def noise_window(frame, offsets):
        window = acoustic_window(candidate, pcm, frame, offsets, rate, factor)
        start, end = window['frames']
        rows = candidate[start * factor:end * factor]
        return window | {'peak_voicing': float(np.max(rows['glottis_voicing'])),
                         'oral_noise_registered': bool(rows['oral_noise'].any()),
                         'oral_noise_peak_dyn_cm2': float(np.max(rows[ORAL_LEVEL])),
                         'glottal_noise_pressure_rms_dyn_cm2': rms(rows[GLOTTAL_PRESSURE])}

    releases = [noise_window(row['frame'], config['release_window_seconds'])
                for row in events if not row['midi_call']['pressed']]
    sustained = [noise_window(frame, config['sustained_hiss_window_seconds']) for frame in starts]
    ends = (np.flatnonzero(np.diff(candidate['call_id']) < 0) + 1).tolist()
    end = ends[0] // factor if len(ends) == 1 else None
    expected_pitch = voice['shape']['pitch_hz']
    checks = {
        'hiss_keeps_performer_pitch': np.all(candidate['target_pitch_hz'] == expected_pitch)
            and np.max(abs(candidate['pitch_hz'] - expected_pitch)) <= config['control_tolerance'],
        'hiss_starts_restore_envelope_targets': all(
            row['after']['call_id'] == CALL_IDS['hiss'] and row['after']['gate_target'] == 0
            and row['after']['target_hiss'] == keys['hiss_first']
            and row['after']['target_mouth'] == keys['mouth_first'] for row in transitions),
        'hiss_retrigger_continues_smoothed_airway_state': before['gate'] >= config['minimum_retrigger_gate_before']
            and before['gate_target'] == 1 and config['minimum_retrigger_gate_after'] <= after['gate'] < before['gate']
            and before['mouth'] < after['mouth'] < after['target_mouth']
            and before['hiss'] < after['hiss'] < after['target_hiss']
            and spec['oral_noise_threshold_cm2'] <= before['oral_tip_area_cm2'] <= after['oral_tip_area_cm2']
            and not before['oral_noise'] and not after['oral_noise'],
        'hiss_outlasts_release': all(row['call_ids'] == [CALL_IDS['hiss']]
            and row['gate_min'] >= config['minimum_release_gate'] for row in releases),
        'hiss_windows_have_glottal_turbulence_without_voicing': all(
            not row['oral_noise_registered'] and row['oral_noise_peak_dyn_cm2'] == 0
            and row['peak_voicing'] <= spec['aspiration_window']['max_voicing']
            and row['glottal_noise_pressure_rms_dyn_cm2'] >= config['minimum_glottal_noise_pressure_rms_dyn_cm2']
            and row['pcm_rms'] >= config['minimum_pcm_rms'] for row in (*releases, *sustained)),
        'hiss_natural_end_restores_manual_targets': end is not None and ends[0] % factor == 0
            and abs((end - starts[-1]) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= config['control_frames'] / rate + config['clock_tolerance_seconds']
            and np.all(candidate['call_id'][end * factor:] == 0)
            and np.all(candidate['gate_target'][end * factor:] == 0)
            and all(np.all(candidate['target_' + key][end * factor:] == voice['shape'][key])
                    for key in OWNERSHIP['hiss']),
    }
    return checks, {'start_transitions': transitions, 'release_windows': releases,
                    'sustained_windows': sustained, 'natural_end_frame': end}


def counterfactuals(artifacts, execute, probe, cli, result, upper_pcm, config):
    payload = read_json(artifacts / 'midi-alligator-case.json')
    voice = payload['alligator_voice']
    events = voice['events']
    first, second = [row['midi_call']['note'] for row in events if row['midi_call']['pressed']]
    exchange = {first: second, second: first}
    swapped = [row | {'midi_call': row['midi_call'] | {'note': exchange[row['midi_call']['note']]}}
               for row in events]
    swapped_case = artifacts / 'swapped-midi-alligator-case.json'
    swapped_case.write_text(json.dumps(payload | {'alligator_voice': voice | {'events': swapped}}) + '\n')
    execute([*cli, 'render-pcm', str(swapped_case), str(artifacts / 'swapped-cli.wav'),
             str(artifacts / 'swapped-cli.csv'), '109'])

    upstream_case = artifacts / 'upstream-case.json'
    payload = read_json(upstream_case)
    upper = payload['alligator_voice']
    first_pitch, second_pitch = [row['play_call']['pitch_hz'] for row in upper['events']]
    swapped = [row | {'play_call': row['play_call'] | {'pitch_hz': pitch}}
               for row, pitch in zip(upper['events'], (second_pitch, first_pitch), strict=True)]
    swapped_upstream_case = artifacts / 'swapped-upstream-case.json'
    swapped_upstream_case.write_text(json.dumps(payload | {'alligator_voice': upper | {'events': swapped}}) + '\n')
    execute([str(probe), str(swapped_upstream_case)], cwd=UPSTREAM, stdout=artifacts / 'swapped-upstream.csv')
    hashes = {name: [sha256(artifacts / name), sha256(artifacts / f'swapped-{name}')]
              for name in ('cli.wav', 'cli.csv', 'upstream.csv')}
    swapped_matches = first != second and first_pitch != second_pitch and all(a == b for a, b in hashes.values())
    if swapped_matches:
        # 同一の全CSVは照合したハッシュと通常入力側の保存系列で参照できる。
        for name in ('swapped-cli.wav', 'swapped-cli.csv', 'swapped-upstream.csv'):
            (artifacts / name).unlink()

    muted_csv = artifacts / 'muted-upstream.csv'
    execute([str(probe), str(upstream_case), '--mute-noise'], cwd=UPSTREAM, stdout=muted_csv)
    muted = read_trace(muted_csv, ('sample', 'frame', 'pcm_f32', *NOISE_FIELDS))
    indices = np.arange(len(upper_pcm) * 2)
    windows = []
    for kind in ('release_windows', 'sustained_windows'):
        for row in result['observations'][kind]:
            start, end = row['frames']
            muted_rms = rms(muted['pcm_f32'][2 * start + 1:2 * end:2])
            regular_rms = rms(upper_pcm[start:end])
            windows.append({'kind': kind, 'frames': [start, end], 'regular_rms': regular_rms, 'muted_rms': muted_rms,
                            'ratio': muted_rms / regular_rms if regular_rms > 0 else None})
    checks = {
        'swapping_hiss_notes_preserves_all_pcm_and_trace_bytes': swapped_matches,
        'muted_trace_uses_same_clock_and_zero_noise': np.array_equal(muted['sample'], indices)
            and np.array_equal(muted['frame'], indices // 2) and np.isfinite(muted['pcm_f32']).all()
            and not any(muted[field].any() for field in NOISE_FIELDS),
        'muting_noise_reduces_pcm_in_hiss_windows': all(row['ratio'] is not None
            and row['ratio'] <= config['maximum_muted_pcm_rms_ratio'] for row in windows),
    }
    return checks, {'note_swap_sha256': hashes, 'note_swap_deduplicated': swapped_matches,
                    'muted_windows': windows}


if __name__ == '__main__':
    raise SystemExit(main(CASE, bounds, hiss_definition_matches, driver=Path(__file__), description=__doc__,
                          extra_inputs=(WORKSPACE / 'tools/measure_alligator_hiss.py',),
                          extra_measurement=('noise', measure_noise), counterfactuals=counterfactuals))
