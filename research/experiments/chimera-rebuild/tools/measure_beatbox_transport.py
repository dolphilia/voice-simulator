"""可変テンポの予約と停止後の呼気を有理数の時刻表から検証する。"""

from fractions import Fraction
import math

import numpy as np

import measure_speech_timing as timing


def predict(config, frames):
    source = config['beatbox_pattern']
    limits = config['measurement']
    rate = source['voice']['output_sample_rate_hz']
    horizon = Fraction(str(limits['horizon_seconds']))
    duration = 15 / Fraction(str(source['bpm']))
    swing = Fraction(str(source['swing']))
    accents = limits['expected_slot_accents']
    sounds = limits['expected_slot_sounds']
    notes = limits['expected_slot_notes']
    events = source['events']
    block = limits['scheduler_block_frames']

    # 通算ステップ0の無スウィング時刻として支点を表す。
    origin = horizon
    next_step = 0
    playing = True
    episodes = [dict(start=0, end=frames, reservations=[])]
    reports = []
    cursor = 0
    for frame in sorted(set(range(0, frames, block)) | {event['frame'] for event in events}):
        clock = Fraction(((frame + 63) // 64) * 64, rate)
        while cursor < len(events) and events[cursor]['frame'] == frame:
            event = events[cursor]
            clear = event['type'] == 'playing' and playing and not event['playing']
            reports.append(dict(frame=frame, clock_seconds=float(clock),
                                next_step_before=next_step, score_cleared=clear))
            if event['type'] == 'tempo':
                if 'bpm' in event:
                    new_duration = 15 / min(240, max(40, Fraction(str(event['bpm']))))
                    if playing:
                        origin += next_step * (duration - new_duration)
                    duration = new_duration
                if 'swing' in event:
                    swing = min(Fraction(3, 5), max(0, Fraction(str(event['swing']))))
            elif clear:
                episodes[-1]['end'] = frame
                playing = False
            elif event['playing'] and not playing:
                episodes.append(dict(start=frame, end=frames, reservations=[]))
                playing, next_step, origin = True, 0, clock + horizon
            cursor += 1
        if not playing or frame % block:
            continue
        while True:
            offset = next_step % 2 * swing / 2
            hit = origin + (next_step + offset) * duration
            if hit > clock + horizon:
                break
            slot = next_step % len(sounds)
            sound = sounds[slot]
            length = next((n for n in range(1, len(sounds))
                           if sounds[(slot + n) % len(sounds)] is not None), len(sounds))
            step = dict(index=next_step, hit_seconds=float(hit), accent=accents[slot], sound=sound,
                        length_seconds=float(length * duration) if sound is not None else None)
            if notes[slot] is not None:
                step['midi_note'] = notes[slot]
            episodes[-1]['reservations'].append(dict(frame=frame, clock_seconds=float(clock), step=step))
            next_step += 1
    return episodes, reports


def compare_clock(config, rows, frames):
    limits = config['measurement']
    rate = config['beatbox_pattern']['voice']['output_sample_rate_hz']
    tol = limits['seconds_absolute_tolerance']
    episodes, events = predict(config, frames)
    expected = [row for episode in episodes for row in episode['reservations']]
    prefix = ('frame', 'clock_seconds')
    times, _ = timing.compare([{key: row[key] for key in prefix} for row in rows],
                              [{key: row[key] for key in prefix} for row in expected], tol)
    steps, largest = timing.compare([row['step'] for row in rows], [row['step'] for row in expected], tol)
    stops = [event['frame'] for event in events if event['score_cleared']]
    restarts = [episode['start'] for episode in episodes[1:]]
    by_episode = [[] for _ in episodes]
    for row in rows:
        episode_index = sum(frame <= row['frame'] for frame in restarts)
        by_episode[episode_index].append(row['step'])
    arrived = []
    canceled = []
    for index, steps_in_episode in enumerate(by_episode):
        end = episodes[index]['end']
        for step in steps_in_episode:
            if step['hit_seconds'] < end / rate:
                arrived.append(step)
            elif end < frames and step['sound'] is not None:
                canceled.append(step['hit_seconds'])
    hit_times = [step['hit_seconds'] for step in arrived if step['sound'] is not None]
    hit_diff, _ = timing.compare(hit_times, limits['expected_hit_times_seconds_in_window'], tol)
    return {
        'independent_step_difference': steps, 'step_maximum_absolute_error': largest,
        'reservation_frame_differences': [times] if times else [],
        'expected_vs_observed_hit_time_difference': hit_diff,
        'scheduled_step_count': len(rows), 'arrived_step_count': len(arrived),
        'window_hit_times_seconds': hit_times,
        'nominal_reservation_frames': [row['frame'] for row in expected],
    }, {
        'episodes': episodes, 'events': events, 'stops': stops, 'restarts': restarts,
        'cycle_hit_times': [[step['hit_seconds'] for step in group] for group in by_episode],
        'canceled_hit_times': canceled,
    }


def tracks(state, frames, rate, slots, tolerance):
    clock = (np.arange(frames) // 64 + 1) * 64 / rate
    earliest = np.full(frames, -1)
    latest = np.full(frames, -1)
    pending = np.zeros(frames, dtype=np.int32)
    episodes = state['episodes']
    for index, episode in enumerate(episodes):
        next_start = episodes[index + 1]['start'] if index + 1 < len(episodes) else frames
        for row in episode['reservations']:
            step = row['step']
            pending[row['frame']:next_start] = step['index'] + 1
            for track, stamp in ((earliest, step['hit_seconds'] - tolerance),
                                 (latest, step['hit_seconds'] + tolerance)):
                start = max(row['frame'], np.searchsorted(clock, stamp))
                track[start:episode['end']] = step['index'] % slots
    return earliest, latest, pending


def observe(trace, pcm, rate, stop, restart, spec):
    times = (trace['frame'] + 1) / rate

    def window(key):
        start, end = spec[key]
        return (times >= start) & (times < end)

    def rms(samples):
        return float(np.sqrt(np.mean(samples.astype('f8')**2)))

    early = window('early_stop_window_seconds')
    quiet = window('quiet_stop_window_seconds')
    restarted = window('restart_voice_window_seconds')
    # 取り消したスコアの直前に呼気があり、150 ms の保持区間に残る制御更新を調べる。
    updates = np.arange(((stop + 63) // 64) * 64, stop + int(rate * 0.14), 64)
    gate = trace['gate']
    predicted = gate[updates - 1] * math.exp(-(64 / rate) / 0.02)
    return {
        'early_stop_pcm_peak': float(np.max(abs(pcm[early]))),
        'quiet_stop_pcm_rms': rms(pcm[quiet]),
        'quiet_stop_gate_maximum': float(gate[quiet].max()),
        'restart_pcm_rms': rms(pcm[restarted]),
        'stopped_playhead_hidden': bool((trace['beat_step'][stop:restart] == -1).all()),
        'gate_recurrence_frames': int(updates.size),
        'gate_recurrence_max_absolute_error': float(max(abs(gate[updates] - predicted))),
    }


def measure(result, config, state, plan, reference, sources):
    limits = config['measurement']
    spec = limits['transport']
    tol = limits['seconds_absolute_tolerance']
    rate = result['sample_rate_hz']
    checks = result['checks']
    actual_events = plan['transport_events']
    expected_events = state['events']
    event_diff, _ = timing.compare(actual_events, expected_events, tol)
    upper_event_diff, _ = timing.compare(
        reference['transport_events'],
        [{key: event[key] for key in ('frame', 'clock_seconds')} for event in expected_events],
        tol,
    )
    registered_event_diff, _ = timing.compare(
        [event['clock_seconds'] for event in actual_events], spec['expected_event_clocks_seconds'], tol)
    cycle_diff, _ = timing.compare(state['cycle_hit_times'], spec['expected_cycle_hit_times_seconds'], tol)
    canceled_diff, _ = timing.compare(
        state['canceled_hit_times'], spec['expected_pending_canceled_hits_seconds'], tol)
    checks['registered_transport_commands'] = (
        event_diff is None and upper_event_diff is None and registered_event_diff is None
        and [event['next_step_before'] for event in actual_events] == spec['expected_next_steps_before_events']
    )
    checks['registered_cycle_times_and_cancellations'] = cycle_diff is None and canceled_diff is None
    checks['transport_pitch_slots_preserved'] = (
        plan['slot_midi_notes'] == reference['slot_midi_notes'] == limits['expected_slot_notes']
    )

    earliest, latest, pending = tracks(state, result['frames'], rate, len(limits['expected_slot_sounds']), tol)
    observations = {}
    for label, trace, pcm in sources:
        observations[label] = observe(trace, pcm, rate, state['stops'][0], state['restarts'][0], spec)
        valid = (trace['beat_step'] == earliest) | (trace['beat_step'] == latest)
        different = np.flatnonzero(~valid)
        observations[label]['first_unexpected_playhead_frame'] = int(different[0]) if different.size else None
        if label == 'candidate':
            checks['render_advances_on_registered_ticks'] = bool(np.array_equal(trace['beat_next_step'], pending))
    checks['independent_playhead_and_immediate_stop'] = all(
        row['stopped_playhead_hidden'] and row['first_unexpected_playhead_frame'] is None
        for row in observations.values()
    )
    checks['stopped_score_leaves_decaying_state'] = all(
        row['early_stop_pcm_peak'] >= spec['minimum_early_stop_pcm_peak']
        and row['gate_recurrence_max_absolute_error'] <= spec['gate_recurrence_absolute_tolerance']
        for row in observations.values()
    )
    checks['canceled_hit_does_not_sound_and_restart_is_audible'] = all(
        row['quiet_stop_pcm_rms'] <= spec['maximum_quiet_stop_pcm_rms']
        and row['quiet_stop_gate_maximum'] <= spec['maximum_quiet_stop_gate']
        and row['restart_pcm_rms'] >= spec['minimum_restart_pcm_rms']
        for row in observations.values()
    )
    result['transport'] = {
        'events': actual_events, 'independent_event_difference': event_diff,
        'upstream_event_difference': upper_event_diff, 'registered_event_clock_difference': registered_event_diff,
        'registered_cycle_time_difference': cycle_diff, 'registered_canceled_time_difference': canceled_diff,
        'cycle_hit_times_seconds': state['cycle_hit_times'], 'pending_canceled_hits_seconds': state['canceled_hit_times'],
        **observations,
    }
