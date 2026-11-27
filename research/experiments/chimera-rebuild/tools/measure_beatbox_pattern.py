"""ビートパターンの予約、再生位置、PCMを固定上流と照合する。"""

import argparse
from fractions import Fraction
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_beatbox_crash as crash
import measure_beatbox_hat as hat
import measure_beatbox_hum as hum
import measure_beatbox_inward_snare as inward
import measure_beatbox_kick as kick
import measure_beatbox_lip_pop as pop
import measure_beatbox_rimshot as rimshot
import measure_beatbox_snare as snare
import measure_beatbox_tongue_click as click
import measure_beatbox_transport as transport
import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = {
    'swing': WORKSPACE / 'cases/beatbox-pattern-swing.json',
    'mixed': WORKSPACE / 'cases/beatbox-pattern-mixed-kit.json',
    'open-short': WORKSPACE / 'cases/beatbox-open-hat-short.json',
    'open-long': WORKSPACE / 'cases/beatbox-open-hat-long.json',
    'snare': WORKSPACE / 'cases/beatbox-pattern-snare-pf.json',
    'rimshot': WORKSPACE / 'cases/beatbox-pattern-rimshot-k-v2.json',
    'inward-snare': WORKSPACE / 'cases/beatbox-pattern-inward-snare.json',
    'tongue-click': WORKSPACE / 'cases/beatbox-pattern-tongue-click.json',
    'lip-pop': WORKSPACE / 'cases/beatbox-pattern-lip-pop.json',
    'crash-short': WORKSPACE / 'cases/beatbox-pattern-crash-short.json',
    'crash-long': WORKSPACE / 'cases/beatbox-pattern-crash-long.json',
    'hum': WORKSPACE / 'cases/beatbox-pattern-hum.json',
    'transport': WORKSPACE / 'cases/beatbox-pattern-transport.json',
}
BASELINE = WORKSPACE / 'cases/beatbox-kick-b-v2.json'
PROBE = WORKSPACE / 'tools/upstream_beatbox_pattern_probe.rs'


def compare_clock(config, rows, frames):
    """十進の登録値から、ドリフトのない有理数のグリッドを独立に作る。"""
    source = config['beatbox_pattern']
    limits = config['measurement']
    rate = source['voice']['output_sample_rate_hz']
    block = limits['scheduler_block_frames']
    horizon = Fraction(str(limits['horizon_seconds']))
    sixteenth = 15 / Fraction(str(source['bpm']))
    swing = Fraction(str(source['swing']))
    slots = limits['expected_slot_accents']
    sounds = expected_sounds(limits)
    notes = limits.get('expected_slot_notes', [None] * len(slots))
    end = Fraction(frames, rate)
    nominal = horizon
    expected = []
    while nominal < end + horizon:
        step = len(expected)
        hit = nominal + (swing * sixteenth / 2 if step % 2 else 0)
        tick_number = (hit - horizon) * rate / block
        frame = math.ceil(tick_number) * block
        if frame >= frames:
            break
        accent = slots[step % len(slots)]
        rests = 0
        if accent is not None:
            for distance in range(1, len(slots)):
                if slots[(step + distance) % len(slots)] is not None:
                    break
                rests += 1
        row = dict(index=step, hit_seconds=float(hit), accent=accent, sound=sounds[step % len(slots)],
                   length_seconds=float((1 + rests) * sixteenth) if accent is not None else None)
        if accent is not None and (note := notes[step % len(slots)]) is not None:
            row['midi_note'] = note
        # 先読み境界と量子の境界が同時なら、足し上げ時計の丸めで次の量子にもなり得る。
        expected.append((row, frame, tick_number.denominator == 1))
        nominal += sixteenth
    expected_steps = [row for row, _, _ in expected]
    steps = [row['step'] for row in rows]
    tol = limits['seconds_absolute_tolerance']
    diff, largest = timing.compare(steps, expected_steps, tol)
    errors = []
    for admission, (_, frame, boundary) in zip(rows, expected):
        actual = admission['frame']
        if actual != frame and (not boundary or actual != frame + block):
            errors.append({'step': admission['step']['index'], 'actual': actual, 'nominal': frame})
        if abs(admission['clock_seconds'] - actual / rate) > tol:
            errors.append({'step': admission['step']['index'], 'clock_seconds': admission['clock_seconds'],
                           'clock_from_frame': actual / rate})
    arrived = [step for step in steps if step['hit_seconds'] < float(end)]
    hit_times = [step['hit_seconds'] for step in arrived if step['accent'] is not None]
    hit_diff, _ = timing.compare(hit_times, limits['expected_hit_times_seconds_in_window'], tol)
    clock = {
        'independent_step_difference': diff, 'step_maximum_absolute_error': largest,
        'reservation_frame_differences': errors, 'expected_vs_observed_hit_time_difference': hit_diff,
        'scheduled_step_count': len(steps), 'arrived_step_count': len(arrived),
        'window_hit_times_seconds': hit_times,
        'nominal_reservation_frames': [frame for _, frame, _ in expected],
    }
    return clock, expected_steps


