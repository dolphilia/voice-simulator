"""実時間IPAのスケジュール、PCM、処理時間とネイティブの割り当てを照合する。"""

from measure_worklet_realtime import compare_scored_capture, read_quantum_allocations


def compare(spec, config, artifacts, browser_run, report, pcm, events, *, allocation_log=None):
    fields = ('tract', 'glottal', 'speech', 'gestures')
    checks, result = compare_scored_capture(
        spec, config, artifacts, browser_run, report, pcm, fields, browser_run['stopped'])
    m = config['measurement']
    result['native_allocations'] = read_quantum_allocations(
        allocation_log or artifacts / 'native-allocations.log', 'ipa_render_allocations=', m['output_frames'],
        m['expected_render_quantum_frames'], spec['timing_exclude_first_blocks'])
    peak = float(abs(pcm[-spec['final_silence_window_frames']:]).max())
    events_fit = all(event is not None and 0 <= event - bound <= spec['release_event_tolerance_frames']
                     for event, bound in zip(events, (m['expected_cli_closure_frame'], m['expected_cli_release_frame']),
                                             strict=True))
    checks['live_closure_release_and_silence'] = events_fit and peak <= spec['final_silence_peak_max']
    result['final_pcm_peak'] = peak
    return checks, result
