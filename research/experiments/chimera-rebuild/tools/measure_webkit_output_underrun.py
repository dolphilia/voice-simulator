"""公開WebKitの出力不足をモデル化し、Safariの採取波形と照合する。"""

import argparse
from itertools import groupby
from pathlib import Path
import sys

import numpy as np

import smooth_tap_marker
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_process_tap_calibration import read_json
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE
from measure_worklet_safari_song_audio_client import write_json


CASE = WORKSPACE / 'cases/webkit-output-underrun.json'


class OutputModel:
    """連続位置へ書くリングと、量子単位で生成される先行信号のFIFO。"""

    def __init__(self, study, condition, source):
        self.q = study['quantum_frames']
        self.capacity = study['fifo_capacity_frames']
        self.maximum_write = condition.get('maximum_write_frames', study['maximum_write_frames'])
        self.source = source
        self.ring = np.zeros((self.q * (study['output_requests'] + 1), 2), dtype='<f4')
        self.ring[:self.q] = source[:self.q]
        self.ring_signal = np.zeros(len(self.ring), dtype=bool)
        self.ring_signal[:self.q] = True
        self.fifo_begin = self.q
        self.graph_end = self.q + condition['initial_fifo_frames']
        self.write_frame = self.q
        self.read_frame = self.requested = self.serviced = 0
        self.last_sample = np.zeros(2, dtype='<f4')
        self.writes = []

    @property
    def fifo_available(self):
        return self.graph_end - self.fifo_begin

    def render_graph(self, frames):
        self.graph_end += ((frames + self.q - 1) // self.q) * self.q
        self.fifo_begin = max(self.fifo_begin, self.graph_end - self.capacity)

    def service(self, request, *, hold_graph=False, recovering=False):
        pending = self.requested - self.serviced
        self.serviced = self.requested
        deferred = 0
        while pending:
            length = min(pending, self.maximum_write)
            pending -= length
            fifo_before = self.fifo_available
            available = min(length, fifo_before)
            start = self.write_frame
            self.ring[start:start + available] = self.source[self.fifo_begin:self.fifo_begin + available]
            self.ring_signal[start:start + available] = True
            self.fifo_begin += available
            render = max(length - self.fifo_available, 0)
            if hold_graph:
                deferred += render
            else:
                self.render_graph(render)
            self.writes.append({'request': request, 'recovering': recovering, 'start': start, 'frames': length, 'fifo_before': fifo_before,
                                'fifo_zero_frames': length - available, 'render_request_frames': render})
            self.write_frame += length
        return deferred

    def device_request(self):
        start = self.read_frame
        end = start + self.q
        ring_end = self.write_frame
        if end <= ring_end:
            output = self.ring[start:end].copy()
            validity = self.ring_signal[start:end]
            if not (validity.all() or not validity.any()):
                raise ValueError('登録した量子の途中で信号とFIFOの無音が切り替わりました')
            kind = 'signal' if validity.all() else 'fifo_zero'
            status = 0
            self.last_sample = output[-1].copy()
            self.read_frame = end
        else:
            status = -1
            kind = 'ring_ramp' if self.last_sample.any() else 'ring_zero'
            output = np.zeros((self.q, 2), dtype='<f4')
            decrement = self.last_sample / np.float32(self.q)
            for frame in output:
                self.last_sample -= decrement
                frame[:] = self.last_sample
            self.last_sample.fill(0)
        self.requested += self.q
        return output, {'kind': kind, 'status': status, 'request_total': self.requested,
                        'read_range': [start, self.read_frame], 'ring_write_end': ring_end}


def simulate(study, settings, source):
    state = OutputModel(study, settings, source)
    resume = settings['resume_before_request']
    deferred = 0
    waves, requests = [], []
    for index in range(study['output_requests']):
        if resume and index == resume:
            state.render_graph(deferred)
            state.service(index, recovering=True)
        wave, record = state.device_request()
        waves.append(wave)
        requests.append(record)
        if index == 0:
            deferred = state.service(index, hold_graph=resume > 0)
        elif index >= resume:
            state.service(index)
    return np.concatenate(waves), requests, state.writes


def validate_model(study, settings, source, wave, requests, writes):
    q = study['quantum_frames']
    expected = settings['expected']
    kinds = [kind for kind, size in expected for _ in range(size)]
    observed = [row['kind'] for row in requests]
    recovery = [row['frames'] for row in writes if row['recovering']]
    checks = {'output_segments': observed == kinds, 'recovery_write_sizes': recovery == settings['expected_recovery_writes']}
    cursor, ramp_error, pcm_equal, zero = 0, 0.0, True, True
    for index, kind in enumerate(kinds):
        block = wave[index*q:(index+1)*q]
        if kind == 'signal':
            pcm_equal &= np.array_equal(block.view('<u4'), source[cursor:cursor+q].view('<u4'))
            cursor += q
        elif kind == 'ring_ramp':
            envelope = 1 - np.arange(1, q+1, dtype=float)[:, None] / q
            expected_ramp = source[cursor - 1] * envelope
            ramp_error = max(ramp_error, float(np.abs(block - expected_ramp).max()))
        else:
            zero &= not block.any()
    checks.update(source_pcm=bool(pcm_equal), zero_pcm=bool(zero), ramp_shape=ramp_error <= study['maximum_ramp_error'],
                  status_and_positions=all(row['request_total'] == (i + 1) * q
                    and ((row['status'], row['read_range'][1] - row['read_range'][0])
                         == ((-1, 0) if kind.startswith('ring_') else (0, q)))
                    for i, (row, kind) in enumerate(zip(requests, kinds, strict=True))))
    summary = {'segments': [[kind, sum(1 for _ in rows) * q] for kind, rows in groupby(observed)],
               'recovery_write_frames': recovery, 'maximum_ramp_error': ramp_error,
               'phase_delay_frames': sum(q for kind in observed if kind != 'signal')}
    return checks, summary


def compare_capture(tap, path, marker, study, model):
    spec = study['recorded_comparison']
    q = study['quantum_frames']
    segments = dict(model['segments'])
    ring_gap = segments['ring_ramp'] + segments['ring_zero']
    fifo_gap = segments['fifo_zero']
    prediction = ring_gap + fifo_gap
    quiet = tap['quiet']['spans']
    exact = tap['exact_stereo_zero']['spans']
    if len(quiet) != 2 or len(exact) != 2:
        return {'two_quiet_intervals': False}, {'quiet_intervals': quiet, 'exact_intervals': exact}
    phase_error = tap['phase_displacement_frames'] + prediction
    counts = [span['range'][1] - span['range'][0] for span in exact]
    checks = {'two_quiet_intervals': True, 'net_phase_shift': abs(phase_error) <= spec['maximum_phase_error_frames'],
              'quiet_widths': all(0 <= expected - seen <= spec['maximum_silent_interior_loss_frames']
                                  for expected, seen in zip((ring_gap, fifo_gap), counts, strict=True))}
    pulse_left, pulse_right = quiet[0]['range'][1], quiet[1]['range'][0]
    center = (pulse_left + pulse_right - q) // 2
    trim = spec['edge_exclusion_frames']
    x = np.fromfile(path, dtype='<f4').reshape(-1, 2).astype(float)
    difference = (x[:, 0] - x[:, 1]) / 2
    a, b = tap['pre_window'], tap['post_window']
    chips = smooth_tap_marker.chip_values(marker)

    def reference(indices, delay):
        step = (indices - a['start']) / (b['start'] - a['start'])
        phase = a['marker_position_frames'] + (indices - a['start']) + phase_error * step - delay
        gain = a['gain'] + (b['gain'] - a['gain']) * step
        return smooth_tap_marker.waveform(chips, marker, phase) * gain

    middle = np.arange(center + trim, center + q - trim)
    middle_expected = reference(middle, ring_gap)
    middle_error = float(np.linalg.norm(difference[middle] - middle_expected) / np.linalg.norm(middle_expected))
    checks['middle_signal_phase'] = middle_error <= spec['maximum_middle_waveform_relative_error']
    alignment = spec['extra_alignment_range_frames']
    boundary = center - ring_gap
    edges = []
    for shift in range(-alignment, alignment + 1):
        start = boundary + shift
        previous = reference(np.asarray([start - 1]), 0)[0]
        if abs(previous) < spec['minimum_boundary_signal_amplitude']:
            continue
        positions = np.arange(q//2, 3*q//4)
        samples = difference[start + positions]
        ramp = previous * (1 - (positions + 1) / q)
        edges.append({'shift': shift, 'previous_signal': float(previous),
                      'observed_to_previous_rms': float(np.sqrt(np.mean((samples / previous)**2))),
                      'ramp_residual_rms': float(np.sqrt(np.mean((samples - ramp)**2))),
                      'zero_residual_rms': float(np.sqrt(np.mean(samples**2)))})
    worst_ratio = max((row['observed_to_previous_rms'] for row in edges), default=None)
    return checks, {'silence_frames': counts, 'expected_gap_frames': [ring_gap, fifo_gap],
                    'gap_shortfall_frames': [ring_gap - counts[0], fifo_gap - counts[1]],
                    'quiet_onset_separation_frames': quiet[1]['range'][0] - quiet[0]['range'][0],
                    'phase_error_frames': phase_error, 'middle_tap_range': [int(middle[0]), int(middle[-1]) + 1],
                    'middle_waveform_relative_error': middle_error, 'first_underrun_estimate': boundary,
                    'edge_alignments': edges, 'maximum_quiet_to_boundary_ratio': worst_ratio,
                    'edge_prefers_zero': (worst_ratio <= spec['maximum_quiet_to_boundary_ratio'] if edges else None)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read_json(CASE)
    related = CASE.parent / study['capture_case']
    capture_study = read_json(related)
    marker_case = CASE.parent / capture_study['calibration_case']
    marker = read_json(marker_case)['marker']
    files = [CASE, related, marker_case, Path(__file__).resolve(), Path(smooth_tap_marker.__file__),
             WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/measure_worklet_safari_song_audio_client.py']
    captures = {}
    for name in study['capture_runs']:
        capture = run_manifest(name, capture_study['id'], study['upstream_revision'])
        summary = verified_path(capture, 'summary.json')
        pcm = verified_path(capture, 'artifacts/bulk/tap.f32le')
        if capture[1]['status'] != 'pass':
            parser.error(f'{name} の合格済み採取が必要です')
        files.extend((capture[0] / 'manifest.json', summary, pcm))
        captures[name] = read_json(summary)['trials']['bulk']['tap'], pcm

    def measure(artifacts, _execute):
        q = study['quantum_frames']
        mono = smooth_tap_marker.marker_pcm((study['output_requests'] + 2) * q, marker)
        source = np.column_stack((mono, -mono))
        checks, models, measured = {}, {}, {}
        for name, settings in study['model_conditions'].items():
            wave, requests, writes = simulate(study, settings, source)
            local, models[name] = validate_model(study, settings, source, wave, requests, writes)
            checks.update({f'{name}/{key}': bool(value) for key, value in local.items()})
            wave.tofile(artifacts / f'{name}.f32le')
            write_json(artifacts / f'{name}-positions.json', {'requests': requests, 'writes': writes})
        for name, (tap, path) in captures.items():
            local, measured[name] = compare_capture(tap, path, marker, study, models['long_pause'])
            checks.update({f'{name}/{key}': bool(value) for key, value in local.items()})
        return {'checks': checks, 'models': models, 'captures': measured}

    details = {'case_id': study['id'], 'upstream_revision': study['upstream_revision'],
               'webkit_revision': study['webkit_revision'], 'capture_runs': study['capture_runs'],
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, files, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
