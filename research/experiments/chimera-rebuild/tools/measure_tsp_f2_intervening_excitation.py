"""追加共鳴を固定し、F0によるTSPのF2採択の変化を測る。"""

import argparse
from collections import Counter
from itertools import product
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_harmonic_spacing as spacing
import measure_tsp_f2_intervening_resonance as resonance
import measure_tsp_f2_known_poles as known
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-intervening-excitation.json'


def wave_name(pitch, extra):
    variant = 'baseline' if extra is None else f'added-{extra}'
    return f'{variant}-f0-{pitch}-hz'


def render_signals(case, prior, cfg, out):
    signal, settings = prior['signal'], prior['measurement']
    rate = signal['sample_rate_hz']
    length = round(cfg['frame_seconds'] * rate)
    grid = np.arange(0, rate / 2 + 5, 5)
    base = signal['fixed_poles_hz']
    pitches = case['signal']['f0_hz']
    extras = [None, *case['signal']['added_pole_frequencies_hz']]
    waves, designs, frames, metadata = {}, [], [], []
    for pitch in pitches:
        period, remainder = divmod(rate, pitch)
        if remainder:
            raise ValueError(f'周期を整数標本で表せません ({pitch} Hz)')
        source = np.zeros(rate * signal['duration_seconds'])
        source[::period] = signal['pulse_amplitude']
        for extra in extras:
            truth = base if extra is None else [base[0], [extra, signal['added_pole_bandwidth_hz']], *base[1:]]
            pcm, _, design = known.design_wave(source, rate, truth, grid)
            waves[wave_name(pitch, extra)] = pcm
            harmonic, harmonic_error = spacing.harmonic_observation(
                pcm, design['sections'], period, signal['pulse_amplitude'], rate, case['measurement']['low_band_hz'])
            designs.append({'f0_hz': pitch, 'added_pole_hz': extra, 'period_samples': period, 'design_poles_hz': truth,
                            'low_band_strongest_harmonic_hz': harmonic, 'harmonic_error': harmonic_error,
                            'design_pole_error_hz': design['max_pole_error_hz'],
                            'design_wave_relative_error': design['max_wave_error'] / float(np.max(abs(pcm))),
                            'design_response_error_db': design['max_response_error_db']})
            for order, center in product(settings['orders'], settings['centers']):
                start = int(center * len(pcm)) - length // 2
                frames.append(pcm[start:start + length])
                metadata.append({'f0_hz': pitch, 'added_pole_hz': extra, 'order': order, 'center': center,
                                 'start_sample': start, 'excitation_phase_samples': start % period})
    np.savez_compressed(out / 'waveforms.npz', **waves)
    return waves, designs, frames, metadata, grid


def compare_archives(case, prior, paths, waves, rows, fixed):
    indexed = {(row['f0_hz'], row['added_pole_hz'], row['order'], row['center']): (row, probe)
               for row, probe in zip(rows, fixed, strict=True)}
    anchor = prior['signal']['f0_hz']
    frequencies = (None, *case['signal']['added_pole_frequencies_hz'])
    pitches = case['signal']['f0_hz']
    with np.load(paths['spacing_waves'], allow_pickle=False) as archive:
        same_control_waves = all(waves[wave_name(pitch, None)].tobytes() == archive[f'f0_{pitch}_hz'].tobytes()
                                 for pitch in pitches)
    with np.load(paths['resonance_waves'], allow_pickle=False) as archive:
        same_anchor_waves = all(waves[wave_name(anchor, extra)].tobytes() ==
                                archive['baseline' if extra is None else f'added-{extra}-hz'].tobytes()
                                for extra in frequencies)
    matches_control = []
    for old, reference in zip(tsp.read(paths['spacing_report'])['windows'], tsp.read(paths['spacing_probes']), strict=True):
        row, probe = indexed[old['f0_hz'], None, old['order'], old['center']]
        public = {name: value for name, value in probe.items() if name != 'roots'}
        matches_control.append(public == reference and row['start_sample'] == old['start_sample']
                               and row['selection'] == old['selected'])
    matches_anchor = []
    for old, reference in zip(tsp.read(paths['resonance_report'])['windows'], tsp.read(paths['resonance_probes']), strict=True):
        extra = old['added_pole_hz']
        if extra in frequencies:
            row, probe = indexed[anchor, extra, old['order'], old['center']]
            matches_anchor.append(probe == reference and all(row[name] == value for name, value in old.items()))
    windows = len(prior['measurement']['orders']) * len(prior['measurement']['centers'])
    return {
        'unmodified_controls_match_archived_wave_and_upstream': same_control_waves
        and len(matches_control) == len(pitches) * windows and all(matches_control),
        'anchor_matches_archived_wave_and_upstream': same_anchor_waves
        and len(matches_anchor) == len(frequencies) * windows and all(matches_anchor),
    }


def changed_windows(rows, reference_pitch, gap_boundary):
    anchor = {(r['added_pole_hz'], r['order'], r['center']): r for r in rows if r['f0_hz'] == reference_pitch}
    changes = []
    for row in rows:
        if row['added_pole_hz'] is None or row['f0_hz'] == reference_pitch:
            continue
        key = (row['added_pole_hz'], row['order'], row['center'])
        before = anchor[key]
        if row['association'] == before['association']:
            continue
        before_gap, current_gap = (x['added_mode_gap_from_selected_f1_hz'] for x in (before, row))
        model_eligible = bool(before['f2_near_eligible_poles'] and row['f2_near_eligible_poles'])
        crosses_gap = (before_gap is not None and current_gap is not None
                       and (before_gap > gap_boundary) != (current_gap > gap_boundary))
        changes.append({'f0_hz': row['f0_hz'], 'added_pole_hz': key[0], 'order': key[1], 'center': key[2],
                        'association': [before['association'], row['association']],
                        'gap_from_selected_f1_hz': [before_gap, current_gap],
                        'model_f2_eligible_in_both': model_eligible, 'crosses_gap': crosses_gap,
                        'first_difference_from_model_f2': [before['first_difference_from_model_f2'],
                                                           row['first_difference_from_model_f2']]})
    return changes


