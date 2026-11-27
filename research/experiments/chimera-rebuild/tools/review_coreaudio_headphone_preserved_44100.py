"""先行接続の保存済みPCMで、当初より長い区間の帯域変化を測る。"""

import argparse
from itertools import groupby
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_firefox_headphone_response_44100 import continuous_blocks, read_stereo
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/coreaudio-headphone-drift-44100-attach-preserved.json'


def analyze(sources, spec, hardware_frames):
    prior, direct_pcm, taped_pcm, output, tape = sources
    before, direct_meta, tap_meta = map(read, (prior, output, tape))
    origin = before['anchor']['origin_in_pcm']
    direct, tap = map(read_stereo, (direct_pcm, taped_pcm))
    first, stop, width, hop = (spec[key] for key in ('first_frame', 'last_exclusive', 'window_frames', 'hop_frames'))
    direct_blocks = continuous_blocks(direct_meta['frameMarks'], 'markerOffset', 'sampleTime',
                                      first, stop, hardware_frames, len(direct))
    tap_blocks = continuous_blocks(tap_meta['blocks'], 'offset', 'sampleTime', origin + first, origin + stop,
                                   hardware_frames, len(tap))
    checks = {f'{tag}_clock': bool(rows and all('hostTime' in row for row in rows)
                                   and all(b['hostTime'] > a['hostTime'] for a, b in zip(rows, rows[1:])))
              for tag, rows in (('direct', direct_blocks), ('tap', tap_blocks))}
    result = {'checks': checks, 'tap_origin_in_pcm': origin}
    if not all(checks.values()):
        return result
    a, b = ((pcm[:, 0] - pcm[:, 1]) * .5 for pcm in (direct, tap))
    starts = range(first, stop - width + 1, hop)
    bins = spec['tone_bins']
    ratios = np.asarray([np.fft.rfft(b[n + origin:n + origin + width])[bins] / np.fft.rfft(a[n:n + width])[bins]
                         for n in starts])
    known = np.asarray([[f['amplitude_ratio'] * np.exp(1j * np.deg2rad(f['raw_phase_degrees']))
                         for f in row['frequencies']] for row in before['windows']])
    count = (spec['old_last_exclusive'] - width - first) // hop + 1
    checks['old_window_count'] = len(known) == count
    if not checks['old_window_count']:
        return result
    error = float(np.max(abs(known - ratios[:count])))
    checks['old_complex_ratios'] = error <= spec['maximum_complex_ratio_error_in_old_window']
    amplitude = abs(ratios[:, spec['frequencies_hz'].index(19845)])
    labels = np.where(amplitude >= spec['wide_band_lower_limit'], 'wide',
                      np.where(amplitude < spec['reduced_band_upper_limit'], 'reduced', 'transition'))
    spans = []
    for label, group in groupby(enumerate(labels), key=lambda row: row[1]):
        indices = [i for i, _ in group]
        if label != 'transition' and len(indices) >= spec['minimum_consecutive_windows']:
            spans.append({'band': str(label), 'first_center_frame': starts[indices[0]] + width // 2,
                          'last_center_frame': starts[indices[-1]] + width // 2, 'windows': len(indices),
                          'median_amplitude_ratio': float(np.median(amplitude[indices]))})
    lows = [row['first_center_frame'] for previous, row in zip(spans, spans[1:])
            if previous['band'] == 'wide' and row['band'] == 'reduced']
    late_lows = [frame for frame in lows if frame >= spec['old_last_exclusive']]
    return {**result, 'windows': len(starts), 'old_window_maximum_complex_ratio_difference': error, 'spans': spans,
            'band_drop_frames_in_extended_region': late_lows, 'reference_drop_seen': any(
                abs(frame - spec['reference_late_event_frame']) <= spec['maximum_event_difference_frames'] for frame in late_lows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    source_case = CASE.with_name(case['source_case'])
    configured = read(source_case)
    capture_base = source_case.with_name(configured['capture_base'])
    reference_id = case['timing_run']
    reference_folder = WORKSPACE / 'runs' / reference_id
    reference_manifest = read(reference_folder / 'manifest.json')
    revision = reference_manifest['upstream_revision']
    reference = verified_file(reference_folder, reference_manifest, 'summary.json')
    inputs = [CASE, source_case, capture_base, Path(__file__).resolve(), reference_folder / 'manifest.json', reference,
              Path(__file__).with_name('measure_firefox_headphone_response_44100.py')]
    trials = {}
    for key in case['source_runs']:
        registered, = [row for row in configured['trials'] if row['run_id'] == key]
        if 'tap_attach_after_release_seconds' in registered:
            parser.error('先行接続の収録を指定してください')
        saved, manifest = hydrate_run(key, configured['id'], revision)
        if manifest['case_revision'] != configured['revision']:
            parser.error('保存済み収録のケース版が一致しません')
        files = [verified_file(saved, manifest, name) for name in ('summary.json', 'artifacts/native/native.f32le',
                 'artifacts/native/tap.f32le', 'artifacts/native/native.json', 'artifacts/native/tap.json')]
        inputs.extend([saved / 'manifest.json', *files])
        trials[key] = files

    def measure(folder, execute):
        width = read(capture_base)['capture_direct']['observed_output_expected_frames']
        result = {key: analyze(files, case['analysis'], width) for key, files in trials.items()}
        return {'checks': {'all_preserved_trials_valid': all(all(row['checks'].values()) for row in result.values())},
                'prediction_matched': sum(row.get('reference_drop_seen', False) for row in result.values()) >= 2,
                'trials': result}

    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
