"""先頭の無音を変えた3組で帯域と波形の変化を比較する。"""

import argparse
from pathlib import Path
import sys

from measure_csd_envelope_timing import verified_file
from measure_firefox_headphone_clock_plateaus_44100 import track
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/coreaudio-headphone-drift-44100-leading-silence.json'


def trial_result(folder, manifest, summary, phase_spec, evidence):
    direct_path, tap_path = (verified_file(folder, manifest, f'artifacts/native/{name}.json')
                             for name in ('native', 'tap'))
    evidence.extend((direct_path, tap_path))
    direct, tape = read(direct_path), read(tap_path)
    dstart, tstart = (summary[f'{point}_anchor']['origin_in_pcm'] for point in ('direct', 'tap'))
    clock = {
        'direct': [(r['markerOffset'] - dstart, r['hostTime']) for r in direct['frameMarks'] if 'hostTime' in r],
        'tap': [(r['offset'] - tstart, r['hostTime']) for r in tape['blocks']],
        'tick': tape['timebaseNumer'] / tape['timebaseDenom'],
    }
    result = {
        'capture_pass': all(summary['checks'].values()),
        'predictions': summary['predictions'],
        'events': summary['events'],
        'first_band_ratios': [point['amplitude_ratio'] for point in summary['windows'][0]['frequencies']],
        'plateaus': track(clock, summary, phase_spec),
    }
    if 'first_host_ticks' in summary:
        tap_anchor, output_anchor = tape['anchorHostTime'], direct['clock']['hostTicks']
        tap_first, output_first = tape['blocks'][0]['hostTime'], direct['frameMarks'][0]['hostTime']
        output_entry = direct['frameMarks'][0]['entered']
        if summary['first_host_ticks'] != {'tap': tap_first, 'direct': output_first}:
            raise ValueError('開始時刻の要約が収録した時計と一致しません')
        ms_per_tick = clock['tick'] / 1e6
        times = {'tap_anchor_to_output_anchor_ms': (output_anchor - tap_anchor) * ms_per_tick,
                 'tap_anchor_to_first_tap_ms': (tap_first - tap_anchor) * ms_per_tick,
                 'output_anchor_to_first_output_entry_ms': (output_entry - output_anchor) * ms_per_tick,
                 'first_output_entry_to_first_output_host_ms': (output_first - output_entry) * ms_per_tick}
        result.update(first_host_ticks=summary['first_host_ticks'], start_host_gap_ms=summary['start_host_gap_ms'],
                      startup_timing_ms=times)
    return result


def compare_pair(control, silence, spec):
    if not (control['capture_pass'] and silence['capture_pass']):
        return {'classification': 'capture_failed'}
    before, after = (row['events']['waveform_departure'] for row in (control, silence))
    if before['output_frame'] is None or after['output_frame'] is None:
        return {'classification': 'departure_missing'}
    deviation = spec['maximum_departure_deviation_frames']
    output_delta = after['output_frame'] - before['output_frame']
    signal_delta = after['source_frame'] - before['source_frame']
    if abs(before['output_frame'] - spec['reference_waveform_departure_output_frame']) > deviation:
        classification = 'control_outside_reference'
    elif abs(output_delta) <= deviation:
        classification = 'output_start'
    elif abs(signal_delta) <= deviation:
        classification = 'signal_start'
    else:
        classification = 'neither'
    return {'classification': classification, 'output_delta_frames': output_delta, 'signal_delta_frames': signal_delta}


def load_trials(case_path, fields):
    spec = read(case_path)
    phase_path = case_path.with_name(spec['phase_clock_case'])
    phase_base = phase_path.with_name(read(phase_path)['base_case'])
    phase_spec = read(phase_base) | read(phase_path)
    revision = phase_spec['upstream_revision']
    inputs = [case_path, case_path.with_name(spec['capture_base']), phase_path, phase_base, Path(__file__).resolve(),
              Path(__file__).with_name('measure_firefox_headphone_clock_plateaus_44100.py')]
    trials = {}
    for row in spec['trials']:
        ident = row['run_id']
        folder = WORKSPACE / 'runs' / ident
        path = folder / 'manifest.json'
        manifest = read(path)
        if (manifest['run_id'], manifest['case_id'], manifest['case_revision'], manifest['upstream_revision']) != (
                ident, spec['id'], spec['revision'], revision):
            raise ValueError(f'{ident} は登録した比較の収録と一致しません')
        inputs.append(path)
        result = {'capture_pass': False, 'manifest_status': manifest['status']}
        if any(entry['path'] == 'summary.json' for entry in manifest['outputs']):
            summary_path = verified_file(folder, manifest, 'summary.json')
            inputs.append(summary_path)
            summary = read(summary_path)
            if any(summary.get(key) != row[key] for key in fields):
                raise ValueError(f'{ident} の試行条件が登録値と一致しません')
            result['checks'] = summary['checks']
            if manifest['status'] == 'pass':
                result.update(trial_result(folder, manifest, summary, phase_spec, inputs))
        trials[ident] = {**result, **{key: row[key] for key in fields}}
    return spec, phase_spec, trials, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    spec, phase_spec, trials, inputs = load_trials(CASE, ('leading_frames',))

    def measure(folder, execute):
        pairs = [{'zero_prefix': a, 'silence_prefix': b, **compare_pair(trials[a], trials[b], spec)}
                 for a, b in spec['pairs']]
        counts = {condition: sum(pair['classification'] == condition for pair in pairs)
                  for condition in sorted({pair['classification'] for pair in pairs})}
        plateaus = [p for result in trials.values() for p in result.get('plateaus', ())]
        return {'checks': {'captures_valid': all(t['capture_pass'] for t in trials.values())},
                'predictions': {'output_start_in_at_least_two_pairs': counts.get('output_start', 0) >= 2,
                                'all_plateau_clocks_match': bool(plateaus) and all(
                                    abs(p['error_ppm']) <= phase_spec['maximum_slope_error_ppm'] for p in plateaus)},
                'pair_counts': counts, 'pairs': pairs, 'trials': trials}

    metadata = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': phase_spec['upstream_revision'],
                'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