def measure(case, prior, spacing_case, cfg, paths, out, execute):
    spec, settings = prior['signal'], prior['measurement']
    rate = spec['sample_rate_hz']
    pitches, additions = case['signal']['f0_hz'], case['signal']['added_pole_frequencies_hz']
    if (pitches != spacing_case['f0_hz'] or spec['fixed_poles_hz'] != spacing_case['fixed_poles_hz']
            or spec['f0_hz'] not in pitches or not set(additions) <= set(spec['added_pole_frequencies_hz'])
            or rate != cfg['sample_rate_hz'] / cfg['decimation']
            or settings['centers'] != cfg['reference_centers'] or set(settings['orders']) != set(cfg['order'].values())
            or settings['pre_emphasis_coefficient'] != cfg['pre_emphasis']
            or settings['comparison_gap_hz'] != cfg['f2_min_gap_hz']):
        raise ValueError('先行ケースと励振、共鳴、固定TSPの設定が一致しません')

    waves, designs, frames, metadata, grid = render_signals(case, prior, cfg, out)
    fixed = envelope.fixed_spectra(frames, grid, out, execute, orders=[row['order'] for row in metadata], include_roots=True)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = [resonance.inspect_window(frame, probe, rate, cfg, spec['fixed_poles_hz'][1][0],
                                     settings['association_tolerance_hz'], row)
            for frame, probe, row in zip(frames, fixed, metadata, strict=True)]
    checks = compare_archives(case, prior, paths, waves, rows, fixed)
    pole_limit = cfg['frequency_bandwidth_agreement_hz']
    checks.update(
        registered_windows_and_finiteness=len(rows) == len(pitches) * (1 + len(additions))
        * len(settings['orders']) * len(settings['centers'])
        and all(frame.shape == (round(cfg['frame_seconds'] * rate),) and np.isfinite(frame).all() for frame in frames),
        analytic_design_and_periodic_response=all(
            row['design_pole_error_hz'] is not None and row['design_pole_error_hz'] <= settings['design_pole_error_limit_hz']
            and row['design_wave_relative_error'] <= settings['design_wave_relative_error_limit']
            and row['design_response_error_db'] <= settings['design_response_error_limit_db']
            and row['harmonic_error'] <= settings['harmonic_error_limit'] for row in designs),
        independent_roots_and_selection=all(
            row['errors']['complex_roots'] <= settings['raw_root_distance_limit']
            and all(value is not None and value <= pole_limit for key, value in row['errors'].items()
                    if key != 'complex_roots') for row in rows))
    changes = changed_windows(rows, spec['f0_hz'], settings['comparison_gap_hz'])
    switched = [row for row in changes if set(row['association']) == {'model_f2', 'added_mode'}]
    return {'checks': checks,
            'predictions': {'f0_changes_selection_at_fixed_added_pole': bool(switched),
                            'some_switches_leave_model_f2_eligible_in_both_windows':
                            any(row['model_f2_eligible_in_both'] and row['crosses_gap'] for row in switched)},
            'reference_f0_hz': spec['f0_hz'], 'changes_from_reference': changes,
            'counts_by_condition': {wave_name(pitch, extra): dict(Counter(
                row['association'] for row in rows if row['f0_hz'] == pitch and row['added_pole_hz'] == extra))
                for pitch, extra in product(pitches, (None, *additions))},
            'designs': designs, 'windows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference, spaced = (tsp.open_run(case[name], revision) for name in ('resonance_reference', 'spacing_reference'))
    prior, prior_path = saved_case(reference, resonance.CASE)
    spacing_case, spacing_path = saved_case(spaced, spacing.CASE)
    upstream = tsp.open_run(prior['tsp_reference'], revision)
    cfg, config_path = saved_case(upstream, tsp.CASE)
    artifacts = {'waves': 'artifacts/waveforms.npz', 'probes': 'artifacts/upstream-envelopes.json',
                 'report': 'summary.json'}
    paths = {f'{prefix}_{key}': tsp.verified_path(run, name)
             for prefix, run in (('resonance', reference), ('spacing', spaced))
             for key, name in artifacts.items()}
    tools = ('measure_tsp_f2_intervening_resonance', 'measure_tsp_f2_harmonic_spacing',
             'measure_tsp_f2_harmonic_bandwidth', 'measure_tsp_f2_bandwidth_envelope', 'measure_tsp_f2_known_poles',
             'measure_tsp_stressed_vowel_formants', 'measure_tsp_f2_bandwidth_held_out', 'measure_tsp_f2_annotation',
             'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline')
    inputs = [CASE, Path(__file__).resolve(), prior_path, spacing_path, config_path, *paths.values(), envelope.PROBE,
              *(run[0] / 'manifest.json' for run in (reference, spaced, upstream)),
              *(WORKSPACE / f'tools/{name}.py' for name in tools),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, prior, spacing_case, cfg['measurement'], paths, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