def expected_sounds(limits):
    return limits.get('expected_slot_sounds', [
        'B' if accent is not None else None for accent in limits['expected_slot_accents']
    ])


def overlap_events(trace, config, independent_steps):
    limits = config['measurement']
    source = config['beatbox_pattern']['voice']
    hats = [hat.hat_control(step['hit_seconds'], step['accent'])
            for step in independent_steps if step['sound'] == 't']
    controls = hat.control_errors(trace, source, hats)
    rate = source['output_sample_rate_hz']
    times = (trace['frame'] + 1) / rate
    begin, end = limits['overlap_window_seconds']
    inside = (times >= begin) & (times <= end)
    overlap = (inside & (trace['larynx_cm'] >= limits['overlap_minimum_larynx_cm'])
               & (trace['abduction_cm2'] >= limits['overlap_minimum_abduction_cm2'])
               & (trace['gate'] >= limits['overlap_minimum_gate']))
    positions = np.flatnonzero(overlap)
    return {
        'independent_control_errors': controls,
        'overlap_frames': int(positions.size),
        'overlap_seconds': float(positions.size / rate),
        'first_overlap_seconds': float(times[positions[0]]) if positions.size else None,
        'last_overlap_seconds': float(times[positions[-1]]) if positions.size else None,
        'teeth_noise_peak': float(abs(trace['teeth_noise_level']).max()),
        'gate_peak': float(trace['gate'].max()),
        'maximum_voicing': float(abs(trace['glottal_voicing']).max()),
    }


def open_hat_events(trace, pcm, config, independent_steps):
    limits = config['measurement']['open_hat']
    source = config['beatbox_pattern']['voice']
    hats = [hat.hat_control(step['hit_seconds'], step['accent'], open_length=step['length_seconds'])
            for step in independent_steps if step['sound'] == 'tss']
    controls = hat.control_errors(trace, source, hats)
    times = (trace['frame'] + 1) / source['output_sample_rate_hz']
    below = np.flatnonzero((times >= hats[0].breath_end) & (trace['gate'] < limits['gate_threshold']))
    late_start, late_end = limits['late_window_seconds']
    late = (times >= late_start) & (times < late_end)
    return {
        'independent_control_errors': controls,
        'first_gate_below_threshold_seconds': float(times[below[0]]) if below.size else None,
        'late_gate_mean': float(trace['gate'][late].mean()),
        'late_pcm_rms': float(np.sqrt(np.mean(pcm[late].astype('f8')**2))),
        'late_teeth_noise_peak': float(abs(trace['teeth_noise_level'][late]).max()),
        'maximum_voicing': float(abs(trace['glottal_voicing']).max()),
    }


