"""Water danceの鍵盤入力、声門周期、放射の低域を照合する。"""

from pathlib import Path

import numpy as np

from measure_alligator_bellow import CALL_IDS, OWNERSHIP
from measure_alligator_dance import (SPECTRAL_FIELDS, dance_definition_matches, measure_spectra, spectral_window,
                                     summarize_spectrum)
from measure_seal_sustain_pcm import independent_output
from measure_songbird_syrinx import compare
from measure_worklet_midi_alligator_call import acoustic_window, main
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-alligator-dance.json'


def bounds(candidate, pcm, voice, events, starts, pitches, factor, config, spec):
    rate = voice['sample_rate_hz']
    keys = spec['dance_keys']
    fields = ('call_id', 'gate_target', 'gate', 'target_pitch_hz', 'pitch_hz', 'target_chaos', 'chaos',
              'target_mouth', 'oral_tip_area_cm2', 'glottis_phase', 'glottis_area_cm2', 'glottis_flow_cm3_s',
              'wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s', 'radiation_cm3_s2')
    transitions = []
    for frame in starts:
        sample = frame * factor
        transitions.append({'frame': frame, 'before': {key: float(candidate[key][sample - 1]) for key in fields},
                            'after': {key: float(candidate[key][sample]) for key in fields}})
    before, after = (transitions[-1][side] for side in ('before', 'after'))
    phase_advance = (after['glottis_phase'] - before['glottis_phase']) % 1.0
    chaos_low, chaos_high = config['retrigger_chaos_target_before']
    releases = [acoustic_window(candidate, pcm, event['frame'], config['release_window_seconds'], rate, factor)
                for event in events if not event['midi_call']['pressed']]
    ends = (np.flatnonzero(np.diff(candidate['call_id']) < 0) + 1).tolist()
    end = ends[0] // factor if len(ends) == 1 else None
    checks = {
        'dance_starts_set_keyed_pitch_and_envelope': all(
            row['after']['call_id'] == CALL_IDS['dance'] and row['after']['gate_target'] == 1
            and row['after']['target_chaos'] == keys['chaos_first'] and row['after']['target_mouth'] == keys['mouth']
            and abs(row['after']['target_pitch_hz'] - keys['pitch_hz'] * pitch / keys['reference_pitch_hz'])
            <= config['control_tolerance'] for row, pitch in zip(transitions, pitches, strict=True)),
        'dance_retrigger_keeps_breath_and_phase': before['gate_target'] == after['gate_target'] == 1
            and abs(after['gate'] - before['gate']) <= config['control_tolerance']
            and chaos_low <= before['target_chaos'] <= chaos_high and 0 < after['chaos'] < before['chaos']
            and before['pitch_hz'] < after['pitch_hz'] < after['target_pitch_hz']
            and 0 < phase_advance < spec['pitch_hz_limits'][1] / (rate * factor),
        'dance_outlasts_release': all(row['call_ids'] == [CALL_IDS['dance']]
            and row['gate_min'] >= config['minimum_release_gate']
            and row['glottis_area_peak_cm2'] >= config['minimum_release_glottis_peak_cm2']
            and row['pcm_rms'] >= config['minimum_release_pcm_rms'] for row in releases),
        'dance_natural_end_restores_manual_targets': end is not None and ends[0] % factor == 0
            and abs((end - starts[-1]) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= config['control_frames'] / rate + config['clock_tolerance_seconds']
            and np.all(candidate['call_id'][end * factor:] == 0)
            and np.all(candidate['gate_target'][end * factor:] == 0)
            and all(np.all(candidate['target_' + key][end * factor:] == voice['shape'][key])
                    for key in OWNERSHIP['dance']),
    }
    return checks, {'start_transitions': transitions, 'release_windows': releases,
                    'natural_end_frame': end, 'retrigger_glottis_phase_advance_cycles': phase_advance}


def measure_low_frequencies(candidate, upstream, pcm, case, variant, spec):
    rate = case['sample_rate_hz']
    factor = len(candidate) // len(pcm)
    internal_rate = rate * factor
    config = variant['midi_measurement']
    limits = spec['spectral_window'] | {'seconds': config['spectral_window_seconds']}
    spectrum_spec = spec | {'spectral_window': limits}
    tolerance = spec['tolerances']
    total = candidate['wall_cm3_s'] + candidate['oral_cm3_s'] + candidate['nasal_cm3_s']
    derivative = np.diff(total, prepend=0.0) * internal_rate
    _, dc, reconstructed_pcm = independent_output(derivative, rate, factor, case['level'], spec['output'])
    last = slice(factor - 1, None, factor)
    differences = {
        'radiation_cm3_s2': compare(candidate['radiation_cm3_s2'], derivative, tolerance['radiation_cm3_s2']),
        'dc_removed': compare(candidate['dc_removed'][last], dc, tolerance['dc_removed']),
        'pcm_f32': compare(pcm, reconstructed_pcm, tolerance['pcm_f32']),
    }
    checks = {f'independent.{name}': data['passed'] for name, data in differences.items()}
    readings = []
    starts = [event['frame'] for event in case['events']]
    for key, event, area_range, boundary in zip(
            ('first', 'second'), case['events'], config['spectral_peak_area_hz'], (*starts[1:], len(pcm)), strict=True):
        start, pitch = event['frame'], event['play_call']['pitch_hz']
        sample_window = spectral_window(internal_rate, start * factor, limits['seconds'])
        output_window = spectral_window(rate, start, limits['seconds'])
        subcase = {'first_control': start, 'peak_area_hz': area_range}
        flags, spectra = measure_spectra(candidate, upstream, pcm, case, subcase, spectrum_spec)
        area = spectra['candidate']['glottis_area_cm2']
        phase = candidate['glottis_phase'][sample_window]
        wraps = np.flatnonzero(np.diff(phase) < spec['cycle_model']['phase_wrap_threshold']) + 1
        periods = np.diff(wraps)
        measured_hz = internal_rate / float(np.mean(periods)) if periods.size else None
        stage_spectra = {
            'total_flow': summarize_spectrum(total[sample_window], internal_rate, limits),
            'differentiated_flow': summarize_spectrum(derivative[sample_window], internal_rate, limits),
            'dc_removed': summarize_spectrum(dc[output_window], rate, limits),
        }
        ratios = {name: data['bands'][1]['rms'] / data['bands'][0]['rms'] if data['bands'][0]['rms'] > 0 else None
                  for name, data in stage_spectra.items()}
        flags.update({
            'uninterrupted_measurement_window': start <= output_window.start < output_window.stop <= boundary
                and np.all(candidate['call_id'][sample_window] == CALL_IDS['dance']),
            'cycle_frequency_near_midi_target': periods.size >= config['minimum_complete_cycles']
                and abs(measured_hz - pitch) <= pitch * config['maximum_cycle_frequency_relative_error'],
            'propagation_peaks_follow_glottal_area': all(
                abs(spectra['candidate'][field]['peak_hz'] - area['peak_hz'])
                <= config['propagation_peak_tolerance_bins'] * area['bin_hz'] for field in SPECTRAL_FIELDS[1:]),
            'pcm_peak_near_second_harmonic': abs(spectra['candidate']['pcm_f32']['peak_hz'] - 2 * area['peak_hz'])
                <= config['pcm_second_harmonic_tolerance_bins'] * area['bin_hz'],
            'high_to_low_rms_ratio_increases': all(value is not None for value in ratios.values())
                and ratios['total_flow'] < ratios['differentiated_flow'] < ratios['dc_removed'],
        })
        checks.update({f'{key}.{name}': value for name, value in flags.items()})
        readings.append({'frames': [output_window.start, output_window.stop], 'midi_target_hz': pitch,
                         'complete_cycles': len(periods), 'cycle_frequency_hz': measured_hz, 'spectra': spectra,
                         'output_stages': stage_spectra, 'upper_band_to_low_band_rms': ratios})
    first_hz, second_hz = (row['cycle_frequency_hz'] for row in readings)
    checks['phase_cycles_cross_frequency_boundary'] = first_hz is not None and second_hz is not None and (
        first_hz < config['frequency_boundary_hz'] < second_hz)
    return checks, {'readings': readings, 'radiation_reconstruction': differences}


if __name__ == '__main__':
    raise SystemExit(main(CASE, bounds, dance_definition_matches, driver=Path(__file__), description=__doc__,
                          extra_inputs=(WORKSPACE / 'tools/measure_alligator_dance.py',),
                          extra_measurement=('spectrum', measure_low_frequencies)))