def measure_open_hat(result, config, expected_hits, independent_steps, candidate, pcm, upper, upper_pcm):
    limits = config['measurement']
    open_limits = limits['open_hat']
    checks = result['checks']
    first = next((row for row in expected_hits if row['step']['sound'] == 'tss'), None)
    first_holds = [
        g['t1'] for g in first['gestures']
        if g.get('speed') == 1.4 or 'breath' in g['targets']
    ] if first else []
    first_length = first['step']['length_seconds'] if first else None
    checks['open_hat_holds_match_registered_duration'] = (
        first_length is not None
        and abs(first_length - open_limits['expected_first_length_seconds']) <= limits['seconds_absolute_tolerance']
        and len(first_holds) == 2
        and all(abs(end - open_limits['expected_first_hold_end_seconds']) <= limits['seconds_absolute_tolerance']
                for end in first_holds)
    )
    observed = open_hat_events(candidate, pcm, config, independent_steps)
    baseline = open_hat_events(upper, upper_pcm, config, independent_steps)
    result['open_hat'] = {
        'first_step_length_seconds': first_length, 'first_frication_and_breath_hold_end_seconds': first_holds,
        'candidate': observed, 'upstream': baseline,
    }
    gate_start, gate_end = open_limits['gate_fall_window_seconds']
    mean_min, mean_max = open_limits['late_gate_mean_range']
    outcomes = (observed, baseline)
    checks['independent_gate_and_abduction'] = all(
        max(row['independent_control_errors'].values()) <= limits['control_absolute_tolerance']
        for row in outcomes
    )
    checks['open_hat_gate_fall_in_registered_window'] = all(
        row['first_gate_below_threshold_seconds'] is not None
        and gate_start <= row['first_gate_below_threshold_seconds'] <= gate_end
        for row in outcomes
    )
    checks['open_hat_late_breath_and_pcm'] = all(
        mean_min <= row['late_gate_mean'] <= mean_max
        and row['late_pcm_rms'] >= open_limits['minimum_late_pcm_rms']
        for row in outcomes
    )


def capture(case_path, blocks, artifacts, execute, *, upstream_case_path=None):
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    settings = artifacts / 'settings.json'
    trace_file = artifacts / 'trace.csv'
    execute([*prefix, 'inspect', str(case_path)], stdout=settings)
    execute([*prefix, 'render', str(case_path), str(trace_file)])
    outputs = []
    for block in blocks:
        wave, index = artifacts / f'pcm-{block}.wav', artifacts / f'pcm-{block}.csv'
        execute([*prefix, 'render-pcm', str(case_path), str(wave), str(index), str(block)])
        outputs.append((wave, index, artifacts / f'upstream-engine-{block}.f32'))
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'beatbox', '--test', 'engine'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(upstream_case_path or case_path), str(artifacts)], cwd=UPSTREAM)
    return settings, trace_file, outputs


def measure(case_path, config, artifacts, execute):
    limits = config['measurement']
    settings, trace_file, outputs = capture(case_path, limits['host_block_frames'], artifacts, execute)
    plan = timing.read(settings)
    reference = timing.read(artifacts / 'upstream-plan.json')
    frames = plan['output_frames']
    rows = plan['beatbox_pattern']['reservations']
    if 'transport' in limits:
        clock, transport_state = transport.compare_clock(config, rows, frames)
    else:
        clock, independent_steps = compare_clock(config, rows, frames)
    expected_accent = limits['expected_slot_accents']
    sounds = expected_sounds(limits)
    expected_hits = [row for row in rows if row['gestures'] is not None]
    upper_hits = reference['hits']
    for row in upper_hits:
        for gesture in row['gestures']:
            gesture['targets'] = {bilabial.KEYS[key]: value for key, value in gesture['targets'].items()}
    first_hit_diff, max_hit_diff = timing.compare(
        [{key: row[key] for key in ('frame', 'clock_seconds', 'gestures')} for row in expected_hits],
        upper_hits, limits['seconds_absolute_tolerance'],
    )
    candidate = bilabial.load_trace(trace_file, frames)
    upper = bilabial.load_trace(artifacts / 'upstream-trace.csv', frames)
    first_trace_diff, trace_errors = kick.compare_traces(candidate, upper, limits)
    trace_counts = np.zeros(frames, dtype=np.int32)
    for row in rows:
        trace_counts[row['frame']] += 1
    wave, index, upper_pcm_path = outputs[0]
    rate, pcm = wavfile.read(wave)
    upper_pcm = np.fromfile(upper_pcm_path, dtype='<f4')
    probe_pcm = np.fromfile(artifacts / 'upstream-probe.f32', dtype='<f4')
    if pcm.shape != (frames,) or upper_pcm.shape != pcm.shape or probe_pcm.shape != pcm.shape:
        raise ValueError('候補・上流でフレーム数が異なります')
    if not np.isfinite(pcm).all() or not np.isfinite(upper_pcm).all() or not np.isfinite(probe_pcm).all():
        raise ValueError('PCMに非有限値があります')
    delta = abs(pcm.astype('f8') - upper_pcm)
    outlier = np.flatnonzero(delta > limits['pcm_absolute_tolerance'])
    peak = float(abs(pcm).max())
    checks = {
        'pattern_matches_upstream_and_registered_slots': (
            plan['beatbox_pattern']['slot_accents'] == reference['slot_accents'] == expected_accent
            and plan['beatbox_pattern']['slot_sounds'] == reference['slot_sounds'] == sounds
        ),
        'registered_step_counts_and_times': (
            clock['scheduled_step_count'] == limits['expected_scheduled_steps']
            and clock['arrived_step_count'] == limits['expected_audible_window_steps']
            and clock['expected_vs_observed_hit_time_difference'] is None
        ),
        'independent_grid_and_first_eligible_tick': (
            clock['independent_step_difference'] is None and not clock['reservation_frame_differences']
        ),
        'upstream_hit_batches_at_same_frames': first_hit_diff is None,
        'render_advances_on_registered_ticks': np.array_equal(candidate['beat_next_step'], trace_counts.cumsum()),
        'playhead_including_rests_matches_upstream': np.array_equal(candidate['beat_step'], upper['beat_step']),
        'acoustic_states_match_upstream': first_trace_diff is None,
        'wave_has_registered_rate_and_frames': (
            rate == config['beatbox_pattern']['voice']['output_sample_rate_hz']
            and frames == round(rate * config['beatbox_pattern']['render_end_seconds'])
        ),
        'pcm_agreement': not bool(outlier.size),
        'pcm_peak_and_gate': peak >= limits['minimum_full_window_pcm_peak']
                             and float(abs(candidate['gate']).max()) <= limits['maximum_gate'],
        'upper_probe_matches_engine': np.array_equal(probe_pcm, upper_pcm),
        'host_partition_byte_agreement': all(
            sha256(other_wave) == sha256(wave) and sha256(other_index) == sha256(index)
            and sha256(other_upstream) == sha256(upper_pcm_path)
            for other_wave, other_index, other_upstream in outputs[1:]
        ),
    }
    result = {
        'checks': checks, 'frames': frames, 'sample_rate_hz': rate, 'clock': clock,
        'reservation_frames': [row['frame'] for row in rows],
        'scheduled_hits': [row['step']['hit_seconds'] for row in expected_hits],
        'upstream_hit_batch_difference': first_hit_diff, 'hit_batch_maximum_absolute_error': max_hit_diff,
        'first_trace_difference': first_trace_diff, 'trace_errors': trace_errors,
        'pcm_max_absolute_error': float(delta.max()), 'pcm_peak': peak,
        'pcm_first_outlier_frame': int(outlier[0]) if outlier.size else None,
    }
    if 'transport' in limits:
        transport.measure(result, config, transport_state, plan['beatbox_pattern'], reference,
                          (('candidate', candidate, pcm), ('upstream', upper, upper_pcm)))
    if 'overlap_window_seconds' in limits:
        observed, baseline = (overlap_events(trace, config, independent_steps) for trace in (candidate, upper))
        result['candidate_overlap'] = observed
        result['upstream_overlap'] = baseline
        checks['independent_gate_and_abduction'] = all(
            max(row['independent_control_errors'].values()) <= limits['control_absolute_tolerance']
            for row in (observed, baseline)
        )
        checks['overlapping_larynx_breath_and_abduction'] = all(
            row['overlap_seconds'] >= limits['minimum_overlap_seconds'] for row in (observed, baseline)
        )
        checks['teeth_turbulence_in_pattern'] = all(
            row['teeth_noise_peak'] >= limits['minimum_teeth_noise_peak'] for row in (observed, baseline)
        )
    if 'open_hat' in limits:
        measure_open_hat(result, config, expected_hits, independent_steps, candidate, pcm, upper, upper_pcm)
    if 'snare' in limits:
        snare_limits = limits['snare']
        source = config['beatbox_pattern']['voice']
        hits = [(step['hit_seconds'], step['accent']) for step in independent_steps if step['sound'] == 'Pf']
        outcomes = {
            label: {
                'control_errors': snare.control_errors(trace, source, hits),
                'peak_gate': float(trace['gate'].max()),
                'peak_labiodental': float(trace['labiodental'].max()),
                'peak_constriction_noise': float(abs(trace['constriction_noise_level']).max()),
            }
            for label, trace in (('candidate', candidate), ('upstream', upper))
        }
        result['snare'] = outcomes
        checks['accented_snare_controls'] = all(
            max(row['control_errors'].values()) <= limits['control_absolute_tolerance']
            and row['peak_gate'] >= snare_limits['minimum_peak_gate'] for row in outcomes.values()
        )
        checks['snare_labiodental_frication'] = all(
            row['peak_labiodental'] >= snare_limits['minimum_labiodental_peak']
            and row['peak_constriction_noise'] >= snare_limits['minimum_constriction_noise_peak']
            for row in outcomes.values()
        )
    if 'rimshot' in limits:
        rimshot_limits = limits['rimshot']
        source = config['beatbox_pattern']
        hits = [(step['sound'], step['hit_seconds'], step['accent'])
                for step in independent_steps if step['sound'] in ('B', 'K')]
        start, end = rimshot_limits['larynx_window_seconds']
        clock = (candidate['frame'] + 1) / rate
        window = (clock >= start) & (clock < end)
        outcomes = {
            label: {
                'control_errors': rimshot.control_errors(trace, source, hits),
                'peak_larynx_cm': float(trace['larynx_cm'][window].max()),
                **rimshot.observe_voicing(trace, rate, rimshot_limits),
            }
            for label, trace in (('candidate', candidate), ('upstream', upper))
        }
        result['rimshot'] = outcomes
        targets = [
            g['targets']['larynx_cm'] for row in expected_hits if row['step']['sound'] == 'K'
            for g in row['gestures'] if 'larynx_cm' in g['targets']
        ]
        checks['accented_rimshot_larynx_bound'] = (
            len(targets) == sum(sound == 'K' for sound, _, _ in hits)
            and bool(targets)
            and all(t == rimshot_limits['accented_larynx_target_cm'] for t in targets)
            and all(row['peak_larynx_cm'] >= rimshot_limits['minimum_larynx_peak_cm']
                    for row in outcomes.values())
        )
        checks['independent_rimshot_controls'] = all(
            max(row['control_errors'].values()) <= limits['control_absolute_tolerance']
            for row in outcomes.values()
        )
        checks['rimshot_transient_voicing_with_gate_closed'] = all(
            row['transient_voicing_with_gate_closed'] for row in outcomes.values()
        )
    if 'inward_snare' in limits:
        source = config['beatbox_pattern']['voice']
        hit_list = [(step['hit_seconds'], step['accent']) for step in independent_steps
                    if step['sound'] == '^K']
        outcomes = {
            label: {
                'control_errors': inward.control_errors(trace, source, hit_list),
                'events': [inward.observe(trace, audio, hit, rate, limits['inward_snare'])
                           for hit, _ in hit_list if hit < frames / rate],
            }
            for label, trace, audio in (('candidate', candidate, pcm), ('upstream', upper, upper_pcm))
        }
        result['inward_snare'] = outcomes
        checks['inward_snare_signed_control'] = all(
            max(row['control_errors'].values()) <= limits['control_absolute_tolerance']
            for row in outcomes.values()
        )
        for key in inward.EVENT_CHECKS:
            checks[f'inward_snare_{key}'] = all(
                row['events'] and all(event.get(key, False) for event in row['events'])
                for row in outcomes.values()
            )
    if 'tongue_click' in limits:
        hits = [step['hit_seconds'] for step in independent_steps if step['sound'] == '!']
        outcomes = {
            label: {
                'dorsum_max_abs_error': click.control_error(trace, rate, hits),
                'events': [click.observe(trace, audio, hit, rate, limits['tongue_click'])
                           for hit in hits if hit < frames / rate],
            }
            for label, trace, audio in (('candidate', candidate, pcm), ('upstream', upper, upper_pcm))
        }
        result['tongue_click'] = outcomes
        checks['tongue_click_independent_dorsum'] = all(
            row['dorsum_max_abs_error'] <= limits['control_absolute_tolerance']
            for row in outcomes.values()
        )
        for key in click.EVENT_CHECKS:
            checks[f'tongue_click_{key}'] = all(
                row['events'] and all(event.get(key, False) for event in row['events'])
                for row in outcomes.values()
            )
    if 'crash' in limits:
        crash.measure_pattern(result, config, expected_hits, independent_steps,
                              (('candidate', candidate, pcm), ('upstream', upper, upper_pcm)))
    if 'hum' in limits:
        spec = limits['hum']
        source = config['beatbox_pattern']
        tol = limits['seconds_absolute_tolerance']
        expected_notes = limits['expected_slot_notes']
        checks['hum_retains_midi_notes'] = (
            plan['beatbox_pattern']['slot_midi_notes'] == reference['slot_midi_notes'] == expected_notes
        )
        planned = [row for row in expected_hits if row['step']['sound'] == 'm']
        lengths = [row['step']['length_seconds'] for row in planned]
        notes = [note for note in expected_notes if note is not None]
        checks['hum_rest_lengths_and_pitch_plan'] = (
            timing.compare(lengths, spec['expected_step_lengths_seconds'], tol)[0] is None
            and len(planned) == len(notes) == len(spec['expected_hold_ends_seconds'])
            and all(hum.registered_pitch_and_hold(row['gestures'], end, note, tol)
                    for row, end, note in zip(planned, spec['expected_hold_ends_seconds'], notes, strict=True))
        )
        hits = [(row['hit_seconds'], row['accent'], row.get('midi_note', 40), row['length_seconds'])
                for row in independent_steps if row['sound'] == 'm']
        outcomes = {
            label: {
                'control_errors': hum.control_errors(trace, source['voice'], source['initial_f0_hz'],
                                                     source['posture']['velum_cm2'], hits),
                'notes': [hum.observe(trace, audio, rate, window, note, spec)
                          for window, note in zip(spec['steady_windows_seconds'], notes, strict=True)],
            }
            for label, trace, audio in (('candidate', candidate, pcm), ('upstream', upper, upper_pcm))
        }
        result['hum'] = {'first_lengths_seconds': lengths, **outcomes}
        checks['hum_independent_controls'] = all(
            max(row['control_errors'].values()) <= limits['control_absolute_tolerance']
            for row in outcomes.values()
        )
        checks['hum_nasal_pcm_pitch'] = all(
            all(note['nasal_voicing'] and note['registered_pcm_pitch'] for note in row['notes'])
            and row['notes'][-1]['pcm_f0_hz'] - row['notes'][0]['pcm_f0_hz'] >= spec['minimum_note_rise_hz']
            for row in outcomes.values()
        )
    if 'lip_pop' in limits:
        source = config['beatbox_pattern']
        hits = [(step['sound'], step['hit_seconds']) for step in independent_steps
                if step['sound'] in ('B', 'P!')]
        outcomes = {
            label: {
                'control_errors': pop.control_errors(trace, rate, source['posture'], hits),
                'events': [pop.observe(trace, audio, hit, rate, source['internal_sample_rate_hz'], limits['lip_pop'])
                           for sound, hit in hits if sound == 'P!' and hit < frames / rate],
            }
            for label, trace, audio in (('candidate', candidate, pcm), ('upstream', upper, upper_pcm))
        }
        result['lip_pop'] = outcomes
        checks['lip_pop_independent_jaw_and_dorsum'] = all(
            max(row['control_errors'].values()) <= limits['control_absolute_tolerance']
            for row in outcomes.values()
        )
        for key in pop.EVENT_CHECKS:
            checks[f'lip_pop_{key}'] = all(
                row['events'] and all(event.get(key, False) for event in row['events'])
                for row in outcomes.values()
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--condition', choices=CASES, default='swing')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = CASES[args.condition]
    config = timing.read(case_path)
    baselines = [BASELINE]
    if args.condition == 'snare':
        baselines.append(snare.CASE)
    elif args.condition == 'rimshot':
        baselines.append(rimshot.CASE)
    elif args.condition == 'inward-snare':
        baselines.append(inward.CASE)
    elif args.condition == 'tongue-click':
        baselines.append(click.CASE)
    elif args.condition == 'lip-pop':
        baselines.append(pop.CASE)
    elif args.condition in ('crash-short', 'crash-long'):
        baselines.append(crash.CASE)
    elif args.condition in ('hum', 'transport'):
        baselines.append(hum.CASE)
    elif args.condition != 'swing':
        baselines.append(hat.CASE)
    for baseline_path in baselines:
        baseline = timing.read(baseline_path)
        for field in ('voice', 'internal_sample_rate_hz', 'posture', 'initial_f0_hz', 'noise_scale'):
            if config['beatbox_pattern'][field] != baseline['beatbox_voice'][field]:
                raise SystemExit(f'単発基準と音源設定が一致しません ({baseline_path.name}, {field})')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [
        case_path, *baselines, PROBE, kick.ORAL_PROBE, Path(__file__).resolve(),
        Path(hat.__file__), Path(kick.__file__), Path(bilabial.__file__),
        Path(snare.__file__), Path(rimshot.__file__), Path(timing.__file__), Path(shared.__file__),
        WORKSPACE / 'tools/upstream_baseline.py',
        Path(inward.__file__), Path(click.__file__), Path(pop.__file__), Path(crash.__file__), Path(hum.__file__),
        Path(transport.__file__),
        *rimshot.REFERENCE_SOURCES,
        *shared.candidate_sources(),
    ]
    upstream_files = (
        'src/control/beat_player.rs', 'src/phonetics/beatbox.rs', 'src/engine.rs', 'tests/beatbox.rs',
        'tests/engine.rs', 'src/voice/human_voice.rs', 'src/voice/human_airway.rs',
        'src/airway/network.rs', 'src/anatomy/human.rs', 'src/control/articulators.rs',
        'src/phonetics/consonantTargets.generated.json',
        'src/math.rs',
    )
    details = {
        'case_id': config['id'], 'upstream_revision': revision,
        'upper_source_sha256': {path: sha256(UPSTREAM / 'crates/chimera' / path) for path in upstream_files},
    }
    return shared.record_measurement(args.run_id, case_path, sources, details,
                                     lambda artifacts, execute: measure(case_path, config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
