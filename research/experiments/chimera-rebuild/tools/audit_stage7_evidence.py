"""第7段階の実行記録を、機能別の観測と現行のビルドに照合する。"""

import argparse
from collections import Counter
import csv
from ctypes import CDLL, c_ulong
from hashlib import sha256 as hash_bytes
from io import BytesIO
import json
import math
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
import wave
from zipfile import ZipFile

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

from audit_plan_evidence import ROOT, RUNS, read_json, read_record
from audit_stage7_f2_annotations import annotation_observations
from audit_stage7_listening_runs import CORPORA, RUN_ID, evaluation_run_inputs, listening_observations
from audit_stage7_physical_midi import physical_midi_observations
from audit_stage7_renewal import audit_renewal
from audit_stage7_songbird import audit_songbird, songbird_inputs
import measure_tsp_f2_bandwidth_envelope as formants
import measure_tsp_f2_annotation_again_pre_emphasis as again_pre_emphasis
import measure_tsp_f2_annotation_w06_pre_emphasis as w06_pre_emphasis
import measure_tsp_again_f2_term_effect as again_f2_term
import measure_tsp_f2_training_reference_sensitivity as f2_training_reference
import measure_tsp_f2_training_reference_ten_speakers as f2_ten_speakers
import measure_tsp_f2_reference_centre_width as f2_centre_width
import measure_tsp_f2_reference_pooled_sexes as f2_pooled
import measure_tsp_f2_pooled_reference_sweep as f2_pooled_sweep
import measure_tsp_f2_pooled_reference_held_fl as f2_held_fl
import measure_tsp_f2_held_synth_over_sets as f2_over_sets
import measure_tsp_f2_full_held_women as f2_full_held
import measure_tsp_f2_full_held_candidate as f2_full_candidate
import measure_tsp_fk61_pcm_first_difference as fk61_pcm
import measure_tsp_fk61_lip_onset as fk61_lip
import measure_tsp_fk61_lip_volume_increment as fk61_volume
import measure_tsp_fk61_lip_area_origin as fk61_area
import measure_tsp_fk61_lip_front_origin as fk61_front
import measure_tsp_fk61_centerline_length_origin as fk61_centerline
import measure_tsp_fk61_lip_front_radiation as fk61_residual
import measure_tsp_fk61_lip_front_terminal_branch as fk61_terminal
import measure_tsp_fk61_node42_volume_source as fk61_node42
import measure_tsp_fk61_node42_area_origin as fk61_node42_area
import measure_tsp_fk61_ray43_intersection as fk61_ray43
import measure_tsp_fk61_lower_lip_bernstein_render as fk61_bernstein
import measure_tsp_fk61_pcm2937_output as fk61_pcm2937
import measure_tsp_fk61_pcm2937_lip_window as fk61_lip_window
import measure_tsp_fk61_pcm2937_terminal_load as fk61_terminal_load
import measure_tsp_fk61_pcm2937_branch_drive as fk61_branch_drive
import measure_tsp_fk61_pcm2937_branch_seed as fk61_branch_seed
import measure_tsp_fk61_branch_first_difference as fk61_branch_first
import measure_tsp_fk61_oral_onset_inflow as fk61_oral_inflow
import measure_tsp_fk61_node40_expanded_volume as fk61_node40_expanded
import measure_tsp_fk61_control5632_mouth_flow as fk61_control5632
import measure_tsp_fk61_control5632_upstream_drive as fk61_upstream_drive
import measure_tsp_fk61_control5632_oral_inlet as fk61_oral_inlet
import measure_tsp_fk61_control5632_oral_geometry as fk61_oral_geometry
import measure_tsp_fk61_control5504_oral_history as fk61_oral_history
import measure_tsp_fk61_onset_to_control5504_volume_history as fk61_onset_history
import measure_tsp_fk61_control4992_5120_area_targets as fk61_area_targets
import measure_tsp_fk61_control4992_5120_indexed_area as fk61_indexed_area
import measure_tsp_fk61_control4992_5120_indexed_area_paired as fk61_paired_area
import measure_tsp_fk61_control4992_5120_expanded_volume_paired as fk61_paired_volume
import measure_tsp_fk61_pcm16682_rounding as fk61_pcm16682
import measure_tsp_fk61_full_pcm_rounding as fk61_full_pcm
import measure_tsp_fk61_02_full_pcm_rounding as fk61_02_full_pcm
import measure_tsp_mk61_02_full_pcm_rounding as mk61_02_full_pcm
import measure_tsp_held_out_pcm_rounding as held_out_pcm_rounding
import measure_csd_en001a_two_phrase_pcm_rounding as csd_two_phrase_rounding
import measure_csd_en005a_full_pcm_rounding as csd_held_out_rounding
import measure_csd_en035a_full_pcm_rounding as csd_en035a_rounding
import measure_csd_en001a_first_lip_load as csd_first_lip_load
import measure_csd_en001a_initial_oral_geometry as csd_initial_oral
import measure_csd_en001a_centerline_coordinate_swap as csd_centerline_swap
import measure_csd_en001a_pharynx_cell7_source as csd_pharynx_cell7
import measure_csd_en001a_pharynx_cell7_first_block as csd_pharynx_block
import measure_csd_en001a_pharynx_cell7_compliance_pulse as csd_pharynx_pulse
import measure_csd_en001a_pharynx_cell7_branch_history as csd_pharynx_history
import measure_tsp_again_initial_tip_mfa as again_tip
import measure_tsp_held_out_matched_speech as matched_speech
import measure_tsp_matched_pitch_drift_mfa as cohort_drift
import measure_tsp_matched_speech_formants as matched_formants
import measure_tsp_matched_speech_mfa as matched_mfa
import measure_tsp_seems_amplitude_shimmer as seems_shimmer
import measure_tsp_seems_drift_only as seems_drift
import measure_tsp_seems_initial_tip as seems_tip
import measure_tsp_seems_period_jitter as seems_jitter
import measure_tsp_seems_pressure_replay as seems_pressure
import measure_tsp_tall_f2_boundary_grid as tall_f2_grid
import measure_tsp_tall_initial_tip_mfa as tall_tip
import measure_tsp_tall_gmm_paths as tall_gmm
import measure_tsp_tall_gmm_frame_swap as tall_gmm_swap
import measure_tsp_tall_gmm_frame_subsets as tall_gmm_subsets
import measure_tsp_tall_mfa_cmvn as tall_cmvn
import measure_tsp_tall_mfa_preroll as tall_preroll
import measure_tsp_tall_mfcc_final_compression as tall_mfcc_final
import measure_tsp_tall_mfcc_input_compression as tall_mfcc
import measure_tsp_tall_output_gain_mfa as tall_gain
import measure_tsp_tall_recording_f2_boundary_grid as tall_recording_grid
from measure_csd_envelope_timing import verified_file
from measure_duet_child_output_gain import envelope_response
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/plan-evidence-stage7.json'
WEB = ROOT / 'web/prototypes/chimera-research'


def midi_endpoint_counts():
    if sys.platform != 'darwin':
        return None
    midi = CDLL('/System/Library/Frameworks/CoreMIDI.framework/CoreMIDI')
    counts = {}
    for label, symbol in [('inputs', 'MIDIGetNumberOfSources'), ('outputs', 'MIDIGetNumberOfDestinations')]:
        count = getattr(midi, symbol)
        count.argtypes = []
        count.restype = c_ulong
        counts[label] = count()
    return counts


def completed_score(run, name, syllables):
    scope = RUNS / run / 'artifacts' / name
    data = read_json(scope / 'settings.json')['song']
    plan = data['plan']
    measured = {'syllables': len(data['syllables']), 'notes': len(plan['notes']),
                'unavailable': plan['unavailable_speech_symbols']}
    return measured, measured == {'syllables': syllables, 'notes': syllables, 'unavailable': []}


def matched_case(run, manifest, item, verified_paths):
    expected = item['expected_case']
    basename = item.get('case_file', f'{expected}.json')
    matches = [name for name in verified_paths if Path(name).name == basename]
    if len(matches) > 1:
        local = [name for name in matches if not (ROOT / name).is_relative_to(RUNS)]
        if len(local) != 1:
            return None
        retained = run / manifest['source_snapshot'] / local[0]
        digest = sha256(retained)
        if any(sha256(ROOT / name) != digest for name in matches if name != local[0]):
            return None
        matches = local
    if len(matches) != 1:
        return None
    name, = matches
    source = ROOT / name
    if not source.is_relative_to(RUNS):
        source = run / manifest['source_snapshot'] / name
    return name if read_json(source).get('id') == expected else None


def keeps_previous_evidence(case, records):
    previous = case['previous']
    path = RUNS / previous['run']
    manifest_path = path / 'manifest.json'
    if sha256(manifest_path) != previous['manifest_sha256']:
        return False
    verified, outputs = read_record(previous['run'], case['upstream_revision'], expected_failure=False)
    previous_definition = str(CASE.relative_to(ROOT))
    if verified['errors'] or 'summary.json' not in outputs or previous_definition not in verified['case_inputs']:
        return False
    older = read_json(path / 'summary.json')['records']
    snapshot = path / read_json(manifest_path)['source_snapshot'] / previous_definition
    older_case = read_json(snapshot)
    registered = {item['run']: item for item in case['evidence']}
    identifiers = ('topic', 'case_id', 'required_checks')
    return (set(older) == {item['run'] for item in older_case['evidence']}
            and set(older_case['required_topics']) == set(case['required_topics'])
            and all(registered.get(item['run']) == item for item in older_case['evidence'])
            and all(name in records and all(old[key] == records[name][key] for key in identifiers)
                    for name, old in older.items()))


def raw_followup_coverage(case, records):
    runs = {row['expected_case']: RUNS / row['run'] for row in case['evidence'] if 'manifest_sha256' in row}
    expected = case['followup_expectations']

    def source_case(case_id):
        run = runs[case_id]
        manifest = read_json(run / 'manifest.json')
        return read_json(run / manifest['source_snapshot'] / records[run.name]['case_definition'])

    prompts = read_json(runs['worklet-midi-browser-prompt'] / 'artifacts/native-prompts.json')
    permission_states = {page: [report[key]['permission'] for key in ('before', 'denied', 'afterReset', 'granted')]
                         for page, report in prompts['reports'].items()}
    checks = {'chrome_dialogs_and_states_from_raw': (
        set(permission_states) == set(expected['native_prompt_pages'])
        and all(states == ['prompt', 'denied', 'prompt', 'granted'] for states in permission_states.values())
        and all([(entry['requested'], entry['pressed']) for entry in report['dialogs']] == [('deny', True), ('allow', True)]
                and report['disconnected']['probe']['subscriptions'] == [0] for report in prompts['reports'].values()))}

    native_input = source_case('worklet-midi-coremidi')['input']
    note_on, note_off = native_input['note_on'], native_input['note_off']
    second_on = source_case('worklet-midi-coremidi-shared-note')['shared_note']['second_note_on']
    midi = {}
    for case_id, action, packets in (('worklet-midi-coremidi', 'note-off', [note_on, note_off]),
                                    ('worklet-midi-coremidi-unplug', 'remove-source', [note_on]),
                                    ('worklet-midi-coremidi-shared-note', 'remove-two-sources', [note_on, second_on])):
        artifacts = runs[case_id] / 'artifacts'
        browser = read_json(artifacts / 'coremidi-browser.json')
        targets = {}
        for page, target in browser['targets'].items():
            final = target['disconnected']
            targets[page] = {'packets': [message['bytes'] for message in final['messages']],
                             'all_packets_trusted': all(message['trusted'] for message in final['messages']),
                             'trusted_disconnects': sum(event['trusted'] and event['state'] == 'disconnected'
                                                        for event in final['topology']),
                             'remaining_subscriptions': final['subscriptions']}
        browser_rate, pcm = wavfile.read(artifacts / 'candidate.wav')
        cli_rate, cli = wavfile.read(artifacts / 'candidate-cli.wav')
        pcm_ok = (cli_rate == browser_rate and pcm.ndim == cli.ndim == 1 and pcm.dtype == cli.dtype == np.float32
                  and len(pcm) > 0 and np.isfinite(pcm).all() and np.array_equal(pcm.view('u4'), cli.view('u4')))
        checks[f'{action}_events_and_pcm_from_raw'] = (
            browser.get('releaseAction', 'note-off') == action and set(targets) == set(expected['native_midi_targets'])
            and all(t['packets'] == packets and t['all_packets_trusted'] and t['remaining_subscriptions'] == 0
                    and t['trusted_disconnects'] == expected['native_removal_counts'][action] for t in targets.values())
            and pcm_ok)
        midi[action] = {'targets': targets, 'sample_rate_hz': browser_rate, 'pcm_frames': len(pcm)}

    duet = {}
    for body in ('child', 'mixed'):
        case_id = f'duet-{body}-output-gain'
        registered = source_case(case_id)
        artifacts = runs[case_id] / 'artifacts'
        candidate, upstream = (np.fromfile(artifacts / f'{stem}.f32le', dtype='<f4') for stem in ('matched', 'upstream'))
        tolerance = registered['tolerances']['pcm_absolute']
        valid = (len(candidate) == len(upstream) == registered['frames'] > 0
                 and np.isfinite(candidate).all() and np.isfinite(upstream).all())
        peak = float(np.max(np.abs(candidate.astype(np.float64) - upstream))) if valid else None
        checks[f'{body}_duet_pcm_from_raw'] = peak is not None and peak <= tolerance
        duet[body] = {'frames': len(candidate), 'maximum_absolute_pcm_error': peak, 'pcm_tolerance': tolerance}

    artifacts = runs['duet-mixed-radiation-origin'] / 'artifacts'
    candidate, upstream = (np.genfromtxt(artifacts / f'{side}-radiation.csv', names=True, delimiter=',')
                           for side in ('candidate', 'upstream'))
    registered = source_case('duet-mixed-radiation-origin')
    times = np.arange(1, registered['trace_output_frames'] * 2 + 1)
    first = {}
    checks['mixed_radiation_first_components_from_raw'] = False
    if all(np.array_equal(trace['internal_sample'], times) for trace in (candidate, upstream)):
        for field in expected['mixed_first_component_difference']:
            different = np.flatnonzero(candidate[field] != upstream[field])
            first[field] = int(times[different[0]]) if different.size else None
        checks['mixed_radiation_first_components_from_raw'] = first == expected['mixed_first_component_difference']

    return ({'native_prompt_states': permission_states, 'virtual_coremidi': midi, 'normal_level_duet': duet,
             'mixed_radiation_first_component_difference': first}, checks)


def saved_definition(run, records):
    manifest = read_json(run / 'manifest.json')
    return read_json(run / manifest['source_snapshot'] / records[run.name]['case_definition'])


def audit_annotation_material(material, fixture, config, expected):
    key = read_json(material / 'artifacts/reference.json')
    reference = key['trials']
    packet = key['packet_id']
    preparation = read_json(material / 'summary.json')
    responses = read_json(fixture / 'summary.json')
    parsed = read_json(fixture / 'artifacts/responses.json')
    statuses = ('measured', 'ambiguous', 'unusable', 'unanswered')
    totals = {trial: Counter(dict.fromkeys(statuses, 0)) for trial in reference}
    samples = {trial: [] for trial in reference}
    files = sorted((fixture / 'artifacts/responses').glob('*.csv'))
    known_kinds = Counter(trial['kind'] for trial in reference.values())
    expected_kinds = {'recording': expected['recording_trials'], 'synthetic': expected['control_trials']}
    axes_match = all(isinstance(item['analysis_samples'], list) and len(item['analysis_samples']) == 2
                     and item['analysis_samples'][1] - item['analysis_samples'][0] == config['analysis_window_samples']
                     for item in reference.values())

    matches = set(parsed) == {path.stem for path in files}
    columns = ['packet_id', 'trial', 'status', 'f2_hz', 'note']
    template = material / 'artifacts/review/observations.csv'
    with template.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream, strict=True)
        blank = list(reader)
        blank_ok = (reader.fieldnames == columns and sorted(row['trial'] for row in blank) == sorted(reference)
                    and all(row['packet_id'] == packet and not any(row[name] for name in columns[2:]) for row in blank))
    for path in files:
        with path.open(newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream, strict=True)
            original = list(reader)
            if reader.fieldnames != columns:
                raise ValueError(f'合成回答の列が一致しません ({path.name})')
        seen = {}
        for row in original:
            trial = row['trial']
            status = row['status'] or 'unanswered'
            value = float(row['f2_hz']) if row['f2_hz'] else None
            if (trial not in reference or trial in seen or row['packet_id'] != packet or status not in statuses
                    or (status == 'measured') != (value is not None)
                    or (value is not None and not math.isfinite(value))):
                raise ValueError(f'合成回答の資料ID・窓・値が不正です ({path.name})')
            seen[trial] = {'status': status, 'f2_hz': value, 'note': row['note']}
            if value is not None:
                samples[trial].append(value)
        matches = matches and seen == parsed[path.stem]
        for trial in reference:
            totals[trial][seen.get(trial, {}).get('status', 'unanswered')] += 1

    outcomes = Counter()
    compared = responses['trials']
    matches = matches and set(compared) == set(reference)
    for trial, values in samples.items():
        spread = max(values) - min(values) if len(values) >= 2 else None
        agreed = spread <= config['rater_agreement_hz'] if spread is not None else None
        outcomes[agreed] += 1
        row = compared.get(trial, {})
        matches = (matches and row.get('range_hz') == spread and row.get('within_rater_agreement') is agreed
                   and row.get('counts') == totals[trial] and row.get('reference') == reference[trial])

    return ({'trials_by_material': dict(known_kinds), 'fixture_data_kind': responses['data_kind'],
             'fixture_raters': len(files), 'fixture_agreements': outcomes[True], 'fixture_disagreements': outcomes[False],
             'human_annotations_recorded_in_material': preparation['human_responses']}, {
        'f2_annotation_packet_and_blank_template': axes_match and known_kinds == expected_kinds and blank_ok
        and packet == preparation['packet_id'] == responses['packet_id'] and len(reference) == preparation['review_windows'],
        'f2_fixture_consensus_recomputed': matches and len(files) == responses['rater_count'] == expected['fixture_raters']
        and outcomes[True] == expected['fixture_agreements'] and outcomes[False] == expected['fixture_disagreements'],
        'f2_fixture_recorded_as_synthetic': responses['data_kind'] == 'synthetic' and preparation['human_responses'] == 0,
    })


def audit_f2_intervening_resonance(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    raw = read_json(run / 'artifacts/upstream-envelopes.json')
    rows = summary['windows']
    measure = definition['measurement']
    signal = definition['signal']
    reference_f2 = signal['fixed_poles_hz'][1][0]
    tolerance = measure['association_tolerance_hz']
    expected_slots = [(frequency, order, center)
                      for frequency in (None, *signal['added_pole_frequencies_hz'])
                      for order in measure['orders'] for center in measure['centers']]
    matches = len(raw) == len(rows) == len(expected_slots)
    switches, eligible_f2 = Counter(), []
    for row, probe in zip(rows, raw):
        frequency = row['added_pole_hz']
        poles = probe['poles']
        picked = formants.select(poles, cfg)
        lower = picked['f1'][0] + cfg['f2_min_gap_hz'] if picked['f1'] is not None else None
        eligible = [p for p in poles if lower is not None and lower < p[0] < cfg['f2_max_frequency_hz']
                    and abs(p[0] - reference_f2) <= tolerance]
        matches = matches and picked == row['selection'] and eligible == row['f2_near_eligible_poles']
        if row['association'] == 'added_mode':
            matches = (matches and frequency is not None and picked['f2'] is not None and bool(eligible)
                       and abs(picked['f2'][0] - frequency) <= tolerance and picked['f2'] not in eligible
                       and row['first_difference_from_model_f2'] == 'f2_selection')
            switches[frequency] += 1
            eligible_f2.extend(p[0] for p in eligible)
        else:
            matches = matches and row['association'] == 'model_f2' and picked['f2'] in eligible
    lower, upper = scope['previous_added_pole_hz'], scope['first_added_pole_hz']
    windows_per_frequency = len(measure['centers']) * len(measure['orders'])
    checks = {'f2_intervening_resonance_public_poles_recounted': matches
              and [(row['added_pole_hz'], row['order'], row['center']) for row in rows] == expected_slots,
              'f2_intervening_resonance_known_mode_still_eligible': not switches[lower]
              and switches[upper] == windows_per_frequency and min(switches, default=None) == upper
              and sum(switches.values()) == scope['displaced_windows']}
    return {'run': run.name, 'windows': len(rows), 'added_mode_windows_by_hz': dict(switches),
            'first_switch_interval_hz': [lower, upper],
            'remaining_eligible_model_f2_hz': [min(eligible_f2), max(eligible_f2)] if eligible_f2 else None}, checks


def audit_f2_intervening_excitation(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    reference = saved_definition(RUNS / definition['resonance_reference']['run'], records)
    rate = reference['signal']['sample_rate_hz']
    model_f2 = reference['signal']['fixed_poles_hz'][1][0]
    tolerance = reference['measurement']['association_tolerance_hz']
    pitches = definition['signal']['f0_hz']
    additions = (None, *definition['signal']['added_pole_frequencies_hz'])
    raw = read_json(run / 'artifacts/upstream-envelopes.json')
    rows = summary['windows']
    expected = [(pitch, extra, p, q) for pitch in pitches for extra in additions
                for p in reference['measurement']['orders'] for q in reference['measurement']['centers']]
    matched = len(raw) == len(rows) == len(expected)
    outcomes, counts = {}, Counter()
    for row, probe in zip(rows, raw):
        pitch, extra, order, center = (row[key] for key in ('f0_hz', 'added_pole_hz', 'order', 'center'))
        poles = probe['poles']
        picked = formants.select(poles, cfg)
        first, second = picked['f1'], picked['f2']
        eligible_f2 = [value for value in poles if first is not None
                       and first[0] + cfg['f2_min_gap_hz'] < value[0] < cfg['f2_max_frequency_hz']
                       and abs(value[0] - model_f2) <= tolerance]
        if second is None:
            association = picked['reason']
        elif second in eligible_f2:
            association = 'model_f2'
        elif extra is not None and abs(second[0] - extra) <= tolerance:
            association = 'added_mode'
        else:
            association = 'other_pole'
        outcomes[pitch, extra, order, center] = association
        counts[association] += 1
        matched = (matched and picked == row['selection'] and eligible_f2 == row['f2_near_eligible_poles']
                   and association == row['association']
                   and row['start_sample'] % (rate // pitch) == row['excitation_phase_samples'])
    anchor = reference['signal']['f0_hz']
    changes = sum(value != outcomes.get((anchor, extra, order, center))
                  for (pitch, extra, order, center), value in outcomes.items() if pitch != anchor and extra is not None)
    retained = sum(bool(row['f2_near_eligible_poles']) and row['association'] != 'model_f2' for row in rows)
    checks = {'f2_intervening_excitation_public_poles_and_phase': matched and list(outcomes) == expected,
              'f2_intervening_excitation_selection_changes': dict(counts) == scope['category_counts']
              and changes == scope['changes_from_reference'] == len(summary['changes_from_reference'])
              and retained == scope['displaced_with_model_f2_available']}
    return {'run': run.name, 'windows': len(rows), 'category_counts': dict(counts),
            'changes_from_reference': changes, 'displaced_with_model_f2_available': retained}, checks


def recount_f2_phase(run, scope, definition, reference, summary, cfg):
    rate, duration = (reference['signal'][name] for name in ('sample_rate_hz', 'duration_seconds'))
    pitch, added = (definition['signal'][name] for name in ('f0_hz', 'added_pole_hz'))
    period, remainder = divmod(rate, pitch)
    model_f2 = reference['signal']['fixed_poles_hz'][1][0]
    tolerance = reference['measurement']['association_tolerance_hz']
    orders, centers = (reference['measurement'][name] for name in ('orders', 'centers'))
    length = round(cfg['frame_seconds'] * rate)
    boundary = cfg['f2_min_gap_hz']
    rows = summary['windows']
    raw = read_json(run / 'artifacts/upstream-envelopes.json')
    expected = [(delay, order, center) for delay in range(period) for order in orders for center in centers]
    same = not remainder and period == scope['period_samples'] == summary['period_samples']
    same = same and len(rows) == len(raw) == len(expected)
    outcomes = {}
    for row, probe, (delay, order, center) in zip(rows, raw, expected):
        start = int(center * duration * rate) - length // 2
        phase = (start - delay) % period
        poles = probe['poles']
        picked = formants.select(poles, cfg)
        first, second = picked['f1'], picked['f2']
        eligible = [p for p in poles if first is not None and first[0] + boundary < p[0] < cfg['f2_max_frequency_hz']
                    and abs(p[0] - model_f2) <= tolerance]
        neighbor = min((p for p in poles if p != first and abs(p[0] - added) <= tolerance),
                       key=lambda p: abs(p[0] - added), default=None)
        gap = neighbor[0] - first[0] if neighbor is not None and first is not None else None
        if second is None:
            category = picked['reason']
        elif second in eligible:
            category = 'model_f2'
        elif abs(second[0] - added) <= tolerance:
            category = 'added_mode'
        else:
            category = 'other_pole'
        same = (same and (delay, order, center, start, phase) ==
                tuple(row[name] for name in ('pulse_offset_samples', 'order', 'center', 'start_sample',
                                             'excitation_phase_samples'))
                and picked == row['selection'] and eligible == row['f2_near_eligible_poles']
                and gap == row['added_mode_gap_from_selected_f1_hz'] and category == row['association'])
        outcomes[order, center, phase] = category, bool(eligible), gap
    counts = {str(order): dict(Counter(outcomes[order, centers[0], phase][0] for phase in range(period)))
              for order in orders}
    repeated = all(outcomes[order, center, phase][:2] == outcomes[order, centers[0], phase][:2]
                   for order in orders for center in centers[1:] for phase in range(period))
    return counts, outcomes, same and repeated


def audit_f2_intervening_phase(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    prior = saved_definition(RUNS / definition['excitation_reference']['run'], records)
    reference = saved_definition(RUNS / prior['resonance_reference']['run'], records)
    counts, outcomes, same = recount_f2_phase(run, scope, definition, reference, summary, cfg)
    period = scope['period_samples']
    center = reference['measurement']['centers'][0]
    boundary = cfg['f2_min_gap_hz']
    near_model_and_added = {'model_f2', 'added_mode'}
    phase_switch = False
    for phase in range(period):
        left, right = (outcomes[12, center, position] for position in ((phase - 1) % period, phase))
        if ({left[0], right[0]} == near_model_and_added and left[1] and right[1]
                and left[2] is not None and right[2] is not None and (left[2] > boundary) != (right[2] > boundary)):
            phase_switch = True
    predictions = {'phase_changes_order_12_selection': near_model_and_added <= counts['12'].keys(),
                   'phase_switch_preserves_model_f2_and_crosses_gap': phase_switch}
    analysis = summary['phase_results']
    checks = {'f2_intervening_phase_public_poles_and_full_cycle': same,
              'f2_intervening_phase_selection_recounted': counts == scope['counts_by_order'] == analysis['counts_by_order']
              and predictions == summary['predictions'] == scope['predictions']}
    return {'run': run.name, 'windows': len(summary['windows']), 'counts_by_order': counts,
            'predictions': predictions}, checks


def audit_f2_intervening_phase_midpoint(scope, records, summaries, cfg):
    run = RUNS / scope['run']
    summary = summaries[run.name]
    definition = saved_definition(run, records)
    before = RUNS / definition['phase_reference']['run']
    prior = saved_definition(before, records)
    excitation = saved_definition(RUNS / prior['excitation_reference']['run'], records)
    reference = saved_definition(RUNS / excitation['resonance_reference']['run'], records)
    counts, outcomes, same = recount_f2_phase(run, scope, definition, reference, summary, cfg)
    period = scope['period_samples']
    center = reference['measurement']['centers'][0]
    boundary = cfg['f2_min_gap_hz']
    changed = Counter()
    for row in summaries[before.name]['windows']:
        order, time, phase = (row[name] for name in ('order', 'center', 'excitation_phase_samples'))
        if outcomes[order, time, phase][0] != row['association']:
            changed[str(order)] += 1
    retained = sum(category == 'added_mode' and eligible for category, eligible, _ in outcomes.values())
    displaced = sum(category == 'added_mode' for category, _, _ in outcomes.values())
    gaps = {phase: outcomes[14, center, phase][2] for phase in range(period)}
    switches = {((phase - 1) % period, phase) for phase in range(period)
                if outcomes[14, center, (phase - 1) % period][0] != outcomes[14, center, phase][0]}
    crossings = {(a, b) for a, b in switches
                 if gaps[a] is not None and gaps[b] is not None and (gaps[a] > boundary) != (gaps[b] > boundary)}
    exceptions = sum((gap is not None and gap > boundary) != (category == 'added_mode')
                     for category, _, gap in outcomes.values())
    predictions = {
        'order_12_always_adds_mode': all(category == 'added_mode' and gap is not None and gap > boundary
                                        for key, (category, _, gap) in outcomes.items() if key[0] == 12),
        'order_14_phase_switch_crosses_gap':
            any({outcomes[14, center, a][0], outcomes[14, center, b][0]} == {'model_f2', 'added_mode'}
                for a, b in crossings),
        'model_f2_stays_eligible_when_displaced': 0 < retained == displaced,
    }
    analysis = summary['phase_results']
    comparison = summary['midpoint_comparison']
    checks = {
        'f2_intervening_phase_midpoint_public_poles_and_full_cycle': same,
        'f2_intervening_phase_midpoint_selection_recounted':
            counts == analysis['counts_by_order'] == scope['counts_by_order']
            and dict(changed) == comparison['changed_windows_by_order'] == scope['changed_windows_by_order']
            and predictions == summary['predictions'] == scope['predictions'],
        'f2_intervening_phase_midpoint_gap_boundary_and_retained_model':
            switches == {tuple(row['phases_samples']) for row in analysis['transitions_by_order']['14']}
            and crossings == {tuple(row['phases_samples']) for row in analysis['transitions_by_order']['14']
                              if row['crosses_gap']}
            and len(crossings) == scope['order_14_gap_crossings'] and retained == scope['displaced_with_model_f2_available']
            and exceptions == len(comparison['gap_rule_exceptions']) == scope['gap_rule_exceptions'],
    }
    return {'run': run.name, 'windows': len(summary['windows']), 'counts_by_order': counts,
            'order_14_gap_crossings': len(crossings), 'displaced_with_model_f2_available': retained,
            'predictions': predictions}, checks


def audit_f2_recording_window_shift(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    first, last = definition['offset_samples']
    offsets = range(first, last + 1)
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    length = definition['target']['frame_samples']
    anchor = definition['target']['start_sample']
    start, end = summary['interval_seconds']
    raw = read_json(run / 'artifacts/upstream-envelopes.json')
    rows = summary['windows']
    matches = len(rows) == len(raw) == len(offsets) == scope['windows']
    matches = matches and summary['target'] == definition['target']
    counts, bandwidth_filtered, retained, above_gap = Counter(), 0, 0, True
    for row, probe, offset in zip(rows, raw, offsets):
        begin = anchor + offset
        poles = probe['poles']
        pair = formants.select(poles, cfg)
        f1, f2 = pair['f1'], pair['f2']
        lower, upper = definition['low_band_hz']
        low_public = [p for p in poles if lower <= p[0] <= upper]
        low_raw_bandwidth = [-math.log(math.hypot(re, im)) * rate / math.pi
                             for re, im in probe['roots']
                             if im > 0 and lower <= math.atan2(im, re) * rate / (2 * math.pi) <= upper]
        lower, upper = definition['high_band_hz']
        high_eligible = [p for p in poles if f1 is not None and lower <= p[0] <= upper
                         and f1[0] + cfg['f2_min_gap_hz'] < p[0] < cfg['f2_max_frequency_hz']]
        gap = [pole[0] - f1[0] for pole in low_public] if f1 is not None else []
        category = pair['reason'] if f2 is None else 'low' if f2 in low_public else 'high' if f2 in high_eligible else 'other'
        counts[category] += 1
        above_gap = above_gap and (not low_public or bool(gap) and min(gap) > cfg['f2_min_gap_hz'])
        retained += bool(high_eligible)
        bandwidth_filtered += (category == 'high' and not low_public and bool(low_raw_bandwidth)
                               and min(low_raw_bandwidth) > cfg['pole_max_bandwidth_hz'])
        matches = (matches and offset == row['offset_samples'] and begin == row['start_sample']
                   and start <= begin / rate and (begin + length) / rate <= end
                   and pair == row['selected'] and category == row['category']
                   and low_public == row['bands']['low']['public'] and high_eligible == row['bands']['high']['eligible']
                   and gap == row['low_public_gaps_from_f1_hz'])
    predictions = {'high_band_remains_eligible': retained == len(offsets), 'low_band_stays_above_gap_while_public': above_gap,
                   'window_shift_changes_selection_at_bandwidth_filter': bool(bandwidth_filtered)}
    if 'annotation' in definition:
        predictions['low_band_remains_selected'] = counts['low'] == len(offsets)
    checks = {
        'f2_recording_window_shift_positions_and_public_poles': matches,
        'f2_recording_window_shift_recounted':
            dict(counts) == scope['selection_counts'] == summary['selection_counts']
            and predictions == scope['predictions'] == summary['predictions'],
    }
    return {'run': run.name, 'windows': len(rows), 'selection_counts': dict(counts), 'predictions': predictions}, checks


def annotation_shift_assets(run, definition):
    association, uid = definition['annotation'], definition['target']['utterance']
    packet = RUNS / association['run']
    manifest = read_json(run / 'manifest.json')
    source, = (entry for entry in manifest['inputs']
               if entry['path'].endswith(f'/artifacts/corpus/recording/{uid}/{uid}.wav'))
    return (ROOT / source['path'], packet / 'artifacts/reference.json',
            packet / 'artifacts/review' / f"{association['trial']}.wav", source['sha256'])


def audit_f2_annotation_window_shift(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    counts, common_checks = audit_f2_recording_window_shift(scope, records, summary, cfg)
    checks = {f"f2_annotation_w06_{name.removeprefix('f2_recording_window_shift_')}": value
              for name, value in common_checks.items()}
    target, association = definition['target'], definition['annotation']
    recording, key_path, clip_path, recorded_sha256 = annotation_shift_assets(run, definition)
    key = read_json(key_path)
    trial = key['trials'][association['trial']]
    left, length = target['start_sample'], target['frame_samples']
    right = left + length
    focus = trial['focus_ms']
    chosen = summary['windows'][-definition['offset_samples'][0]]['selected']['f2']
    with wave.open(str(recording), 'rb') as original, wave.open(str(clip_path), 'rb') as clip:
        first, count = trial['clip_start_sample'], trial['clip_frames']
        original.setpos(first)
        pcm_equal = (original.getparams()[:3] == clip.getparams()[:3] == (1, 2, trial['sample_rate_hz'])
                     and clip.getnframes() == count and original.readframes(count) == clip.readframes(count))
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    sample_focus = [round((first + ms * trial['sample_rate_hz'] / 1000) / cfg['decimation']) for ms in focus]
    raw = read_json(run / 'artifacts/upstream-envelopes.json')
    candidates = {'low': [], 'high': []}
    for item in raw:
        poles = item['poles']
        f1 = formants.select(poles, cfg)['f1']
        for region in candidates:
            lower, upper = definition[f'{region}_band_hz']
            candidates[region].append([p for p in poles if f1 is not None and lower <= p[0] <= upper
                                       and f1[0] + cfg['f2_min_gap_hz'] < p[0] < cfg['f2_max_frequency_hz']])
    ranges = {}
    for region, windows in candidates.items():
        pairs = [pole for poles in windows for pole in poles]
        ranges[region] = {'eligible_windows': sum(map(bool, windows)),
                          'frequency_hz': [min(p[0] for p in pairs), max(p[0] for p in pairs)] if pairs else None,
                          'bandwidth_hz': [min(p[1] for p in pairs), max(p[1] for p in pairs)] if pairs else None}
    segment = tall_gmm.read_npz(run / 'artifacts/decimated-segment.npz')
    begin, end = definition['offset_samples']
    computed = tall_f2_grid.formants.filtered_wave(recording, 'recording', cfg)[left + begin:right + end]
    checks.update({
        'f2_annotation_w06_packet_and_pcm_identity': (pcm_equal and sha256(recording) == recorded_sha256
            and sha256(clip_path) == trial['wave_sha256'] == summary['annotation']['clip_sha256']
            and key['packet_id'] == association['packet_id'] == summary['annotation']['packet_id']
            and association['trial'] == summary['annotation']['trial']
            and all(trial[field] == target[field] for field in ('utterance', 'word', 'center'))
            and trial['phone_seconds'] == summary['interval_seconds']
            and [left, right] == sample_focus == trial['analysis_samples'] == summary['annotation']['analysis_samples']
            and 0 <= focus[0] < focus[1] <= 1000 * count / cfg['sample_rate_hz']
            and abs((focus[1] - focus[0]) * rate / 1000 - length) <= 1e-9
            and chosen is not None and abs(chosen[0] - trial['held_out_lpc_f2_hz'][0])
            <= cfg['frequency_bandwidth_agreement_hz']),
        'f2_annotation_w06_source_samples_and_candidate_ranges': (int(segment['first_sample']) == left + begin
            and np.array_equal(segment['samples'], computed) and ranges == summary['candidate_ranges']),
    })
    return counts | {'candidate_ranges': ranges}, checks


def annotation_pre_emphasis_assets(definition):
    previous = RUNS / definition['window_sweep']['run']
    endpoint = RUNS / definition['endpoints']['run'] / 'artifacts/upstream-pre-emphasis-04.json'
    return previous / 'artifacts/decimated-segment.npz', previous / 'summary.json', endpoint


def audit_f2_annotation_pre_emphasis(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    settings = definition['measurement']
    segment_path, window_summary, endpoints_path = annotation_pre_emphasis_assets(definition)
    segment = tall_gmm.read_npz(segment_path)
    start, stop = settings['frame_samples']
    first = int(segment['first_sample'])
    frame = np.load(run / 'artifacts/frame.npy', allow_pickle=False)
    source_frame = segment['samples'][start - first:stop - first]
    raw = read_json(run / 'artifacts/upstream-pre-emphasis.json')
    archived = read_json(endpoints_path)
    previous = read_json(window_summary)
    fs, order = settings['sample_rate_hz'], settings['order']
    rows = []
    trace_ok = True
    for item, row in zip(raw, summary['rows'], strict=True):
        selection = formants.select(item['poles'], cfg)
        coefficient = item['pre_emphasis_coefficient']
        chosen, errors = w06_pre_emphasis.independent_trace(frame, item, fs, order, cfg)
        trace_ok &= (errors == row['errors'] and chosen == selection and row['first_difference'] is None)
        rows.append({'coefficient': coefficient, 'selected': selection,
                     'band': w06_pre_emphasis.selected_band(selection, settings)})
    first_step, last_step = settings['coefficient_steps']
    coefficients = [step / settings['coefficient_divisor'] for step in range(first_step, last_step + 1)]
    counts = dict(Counter(row['band'] for row in rows))
    changes = w06_pre_emphasis.transitions(settings, cfg, raw, rows)
    switch = [row for row in changes if row['bands'] == ['low', 'high']]
    predictions = {
        'low_to_high_selection_transition': bool(switch),
        'low_f2_becomes_f1_at_transition': bool(switch) and all(
            row['root_matches']['f2']['next_chosen_as'] == 'f1'
            and not row['root_matches']['f1']['next_f1_eligible'] for row in switch),
    }
    corresponding = switch[0]['root_matches']['f1'] if switch else {}
    max_bw = cfg['f1_max_bandwidth_hz']
    checks = {
        'f2_w06_pre_emphasis_fixed_source_pcm_and_grid': (np.array_equal(frame, source_frame)
            and previous['annotation'] == summary['annotation'] and [start, stop] == summary['annotation']['analysis_samples']
            and len(raw) == scope['points'] and [row['coefficient'] for row in rows] == coefficients
            and [item['pre_emphasis_option'] for item in raw] == [*coefficients[:-1], None]),
        'f2_w06_pre_emphasis_archived_endpoints': all(
            {k: v for k, v in observed.items() if k != 'lpc_envelope_db'}
            == {k: v for k, v in expected.items() if k != 'lpc_envelope_db'}
            for observed, expected in ((raw[0], archived[1]), (raw[-1], archived[0]))),
        'f2_w06_pre_emphasis_recounted_and_independent': trace_ok
            and all(all(row[k] == entry[k] for k in row) for row, entry in zip(rows, summary['rows'], strict=True))
            and counts == scope['selection_counts'] == summary['selection_counts'],
        'f2_w06_pre_emphasis_width_crossing_at_recorded_coefficients': (changes == summary['transitions']
            and predictions == scope['predictions'] == summary['predictions'] and len(switch) == 1
            and switch[0]['coefficients'] == scope['transition_coefficients']
            and corresponding['next_public']
            and switch[0]['selections'][0]['f1'][1] < max_bw <= corresponding['next_pole_hz'][1]),
    }
    return {'run': run.name, 'points': len(rows), 'selection_counts': counts, 'predictions': predictions,
            'transitions': changes}, checks


def again_pre_emphasis_assets(run, definition):
    settings = definition['measurement']
    packet = RUNS / definition['annotation']['run']
    center = RUNS / definition['center_reference']['run']
    uid = settings['utterance']
    manifest = read_json(run / 'manifest.json')
    source, = (item for item in manifest['inputs']
               if item['path'].endswith(f'/artifacts/corpus/recording/{uid}/{uid}.wav'))
    return {'recording': ROOT / source['path'], 'packet': packet / 'artifacts/reference.json',
            'center': center / 'summary.json', 'center_frame': center / 'artifacts/frame.npy',
            **{name: packet / 'artifacts/review' / f'{name}.wav'
               for name in [*settings['target_trials'], settings['center_trial']]}}


def audit_f2_annotation_again_pre_emphasis(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    settings = definition['measurement']
    targets, center = settings['target_trials'], settings['center_trial']
    assets = again_pre_emphasis_assets(run, definition)
    packet = read_json(assets['packet'])
    frames = tall_gmm.read_npz(run / 'artifacts/frames.npz')
    samples = tall_f2_grid.formants.filtered_wave(assets['recording'], 'recording', cfg)
    packet_matches = packet['packet_id'] == definition['annotation']['packet_id']
    for name in [*targets, center]:
        trial = packet['trials'][name]
        start, stop = trial['analysis_samples']
        packet_matches &= (again_pre_emphasis.verify_packet_window(trial, assets['recording'], assets[name], cfg)
                           and np.array_equal(frames[name], samples[start:stop]))
    original = read_json(assets['center'])
    packet_matches &= np.array_equal(frames[center], np.load(assets['center_frame'], allow_pickle=False))
    packet_matches &= original['annotation']['analysis_samples'] == packet['trials'][center]['analysis_samples']
    coefficients, options = w06_pre_emphasis.coefficient_options(settings, cfg)
    matches, counts, transitions, selections = True, {}, {}, {}
    fs, order = settings['sample_rate_hz'], settings['order']
    for index, name in enumerate(targets):
        raw = read_json(run / 'artifacts' / f'upstream-pre-emphasis-{index:02d}.json')
        rows = summary['rows'][name]
        matches &= (len(rows) == len(raw) == scope['points_per_new_window']
                    and [r['pre_emphasis_coefficient'] for r in raw] == coefficients
                    and [r['pre_emphasis_option'] for r in raw] == options)
        selected = []
        for record, row in zip(raw, rows, strict=True):
            selection = formants.select(record['poles'], cfg)
            independent, errors = w06_pre_emphasis.independent_trace(frames[name], record, fs, order, cfg)
            band = w06_pre_emphasis.selected_band(selection, settings)
            matches &= (independent == selection == row['selected'] and errors == row['errors']
                        and band == row['band'] and row['coefficient'] == record['pre_emphasis_coefficient']
                        and row['first_difference'] is None)
            selected.append({'coefficient': row['coefficient'], 'selected': selection, 'band': band})
        selections[name] = selected
        counts[name] = dict(Counter(row['band'] for row in selected))
        transitions[name] = w06_pre_emphasis.transitions(settings, cfg, raw, selected)
        for move in transitions[name]:
            move['cause'] = again_pre_emphasis.classification(move, cfg)
        ends = [selected[-1]['selected']['f2'][0], selected[0]['selected']['f2'][0]]
        matches &= ends == packet['trials'][name]['held_out_lpc_f2_hz']
    relevant = [move for move in transitions['W02'] if move['bands'] == ['low', 'high']]
    width = cfg['pole_max_bandwidth_hz']
    median_rows = []
    for i, coefficient in enumerate(coefficients):
        poles = [rows[i]['selected']['f2'] for rows in (selections | {center: original['rows']}).values()]
        values = [pole[0] for pole in poles if pole is not None]
        value = float(np.median(values)) if values else None
        band = w06_pre_emphasis.selected_band({'f2': [value] if value is not None else None, 'reason': 'no_f2'}, settings)
        median_rows.append({'coefficient': coefficient, 'f2_hz': value, 'support': len(values), 'band': band})
    median_switches = [[left['coefficient'], right['coefficient']] for left, right in zip(median_rows, median_rows[1:])
                       if left['band'] != right['band']]
    predictions = {
        'w07_stays_high': counts['W07'] == {'high': len(coefficients)},
        'w02_switches_low_to_high': bool(relevant),
        'w02_low_pole_excluded_from_public_at_switch': bool(relevant) and relevant[0]['cause'] == 'public_bandwidth',
        'token_f2_median_switches_once': len(median_switches) == 1
            and median_rows[0]['band'] == 'low' and median_rows[-1]['band'] == 'high',
    }
    checks = {
        'f2_again_pre_emphasis_annotation_frames_replayed': packet_matches,
        'f2_again_pre_emphasis_independent_traces_and_branch_counts': matches
            and counts == summary['selection_counts'] == scope['selection_counts'],
        'f2_again_pre_emphasis_w02_public_cutoff': (transitions == summary['transitions'] and len(relevant) == 1
            and relevant[0]['coefficients'] == scope['w02_transition_coefficients']
            and relevant[0]['selections'][0]['f2'][1] <= width < relevant[0]['root_matches']['f2']['next_pole_hz'][1]
            and relevant[0]['root_matches']['f1']['next_chosen_as'] == 'f1'),
        'f2_again_pre_emphasis_token_median_recounted': (median_rows == summary['median_rows']
            and all(row['support'] == 3 for row in median_rows)
            and median_switches == summary['median_transitions'] == [scope['median_transition_coefficients']]
            and predictions == summary['predictions'] == scope['predictions']),
    }
    return {'run': run.name, 'selection_counts': counts, 'transitions': transitions,
            'median_transitions': median_switches, 'predictions': predictions}, checks


def again_f2_term_assets(definition):
    prior = RUNS / definition['alignment_reference']['run']
    uid = definition['measurement']['target']['utterance']
    sweep = RUNS / definition['sweep']['run'] / 'summary.json'
    target = prior / 'artifacts' / 'corpus' / 'recording' / uid / f'{uid}.wav'
    archive = WORKSPACE / 'cases' / definition['archive_case']
    return sweep, target, archive


def audit_again_f2_term_effect(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    settings = definition['measurement']
    sweep_path, wav, archive_case = again_f2_term_assets(definition)
    sweep = read_json(sweep_path)
    archive = read_json(archive_case)['reference']
    raw = read_json(run / 'artifacts/native.json')
    recordings = read_json(run / 'artifacts/recordings.json')
    selected = [next(row['f2_hz'] for row in sweep['median_rows'] if row['coefficient'] == coefficient)
                for coefficient in settings['coefficients']]
    computed, inputs = again_f2_term.independent_evaluation(settings, raw, selected)
    expected_ids = [uid for ids in settings['cohort'].values() for uid in ids]
    archive_path = Path(archive['archive_path'])
    with ZipFile(archive_path) as source:
        from_zip = {uid: hash_bytes(source.read(f'48k/{uid[:2]}/{uid}.wav')).hexdigest() for uid in expected_ids}
    target = settings['target']
    uid = target['utterance']
    anchor = raw['correspondence'][uid]['tokens'][raw['target_slot']]
    sound = again_f2_term.tsp.filtered_wave(wav, 'recording', cfg)
    independent_windows = [again_f2_term.tsp.window(
        sound, [*anchor['recording_interval'], 'EH1'], q, cfg['order']['F'], cfg) for q in cfg['reference_centers']]
    default_f2 = median(v['f1_f2_hz'][1] for v in independent_windows)
    limit = settings['tolerance']
    variants = raw['conditions']
    baseline = variants['default']
    groups = ('level', 'sibilants', 'timing')
    same_grade = all(row['held_synth_report'] == baseline['held_synth_report']
                     and row['held_human_score_report'] == baseline['held_human_score_report']
                     and all(row['human_term']['groups'][key] == baseline['human_term']['groups'][key] for key in groups)
                     for row in variants.values())
    matching = all(again_f2_term.agrees(variants[key]['human_term'], value, limit)
                   for key, value in computed['conditions'].items())
    matching &= all(again_f2_term.agrees(raw['training'][key], value, limit)
                    for key, value in computed['training'].items())
    before, after = (computed['conditions'][k]['median_hz'] for k in ('before', 'after'))
    predictions = {
        'speaker_median_change_smaller_than_token_change': abs(after - before) < abs(selected[1] - selected[0]),
        'training_reference_and_scored_groups_unchanged': same_grade and matching,
        'two_tokens_leave_f2_cost_missing': raw['first_two_recordings']['cost'] is None
            and raw['support_controls']['2']['cost'] is None and raw['support_controls']['2']['support'] == 2,
    }
    checks = {
        'tsp_again_f2_term_dataset_and_target_f2_replayed': (set(expected_ids) == set(raw['correspondence'])
            and sha256(archive_path) == recordings['archive_sha256'] == archive['sha256']
            and from_zip == recordings['wav_sha256'] and sha256(wav) == from_zip[uid]
            and anchor['recording_interval'] == target['phone_seconds'] and anchor['ipa'] == settings['ipa']
            and anchor['stressed'] and abs(default_f2 - inputs['default']) <= limit),
        'tsp_again_f2_term_reference_and_cost_recounted': matching and computed == summary['independent']
            and again_f2_term.tsp.max_error(computed['reference'], raw['reference']) <= limit
            and inputs == summary['input_f2_hz']
            and {key: row['human_term'] for key, row in variants.items()} == summary['conditions'],
        'tsp_again_f2_term_missing_support_and_group_membership_recounted': (
            all(again_f2_term.agrees(raw['support_controls'][key], value, limit)
                for key, value in computed['support_controls'].items())
            and again_f2_term.agrees(raw['first_two_recordings'], computed['first_two_recordings'], limit)
            and all(row['four_training_speakers']['cost'] is None for row in variants.values())
            and variants['default']['held_synth_report']['terms'][settings['term']]['scored'] is False
            and predictions == scope['predictions'] == summary['predictions']),
    }
    return {'run': run.name, 'recordings': len(expected_ids), 'conditions': computed['conditions'],
            'predictions': predictions}, checks


def audit_f2_training_reference(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    settings = definition['measurement']
    source = RUNS / definition['cohort']['run']
    request = f2_training_reference.frozen_f2_inputs(
        settings, read_json(source / 'artifacts/native.json'), read_json(source / 'summary.json'))
    native = read_json(run / 'artifacts/native.json')
    baseline, recomputed = f2_training_reference.independent_sweep(settings, request)
    stats = f2_training_reference.summarize_sweep(settings, recomputed)
    tol = settings['tolerance']
    identity = ('speaker', 'utterance', 'slot', 'original_hz')
    comparisons = all(all(row[k] == raw[k] for k in identity)
                      and all(f2_training_reference.report_agrees(value, raw['scenarios'][name], tol)
                              for name, value in row['scenarios'].items())
                      for row, raw in zip(recomputed, native['interventions'], strict=True))
    predictions = {
        'finite_replacements_preserve_support': all(
            all(profile['training'][key]['support'] == start['support'] for key, start in baseline['training'].items())
            for entry in recomputed for profile in entry['scenarios'].values()),
        'centre_is_monotone_with_replacement': all(
            entry['scenarios']['before']['reference'][0] <= entry['scenarios']['after']['reference'][0]
            for entry in recomputed),
        'spread_changes_without_centre_movement': any(
            row['spread_changed_centre_fixed'] for row in stats['by_speaker'].values()),
    }
    stopped = RUNS / scope['compile_failure']['run']
    manifest = read_json(stopped / 'manifest.json')
    failure, stored = read_record(stopped.name, definition['upstream_revision'], expected_failure=True,
                                  expected_error=manifest['error'])
    comparisons_count = sum(len(row['scenarios']) for row in recomputed)
    checks = {
        'f2_training_reference_inputs_and_baseline_replayed': (
            request == read_json(run / 'artifacts/inputs.json')
            and f2_training_reference.report_agrees(baseline, native['baseline'], tol)
            and native['baseline'] == native['after_restore']
            and native['group'] == 'formants' and native['scored'] is False),
        'f2_training_reference_all_replacements_recounted': (comparisons and baseline == summary['baseline']
            and recomputed == summary['interventions'] and comparisons_count == scope['comparisons']),
        'f2_training_reference_spread_and_costs_recounted': (
            stats == summary['statistics']
            and sum(row['spread_changed_centre_fixed'] for row in stats['by_speaker'].values()) == scope['spread_only_pairs']
            and stats['spread_floor_conditions'] == scope['spread_floor_conditions']
            and predictions == summary['predictions'] == scope['predictions']),
        'f2_training_reference_initial_compile_failure_retained': (
            not failure['errors'] and sha256(stopped / 'manifest.json') == scope['compile_failure']['manifest_sha256']
            and 'error[E0753]' in (stopped / 'artifacts/cargo.log').read_text()
            and stored['artifacts/inputs.json'] == sha256(run / 'artifacts/inputs.json')),
    }
    return {'run': run.name, 'comparisons': comparisons_count, 'statistics': stats, 'predictions': predictions}, checks


def audit_f2_recording_collection(definition, run, collection, cfg, ipa):
    archive = read_json(WORKSPACE / 'cases' / definition['archive_case'])['reference']
    archive_path = Path(archive['archive_path'])
    recordings = read_json(run / 'artifacts/collection/recordings.json')
    hashes, errors = {}, []
    missing_mismatches = 0
    with ZipFile(archive_path) as wavs:
        for uid, utt in collection['correspondence'].items():
            payload = wavs.read(f"48k/{utt['speaker']}/{uid}.wav")
            hashes[uid] = hash_bytes(payload).hexdigest()
            lo = again_f2_term.tsp.filtered_wave(BytesIO(payload), 'recording', cfg)
            for row in utt['tokens']:
                if not row['stressed'] or row['ipa'] != ipa:
                    continue
                frames = [again_f2_term.tsp.window(lo, [*row['recording_interval'], 'EH1'],
                          q, cfg['order'][utt['speaker'][0]], cfg)['f1_f2_hz'] for q in cfg['reference_centers']]
                f2 = [pair[1] for pair in frames if pair is not None]
                recorded = row['recording_f2_hz']
                if f2 and recorded is not None:
                    errors.append(abs(median(f2) - recorded))
                else:
                    missing_mismatches += bool(f2) != (recorded is not None)
    counts = {
        'added_recordings': len(hashes), 'added_finite_tokens': len(errors),
        'maximum_independent_f2_error_hz': max(errors, default=None), 'missing_mismatches': missing_mismatches,
    }
    matched = (sha256(archive_path) == recordings['archive_sha256'] == archive['sha256']
               and hashes == recordings['wav_sha256'] and not missing_mismatches and bool(errors)
               and max(errors) <= cfg['frequency_bandwidth_agreement_hz'])
    return counts, matched


def audit_f2_ten_speakers(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    source = RUNS / definition['baseline']['run']
    settings = saved_definition(source, records)['measurement']
    frozen = read_json(source / 'artifacts/inputs.json')
    collection = read_json(run / 'artifacts/collection/native.json')
    request = f2_ten_speakers.enlarged_request(definition, settings, frozen, collection)
    native = read_json(run / 'artifacts/native.json')
    recomputed = f2_ten_speakers.evaluate(definition, settings, frozen, read_json(source / 'summary.json'), request, native)
    counts, matched = audit_f2_recording_collection(definition, run, collection, cfg, settings['ipa'])
    stats = recomputed['ten_speakers']['effects']
    checks = {
        'f2_ten_speakers_recordings_and_independent_lpc': (
            matched and all(counts[key] == scope[key] for key in ('added_recordings', 'added_finite_tokens'))),
        'f2_ten_speakers_fixed_inputs_and_reports_recounted': (
            request == read_json(run / 'artifacts/inputs.json')
            and all(recomputed['checks'].values()) and recomputed == summary
            and sum(len(row['scenarios']) for row in recomputed['interventions']) == scope['comparisons']),
        'f2_ten_speakers_spread_and_predictions_recounted': (
            recomputed['predictions'] == scope['predictions']
            and sum(row['spread_changed_centre_fixed'] for row in stats['by_speaker'].values()) == scope['spread_only_pairs']
            and stats['spread_floor_conditions'] == scope['spread_floor_conditions']),
    }
    return {
        'run': run.name, **counts, 'predictions': recomputed['predictions'], 'effects': stats,
    }, checks


def audit_f2_centre_width(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    sources = {name: tuple(read_json(RUNS / definition[name]['run'] / 'artifacts' / f'{path}.json')
                          for path in ('inputs', 'native')) for name in f2_centre_width.COHORTS}
    settings = saved_definition(RUNS / definition['five_speakers']['run'], records)['measurement']
    request, matched = f2_centre_width.comparison_input(definition, settings, sources)
    native = read_json(run / 'artifacts/native.json')
    replay = f2_centre_width.evaluate(definition, settings, request, matched, native)
    zero_cells = {
        name: sorted(key for key, voices in cohort.items() if voices['held_synth']['zero'])
        for name, cohort in replay['cells'].items()
    }
    return {'run': run.name, 'comparisons': replay['comparisons'], 'effects': replay['effects'], 'synth_zero_cells': zero_cells}, {
        'f2_centre_width_fixed_inputs_and_cells_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values())
            and replay['comparisons'] == scope['comparisons'] and replay == summary),
        'f2_centre_width_synth_zero_and_predictions_replayed': (
            zero_cells == scope['synth_zero_cells'] and replay['predictions'] == scope['predictions']),
    }


def audit_f2_pooled_sexes(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    female = RUNS / definition['female_reference']['run']
    contrast = RUNS / definition['centre_width']['run']
    prior = saved_definition(contrast, records)
    prototype = RUNS / saved_definition(female, records)['baseline']['run']
    settings = saved_definition(prototype, records)['measurement']
    collection = read_json(run / 'artifacts/collection/native.json')
    frozen = read_json(female / 'artifacts/inputs.json')
    prior_input = read_json(contrast / 'artifacts/inputs.json')['cohorts']['ten_speakers']
    request = f2_pooled.derive_input(definition, prior, frozen, collection)
    replay = f2_pooled.evaluate(definition, settings, prior_input, request, read_json(run / 'artifacts/native.json'))
    counts, matched = audit_f2_recording_collection(definition, run, collection, cfg, settings['ipa'])
    sizes = {name: len(states['baseline']['residuals']) for name, states in replay['cohorts'].items()}
    return {'run': run.name, **counts, 'residual_counts': sizes,
            'held_cost_change': replay['held_cost_change'], 'predictions': replay['predictions']}, {
        'f2_pooled_recordings_and_independent_lpc': (
            matched and all(counts[key] == scope[key] for key in ('added_recordings', 'added_finite_tokens'))),
        'f2_pooled_reference_and_fixed_intervention_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values()) and replay == summary),
        'f2_pooled_threshold_and_predictions_replayed': (
            sizes == scope['residual_counts'] and replay['predictions'] == scope['predictions']),
    }


def audit_f2_pooled_sweep(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    source, female, original = (RUNS / definition[key]['run']
                                for key in ('pooled_source', 'female_source', 'original_interventions'))
    settings = saved_definition(original, records)['measurement']
    inputs = [read_json(r / 'artifacts/inputs.json') for r in (source, female, original)]
    reports = [read_json(r / 'artifacts/native.json') for r in (female, source)]
    request = f2_pooled_sweep.derive_input(definition, *inputs)
    replay = f2_pooled_sweep.evaluate(definition, settings, request, read_json(run / 'artifacts/native.json'), *reports)
    stats = replay['statistics']
    changes = {name: row['absolute_change_comparison'] for name, row in stats['held_costs'].items()}
    reversals = {name: len(row['signed_reversals']) for name, row in stats['held_costs'].items()}
    return {'run': run.name, 'pairs': len(request['trials']), 'statistics': stats, 'predictions': replay['predictions']}, {
        'f2_pooled_sweep_fixed_inputs_and_paired_reports_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values())
            and replay == summary and len(request['trials']) == scope['pairs']),
        'f2_pooled_sweep_cost_changes_and_predictions_replayed': (
            changes == scope['cost_changes'] and reversals == scope['reversals']
            and stats['width_floor_conditions'] == scope['width_floor_conditions']
            and stats['zero_cost_conditions'] == scope['zero_cost_conditions']
            and replay['predictions'] == scope['predictions']),
    }


def audit_f2_held_fl(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    sweep = RUNS / definition['sweep']['run']
    source = saved_definition(sweep, records)
    original = RUNS / source['original_interventions']['run']
    settings = saved_definition(original, records)['measurement']
    previous = read_json(sweep / 'artifacts/inputs.json')
    past = read_json(sweep / 'artifacts/native.json')
    collection = read_json(run / 'artifacts/collection/native.json')
    request = f2_held_fl.held_request(definition, previous, collection)
    native = read_json(run / 'artifacts/native.json')
    replay = f2_held_fl.evaluate(definition, settings, request, past, native)
    wavs, matched = audit_f2_recording_collection(definition, run, collection, cfg, settings['ipa'])
    zeros = {name: {voice: row['zero_conditions'] for voice, row in stats.items()}
             for name, stats in replay['fl_statistics'].items()}
    support = {key: value['support'] for key, value in replay['profiles'].items()}
    return {'run': run.name, **wavs, 'support': support, 'fl_zero_conditions': zeros,
            'fk_zero_conditions': replay['fk_zero_conditions'], 'predictions': replay['predictions']}, {
        'f2_held_fl_recordings_and_independent_lpc': (
            matched and all(wavs[key] == scope[key] for key in ('added_recordings', 'added_finite_tokens'))),
        'f2_held_fl_fixed_references_and_costs_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values())
            and replay == summary and scope['pairs'] == len(request['trials'])),
        'f2_held_fl_support_and_zero_counts_replayed': (
            zeros == scope['fl_zero_conditions'] and support == scope['support']
            and replay['predictions'] == scope['predictions']),
    }


def audit_f2_over_sets(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    sources = {name: RUNS / definition[name.lower()]['run'] for name in f2_over_sets.SPEAKERS}
    fk_case = saved_definition(sources['FK'], records)
    settings = saved_definition(RUNS / fk_case['original_interventions']['run'], records)['measurement']
    inputs = {name: read_json(root / 'artifacts/inputs.json') for name, root in sources.items()}
    reports = {name: read_json(root / 'artifacts/native.json') for name, root in sources.items()}
    request = f2_over_sets.derive_input(definition, inputs, reports)
    replay = f2_over_sets.evaluate(definition, settings, request, reports, read_json(run / 'artifacts/native.json'))
    stats = replay['statistics']
    counts = {cohort: {name: values['zero_conditions'] for name, values in modes.items()} for cohort, modes in stats.items()}
    availability = {name: data['support'] for name, data in replay['aggregate_profiles'].items()}
    changes = {name: len(values) for name, values in replay['zero_classification_changes'].items()}
    return {'run': run.name, 'cases': len(replay['costs']), 'statistics': stats,
            'aggregate_support': availability, 'classification_changes': changes, 'predictions': replay['predictions']}, {
        'f2_over_sets_fixed_inputs_and_costs_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values())
            and replay == summary and len(replay['costs']) == scope['cases']),
        'f2_over_sets_zero_and_support_counts_replayed': (
            counts == scope['zero_conditions'] and availability == scope['aggregate_support']
            and changes == scope['classification_changes'] and replay['predictions'] == scope['predictions']
            and all(data['both_short']['missing_conditions'] == scope['cases'] - 1 for data in stats.values())),
    }


def audit_f2_full_held(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    source = RUNS / definition['partial']['run']
    source_case = saved_definition(source, records)
    sweep = saved_definition(RUNS / source_case['fk']['run'], records)
    settings = saved_definition(RUNS / sweep['original_interventions']['run'], records)['measurement']
    fk = RUNS / definition['fk_recordings']['run']
    fl = RUNS / definition['fl_recordings']['run']
    overlap = f2_full_held.partial_rows(
        saved_definition(fl, records), read_json(fk / 'artifacts/native.json'),
        read_json(fl / 'artifacts/collection/native.json'), saved_definition(fk, records))
    partial = read_json(source / 'artifacts/inputs.json')
    collection = read_json(run / 'artifacts/collection/native.json')
    request = f2_full_held.full_request(definition, partial, collection)
    replay = f2_full_held.evaluate(definition, settings, partial, read_json(source / 'summary.json'),
                                  overlap, collection, request, read_json(run / 'artifacts/native.json'))
    counts, matched = audit_f2_recording_collection(definition, run, collection, cfg, request['ipa'])
    zeros = {name: stat['over_sets']['zero_conditions'] for name, stat in replay['statistics'].items()}
    synthesised = {speaker: row['support'] for speaker, row in replay['synth_profiles'].items()}
    changed = sorted(replay['overlap']['differences'])
    return {'run': run.name, **counts, 'synth_support': synthesised, 'zero_conditions': zeros,
            'changed_recordings': changed, 'predictions': replay['predictions']}, {
        'f2_full_held_recordings_and_independent_lpc': (
            matched and all(counts[key] == scope[key] for key in ('added_recordings', 'added_finite_tokens'))),
        'f2_full_held_fixed_reference_and_all_costs_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values())
            and replay == summary and len(replay['costs']) == scope['cases']),
        'f2_full_held_support_overlap_and_zero_counts_replayed': (
            synthesised == scope['synth_support'] and zeros == scope['zero_conditions']
            and changed == scope['changed_recordings'] and replay['predictions'] == scope['predictions']),
    }


def audit_f2_full_candidate(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    source = RUNS / definition['baseline']['run']
    corpus = saved_definition(source, records)
    partial = saved_definition(RUNS / corpus['partial']['run'], records)
    sweep = saved_definition(RUNS / partial['fk']['run'], records)
    settings = saved_definition(RUNS / sweep['original_interventions']['run'], records)['measurement']
    template = read_json(RUNS / definition['matched_settings']['run'] / definition['render_template'])
    expected = f2_full_candidate.candidate_inputs(corpus, template['speech_voice'])
    archive = [read_json(source / name) for name in ('artifacts/inputs.json', 'summary.json', 'artifacts/collection/native.json')]
    upper_input, upper_summary, upper_collection = archive
    observed = read_json(run / 'artifacts/collection/native.json')
    renders = read_json(run / 'artifacts/renders.json')
    indices = read_json(run / 'artifacts/f2-frame-index.json')
    with np.load(run / 'artifacts/f2-frames.npz', allow_pickle=False) as retained:
        lpc = f2_full_candidate.audit_f2_frames(observed, upper_input['ipa'], cfg, indices, retained['frames'])
    request = f2_full_held.full_request(corpus, upper_input, observed)
    replay = f2_full_candidate.evaluate(definition, settings, upper_input, upper_summary,
        upper_collection, observed, renders, request, read_json(run / 'artifacts/native.json'), lpc)
    stats = {
        'plan_timing_changed': sum(row['plan_first_difference'] is not None or not row['plan_frames_match']
                                   for row in replay['stages'].values()),
        'pcm_differs': sum(row['pcm_first_difference'] is not None for row in replay['stages'].values()),
        'pcm_exceeds_tolerance': sum(row['pcm_exceeds_tolerance'] for row in replay['stages'].values()),
        'alignment_changed': sum(row['alignment_differences'] > 0 for row in replay['stages'].values()),
        'f2_changed': sum(row['f2_differences'] > 0 for row in replay['stages'].values()),
        'first_pcm_difference': min((row['pcm_first_difference'] for row in replay['stages'].values()
                                     if row['pcm_first_difference'] is not None), default=None),
    }
    zeros = {name: row['over_sets']['zero_conditions'] for name, row in replay['statistics'].items()}
    same_recordings = read_json(run / 'artifacts/collection/recordings.json') == read_json(source / 'artifacts/collection/recordings.json')
    archived = RUNS / definition['matched_settings']['run'] / 'artifacts/matched-pcm.npz'
    archived_pcm_checks = []
    with np.load(archived, allow_pickle=False) as stored:
        for uid, stage in replay['stages'].items():
            if f'{uid}_upstream' not in stored.files:
                continue
            a, b = (stored[f'{uid}_{tag}'].astype(np.float64) for tag in ('upstream', 'candidate'))
            residual = np.abs(a - b)
            positions = np.flatnonzero(residual)
            first = int(positions[0]) if len(positions) else None
            archived_pcm_checks.append(first == stage['pcm_first_difference']
                                       and float(residual.max()) == stage['pcm_maximum_absolute_difference'])
    return {'run': run.name, 'difference_counts': stats, 'lpc': lpc,
            'zero_conditions': zeros, 'archived_pcm_comparisons': len(archived_pcm_checks),
            'predictions': replay['predictions']}, {
        'f2_full_candidate_inputs_and_retained_frames_replayed': (
            same_recordings and expected == read_json(run / 'artifacts/render-inputs.json')
            and lpc['maximum_error_hz'] is not None and lpc['maximum_error_hz'] <= cfg['frequency_bandwidth_agreement_hz']
            and lpc['finite_tokens'] == scope['finite_tokens']),
        'f2_full_candidate_costs_and_observations_replayed': (
            request == read_json(run / 'artifacts/inputs.json') and all(replay['checks'].values()) and replay == summary),
        'f2_full_candidate_stage_and_zero_counts_replayed': (
            stats == scope['difference_counts'] and zeros == scope['zero_conditions']
            and replay['predictions'] == scope['predictions']
            and len(archived_pcm_checks) == scope['archived_pcm_comparisons'] and all(archived_pcm_checks)),
    }


def audit_fk61_pcm(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    matched = RUNS / definition['matched']['run']
    configuration = saved_definition(matched, records)
    uid = definition['measurement']['recording_id']
    archived = fk61_pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    coefficients = read_json(run / 'artifacts/coefficients.json')
    matches = read_json(run / 'artifacts/ordinary-pcm.json')
    with np.load(run / 'artifacts/prefix.npz', allow_pickle=False) as retained:
        replay = fk61_pcm.evaluate(definition, configuration, gain, retained, coefficients, archived, matches)
    source = replay['source_differences']
    stages = replay['output_differences']
    moments = {
        'radiation_internal': source['radiation_derivative_cm3_s2']['first_unequal_sample'],
        'fir_output': stages['decimated']['first_unequal_sample'],
        'dc_output': stages['dc_removed']['first_unequal_sample'],
        'pcm_output': replay['pcm_difference']['first_unequal_sample'],
    }
    return {'run': run.name, 'first_differences': moments, 'rounding': replay['rounding'],
            'predictions': replay['predictions']}, {
        'fk61_pcm_retained_prefix_and_exact_replay': all(replay['checks'].values()) and replay == summary,
        'fk61_pcm_first_sample_and_rounding_replayed': (
            moments == scope['first_differences'] and replay['predictions'] == scope['predictions']),
    }


def audit_fk61_lip(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    previous = RUNS / definition['previous']['run']
    matched = RUNS / definition['matched']['run']
    uid = definition['measurement']['recording_id']
    first, stop = definition['measurement']['comparison_internal_samples']
    artifacts = run / 'artifacts'
    digests = read_json(artifacts / 'pcm-digests.json')
    archive = fk61_lip.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)
    matches = {
        name: item['bit_equal'] and item['ordinary'] == item['probe'] == item['archived']
            == fk61_lip.pcm_digest(archive[name])
        for name, item in digests.items()
    }
    traces = {name: fk61_lip.read_trace(artifacts / f'{name}-lip.f64le', stop - first) for name in fk61_lip.MODES}
    with np.load(previous / 'artifacts/prefix.npz', allow_pickle=False) as prefix:
        replay = fk61_lip.evaluate(definition, traces, matches, prefix)
    rounding = replay['volume_rounding']
    relative = max(row['relative_error'] for row in replay['geometry_inflow_swap'].values())
    delta = rounding['stored_candidate_minus_upstream']
    return {'run': run.name, 'first_lip_difference': replay['first_lip_difference'], 'window': replay['window'],
            'predictions': replay['predictions'], 'volume_delta_difference_cm3': delta,
            'swap_max_relative_error': relative}, {
        'fk61_lip_retained_geometry_and_exact_replay': (
            all(replay['checks'].values()) and replay == summary
            and read_json(artifacts / 'columns.json') == list(fk61_lip.LOAD_FIELDS + fk61_lip.observer.FIELDS)),
        'fk61_lip_first_sample_and_inflow_swap': (
            replay['first_lip_difference'] == scope['first_lip_difference']
            and replay['window'] == scope['window'] and replay['predictions'] == scope['predictions']
            and relative <= scope['swap_relative_limit']),
        'fk61_lip_volume_rounding_replayed': (
            delta == scope['volume_delta_difference_cm3']
            and all(rounding['same_multiply_and_divide_on_each_rounded_delta'].values())
            and abs(rounding['exact_candidate_minus_upstream']) < scope['exact_raw_difference_limit_cm3_s']),
    }


def audit_fk61_volume(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    prior = RUNS / study['lip']['run'] / 'artifacts'
    output = RUNS / study['output']['run'] / 'artifacts'
    matched = RUNS / study['matched']['run']
    artifacts = run / 'artifacts'
    uid = study['measurement']['recording_id']
    first, stop = study['measurement']['internal_window']
    config = saved_definition(matched, records)
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    coeffs = read_json(output / 'coefficients.json')['candidate']
    archived = fk61_pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)
    previous_lip = fk61_lip.read_trace(prior / 'candidate-lip.f64le', stop - first)
    trial_lip = fk61_lip.read_trace(artifacts / 'lip.f64le', stop - first)
    proof = read_json(artifacts / 'pcm-digests.json')
    with np.load(output / 'prefix.npz', allow_pickle=False) as prefix, \
            np.load(artifacts / 'render.npz', allow_pickle=False) as trial:
        replay = fk61_volume.evaluate(study, config, gain, prefix, archived, trial, proof, coeffs,
                                      previous_lip, trial_lip)
    pcm_first = {name: row['first_unequal_sample'] for name, row in replay['pcm'].items()}
    radiation_first = replay['intervention']['radiation_derivative_cm3_s2']['first_unequal_sample']
    rounding = replay['first_trial_rounding']
    return {'run': run.name, 'pcm_first': pcm_first, 'intervention_radiation_first': radiation_first,
            'predictions': replay['predictions'], 'event': replay['event'], 'first_trial_rounding': rounding}, {
        'fk61_volume_retained_trial_and_exact_replay': all(replay['checks'].values()) and replay == summary,
        'fk61_volume_first_differences_and_predictions_replayed': (
            pcm_first == scope['pcm_first'] and radiation_first == scope['intervention_radiation_first']
            and replay['predictions'] == scope['predictions']),
        'fk61_volume_first_pcm_rounding_replayed': (
            rounding['adjacent'] and rounding['straddles']
            and rounding['frame'] == pcm_first['upstream_to_trial']
            and rounding['from_midpoint']['trial'] < 0 < rounding['from_midpoint']['candidate']
            and rounding['pcm']['candidate'] == rounding['pcm']['upstream']),
    }


def audit_fk61_area(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    prior = RUNS / study['lip']['run']
    matched = RUNS / study['matched']['run']
    cfg = study['measurement']
    artifacts = run / 'artifacts'
    low, high = saved_definition(prior, records)['measurement']['comparison_internal_samples']
    previous = {name: dict(zip(range(low, high),
                      fk61_lip.read_trace(prior / 'artifacts' / f'{name}-lip.f64le', high - low), strict=True))
                for name in fk61_lip.MODES}
    snapshots = {name: fk61_area.read_snapshots(artifacts / f'{name}.jsonl', cfg['completed_frames'])
                 for name in fk61_lip.MODES}
    reference = fk61_pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', cfg['recording_id'])
    replay = fk61_area.evaluate(study, snapshots, previous, read_json(artifacts / 'pcm-digests.json'), reference)
    initial = replay['frames'][0]
    raw_at_init = {name: initial['model'][name]['raw'][0] for name in fk61_lip.MODES}
    rays = replay['initial_ray_diagnostics']
    by_index = {row['ray']: row for row in rays['per_ray_area_input_swaps']}
    sources = scope['ray_sources']
    return {'run': run.name, 'initial_raw_mean_cm2': raw_at_init, 'predictions': replay['predictions'],
            'initial_grid_differences_in_cell_rays': initial['grid_differences_in_cell_rays'],
            'changed_rays': rays['changed_rays']}, {
        'fk61_area_retained_geometry_and_independent_replay': (
            all(replay['checks'].values()) and replay == summary
            and read_json(artifacts / 'grid-columns.json') == list(fk61_area.GRID_COLUMNS)),
        'fk61_area_first_geometry_difference_and_exchange_replayed': (
            raw_at_init == scope['initial_raw_mean_cm2'] and replay['predictions'] == scope['predictions']),
        'fk61_area_initial_ray_inputs_and_swaps_replayed': (
            rays['changed_rays'] == scope['changed_rays']
            and all(row[name]['measured_area'] == row[name]['replayed_area']
                    for row in rays['per_ray_area_input_swaps'] for name in fk61_lip.MODES)
            and all(by_index[int(index)][name][field] == by_index[int(index)][other]['measured_area']
                    for index, field in sources.items() for name, other in (fk61_lip.MODES, fk61_lip.MODES[::-1]))
            and all(rows[-1]['matches_donor'] for rows in rays['resampling_swaps'].values())),
    }


def audit_fk61_front(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    geometry = RUNS / study['geometry']['run']
    matched = RUNS / study['matched']['run']
    cfg = study['measurement']
    artifacts = run / 'artifacts'
    baseline_frames = saved_definition(geometry, records)['measurement']['completed_frames']
    baseline = {name: fk61_area.read_snapshots(geometry / 'artifacts' / f'{name}.jsonl', baseline_frames)
                for name in fk61_lip.MODES}
    snapshots = {name: fk61_area.read_snapshots(artifacts / f'{name}.jsonl', cfg['completed_frames'])
                 for name in fk61_front.MODES}
    archived = fk61_pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', cfg['recording_id'])
    proof = read_json(artifacts / 'pcm-digests.json')
    with np.load(artifacts / 'trial-pcm.npz', allow_pickle=False) as trial:
        replay = fk61_front.evaluate(study, snapshots, baseline, archived, proof, trial['pcm'])
    initial = replay['observations']['0']
    root = replay['first_coordinate_difference']
    first_pcm = {name: row['first_unequal_sample'] for name, row in replay['pcm'].items()}
    coordinates = {name: row['coordinates'][root] for name, row in initial.items()}
    return {'run': run.name, 'first_coordinate_difference': root, 'coordinates_cm': coordinates,
            'initial_cell': {name: row['local_cell'] for name, row in initial.items()},
            'first_pcm': first_pcm, 'predictions': replay['predictions']}, {
        'fk61_front_retained_trial_coordinates_and_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_front_transform_and_first_pcm_difference_replayed': (
            root == scope['first_coordinate_difference'] and coordinates == scope['coordinates_cm']
            and first_pcm == scope['first_pcm'] and replay['predictions'] == scope['predictions']),
    }


def audit_fk61_centerline(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    geometry = RUNS / study['geometry']['run']
    matched = RUNS / study['matched']['run']
    cfg = study['measurement']
    artifacts = run / 'artifacts'
    previous_frames = saved_definition(geometry, records)['measurement']['completed_frames']
    previous = {name: fk61_area.read_snapshots(geometry / 'artifacts' / f'{name}.jsonl', previous_frames)
                for name in fk61_lip.MODES}
    snapshots = {name: fk61_area.read_snapshots(artifacts / f'{name}.jsonl', cfg['completed_frames'])
                 for name in fk61_centerline.MODES}
    source = RUNS / saved_definition(geometry, records)['geometry']['run']
    source_measurement = saved_definition(source, records)['measurement']
    [frame] = cfg['completed_frames']
    before = {name: fk61_area.read_snapshots(source / 'artifacts' / f'{name}.jsonl',
                                            source_measurement['completed_frames'])[frame - 1]
              for name in fk61_lip.MODES}
    ramps = fk61_centerline.compare_length_ramps(
        before, {name: values[frame] for name, values in snapshots.items()}, source_measurement['control_samples'])
    archived = fk61_pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', cfg['recording_id'])
    proof = read_json(artifacts / 'pcm-digests.json')
    with np.load(artifacts / 'trial-pcm.npz', allow_pickle=False) as trial:
        replay = fk61_centerline.evaluate(study, snapshots, previous, archived, proof, trial['pcm'])
    first_pcm = {name: row['first_unequal_sample'] for name, row in replay['pcm'].items()}
    lengths = {name: row['target_cm'] for name, row in replay['geometry'].items()}
    return {'run': run.name, 'first_cumulative_difference': replay['first_cumulative_difference'],
            'length_targets_cm': lengths, 'predictions': replay['predictions'], 'first_pcm': first_pcm,
            'midpoint_at_focus': replay['midpoint_at_focus'], 'length_ramp_replay': ramps}, {
        'fk61_centerline_retained_distances_and_trial_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_centerline_gap_rounding_and_trial_replayed': (
            replay['first_cumulative_difference'] == scope['first_cumulative_difference']
            and lengths == scope['length_targets_cm'] and replay['predictions'] == scope['predictions']
            and first_pcm == scope['first_pcm']),
        'fk61_centerline_length_ramp_rounding_replayed': (
            ramps['same_length_each_predicted_sample']
            and all(row['matches_observation_after_two'] for row in ramps['model'].values())),
    }


def audit_fk61_residual(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    cfg = study['measurement']
    uid = cfg['recording_id']
    first, stop = cfg['comparison_internal_samples']
    artifacts = run / 'artifacts'
    baselines = {name: RUNS / study[name]['run'] / 'artifacts' for name in ('front', 'lip', 'output', 'matched')}
    configuration = saved_definition(baselines['matched'].parent, records)
    gain = read_json(baselines['matched'] / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    archived = fk61_pcm.archived_pcm(baselines['matched'] / 'matched-pcm.npz', uid) | {
        'trial': fk61_residual.read_trial(baselines['front'] / 'trial-pcm.npz')}
    older = {name: fk61_lip.read_trace(baselines['lip'] / f'{name}-lip.f64le', stop - first) for name in fk61_lip.MODES}
    geometry = {name: fk61_lip.read_trace(artifacts / f'{name}-lip.f64le', stop - first) for name in fk61_residual.MODES}
    cells = {name: fk61_residual.read_nodes(artifacts / f'{name}-nodes.csv', first, stop) for name in fk61_residual.MODES}
    coefficients = read_json(baselines['output'] / 'coefficients.json')
    with np.load(artifacts / 'prefix.npz', allow_pickle=False) as prefix, \
            np.load(baselines['output'] / 'prefix.npz', allow_pickle=False) as previous:
        replay = fk61_residual.analyze(study, configuration, gain, prefix, previous, coefficients, archived, geometry,
                                       cells, read_json(artifacts / 'pcm-digests.json'), older)
        counterfactuals = fk61_residual.onset_counterfactuals(study, configuration, gain, prefix, coefficients)
    first_sources = {key: replay['first_source_differences_from_upstream']['trial'][key]['first_unequal_sample']
                     for key in (*fk61_residual.COMPONENTS, fk61_residual.RADIATION)}
    successful_single_components = [row['components'][0] for row in replay['radiation_component_swaps']['trial']
                                    if len(row['components']) == 1 and row['matches_pcm_through_frame']]
    first_pcm = replay['pcm']['trial']['first_unequal_sample']
    single_samples = [row['sample'] for row in counterfactuals['mouth_sample_swaps'] if row['pcm_matches_through_frame']]
    order_swaps = counterfactuals['derivative_order_swaps']
    return {'run': run.name, 'first_sources': first_sources, 'first_pcm': first_pcm,
            'successful_single_components': successful_single_components, 'predictions': replay['predictions'],
            'first_pcm_rounding': replay['first_pcm_rounding'], 'onset_counterfactuals': counterfactuals}, {
        'fk61_residual_network_and_output_replayed': (
            all(replay['checks'].values()) and replay == summary
            and read_json(artifacts / 'node-columns.json') == list(fk61_residual.observer.FIELDS)),
        'fk61_residual_first_radiation_and_component_exchange_replayed': (
            first_sources == scope['first_sources'] and first_pcm == scope['first_pcm']
            and successful_single_components == scope['successful_single_components']
            and replay['predictions'] == scope['predictions']),
        'fk61_residual_derivative_order_and_single_sample_swaps_replayed': (
            order_swaps['upstream']['first_pcm_difference'] is None
            and order_swaps['trial']['first_pcm_difference'] == first_pcm
            and single_samples == scope['successful_single_mouth_samples']),
    }


def audit_fk61_terminal(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    artifacts = run / 'artifacts'
    prior, output, matched = (RUNS / study[key]['run'] / 'artifacts' for key in ('radiation', 'output', 'matched'))
    configuration = saved_definition(matched.parent, records)
    uid = study['measurement']['recording_id']
    gain = read_json(matched / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    proof = read_json(artifacts / 'pcm-digests.json')
    replay = fk61_terminal.analyze(study, configuration, gain, read_json(output / 'coefficients.json'), artifacts,
                                   {name: prior / name for name in fk61_terminal.RETAINED}, proof)
    interventions = {','.join(row['terms']): row['first_pcm_difference_through_frame']
                     for row in (*replay['output_interventions'], *replay['exploratory_interventions'])}
    initial = scope['retained_failure']
    before = RUNS / initial['run']
    failed, hashes = read_record(before.name, study['upstream_revision'], expected_failure=True,
                                 expected_failed_checks=(initial['check'],))
    unchanged = all(hashes.get(f'artifacts/{name}') == sha256(artifacts / name) for name in (
        *fk61_terminal.RETAINED, *(f'{mode}-{tag}.csv' for mode in fk61_terminal.MODES
                                   for tag in fk61_terminal.observer.FIELDS)))
    return {'run': run.name, 'local_samples': replay['local_samples'], 'predictions': replay['predictions'],
            'pcm_difference_by_intervention': interventions}, {
        'fk61_terminal_branch_and_two_cell_state_replayed': (
            all(replay['checks'].values()) and replay == summary
            and proof == read_json(prior / 'pcm-digests.json')),
        'fk61_terminal_pressure_and_pcm_interventions_replayed': (
            replay['predictions'] == scope['predictions']
            and interventions == scope['pcm_difference_by_intervention']),
        'fk61_terminal_first_comparison_failure_retained': (
            not failed['errors'] and unchanged and sha256(before / 'manifest.json') == initial['manifest_sha256']),
    }


def audit_fk61_node42(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    artifacts = run / 'artifacts'
    prior, output, matched = (RUNS / study[key]['run'] / 'artifacts' for key in ('terminal', 'output', 'matched'))
    configuration = saved_definition(matched.parent, records)
    uid = study['measurement']['recording_id']
    gain = read_json(matched / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    replay = fk61_node42.analyze(study, configuration, gain, read_json(output / 'coefficients.json'), artifacts,
                                 prior, read_json(artifacts / 'pcm-digests.json'))
    first = replay['first_trial_difference']
    interventions = {name: row['first_pcm_difference_through_frame']
                     for name, row in replay['output_interventions'].items()}
    return {'run': run.name, 'first_trial_difference': first, 'predictions': replay['predictions'],
            'pcm_difference_by_intervention': interventions}, {
        'fk61_node42_geometry_routing_and_poles_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_node42_first_source_difference_and_pcm_interventions_replayed': (
            first == scope['first_trial_difference'] and replay['predictions'] == scope['predictions']
            and interventions == scope['pcm_difference_by_intervention']),
    }


def audit_fk61_node42_area(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    measure = study['measurement']
    artifacts = run / 'artifacts'
    front = RUNS / study['front']['run'] / 'artifacts'
    volume = RUNS / study['volume']['run']
    modes = fk61_node42_area.front.MODES
    snapshots = {mode: fk61_node42_area.area.read_snapshots(artifacts / f'{mode}.jsonl', measure['completed_frames'])
                 for mode in modes}
    prior = {mode: fk61_node42_area.read_ramp(volume / 'artifacts' / f'{mode}-geometry.csv', measure) for mode in modes}
    previous = {mode: fk61_node42_area.area.read_snapshots(front / f'{mode}.jsonl', [0, 1985]) for mode in modes}
    replay = fk61_node42_area.analyze(study, snapshots, prior, previous, read_json(artifacts / 'pcm-digests.json'),
                                      read_json(front / 'pcm-digests.json'),
                                      fk61_node42_area.read_trial(front / 'trial-pcm.npz'),
                                      read_json(volume / 'summary.json'))
    aligned = {frame: [row['terms'] for row in report['combinations'] if row['mean_error_cm2'] == 0.0]
               for frame, report in replay['resampling_interventions'].items()}
    area_swaps = [name for name, row in replay['ramp_area_interventions'].items() if row['error_cm3_s'] == 0.0]
    return {'run': run.name, 'matches_by_frame': aligned, 'matching_ramp_area_swaps': area_swaps,
            'predictions': replay['predictions']}, {
        'fk61_node42_area_and_ramp_replayed': (
            all(replay['checks'].values()) and replay == summary
            and sha256(artifacts / 'trial-pcm.npz') == sha256(front / 'trial-pcm.npz')),
        'fk61_node42_area_and_ramp_interventions_replayed': (
            replay['predictions'] == scope['predictions'] and aligned == scope['matches_by_frame']
            and area_swaps == scope['matching_ramp_area_swaps']),
    }


def audit_fk61_ray43(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    measure = study['measurement']
    artifacts = run / 'artifacts'
    prior = RUNS / study['area']['run'] / 'artifacts'
    modes = fk61_ray43.front.MODES
    snapshots = [{mode: fk61_ray43.area.read_snapshots(path / f'{mode}.jsonl', measure['completed_frames'])
                  for mode in modes} for path in (artifacts, prior)]
    replay = fk61_ray43.analyze(study, *snapshots, read_json(artifacts / 'pcm-digests.json'),
                                read_json(prior / 'pcm-digests.json'), fk61_ray43.read_trial(prior / 'trial-pcm.npz'))
    focus = str(replay['focus_frame'])
    upper = replay['frames'][focus]['upstream']
    parts = {mode: row['lower_part'] for mode, row in replay['frames'][focus].items()}
    aligned = [row['terms'] for row in replay['interventions'] if row['inner_xy_cm'] == upper['inner_xy_cm']]
    curves = fk61_ray43.curve_comparison(
        {mode: snapshots[0][mode][int(focus)] for mode in modes}, measure['grid_index'])
    native_methods = {'upstream': 'bernstein', 'candidate': 'de_casteljau', 'trial': 'de_casteljau'}
    same_controls = curves['upstream']['controls'] == curves['trial']['controls']
    native_curves = all(curves[mode]['methods'][method]['matches_native_endpoints']
                        for mode, method in native_methods.items())
    with_bernstein = curves['trial']['methods']['bernstein']
    return {'run': run.name, 'lower_parts': parts, 'matches_at_focus': aligned,
            'first_divergent_term': replay['lower_first_divergent_term'], 'predictions': replay['predictions'],
            'exploratory_lower_lip_curves': curves}, {
        'fk61_ray43_intersections_and_areas_replayed': (
            all(replay['checks'].values()) and replay == summary
            and sha256(artifacts / 'trial-pcm.npz') == sha256(prior / 'trial-pcm.npz')),
        'fk61_ray43_endpoint_interventions_replayed': (
            replay['predictions'] == scope['predictions'] and parts == scope['lower_parts']
            and replay['lower_first_divergent_term'] == scope['first_divergent_term']
            and aligned == scope['matches_at_focus']),
        'fk61_ray43_exploratory_bezier_evaluation_replayed': (
            same_controls and native_curves and with_bernstein['endpoints'] == upper['chosen']['lower']['endpoints']
            and with_bernstein['distance_cm'] == upper['chosen']['lower']['distance']
            and with_bernstein['cell_cm2'] == snapshots[0]['upstream'][int(focus)]['before_lip']['raw']),
    }


def audit_fk61_bernstein(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    measure = study['measurement']
    artifacts = run / 'artifacts'
    intersection, volume, output, matched = (RUNS / study[key]['run'] for key in ('intersection', 'volume', 'output', 'matched'))
    configuration = saved_definition(matched, records)
    uid = measure['recording_id']
    spec = read_json(matched / 'artifacts' / uid / 'matched-case.json')
    gain = spec['speech_voice']['voice']['output_gain']
    prior = {mode: fk61_bernstein.front.area.read_snapshots(intersection / 'artifacts' / f'{mode}.jsonl',
                                                           measure['completed_frames'])
             for mode in ('upstream', 'trial')}
    archived = fk61_bernstein.front.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid) | {
        'trial': fk61_bernstein.ray.read_trial(intersection / 'artifacts/trial-pcm.npz')}
    with np.load(volume / 'artifacts/prefix.npz', allow_pickle=False) as prefix:
        replay = fk61_bernstein.analyze(study, configuration, gain, read_json(output / 'artifacts/coefficients.json'),
                                       artifacts, prior, archived, prefix, read_json(volume / 'summary.json'))
    first, stop = measure['comparison_internal_samples']
    clock = measure['internal_sample_rate_hz']
    observed_lip = fk61_bernstein.lip.read_trace(artifacts / f'{fk61_bernstein.LABEL}-lip.f64le', stop - first)
    with np.load(artifacts / 'render.npz', allow_pickle=False) as render:
        state = dict(zip(fk61_bernstein.radiation.FIELDS, render['source'].T, strict=True))
        terminal_verified = all(fk61_bernstein.lip.solve_matches(row, clock, False) for row in observed_lip) and np.array_equal(
            state['lip_cm3_s'][first:stop], [row['lip_flow_cm3_s'] for row in observed_lip])
    def edits(path):
        return [line for line in path.read_text().splitlines()
                if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))]

    failures = {}
    for failed in scope['retained_failures']:
        before = RUNS / failed['run']
        manifest = read_json(before / 'manifest.json')
        report, _ = read_record(before.name, study['upstream_revision'], expected_failure=True,
                                expected_error=manifest['error'])
        log = (before / 'artifacts/cargo.log').read_text()
        last = manifest['commands'][-1]
        if failed['kind'] == 'test_fixtures':
            cause = (last['exit_code'] == 101 and last['argv'][-2:] == ['--lib', 'anatomy::grid::tests']
                     and log.count('No such file or directory') >= 2
                     and all(path.name in log for path in fk61_bernstein.TEST_CASES))
        else:
            cause = (failed['kind'] == 'observation_anchor' and last['exit_code'] == 0
                     and manifest['error'] == '観測挿入位置を特定できません (anatomy.rs:     );)'
                     and '0 failed' in (before / 'artifacts/grid-tests.log').read_text())
        failures[before.name] = (
            not report['errors'] and sha256(before / 'manifest.json') == failed['manifest_sha256'] and cause
            and edits(before / 'artifacts/lower-lip-evaluation.patch') == edits(artifacts / 'lower-lip-evaluation.patch'))
    return {'run': run.name, 'predictions': replay['predictions'], 'pcm': replay['pcm'],
            'volume_focus': replay['volume_focus'], 'retained_failures': failures}, {
        'fk61_bernstein_geometry_volume_and_full_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_bernstein_first_differences_replayed': (
            replay['predictions'] == scope['predictions']
            and replay['pcm']['bernstein']['first_unequal_sample'] == scope['first_pcm']
            and replay['radiation_prefix']['upstream'][fk61_bernstein.radiation.RADIATION]['first_unequal_sample']
            == scope['first_radiation_derivative']),
        'fk61_bernstein_terminal_load_replayed': terminal_verified,
        'fk61_bernstein_setup_failures_retained': bool(failures) and all(failures.values()),
    }


def audit_fk61_pcm2937(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    bernstein, output, volume, matched = (RUNS / study[key]['run']
                                          for key in ('bernstein', 'output', 'volume', 'matched'))
    configuration = saved_definition(matched, records)
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    expected = fk61_pcm2937.pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)['upstream']
    with np.load(volume / 'artifacts/prefix.npz', allow_pickle=False) as prior:
        replay = fk61_pcm2937.analyze(
            study, configuration, gain, run / 'artifacts', bernstein / 'artifacts/render.npz', prior,
            read_json(output / 'artifacts/coefficients.json'), expected)
    dc = [row['terms'] for row in replay['dc_state_swaps']['variants'] if row['matches_upstream_at_focus']]
    windows = [row['windows'] for row in replay['radiation_window_swaps']['variants'] if row['matches_upstream_at_focus']]
    components = [{key: row[key] for key in ('derivative_order', 'components')}
                  for row in replay['radiation_component_swaps'] if row['matches_upstream_at_focus']]
    return {'run': run.name, 'rounding': replay['rounding'], 'predictions': replay['predictions'],
            'matching_dc_swaps': dc, 'matching_radiation_windows': windows, 'matching_radiation_components': components}, {
        'fk61_pcm2937_radiation_and_output_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_pcm2937_controlled_swaps_replayed': (
            replay['predictions'] == scope['predictions'] and dc == scope['matching_dc_swaps']
            and windows == scope['matching_radiation_windows'] and components == scope['matching_radiation_components']),
    }


def audit_fk61_lip_window(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    measured, bernstein, output, matched = (RUNS / study[key]['run']
                                             for key in ('comparison', 'bernstein', 'output', 'matched'))
    configuration = saved_definition(matched, records)
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    sources = fk61_lip_window.load_series(measured / 'artifacts/upstream-prefix.npz', bernstein / 'artifacts/render.npz',
                                          study['measurement']['prefix_frames'])
    proof = {mode: read_json(path / 'artifacts/pcm-digests.json')
             for mode, path in zip(fk61_pcm2937.MODES, (measured, bernstein), strict=True)}
    replay, arrays = fk61_lip_window.analyze(study, configuration, gain, read_json(output / 'artifacts/coefficients.json'),
                                            sources, proof, read_json(measured / 'summary.json'))
    with np.load(run / 'artifacts/window-scan.npz', allow_pickle=False) as stored:
        array_checks = set(stored.files) == set(arrays) and all(
            value.dtype == stored[key].dtype and value.shape == stored[key].shape
            and value.tobytes() == stored[key].tobytes() for key, value in arrays.items())
    evidence = ('predictions', 'matching_intervals', 'matching_at_focus', 'shortest_intervals', 'single_matching_at_focus')
    failures = {}
    for failed in scope['retained_failures']:
        initial = RUNS / failed['run']
        verified, hashes = read_record(initial.name, study['upstream_revision'], expected_failure=True,
                                       expected_error='Object of type bool is not JSON serializable')
        failures[initial.name] = (
            not verified['errors'] and sha256(initial / 'manifest.json') == failed['manifest_sha256']
            and hashes.get('artifacts/window-scan.npz') == sha256(run / 'artifacts/window-scan.npz'))
    return {'run': run.name, **{key: replay[key] for key in evidence}, 'retained_failures': failures}, {
        'fk61_pcm2937_lip_window_and_linear_weights_replayed': (
            all(replay['checks'].values()) and replay == summary and array_checks),
        'fk61_pcm2937_shortest_lip_intervals_replayed': all(replay[key] == scope[key] for key in evidence),
        'fk61_pcm2937_lip_scan_serialization_failures_retained': bool(failures) and all(failures.values()),
    }


def audit_fk61_terminal_load(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    reference = {name: RUNS / study[name]['run'] / paths[0]
                 for name, paths in fk61_terminal_load.REFERENCE_FILES.items()}
    matched = RUNS / study['matched']['run']
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    proof = read_json(artifacts / 'pcm-digests.json')
    archived = fk61_terminal_load.pcm.archived_pcm(reference['matched'], uid)
    with np.load(reference['bernstein'], allow_pickle=False) as stored:
        archived['trial'] = stored['pcm']
    replay = fk61_terminal_load.analyze(study, saved_definition(matched, records), gain,
                                        read_json(reference['output']), artifacts, reference, proof)
    evidence = {
        'hypotheses_by_sample': replay['hypotheses_by_sample'],
        'lip_deltas_cm3_s': {n: row['lip_delta_upstream_minus_trial_cm3_s'] for n, row in replay['focus'].items()},
        'matching_history_exchanges': [row['groups'] for row in replay['history_exchanges']
                                       if row['first_difference_through_focus'] is None],
    }
    retained = (*fk61_terminal_load.terminal.RETAINED, 'pcm-digests.json',
                *(f'{mode}-{tag}.csv' for mode in fk61_terminal_load.MODES
                  for tag in fk61_terminal_load.observer.FIELDS))
    failures = {}
    for failed in scope.get('retained_failures', ()):
        previous = RUNS / failed['run']
        verified, hashes = read_record(previous.name, study['upstream_revision'], expected_failure=True,
                                       expected_error=failed.get('error'),
                                       expected_failed_checks=tuple(failed.get('failed_checks', ())))
        failures[previous.name] = (
            not verified['errors'] and sha256(previous / 'manifest.json') == failed['manifest_sha256']
            and all(hashes.get(f'artifacts/{name}') == sha256(artifacts / name) for name in retained))
    return {'run': run.name, **evidence, 'retained_failures': failures}, {
        'fk61_pcm2937_terminal_load_native_inputs_and_history_replayed': (
            all(replay['checks'].values()) and replay == summary
            and all(proof[mode]['archived'] == fk61_terminal_load.lip.pcm_digest(samples)
                    for mode, samples in archived.items())),
        'fk61_pcm2937_terminal_load_exchanges_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_pcm2937_terminal_load_initial_failures_retained': all(failures.values()),
    }


def audit_fk61_branch_drive(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    source, matched, output = (RUNS / study[key]['run'] for key in ('terminal_load', 'matched', 'output'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = source / 'artifacts'
    replay = fk61_branch_drive.analyze(study, saved_definition(matched, records), gain,
                                       read_json(output / 'artifacts/coefficients.json'), artifacts,
                                       read_json(source / 'summary.json'), read_json(artifacts / 'pcm-digests.json'))
    evidence = {
        'hypotheses': replay['hypotheses'],
        'matching_exchanges': [row['groups'] for row in replay['sequence_exchanges']
                               if row['first_difference_through_focus'] is None],
        'largest_analytical_residual_ulps': max(
            row['decomposition']['absolute_residual_ulps'] for row in replay['focus'].values()),
    }
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    return {'run': run.name, **evidence}, {
        'fk61_pcm2937_branch_dynamic_state_and_signed_decomposition_replayed': (
            all(replay['checks'].values()) and replay == summary),
        'fk61_pcm2937_branch_exchange_predictions_and_pcm_replayed': all(
            value == scope[key] for key, value in evidence.items()),
        'fk61_pcm2937_branch_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and hashes['summary.json'] == sha256(run / 'summary.json')),
    }


def audit_fk61_branch_seed(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    source, prior, matched, output = (RUNS / study[key]['run']
                                       for key in ('terminal_load', 'branch_drive', 'matched', 'output'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = source / 'artifacts'
    replay = fk61_branch_seed.analyze(study, saved_definition(matched, records), gain,
                                      read_json(output / 'artifacts/coefficients.json'), artifacts,
                                      read_json(prior / 'summary.json'), read_json(artifacts / 'pcm-digests.json'))
    evidence = {key: replay[key] for key in ('hypotheses', 'matching_starts_by_group', 'maximum_linear_residual_ulps')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    return {'run': run.name, **evidence}, {
        'fk61_pcm2937_branch_seed_sweep_and_linear_response_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_pcm2937_branch_seed_pcm_register_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_pcm2937_branch_seed_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and hashes['summary.json'] == sha256(run / 'summary.json')),
    }


def audit_fk61_branch_first(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    prior = RUNS / study['terminal_load']['run'] / 'artifacts'
    artifacts = run / 'artifacts'
    replay = fk61_branch_first.analyze(study, artifacts, prior, read_json(prior / 'pcm-digests.json'),
                                       read_json(artifacts / 'pcm-digests.json'))
    evidence = {
        'hypotheses': replay['hypotheses'],
        'first_flow_samples': {mode: {
            **{edge: row['flow']['sample'] for edge, row in analyses['edges'].items()},
            'mouth': analyses['mouth']['sample'],
        } for mode, analyses in replay['chronologies'].items()},
    }
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{file}' for file in fk61_branch_first.SAVED_FILES))
    return {'run': run.name, **evidence}, {
        'fk61_first_branch_kinematics_and_overlap_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_first_branch_times_and_hypotheses_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_first_branch_ordinary_and_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_oral_inflow(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    prior = RUNS / study['branch_first']['run'] / 'artifacts'
    artifacts = run / 'artifacts'
    replay = fk61_oral_inflow.analyze(study, artifacts, prior, read_json(artifacts / 'pcm-digests.json'))
    evidence = {key: replay[key] for key in ('hypotheses', 'node41_input_deltas', 'node40_volume_source')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_oral_inflow.SAVED_FILES))
    return {'run': run.name, **evidence}, {
        'fk61_oral_onset_branch_node_and_volume_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_oral_onset_causal_exchanges_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_oral_onset_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_node40_expanded(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, bernstein, prior, output = (RUNS / study[key]['run']
                                         for key in ('matched', 'bernstein', 'oral_inflow', 'coefficients'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    archived = fk61_node40_expanded.pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)
    with np.load(bernstein / 'artifacts/render.npz', allow_pickle=False) as stored:
        archived['trial'] = stored['pcm']
    artifacts = run / 'artifacts'
    replay = fk61_node40_expanded.analyze(study, artifacts, prior / 'artifacts', archived,
                                         saved_definition(matched, records), gain,
                                         read_json(output / 'artifacts/coefficients.json')['candidate'],
                                         read_json(artifacts / 'pcm-digests.json'))
    evidence = {key: replay[key] for key in ('hypotheses', 'local_volume', 'mouth', 'pcm')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_node40_expanded.SAVED_FILES))
    return {'run': run.name, **evidence}, {
        'fk61_node40_expanded_single_sample_and_full_utterance_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_node40_expanded_pcm_and_volume_evidence_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_node40_expanded_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_control5632(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, source, previous, early = (RUNS / study[key]['run'] for key in
                                               ('matched', 'output', 'branch_first', 'previous_focus', 'early_expansion'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    captured = source / 'artifacts'
    replay, arrays = fk61_control5632.analyze(study, captured, read_json(previous / 'summary.json'),
                                               read_json(early / 'summary.json'), saved_definition(matched, records),
                                               gain, read_json(output / 'artifacts/coefficients.json'),
                                               read_json(captured / 'pcm-digests.json'))
    with np.load(run / 'artifacts/trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_control5632.load.same_bits(stored[key], array) for key, array in arrays.items())
    evidence = {key: replay[key] for key in ('hypotheses', 'boundary_volume42', 'matching_groups')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    return {'run': run.name, **evidence}, {
        'fk61_control5632_two_node_trajectory_and_pcm_replayed': all(replay['checks'].values())
                                                               and replay == summary and arrays_match,
        'fk61_control5632_boundary_volume_and_exchange_evidence_replayed': all(
            value == scope[key] for key, value in evidence.items()),
        'fk61_control5632_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in ('summary.json', 'artifacts/trajectories.npz'))),
    }


def audit_fk61_upstream_drive(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, earlier, previous = (RUNS / study[key]['run']
                                           for key in ('matched', 'coefficients', 'branch_first', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    replay, arrays = fk61_upstream_drive.analyze(study, artifacts, earlier / 'artifacts',
                                                 read_json(previous / 'summary.json'), saved_definition(matched, records),
                                                 gain, read_json(output / 'artifacts/coefficients.json'),
                                                 read_json(artifacts / 'pcm-digests.json'))
    with np.load(artifacts / 'trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_upstream_drive.load.same_bits(stored[key], array) for key, array in arrays.items())
    evidence = {key: replay[key] for key in ('hypotheses', 'matching_groups')}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', 'artifacts/trajectories.npz',
                  *(f'artifacts/{name}' for name in fk61_upstream_drive.SAVED_FILES))
    return {'run': run.name, **evidence}, {
        'fk61_upstream_drive_six_node_trajectory_and_pcm_replayed': all(replay['checks'].values())
                                                                 and replay == summary and arrays_match,
        'fk61_upstream_drive_exchanges_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_upstream_drive_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_oral_inlet(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, previous = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    replay, arrays = fk61_oral_inlet.analyze(study, artifacts, previous / 'artifacts',
                                            read_json(previous / 'summary.json'), saved_definition(matched, records),
                                            gain, read_json(output / 'artifacts/coefficients.json'),
                                            read_json(artifacts / 'pcm-digests.json'))
    with np.load(artifacts / 'trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_oral_inlet.load.same_bits(stored[key], value) for key, value in arrays.items())
    evidence = {key: replay[key] for key in ('hypotheses', 'matching_groups', 'first_flow_at_least_1e_12')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', 'artifacts/trajectories.npz',
                  *(f'artifacts/{name}' for name in fk61_oral_inlet.SAVED_FILES))
    return {'run': run.name, **evidence}, {
        'fk61_oral_inlet_order_and_sixteen_node_trajectory_replayed': all(replay['checks'].values())
                                                                   and replay == summary and arrays_match,
        'fk61_oral_inlet_flow_and_volume_exchanges_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_oral_inlet_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_oral_geometry(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, previous = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    config = saved_definition(matched, records)
    coefficients = read_json(output / 'artifacts/coefficients.json')
    prior = read_json(previous / 'summary.json')
    replay, arrays = fk61_oral_geometry.analyze(study, artifacts, previous / 'artifacts', prior, config, gain, coefficients,
                                               read_json(artifacts / 'pcm-digests.json'))
    with np.load(artifacts / 'trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_oral_geometry.load.same_bits(stored[key], value) for key, value in arrays.items())
    filter_control = fk61_oral_geometry.filter_initial_state_control(
        study, artifacts, previous / 'artifacts', config, gain, coefficients)
    seeded = [name for name, row in filter_control.items() if row['first_difference_through_focus'] is None]
    evidence = {key: replay[key] for key in ('hypotheses', 'matching_conditions')}
    evidence['control_target_differences'] = {
        n: row['target_differences'] for n, row in replay['controls'].items()}
    evidence['pcm_restored_by_filter_control'] = seeded
    prior_restored = next(row['pcm_full_interval'] for row in prior['conditions']
                          if row['groups'] == ['upstream_boundary', 'inner_volume'])
    trial_geometry = replay['conditions']['nodes28_37:area+length:upstream']['pcm_full_interval']
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_oral_geometry.SAVED_FILES))
    return {'run': run.name, **evidence, 'filter_initial_state_control': filter_control}, {
        'fk61_oral_geometry_ramps_sources_and_pcm_replayed': all(replay['checks'].values())
                                                          and replay == summary and arrays_match,
        'fk61_oral_geometry_area_and_length_exchanges_replayed': all(value == scope[key] for key, value in evidence.items()),
        'fk61_oral_geometry_filter_state_effect_replayed': all(
            {key: row[key] for key in prior_restored} == (prior_restored if name.endswith(':upstream') else trial_geometry)
            for name, row in filter_control.items()),
        'fk61_oral_geometry_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_oral_history(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, previous = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    replay, arrays = fk61_oral_history.analyze(
        study, artifacts, previous / 'artifacts', read_json(previous / 'summary.json'),
        saved_definition(matched, records), gain, read_json(output / 'artifacts/coefficients.json'),
        read_json(artifacts / 'pcm-digests.json'))
    with np.load(artifacts / 'trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_oral_history.load.same_bits(stored[key], value) for key, value in arrays.items())
    evidence = {key: replay[key] for key in ('hypotheses', 'matches', 'cell_length_target_delta_cm',
                                             'cell_length_end_delta_cm', 'analytic_seed_residual_cm3_s')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_oral_history.SAVED_FILES))
    return {'run': run.name, **evidence, 'endpoints': replay['endpoints']}, {
        'fk61_oral_history_centerline_sources_and_pcm_replayed': all(replay['checks'].values())
                                                               and replay == summary and arrays_match,
        'fk61_oral_history_exchange_evidence_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_oral_history_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_onset_history(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, prior = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    replay, arrays = fk61_onset_history.analyze(
        study, artifacts, prior / 'artifacts', read_json(prior / 'summary.json'),
        saved_definition(matched, records), gain, read_json(output / 'artifacts/coefficients.json'),
        read_json(artifacts / 'pcm-digests.json'))
    with np.load(artifacts / 'trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_onset_history.load.same_bits(stored[key], value) for key, value in arrays.items())
    evidence = {key: replay[key] for key in ('hypotheses', 'matched', 'strongest_block', 'peak_sample',
                                             'filter_weight_peak_sample', 'analytic_residual_cm3_s')}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_onset_history.SAVED_FILES))
    return {'run': run.name, **evidence, 'contributions': replay['contributions']}, {
        'fk61_onset_history_filter_contributions_and_pcm_replayed': all(replay['checks'].values())
                                                                   and replay == summary and arrays_match,
        'fk61_onset_history_block_exchange_evidence_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_onset_history_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_area_targets(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, prior = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    artifacts = run / 'artifacts'
    replay, arrays = fk61_area_targets.analyze(
        study, artifacts, prior / 'artifacts', read_json(prior / 'summary.json'),
        saved_definition(matched, records), gain, read_json(output / 'artifacts/coefficients.json'),
        read_json(artifacts / 'pcm-digests.json'))
    with np.load(artifacts / 'trajectories.npz', allow_pickle=False) as stored:
        arrays_match = set(stored.files) == set(arrays) and all(
            fk61_area_targets.load.same_bits(stored[key], value) for key, value in arrays.items())
    evidence = {key: replay[key] for key in ('hypotheses', 'matches', 'isolated_grid_l2_cm2')}
    roundoff = fk61_area_targets.boundary_roundoff(artifacts, study['measurement'])
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_area_targets.SAVED_FILES))
    return {'run': run.name, **evidence, 'stages': replay['stages'], 'boundary_roundoff': roundoff}, {
        'fk61_area_targets_observations_stages_and_pcm_replayed': all(replay['checks'].values())
                                                               and replay == summary and arrays_match,
        'fk61_area_targets_exchange_evidence_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_area_targets_accumulated_roundoff_confirmed': all(
            row['match'] for mode in roundoff.values() for row in mode.values()),
        'fk61_area_targets_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_indexed_area(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, bernstein, output, prior = (RUNS / study[key]['run'] for key in
                                         ('matched', 'bernstein', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    archived = fk61_indexed_area.volume.pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)
    with np.load(bernstein / 'artifacts/render.npz', allow_pickle=False) as saved:
        archived['trial'] = saved['pcm']
    artifacts = run / 'artifacts'
    replay = fk61_indexed_area.analyze(
        study, artifacts, prior / 'artifacts', archived, saved_definition(matched, records),
        gain, read_json(output / 'artifacts/coefficients.json')['candidate'], read_json(artifacts / 'pcm-digests.json'))
    diagnostics = fk61_indexed_area.pcm_diagnostics(artifacts, prior / 'artifacts', archived,
                                                     study['measurement']['focus_frame'])
    evidence = {key: replay[key] for key in ('hypotheses', 'pcm', 'start_area_minus_upstream_cm2')}
    evidence['pcm_diagnostics'] = diagnostics
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_indexed_area.SAVED_FILES))
    return {'run': run.name, **evidence, 'mouth': replay['mouth'], 'local_first_difference': replay['local_first_difference']}, {
        'fk61_indexed_area_geometry_dynamics_and_full_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_indexed_area_pcm_comparison_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_indexed_area_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_paired_area(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, research, prior = (RUNS / study[key]['run'] for key in
                                        ('matched', 'coefficients', 'previous_focus', 'original_observation'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    archived = fk61_paired_area.volume.pcm.archived_pcm(matched / 'artifacts/matched-pcm.npz', uid)
    replay = fk61_paired_area.analyze(
        study, run / 'artifacts', research / 'artifacts', prior / 'artifacts', archived,
        saved_definition(matched, records), gain, read_json(output / 'artifacts/coefficients.json'))
    evidence = {'hypotheses': replay['hypotheses'], 'pcm_comparisons': {
        name: values['pcm'] for name, values in replay['comparisons'].items()}}
    earlier = RUNS / scope['first_run']['run']
    first, hashes = read_record(earlier.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_paired_area.SAVED_FILES))
    return {'run': run.name, **evidence, 'comparisons': replay['comparisons'], 'within_upstream': replay['within_upstream']}, {
        'fk61_paired_area_ramps_dynamics_and_full_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_paired_area_comparisons_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_paired_area_independent_reproduction_retained': (
            not first['errors'] and sha256(earlier / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_paired_volume(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output = (RUNS / study[key]['run'] for key in ('matched', 'coefficients'))
    baselines = {side: RUNS / study[f'indexed_{side}']['run'] / 'artifacts' for side in fk61_paired_volume.SIDES}
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    replay = fk61_paired_volume.analyze(
        study, run / 'artifacts', baselines, saved_definition(matched, records), gain,
        read_json(output / 'artifacts/coefficients.json'))
    evidence = {'hypotheses': replay['hypotheses'], 'source_error': replay['source_error'],
                'comparison_results': {
                    key: {field: row[field] for field in ('arithmetic_residual_rms_cm3_s', 'pcm')}
                    for key, row in replay['comparisons'].items()}}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{side}/{name}' for side in fk61_paired_volume.SIDES
                                    for name in fk61_paired_volume.SAVED))
    return {'run': run.name, **evidence, 'comparisons': replay['comparisons'], 'within_version': replay['within_version']}, {
        'fk61_paired_volume_dynamics_and_radiation_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_paired_volume_comparisons_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_paired_volume_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_pcm16682(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output = (RUNS / study[key]['run'] for key in ('matched', 'coefficients'))
    files = {key: [RUNS / study[key]['run'] / 'artifacts' / name for name in names]
             for key, names in fk61_pcm16682.ARCHIVED.items()}
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    replay = fk61_pcm16682.analyze(study, run / 'artifacts', fk61_pcm16682.archived_paths(files),
                                   saved_definition(matched, records), gain,
                                   read_json(output / 'artifacts/coefficients.json'))
    evidence = {key: replay[key] for key in ('hypotheses', 'rounding')}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_pcm16682.SAVED_FILES))
    return {'run': run.name, **evidence, 'stage_differences': replay['stage_differences'],
            'component_swaps': replay['component_swaps']}, {
        'fk61_pcm16682_complete_radiation_and_output_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_pcm16682_rounding_outcomes_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_pcm16682_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_fk61_full_pcm(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, observed = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'observed_prefix'))
    files = {key: [RUNS / study[key]['run'] / 'artifacts' / name for name in names]
             for key, names in fk61_pcm16682.ARCHIVED.items()}
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    replay = fk61_full_pcm.analyze(study, run / 'artifacts', fk61_pcm16682.archived_paths(files),
                                  observed / 'artifacts/prefix.npz', saved_definition(matched, records), gain,
                                  read_json(output / 'artifacts/coefficients.json'))
    frame = study['measurement']['registered_expanded_peak_frame']
    evidence = {key: replay[key] for key in ('hypotheses', 'precast_rms_ratio')} | {
        'focus': replay['comparisons']['expanded:expanded']['witnesses'][str(frame)]}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in fk61_full_pcm.SAVED_FILES))
    return {'run': run.name, **evidence, 'comparisons': replay['comparisons']}, {
        'fk61_full_pcm_all_frames_and_rounding_replayed': all(replay['checks'].values()) and replay == summary,
        'fk61_full_pcm_late_witness_and_statistics_registered': all(value == scope[key] for key, value in evidence.items()),
        'fk61_full_pcm_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


MATCHED_PCM_ROUNDING = (
    ('fk61_02_full_pcm', fk61_02_full_pcm, ()),
    ('mk61_02_full_pcm', mk61_02_full_pcm, ('male_over_female',)),
)


def audit_matched_pcm_rounding(scope, records, summary, label, measurement, extra_fields):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output, previous = (RUNS / study[key]['run'] for key in ('matched', 'coefficients', 'comparison'))
    uid = study['measurement']['recording_id']
    gain = read_json(matched / 'artifacts' / uid / 'matched-case.json')['speech_voice']['voice']['output_gain']
    replay = measurement.analyze(
        study, run / 'artifacts', matched / 'artifacts/matched-pcm.npz', read_json(matched / 'summary.json'),
        read_json(previous / 'summary.json'), saved_definition(matched, records), gain,
        read_json(output / 'artifacts/coefficients.json'))
    evidence = {key: replay[key] for key in ('hypotheses', 'matched_pcm', 'amplitude_by_ulp', *extra_fields)}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    comparable = ('summary.json', *(f'artifacts/{name}' for name in measurement.SAVED_FILES))
    return {'run': run.name, **evidence, 'comparison': replay['comparison'],
            'radiation_and_source_differences': replay['radiation_and_source_differences']}, {
        f'{label}_radiation_through_rounding_replayed': all(replay['checks'].values()) and replay == summary,
        f'{label}_held_out_outcomes_registered': all(value == scope[key] for key, value in evidence.items()),
        f'{label}_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
    }


def audit_held_out_pcm_rounding(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    matched, output = (RUNS / study[key]['run'] for key in ('matched', 'coefficients'))
    specs = {row['recording_id']: matched / 'artifacts' / row['recording_id'] / 'matched-case.json'
             for row in study['measurement']['cases']}
    references = {uid: read_json(RUNS / reference['run'] / 'summary.json')
                  for uid, reference in study['reproductions'].items()}
    replay = held_out_pcm_rounding.analyze(
        study, run / 'artifacts', matched / 'artifacts/matched-pcm.npz', read_json(matched / 'summary.json'),
        specs, references, saved_definition(matched, records), read_json(output / 'artifacts/coefficients.json'))
    evidence = {name: replay[name] for name in ('hypotheses', 'ranking', 'separate_peak_frames', 'multiple_ulp_quiet_share')}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    captures = tuple(f'artifacts/{name}' for name in held_out_pcm_rounding.retained_files(study))
    comparable = ('summary.json', *captures)
    initial_run = RUNS / scope['initial_run']['run']
    initial, initial_hashes = read_record(initial_run.name, study['upstream_revision'], expected_failure=True,
                                         expected_failed_checks=('both_independent_utterance_runs_reproduced',))
    before = read_json(initial_run / 'summary.json')
    return {'run': run.name, **evidence, 'same_text_rms_ratios': replay['same_text_rms_ratios'],
            'groups_by_pcm_amplitude': replay['groups_by_pcm_amplitude']}, {
        'held_out_pcm_all_utterances_replayed': all(replay['checks'].values()) and replay == summary,
        'held_out_pcm_ranking_and_amplitude_outcomes_registered': all(value == scope[key] for key, value in evidence.items()),
        'held_out_pcm_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in comparable)),
        'held_out_pcm_initial_failed_comparison_retained': (
            not initial['errors'] and sha256(initial_run / 'manifest.json') == scope['initial_run']['manifest_sha256']
            and before['utterances'] == replay['utterances'] and before['ranking'] == replay['ranking']
            and all(initial_hashes[name] == hashes[name] for name in captures)),
    }


def audit_csd_two_phrase_rounding(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    revision = study['upstream_revision']
    tsp = csd_two_phrase_rounding.tsp
    reference, stage, coeff = (tsp.open_run(study[key], revision) for key in ('reference', 'config', 'coefficients'))
    files = {name: tsp.verified_path(reference, f'artifacts/{name}') for name in csd_two_phrase_rounding.REFERENCE_FILES}
    config, _ = csd_two_phrase_rounding.radiation.saved_case(stage, csd_two_phrase_rounding.lip.CONFIG)
    coefficients = read_json(tsp.verified_path(coeff, 'artifacts/coefficients.json'))
    replay = csd_two_phrase_rounding.analyze(study, run / 'artifacts', files, config, coefficients)
    evidence = {'hypotheses': replay['hypotheses'], 'archive': replay['archive'], 'full': replay['comparison']['full'],
                'between_phrases': replay['comparison']['segments']['between_phrases']}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, revision, expected_failure=False)
    initial_run = RUNS / scope['initial_run']['run']
    initial, initial_hashes = read_record(initial_run.name, revision, expected_failure=True,
        expected_failed_checks=('internal_radiation_and_output_stages_replay',))
    before = read_json(initial_run / 'summary.json')
    captures = tuple(f'artifacts/{name}' for name in csd_two_phrase_rounding.SAVED_FILES)
    return {'run': run.name, **evidence, 'internal_differences': replay['internal_differences'],
            'amplitude_by_ulp': replay['amplitude_by_ulp']}, {
        'csd_two_phrase_full_output_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_two_phrase_matched_and_gap_outcomes_registered': all(value == scope[key] for key, value in evidence.items()),
        'csd_two_phrase_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in ('summary.json', *captures))),
        'csd_two_phrase_initial_missing_state_trim_retained': (
            not initial['errors'] and sha256(initial_run / 'manifest.json') == scope['initial_run']['manifest_sha256']
            and before['output_replay'] == {'upstream_normal': False, 'research_normal': True}
            and all(before[key] == replay[key] for key in ('comparison', 'internal_differences', 'hypotheses'))
            and all(initial_hashes[name] == hashes[name] for name in captures)),
    }


def csd_held_out_output_effect(summary):
    return {key: summary[key] for key in ('plan', 'hypotheses', 'archive', 'peaks', 'amplitude_by_ulp',
                                          'internal_differences', 'limiter')} | {
        'whole_song': summary['comparison']['full'],
        'output_intervals': summary['comparison']['segments'],
        'pcm_unequal_values': summary['comparison']['pcm_unequal_values'],
        'pcm_one_ulp': summary['comparison']['pcm_one_ulp'],
        'pcm_more_than_one_ulp': summary['comparison']['pcm_more_than_one_ulp'],
    }


def audit_csd_held_out_output_rounding(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    config, paths = csd_held_out_rounding.study_inputs(study)
    replay = csd_held_out_rounding.analyze(study, run / 'artifacts', config, paths)
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_held_out_rounding.SAVED_FILES))
    evidence = csd_held_out_output_effect(replay)
    originals_match = True
    for analysis, acquisition in zip((first_run, run), scope['capture_runs'], strict=True):
        raw, retained = read_record(acquisition['run'], study['upstream_revision'], expected_failure=True,
                                    expected_error=csd_held_out_rounding.ORIGINAL_ERROR)
        manifest = read_json(analysis / 'manifest.json')
        originals_match &= (
            not raw['errors'] and manifest['capture_run'] == acquisition['run']
            and manifest['capture_manifest_sha256'] == acquisition['manifest_sha256']
            and sha256(RUNS / acquisition['run'] / 'manifest.json') == acquisition['manifest_sha256']
            and all(retained[name] == sha256(analysis / name) for name in captures[1:]))
    return {'run': run.name, **evidence}, {
        'csd_held_out_entire_song_output_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_held_out_rounding_and_score_outcomes_registered': evidence == scope['observed'],
        'csd_held_out_rounding_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
        'csd_held_out_limiter_stops_and_raw_captures_retained': originals_match,
    }


def csd_interval_output_effect(summary):
    return {key: summary[key] for key in ('plan', 'hypotheses', 'archive', 'peaks', 'amplitude_by_ulp',
                                           'intervals', 'reference_prefix', 'limiter', 'internal_differences',
                                           'song_comparisons', 'short_extension') if key in summary} | {
        'whole_song': summary['comparison']['full'],
        'output_intervals': summary['comparison']['segments'],
    }


def audit_csd_interval_output_rounding(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    config, paths = csd_en035a_rounding.study_inputs(study)
    replay = csd_en035a_rounding.analyze(study, run / 'artifacts', config, paths)
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_en035a_rounding.SAVED_FILES))
    evidence = csd_interval_output_effect(replay)
    label = f'csd_{study["measurement"]["song"]}'
    return {'run': run.name, **evidence}, {
        f'{label}_full_output_and_archives_replayed': all(replay['checks'].values()) and replay == summary,
        f'{label}_intervals_limiter_and_rounding_registered': evidence == scope['observed'],
        f'{label}_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
    }


def audit_csd_first_lip_load(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    revision = study['upstream_revision']
    reference = csd_first_lip_load.tsp.open_run(study['reference'], revision)
    replay = csd_first_lip_load.analyze(study, run / 'artifacts', reference)
    evidence = {key: replay[key] for key in ('hypotheses', 'first_differences', 'first_volume_rounding',
                                            'focus_lip_flow_cm3_s', 'load_exchanges_at_focus')}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, revision, expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_first_lip_load.SAVED_FILES))
    return {'run': run.name, **evidence}, {
        'csd_first_lip_geometry_and_load_replayed': all(replay['checks'].values())
            and json.dumps(replay, sort_keys=True) == json.dumps(summary, sort_keys=True),
        'csd_first_lip_outcomes_registered': all(
            json.dumps(value, sort_keys=True) == json.dumps(scope[key], sort_keys=True) for key, value in evidence.items()),
        'csd_first_lip_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
    }


def audit_csd_initial_oral_geometry(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    revision = study['upstream_revision']
    reference = csd_initial_oral.tsp.open_run(study['lip_load'], revision)
    replay = csd_initial_oral.analyze(study, run / 'artifacts', reference)
    evidence = {'hypotheses': replay['hypotheses'], 'first_volume_exchanges': replay['first_volume_exchanges'],
                'frames': [{key: row[key] for key in ('first_differences', 'geometry', 'input_exchanges')}
                           for row in replay['frames']]}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, revision, expected_failure=False)
    initial_run = RUNS / scope['initial_run']['run']
    initial_manifest = read_json(initial_run / 'manifest.json')
    initial, initial_hashes = read_record(initial_run.name, revision, expected_failure=True,
                                         expected_error=initial_manifest['error'])
    stop = initial_manifest['commands'][-1]
    cargo_log = (initial_run / 'artifacts/cargo.log').read_text()
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_initial_oral.FILES))
    return {'run': run.name, **evidence}, {
        'csd_initial_oral_geometry_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_initial_oral_counterfactuals_registered': all(value == scope[key] for key, value in evidence.items()),
        'csd_initial_oral_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
        'csd_initial_oral_initial_missing_fixtures_retained': (
            not initial['errors'] and sha256(initial_run / 'manifest.json') == scope['initial_run']['manifest_sha256']
            and stop['argv'][-4:] == ['-p', 'vocal-core', '--lib', 'resample'] and stop['exit_code'] == 101
            and all(f"cases/{path.name}`: No such file" in cargo_log for path in csd_initial_oral.CANDIDATE_TEST_CASES)
            and all(initial_hashes[name] == hashes[name]
                    for name in ('artifacts/upstream.jsonl', 'artifacts/upstream-observation.patch'))),
    }


def audit_csd_centerline_coordinate_swap(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    revision = study['upstream_revision']
    geom, lip = (csd_centerline_swap.tsp.open_run(study[key], revision) for key in ('geometry', 'lip_load'))
    replay = csd_centerline_swap.analyze(study, run / 'artifacts', geom, lip)
    evidence = {key: replay[key] for key in ('hypotheses', 'native_midpoint_at_ray6', 'paired_pcm_difference')}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, revision, expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_centerline_swap.FILES))
    changed = {}
    rows = read_json(run / 'artifacts/observations.json')
    with np.load(run / 'artifacts/pcm.npz', allow_pickle=False) as pcm:
        for name, conditions in rows.items():
            changed[name] = {
                condition: {
                    'axial_ray_indexes': {
                        frame: [i for i, (a, b) in enumerate(zip(row['grid'], conditions['native'][frame]['grid'], strict=True))
                                if a[0] != b[0]] for frame, row in snapshots.items()},
                    'pcm_frames': int(np.count_nonzero(pcm[f'{name}_{condition}'] != pcm[f'{name}_native'])),
                } for condition, snapshots in conditions.items() if condition != 'native'
            }
    return {'run': run.name, **evidence, 'trials': replay['trials'], 'observed_differences': changed}, {
        'csd_centerline_swap_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_centerline_swap_outcomes_registered': all(value == scope[key] for key, value in evidence.items()),
        'csd_centerline_swap_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
        'csd_centerline_swap_axial_and_pcm_change_counts': changed == scope['observed_differences'],
    }


def audit_csd_pharynx_cell7_source(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    revision = study['upstream_revision']
    reference = csd_pharynx_cell7.tsp.open_run(study['centerline'], revision)
    replay = csd_pharynx_cell7.analyze(study, run / 'artifacts', reference)
    evidence = {key: replay[key] for key in ('hypotheses_by_side', 'trials')}
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, revision, expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_pharynx_cell7.FILES))
    proof = read_json(run / 'artifacts/pcm-digests.json')
    separation = {name: {
        'initial_only_equals_ray5': rows['initial_only']['pcm'] == rows['ray5']['pcm'],
        'target_only_equals_native': rows['target_only']['pcm'] == rows['native']['pcm'],
        'first_two_volume_sources_match_native': all(
            [s['raw_cm3_s'] for s in trial['first_samples']] == [s['raw_cm3_s'] for s in replay['trials'][name]['native']['first_samples']]
            and [s['smoothed_cm3_s'] for s in trial['first_samples']] == [s['smoothed_cm3_s'] for s in replay['trials'][name]['native']['first_samples']]
            for trial in replay['trials'][name].values()),
    } for name, rows in proof.items()}
    return {'run': run.name, **evidence, 'observed_separation': separation}, {
        'csd_pharynx_cell7_volume_and_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_pharynx_cell7_exchange_outcomes_registered': all(value == scope[key] for key, value in evidence.items()),
        'csd_pharynx_cell7_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
        'csd_pharynx_cell7_initial_area_and_first_volume_separated': separation == scope['observed_separation'],
    }


def audit_csd_pharynx_cell7_first_block(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    revision = study['upstream_revision']
    reference = csd_pharynx_block.tsp.open_run(study['cell_source'], revision)
    replay = csd_pharynx_block.analyze(study, run / 'artifacts', reference)
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, revision, expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_pharynx_block.FILES))
    return {'run': run.name, 'sides': replay['sides']}, {
        'csd_pharynx_first_block_flow_pressure_and_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_pharynx_first_block_differences_and_exchanges_registered': replay['sides'] == scope['sides'],
        'csd_pharynx_first_block_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
    }


def csd_compliance_effect(summary):
    return {name: {
        'sample_zero': side['sample_zero'],
        'hypotheses': side['hypotheses'],
        'whole_pcm': {key: values['pcm'] for key, values in side['comparisons'].items()},
        'pulse_radiation': side['comparisons']['native_to_compliance_only']['radiation'],
        'pulse_pressure_first_by_node': side['comparisons']['native_to_compliance_only']['pressure_first_by_node'],
        'pulse_precast': side['comparisons']['native_to_compliance_only']['output']['dc_removed'],
    } for name, side in summary['sides'].items()}


def audit_csd_pharynx_cell7_compliance_pulse(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    baseline, _, _, config, paths = csd_pharynx_pulse.study_inputs(study)
    replay = csd_pharynx_pulse.analyze(study, run / 'artifacts', baseline, config, paths)
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_pharynx_pulse.FILES))
    observed = csd_compliance_effect(replay)
    return {'run': run.name, 'observed': observed}, {
        'csd_pharynx_pulse_pressure_radiation_and_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_pharynx_pulse_outcomes_registered': observed == scope['observed'],
        'csd_pharynx_pulse_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
    }


def audit_csd_pharynx_cell7_branch_history(scope, records, summary):
    run = RUNS / scope['run']
    study = saved_definition(run, records)
    _, _, paths = csd_pharynx_history.study_inputs(study)
    replay = csd_pharynx_history.analyze(study, run / 'artifacts', paths)
    first_run = RUNS / scope['first_run']['run']
    first, hashes = read_record(first_run.name, study['upstream_revision'], expected_failure=False)
    captures = ('summary.json', *(f'artifacts/{name}' for name in csd_pharynx_history.FILES))
    return {'run': run.name, 'sides': replay['sides']}, {
        'csd_pharynx_history_flows_pressure_and_pcm_replayed': all(replay['checks'].values()) and replay == summary,
        'csd_pharynx_history_pressure_and_output_registered': replay['sides'] == scope['sides'],
        'csd_pharynx_history_independent_reproduction_retained': (
            not first['errors'] and sha256(first_run / 'manifest.json') == scope['first_run']['manifest_sha256']
            and all(hashes[name] == sha256(run / name) for name in captures)),
    }


def audit_f2_candidate_report(scope, summary, cfg):
    report = read_json(RUNS / scope['diagnostic_run'] / 'artifacts/f2-candidates.json')
    rows = report['windows']
    missing = Counter()
    multiple = 0
    matches = len(rows) == scope['windows'] == summary['windows']
    for row in rows:
        poles = [[pole['frequency_hz'], pole['bandwidth_hz']] for pole in row['poles']]
        picked = formants.select(poles, cfg)
        f1, f2 = picked['f1'], picked['f2']
        reason = 'outside_wave' if row['missing_reason'] == 'outside_wave' and not poles else picked['reason']
        actual = [(p['frequency_hz'], p['f2_rank']) for p in row['poles'] if p['f2_rank'] is not None]
        eligible = [f for f, _ in poles if f1 is not None
                    and f1[0] + cfg['f2_min_gap_hz'] < f < cfg['f2_max_frequency_hz']]
        matches = (matches and actual == [(f, rank) for rank, f in enumerate(eligible, 1)]
                   and row['f2_hz'] == (f2[0] if f2 else None) and row['missing_reason'] == reason)
        if reason is not None:
            missing[reason] += 1
        multiple += len(eligible) > 1
    checks = {'f2_candidate_report_rank_and_selection': matches,
              'f2_candidate_report_counts_and_missing':
                  multiple == summary['windows_with_multiple_candidates'] == scope['multiple_candidates']
                  and dict(missing) == summary['missing_reasons'] == scope['missing_reasons']}
    return {'run': scope['diagnostic_run'], 'windows': len(rows), 'windows_with_multiple_candidates': multiple,
            'missing_reasons': dict(missing)}, checks


def audit_f2_source_comparison(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    low_min, low_max = definition['low_band_hz']
    high_min, high_max = definition['shared_high_band_hz']
    windows = summary['windows']
    raw = read_json(run / 'artifacts/upstream-envelopes.json')
    matches = len(windows) == len(raw) == scope['windows']
    observed = {}
    for row, probe in zip(windows, raw):
        pair = formants.select(probe['poles'], cfg)
        first, second = pair['f1'], pair['f2']
        low_root = any(im > 0 and low_min <= math.atan2(im, re) * rate / (2 * math.pi) <= low_max
                       for re, im in probe['roots'])
        higher = [p for p in probe['poles'] if first is not None and high_min <= p[0] <= high_max
                  and first[0] + cfg['f2_min_gap_hz'] < p[0] < cfg['f2_max_frequency_hz']]
        matches = (matches and pair == row['selected'] and low_root == bool(row['bands']['low']['raw'])
                   and higher == row['bands']['high']['eligible'] and second is not None and bool(higher))
        observed[row['source'], row['center']] = (second[0], higher[0][0], low_root)
    baselines = 0
    absent = 0
    differences_agree = True
    for row in summary['comparisons']:
        center = row['center']
        recorded, recorded_high, _ = observed['recording', center]
        synth, synth_high, has_low = observed[row['source'], center]
        delta = row['frequency_difference']
        differences_agree = (differences_agree and delta['selected_synth_minus_recording_hz'] == synth - recorded
                             and delta['high_band_synth_minus_recording_hz'] == synth_high - recorded_high
                             and delta['recording_high_minus_selected_hz'] == recorded_high - recorded
                             and delta['synth_selected_minus_high_hz'] == synth - synth_high)
        if center in cfg['reference_centers']:
            baselines += 1
            absent += not has_low
    checks = {'f2_source_comparison_public_poles_and_raw_low_band': matches,
              'f2_source_comparison_differences_and_stage_counts':
                  differences_agree and baselines == scope['reference_comparisons']
                  and absent == scope['without_synth_low_root'] == summary['reference_center_low_band_stages']['pole_estimation']}
    return {'run': run.name, 'windows': len(windows), 'reference_comparisons': baselines,
            'without_synth_low_root': absent}, checks


def audit_seems_tract_transfer(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    budget = definition['limits']
    pcm_run = RUNS / definition['source_comparison']['run']
    prior = read_json(pcm_run / 'summary.json')
    low, high = definition['transfer']['high_band_hz']
    frame = definition['observation']['completed_pcm_frames']
    observed, pcm = {}, {}
    agrees = frame == scope['frame'] == summary['completed_frames']
    for name in ('upstream', 'candidate'):
        snapshot = read_json(run / f'artifacts/{name}-linear.json')
        grid = snapshot['frequencies_hz']
        values = snapshot['magnitude']
        indices = [i for i in range(1, len(grid) - 1)
                   if low <= grid[i] <= high and values[i - 1] < values[i] >= values[i + 1]]
        index = max(indices, key=values.__getitem__)
        left, center, right = (math.log(values[i] + 1e-30) for i in (index - 1, index, index + 1))
        shift = (left - right) / (2 * (left - 2 * center + right))
        observed[name] = grid[index] + shift * (grid[index + 1] - grid[index])
        pcm[name], = (row['bands']['high']['eligible'][0][0] for row in prior['windows']
                      if row['source'] == name and row['center'] == definition['target']['center'])
        agrees = (agrees and snapshot['completed_frames'] == frame and len(snapshot['sections']) == scope['sections']
                  and abs(observed[name] - summary['linear'][name]['high_band_peak'][0]) <= budget['native_peak_difference_hz'])
    delta = observed['candidate'] - observed['upstream']
    resolved = abs(delta) > budget['minimum_linear_difference_to_resolve_sign_hz']
    checks = {'seems_tract_snapshot_and_peak': agrees and pcm == summary['pcm_poles_hz'],
              'seems_tract_peak_sign_recounted': resolved == scope['sign_resolved'] == summary['sign_resolution']['linear_sign_resolved']
              and abs(delta - summary['linear_delta_hz']) <= budget['native_peak_difference_hz']
              and pcm['candidate'] - pcm['upstream'] == summary['pcm_delta_hz']}
    return {'run': run.name, 'completed_frames': frame, 'peak_frequency_hz': observed,
            'linear_sign_resolved': resolved}, checks


def audit_seems_spectrum_stages(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    low, high = definition['spectra']['band_hz']
    stages = ('decimated', 'dc_removed', 'pcm', 'common_output_replay')
    keys = [(voice, name) for voice in ('upstream', 'candidate') for name in stages]
    probes = read_json(run / 'artifacts/upstream-envelopes.json')
    poles = {}
    for (voice, name), probe in zip(keys, probes, strict=True):
        result = formants.select(probe['poles'], cfg)
        first = result['f1']
        poles[voice, name] = next((f for f, _ in probe['poles'] if first is not None
                                   and low <= f <= high and first[0] + cfg['f2_min_gap_hz'] < f < cfg['f2_max_frequency_hz']), None)
    agrees = all(value is not None for value in poles.values())
    delta = {name: poles['candidate', name] - poles['upstream', name] for name in stages} if agrees else {}
    with np.load(run / 'artifacts/stage-spectra.npz', allow_pickle=False) as data:
        band = (data['frequency_hz'] >= low) & (data['frequency_hz'] <= high)
        powers = [data[f'{voice}_glottal_flow_cm3_s'][band] for voice in ('upstream', 'candidate')]
        base, candidate = (p / p.sum() for p in powers)
        distance = float(0.5 * np.sum(abs(base - candidate)))
    checks = {
        'seems_spectrum_glottal_distribution': abs(distance - summary['spectra']['glottal_flow_cm3_s']['total_variation_high_band'])
            <= 1e-12 and (distance >= definition['limits']['different_high_band_distribution']) == scope['glottal_difference'],
        'seems_spectrum_lpc_before_output_recounted': agrees and delta == summary['lpc_high_candidate_minus_upstream_hz']
            and (abs(delta['decimated'] - delta['pcm']) <= definition['limits']['same_lpc_shift_hz']) == scope['same_shift_before_dc']
            and abs(delta['common_output_replay'] - delta['pcm']) <= cfg['frequency_bandwidth_agreement_hz'],
    }
    return {'run': run.name, 'glottal_high_band_distance': distance, 'lpc_high_differences_hz': delta}, checks


def audit_seems_drift_only(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    reference = RUNS / definition['reference']['run']
    base = saved_definition(reference, records)
    low, high = base['spectra']['band_hz']
    limits = definition['limits']
    with np.load(run / 'artifacts/pitch-trace.npz', allow_pickle=False) as data:
        upstream, disabled = data['upstream_f0_hz'], data['drift_zero_f0_hz']
        ratio = 1200 * np.log2(upstream / disabled)
        expected = seems_drift.drift_cents(definition['source_drift'], base['internal_sample_rate_hz'], len(ratio))
        pitch_error = float(np.max(abs(ratio - expected)))
        pitch_reference_matches = np.array_equal(data['expected_cents'], expected)
        first_at_zero = upstream[0] != disabled[0] and summary['first_different_internal_sample']['f0_hz'] == 0
    with np.load(run / 'artifacts/drift-spectra.npz', allow_pickle=False) as data:
        band = (data['frequency_hz'] >= low) & (data['frequency_hz'] <= high)
        powers = {name: data[name][band] / data[name][band].sum() for name in seems_drift.CONDITIONS}
    distances = {name: float(0.5 * np.sum(abs(power - powers['candidate'])))
                 for name, power in powers.items() if name != 'candidate'}
    distribution_shift = distances['upstream'] - distances['drift_zero']
    probes = read_json(run / 'artifacts/upstream-envelopes.json')
    poles = {}
    for name, probe in zip(seems_drift.CONDITIONS, probes, strict=True):
        first = formants.select(probe['poles'], cfg)['f1']
        poles[name] = next((f for f, _ in probe['poles'] if first is not None
                            and low <= f <= high and first[0] + cfg['f2_min_gap_hz'] < f < cfg['f2_max_frequency_hz']), None)
    available = all(pole is not None for pole in poles.values())
    gaps = {name: poles['candidate'] - poles[name] for name in seems_drift.UPSTREAM_CONDITIONS} if available else {}
    reduction = abs(gaps['upstream']) - abs(gaps['drift_zero']) if gaps else None
    checks = {
        'seems_drift_f0_recounted': pitch_reference_matches and first_at_zero
            and pitch_error == summary['pitch_ratio_max_error_cents'] <= limits['pitch_ratio_agreement_cents']
            and len(ratio) == summary['pitch_ratio_internal_samples'],
        'seems_drift_glottal_change_recounted': all(
            abs(distance - summary['glottal_distance_to_candidate'][name]['total_variation_high_band']) <= 1e-12
            for name, distance in distances.items())
            and (distribution_shift > 0) == scope['moves_glottal_distribution_toward_candidate'],
        'seems_drift_lpc_change_recounted': available and gaps == summary['lpc_high_candidate_minus_upstream_hz']
            and reduction == summary['lpc_gap_reduction_hz']
            and (reduction >= limits['meaningful_lpc_convergence_hz']) == scope['pcm_pole_moves_toward_candidate'],
    }
    return {'run': run.name, 'f0_trace_samples': len(ratio), 'glottal_distance_reduction': distribution_shift,
            'lpc_gap_reduction_hz': reduction}, checks


def audit_seems_pressure_replay(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    drift_definition = saved_definition(RUNS / definition['reference']['run'], records)
    base = saved_definition(RUNS / drift_definition['reference']['run'], records)
    rate = base['internal_sample_rate_hz']
    factor = rate // base['sample_rate_hz']
    start = base['window_start_12khz'] * cfg['decimation'] * factor
    stop = start + base['window_samples_12khz'] * cfg['decimation'] * factor
    interval = slice(start, stop)
    limits = definition['limits']
    settings = definition['pressure']
    _, upper_gate = seems_pressure.gate_limits(settings)
    pair = seems_pressure.COMPARE
    with np.load(run / 'artifacts/pressure-traces.npz', allow_pickle=False) as data:
        donor = data['upstream_applied']
        applied = data['pressure_replay_applied']
        source_matches = np.array_equal(applied.view('<u8'), donor.view('<u8'))
        self_matches = all(np.array_equal(data[f'drift_zero_{key}'].view('<u8'), data[f'pressure_self_{key}'].view('<u8'))
                           for key in ('physical', 'applied', 'smoothed'))
        errors = {name: float(np.max(abs(seems_pressure.pressure_filter(settings, rate, data[f'{name}_applied'])
                                        - data[f'{name}_smoothed']))) for name in pair}
        saturated = {name: int(np.count_nonzero(data[f'{name}_smoothed'][interval] >= upper_gate)) for name in pair}
    low, high = base['spectra']['band_hz']
    with np.load(run / 'artifacts/drift-spectra.npz', allow_pickle=False) as data:
        band = (data['frequency_hz'] >= low) & (data['frequency_hz'] <= high)
        powers = [data[name][band] for name in pair]
        zero, replayed = (p / p.sum() for p in powers)
        distance = float(0.5 * np.sum(abs(zero - replayed)))
    probes = read_json(run / 'artifacts/upstream-envelopes.json')
    poles = {}
    for name, probe in zip(('upstream', *pair, 'candidate'), probes, strict=True):
        first = formants.select(probe['poles'], cfg)['f1']
        poles[name] = next((f for f, _ in probe['poles'] if first is not None and low <= f <= high
                            and first[0] + cfg['f2_min_gap_hz'] < f < cfg['f2_max_frequency_hz']), None)
    available = all(poles[name] is not None for name in pair)
    shift = poles['pressure_replay'] - poles['drift_zero'] if available else None
    small_effect = shift is not None and abs(shift) < limits['meaningful_lpc_shift_hz']
    small_effect = small_effect and distance < limits['meaningful_glottal_spectral_distance']
    checks = {
        'seems_pressure_donor_and_filter_recounted': source_matches and self_matches
            and len(applied) == summary['trace_pressure_samples']
            and max(errors.values()) <= limits['filter_absolute_dyn_cm2'],
        'seems_pressure_gate_recounted': [start, stop] == summary['internal_sample_interval']
            and all(saturated[name] == summary['window_pressure'][name]['samples_at_upper_limit'] for name in pair)
            and all(count == stop - start for count in saturated.values()) == scope['gate_saturated'],
        'seems_pressure_output_change_recounted': available and shift == summary['lpc_change_from_pressure_replay_hz']
            and abs(distance - summary['glottal_change_from_pressure_replay']['total_variation_high_band']) <= 1e-12
            and small_effect == scope['small_effect'],
    }
    return {'run': run.name, 'pressure_samples': len(applied), 'saturated_samples': saturated,
            'glottal_spectral_distance': distance, 'lpc_shift_hz': shift}, checks


def audit_seems_period_jitter(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    pressure = saved_definition(RUNS / definition['reference']['run'], records)
    drift_definition = saved_definition(RUNS / pressure['reference']['run'], records)
    base = saved_definition(RUNS / drift_definition['reference']['run'], records)
    cycle_matches, first_phases = {}, {}
    rate = base['internal_sample_rate_hz']
    tolerance = definition['limits']['cycle_absolute']
    with np.load(run / 'artifacts/cycle-traces.npz', allow_pickle=False) as data:
        for name in seems_jitter.PARTS:
            settings = definition['cycle']
            jitter, shimmer = seems_jitter.cycle_parameters(settings, name)
            phase = data[f'{name}_phase']
            estimate, scales, boundaries = seems_jitter.cycle_model(settings, rate, data[f'{name}_f0_hz'], jitter, shimmer)
            cycle_matches[name] = (
                np.array_equal(boundaries, seems_jitter.phase_wraps(phase))
                and len(boundaries) == summary['cycle_models'][name]['cycle_count']
                and np.max(abs(estimate - phase)) <= tolerance
                and np.max(abs(scales[:, 1] - data[f'{name}_amplitude'])) <= tolerance)
            if f'{name}_period' in data:
                cycle_matches[name] = cycle_matches[name] and np.max(abs(scales[:, 0] - data[f'{name}_period'])) <= tolerance
        for engine, (inactive, active) in seems_jitter.PAIRS.items():
            indices = np.flatnonzero(data[f'{active}_phase'] != data[f'{inactive}_phase'])
            first_phases[engine] = int(indices[0]) if indices.size else None
        same_matched_phase = all(np.array_equal(data[f'{upper}_{field}'], data[f'{candidate}_{field}'])
            for upper, candidate in zip(seems_jitter.PAIRS['upstream'], seems_jitter.PAIRS['candidate'], strict=True)
            for field in ('f0_hz', 'phase'))
    low, high = base['spectra']['band_hz']
    with np.load(run / 'artifacts/drift-spectra.npz', allow_pickle=False) as data:
        band = (data['frequency_hz'] >= low) & (data['frequency_hz'] <= high)
        distances = {}
        for engine, pair in seems_jitter.PAIRS.items():
            powers = [data[name][band] for name in pair]
            zero, active = (p / p.sum() for p in powers)
            distances[engine] = float(0.5 * np.sum(abs(zero - active)))
    probes = read_json(run / 'artifacts/upstream-envelopes.json')
    poles = {}
    for name, probe in zip(seems_jitter.PARTS, probes, strict=True):
        first = formants.select(probe['poles'], cfg)['f1']
        poles[name] = next((f for f, _ in probe['poles'] if first is not None and low <= f <= high
                            and first[0] + cfg['f2_min_gap_hz'] < f < cfg['f2_max_frequency_hz']), None)
    available = all(pole is not None for pole in poles.values())
    shifts = {engine: poles[active] - poles[inactive] for engine, (inactive, active) in seems_jitter.PAIRS.items()} if available else {}
    large_shift = available and abs(shifts['upstream']) >= definition['limits']['meaningful_lpc_shift_hz']
    same_direction = available and shifts['upstream'] * shifts['candidate'] > 0
    checks = {
        'seems_jitter_cycle_state_recounted': all(cycle_matches.values()) and all(
            sample == summary['within_engine'][engine]['first_different_internal_sample']['phase']
            for engine, sample in first_phases.items()),
        'seems_jitter_matched_phase_recounted': same_matched_phase == scope['same_matched_phase'],
        'seems_jitter_glottal_distance_recounted': all(
            abs(value - summary['glottal_jitter_effect'][engine]['total_variation_high_band']) <= 1e-12
            for engine, value in distances.items()),
        'seems_jitter_lpc_change_recounted': shifts == summary['lpc_shift_zero_to_active_hz']
            and large_shift == scope['upstream_moves_at_least_two_hz'] and same_direction == scope['same_direction'],
    }
    return {'run': run.name, 'first_phase_difference': first_phases, 'matched_phase_across_engines': same_matched_phase,
            'glottal_spectral_distance': distances, 'lpc_shifts_hz': shifts}, checks


def audit_seems_amplitude_shimmer(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    jitter_definition = saved_definition(RUNS / definition['reference']['run'], records)
    pressure = saved_definition(RUNS / jitter_definition['reference']['run'], records)
    drift_definition = saved_definition(RUNS / pressure['reference']['run'], records)
    base = saved_definition(RUNS / drift_definition['reference']['run'], records)
    settings = {**jitter_definition['cycle'], 'shimmer_inactive': definition['shimmer']['inactive'],
                'shimmer_active': definition['shimmer']['active']}
    rate = base['internal_sample_rate_hz']
    tolerance = jitter_definition['limits']['cycle_absolute']
    errors, first_amplitudes, matches = {}, {}, {}
    with np.load(run / 'artifacts/cycle-traces.npz', allow_pickle=False) as data:
        for name in seems_shimmer.PARTS:
            jitter, shimmer = seems_shimmer.parameters(settings, name)
            _, scales, _ = seems_jitter.cycle_model(settings, rate, data[f'{name}_f0_hz'], jitter, shimmer)
            errors[name] = float(np.max(abs(scales[:, 1] - data[f'{name}_amplitude'])))
        for engine, (left, right) in seems_shimmer.PAIRS.items():
            indices = np.flatnonzero(data[f'{left}_amplitude'] != data[f'{right}_amplitude'])
            first_amplitudes[engine] = int(indices[0]) if indices.size else None
        for tag, (left, right) in seems_shimmer.MATCHED.items():
            matches[tag] = np.array_equal(data[f'{left}_amplitude'], data[f'{right}_amplitude'])
    low, high = base['spectra']['band_hz']
    with np.load(run / 'artifacts/drift-spectra.npz', allow_pickle=False) as data:
        band = (data['frequency_hz'] >= low) & (data['frequency_hz'] <= high)
        distances = {}
        for tag, pair in seems_shimmer.MATCHED.items():
            a, b = (data[name][band] for name in pair)
            distances[tag] = float(0.5 * np.sum(abs(a / a.sum() - b / b.sum())))
    with np.load(run / 'artifacts/drift-windows.npz', allow_pickle=False) as data:
        same_lpc_inputs = all(np.array_equal(data[f'{left}_lpc_pcm'], data[f'{right}_lpc_pcm'])
                              for left, right in seems_shimmer.MATCHED.values())
    poles = {}
    for name, probe in zip(seems_shimmer.PARTS, read_json(run / 'artifacts/upstream-envelopes.json'), strict=True):
        first = formants.select(probe['poles'], cfg)['f1']
        poles[name] = next((f for f, _ in probe['poles'] if first is not None and low <= f <= high
                            and first[0] + cfg['f2_min_gap_hz'] < f < cfg['f2_max_frequency_hz']), None)
    available = all(pole is not None for pole in poles.values())
    gaps = {tag: poles[right] - poles[left] for tag, (left, right) in seems_shimmer.MATCHED.items()} if available else {}
    small_gaps = available and all(abs(gap) <= definition['limits']['matched_lpc_gap_hz'] for gap in gaps.values())
    checks = {
        'seems_shimmer_cycle_amplitude_recounted': max(errors.values()) <= tolerance and all(
            sample == summary['within_engine'][engine]['first_different_internal_sample']['cycle_amplitude']
            for engine, sample in first_amplitudes.items()),
        'seems_shimmer_matched_amplitudes_recounted': all(matches.values()) == scope['matched_amplitudes'] and all(
            matched == (summary['across_engines'][tag]['first_different_internal_sample']['cycle_amplitude'] is None)
            for tag, matched in matches.items()),
        'seems_shimmer_matched_spectra_recounted': all(
            abs(distance - summary['across_engines'][tag]['glottal_spectra']['total_variation_high_band']) <= 1e-12
            for tag, distance in distances.items()),
        'seems_shimmer_lpc_gaps_recounted': available and small_gaps == scope['matched_lpc_gaps_within_limit']
            and all(gap == summary['across_engines'][tag]['lpc_delta_hz'] for tag, gap in gaps.items())
            and same_lpc_inputs == scope['matched_lpc_inputs'],
    }
    return {'run': run.name, 'first_amplitude_difference': first_amplitudes, 'matched_amplitudes': matches,
            'matched_lpc_inputs': same_lpc_inputs, 'matched_glottal_spectral_distance': distances,
            'matched_lpc_gaps_hz': gaps}, checks


def audit_seems_initial_tip(scope, records, summary):
    run = RUNS / scope['run']
    case = saved_definition(run, records)
    limits = case['limits']
    directory = run / 'artifacts'
    snapshots = {name: read_json(directory / f'{name}-initial-geometry.json') for name in seems_tip.MODES}
    upstream = snapshots['shimmer_zero']
    original = seems_tip.section_errors(upstream, snapshots['candidate'])
    matched = seems_tip.section_errors(upstream, snapshots['candidate_rest_tip'])
    confirmed_sections = all(row['length_cm'] <= limits['geometry_cm']
                             and max(row['area_cm2'], row['minimum_cm2']) <= limits['geometry_cm2']
                             for row in matched.values())
    with np.load(directory / 'pre-roll.npz', allow_pickle=False) as data:
        control = data['shimmer_zero_pcm']
        baseline = float(np.max(abs(data['candidate_pcm'].astype(float) - control)))
        aligned = float(np.max(abs(data['candidate_rest_tip_pcm'].astype(float) - control)))
        first_changed = np.flatnonzero(data['candidate_pcm'] != control)
        lip_peak = float(np.max(abs(data['shimmer_zero_lip_cm3_s'] - data['candidate_rest_tip_lip_cm3_s'])))
    with np.load(directory / 'lpc-windows.npz', allow_pickle=False) as data:
        same_window = all(np.array_equal(data[name], data['shimmer_zero']) for name in seems_tip.MODES)
    checks = {
        'seems_tip_initial_geometry_recounted': all(row['completed_frames'] == 0 for row in snapshots.values())
            and original == summary['section_errors']['candidate'] and matched == summary['section_errors']['candidate_rest_tip']
            and confirmed_sections == scope['matched_geometry'],
        'seems_tip_pre_roll_recounted': baseline == summary['pcm']['candidate']['pre_roll_peak_absolute_difference']
            and aligned == summary['pcm']['candidate_rest_tip']['pre_roll_peak_absolute_difference']
            and (aligned <= limits['pre_roll_pcm']) == scope['matched_pre_roll']
            and (int(first_changed[0]) if first_changed.size else None) == summary['pcm']['candidate']['first_different_frame']
            and lip_peak == scope['matched_pre_roll_lip_peak_cm3_s'],
        'seems_tip_lpc_window_recounted': same_window == summary['lpc_inputs_match'] == scope['lpc_inputs_match'],
    }
    return {'run': run.name, 'pre_roll_peak_unmatched': baseline, 'pre_roll_peak_matched': aligned,
            'matched_pre_roll_lip_peak_cm3_s': lip_peak, 'matched_geometry': confirmed_sections,
            'lpc_inputs_match': same_window}, checks


def audit_matched_held_out_speech(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    directory = run / 'artifacts'
    pcm_checks, boundaries, intervals, maxima = {}, {}, {}, {}
    limit = definition['limits']['pcm_absolute']
    with np.load(directory / 'matched-pcm.npz', allow_pickle=False) as data:
        for uid in definition['recording_ids']:
            original, candidate = (data[f'{uid}_{name}'] for name in ('upstream', 'candidate'))
            raw, _ = matched_speech.pcm_report(original, candidate, definition)
            row = summary['utterances'][uid]
            maxima[uid] = raw['maximum_absolute_difference']
            pcm_checks[uid] = raw == row['matched_pcm']
            plans = {name: matched_speech.phone_intervals(
                read_json(directory / uid / filename), definition['sample_rate_hz'], upstream=name == 'upstream')
                for name, filename in (('upstream', 'upstream-plan.json'), ('candidate', 'matched-plan.json'))}
            phone_match = plans['upstream'] == plans['candidate']
            event = row['difference_events']['peak_frame']
            boundaries[uid] = {'matches': phone_match,
                               'recorded': (plans | {'match': phone_match}) == row['phones']
                               and event['frame'] == raw['peak_frame']
                               and all(event[name] == matched_speech.phone_at(probe, raw['peak_frame'])
                                       for name, probe in plans.items())}
            actual = [matched_speech.duration(wave, definition)['interval'] for wave in (original, candidate)]
            intervals[uid] = {'matches': actual[0] == actual[1],
                              'recorded': actual == [row['active_intervals'][name]['interval']
                                                     for name in ('upstream', 'candidate')]}
    worst = max(maxima, key=maxima.get)
    counts = {'utterances': len(maxima), 'phonetic_plans_match': sum(row['matches'] for row in boundaries.values()),
              'active_intervals_match': sum(row['matches'] for row in intervals.values()),
              'within_pcm_limit': sum(value <= limit for value in maxima.values())}
    checks = {
        'held_out_matched_pcm_recounted': all(pcm_checks.values()) and counts['within_pcm_limit'] == scope['within_pcm_limit']
            and counts['utterances'] == scope['utterances'] == summary['utterance_count']
            and worst == scope['largest_difference_utterance'] == summary['largest_difference_utterance'],
        'held_out_matched_phone_boundaries_recounted': all(row['recorded'] for row in boundaries.values())
            and counts['phonetic_plans_match'] == scope['phonetic_plans_match'],
        'held_out_matched_active_intervals_recounted': all(row['recorded'] for row in intervals.values())
            and counts['active_intervals_match'] == scope['active_intervals_match'],
    }
    return ({'run': run.name, **counts, 'largest_difference_utterance': worst, 'peak_pcm_difference': maxima[worst]},
            checks)


def audit_matched_speech_formants(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    directory = run / 'artifacts'
    observed = read_json(directory / 'upstream-formants.json')
    comparison = read_json(directory / 'window-comparisons.json')
    limits = cfg['frequency_bandwidth_agreement_hz']
    all_pairs = {route: [] for route in ('same_window', 'window_only')}
    def f2(pair):
        return pair['f1_f2_hz'][1] if pair['f1_f2_hz'] is not None else None

    for uid in summary['pcm']:
        row = observed[uid]
        for entries in zip(*(row['sources'][name] for name in ('upstream', 'candidate_common', 'candidate')), strict=True):
            for reference, shared, individual in zip(*(entry['windows'] for entry in entries), strict=True):
                for name, (a, b) in (('same_window', (reference, shared)), ('window_only', (shared, individual))):
                    all_pairs[name].append((b['start_sample'] - a['start_sample'], f2(a), f2(b)))
    identical = all(delta == 0 and ((left is None and right is None) or
                    (left is not None and right is not None and abs(left - right) <= limits))
                    for delta, left, right in all_pairs['same_window'])
    windows_changed = sum(delta != 0 for delta, _, _ in all_pairs['window_only'])
    f2_changed = sum((left is None) != (right is None) or
                     (left is not None and right is not None and abs(left - right) > limits)
                     for _, left, right in all_pairs['window_only'])
    same_rows = all([(row['start_delta_samples'], *row['f2_hz']) for row in comparison['windows'][name]] == pairs
                    for name, pairs in all_pairs.items())
    common = summary['route_summary']['same_window']
    time_only = summary['route_summary']['window_only']
    gap = summary['f2_recording_comparison']
    target = definition['recording_gap']
    # 既存F2レポートの語と窓を起点に、固定Rustの公開結果を引き直す。
    label = next(row for row in read_json(directory / 'f2-candidates.json')['windows']
                 if row['source'] == 'upstream' and row['utterance'] == target['utterance']
                 and row['word'] == target['word'] and row['center'] == target['center'])
    index = next(i for i, token in enumerate(observed[target['utterance']]['sources']['upstream'])
                 if token['index'] == label['phone_index'])
    layout = sorted(cfg['boundary_centers'] + cfg['reference_centers'])
    center = layout.index(target['center'])
    f2_values = {voice: f2(entries[index]['windows'][center])
                 for voice, entries in observed[target['utterance']]['sources'].items()}
    checks = {
        'matched_f2_shared_windows_recounted': same_rows and len(all_pairs['same_window']) == scope['common_windows']
            and common['windows'] == scope['common_windows'] and identical == scope['shared_f2_agrees'],
        'matched_f2_window_only_recounted': windows_changed == time_only['different_starts'] == scope['different_starts']
            and f2_changed == time_only['different_f2_selections'] == scope['window_switch_f2_changes'],
        'matched_f2_recording_gap_recounted': f2_values == gap['f2_hz']
            and ((f2_values['upstream'] is not None and f2_values['recording'] is not None
                  and abs(f2_values['upstream'] - f2_values['recording']) >= target['minimum_f2_difference_hz'])
                 == scope['recording_gap_persists']),
    }
    return {'run': run.name, 'shared_f2_agrees': identical, 'window_switch_f2_changes': f2_changed,
            'different_starts': windows_changed, 'seems_f2_hz': f2_values}, checks


def matched_mfa_paths(definition, run):
    prior = RUNS / definition['alignment']['run'] / 'artifacts'
    current = run / 'artifacts'
    return {
        f'{uid}-{voice}': (
            *(prior / 'corpus/synth' / f'{uid}-{voice}' / f'{uid}-{voice}.{ext}' for ext in ('wav', 'lab')),
            prior / 'aligned-1-synth' / f'{uid}-{voice}' / f'{uid}-{voice}.json',
            *(current / 'corpus' / f'{uid}-{voice}' / f'{uid}-{voice}.{ext}' for ext in ('wav', 'lab')),
            current / 'aligned' / f'{uid}-{voice}' / f'{uid}-{voice}.json',
        )
        for uid in definition['utterances'] for voice in matched_mfa.VOICES
    }


def audit_matched_speech_mfa(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    prior = RUNS / definition['alignment']['run'] / 'artifacts'
    current = run / 'artifacts'
    rate = definition['measurement']['sample_rate_hz']
    paths = matched_mfa_paths(definition, run)
    reports = RUNS / definition['formants']['run'] / 'artifacts/f2-candidates.json'
    previous, observed, measured_pcm = {}, {}, {}
    same_labs = True
    same_upstream = True
    for tag, (old_wav, old_lab, old_json, wav, lab, alignment) in paths.items():
        same_labs = same_labs and old_lab.read_bytes() == lab.read_bytes()
        previous[tag], observed[tag] = (matched_mfa.mfa.tiers(path) for path in (old_json, alignment))
        measured_pcm[tag] = matched_mfa.wave_samples(wav, rate, np.int16)
        if tag.endswith('-upstream'):
            same_upstream = (same_upstream and old_wav.read_bytes() == wav.read_bytes()
                             and previous[tag] == observed[tag])
    equal_pcm, equal_boundaries = 0, 0
    for uid in definition['utterances']:
        left, right = (f'{uid}-{voice}' for voice in matched_mfa.VOICES)
        equal_pcm += np.array_equal(measured_pcm[left], measured_pcm[right])
        equal_boundaries += observed[left] == observed[right]
    rows = matched_mfa.compare_windows(definition, previous, observed, read_json(reports))
    stats = matched_mfa.window_summary(rows)
    checks = {
        'matched_mfa_upstream_input_reproduced': (same_labs and same_upstream
            and (current / 'synth.dict').read_bytes() == (prior / 'synth.dict').read_bytes()),
        'matched_mfa_pairs_recounted': (equal_pcm == scope['same_pcm16_pairs'] == summary['same_pcm16_pairs']
            and equal_boundaries == scope['same_boundary_pairs']),
        'matched_mfa_window_offsets_recounted': (stats == summary['windows']
            and rows == read_json(current / 'window-comparisons.json')
            and stats is not None and stats['windows'] == scope['windows']
            and stats['prior']['different_starts'] == scope['different_prior_starts']
            and stats['realigned']['different_starts'] == scope['different_realigned_starts']),
    }
    return {'run': run.name, 'same_pcm16_pairs': equal_pcm, 'same_boundary_pairs': equal_boundaries,
            'windows': stats}, checks


def again_mfa_windows(definition, root, variant):
    cfg = definition['measurement']
    uid = definition['utterance']
    prior_align = RUNS / definition['previous_alignment']['run'] / 'artifacts/aligned-1-synth'
    tags = {'matched': f'{uid}-candidate', variant: f'{uid}-{variant}', 'prior': f'{uid}-candidate'}
    tiers = {mode: matched_mfa.mfa.tiers((prior_align if mode == 'prior' else root / 'aligned') / tag / f'{tag}.json')
             for mode, tag in tags.items()}
    intervals = {mode: tier['phones'][again_tip.phone_at_word(tier, cfg)] for mode, tier in tiers.items()}
    boundaries = {mode: row[1] for mode, row in intervals.items()}
    recorded = read_json(root / 'window-comparisons.json')
    native = read_json(root / 'upstream-formants.json')[uid]['sources']
    routes = {'upstream': 'matched', 'matched': 'matched', 'matched_prior_window': 'prior',
              f'{variant}_fixed_window': 'matched', f'{variant}_realigned': variant}
    values, verified_windows = {}, True
    for name, mode in routes.items():
        start, end, _ = intervals[mode]
        fixed = native[name][0]['windows']
        expected = [int((start + q * (end - start)) * cfg['analysis_rate_hz']) - cfg['frame_samples'] // 2
                    for q in cfg['analysis_centers']]
        verified_windows &= expected == [row['start_sample'] for row in fixed]
        verified_windows &= [(row['start_sample'], row['f1_f2_hz']) for row in fixed] == [
            (row['start_sample'], row['f1_f2_hz']) for row in recorded[name]]
        values[name] = fixed[-1]['start_sample']
    return boundaries, values, verified_windows, native


def audit_again_tip_mfa(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    cfg = definition['measurement']
    root = run / 'artifacts'
    baseline = read_json(root / 'matched-case.json')
    changed = read_json(root / 'old_tip-case.json')
    changed_tip = changed['speech_voice']['posture']['tongue_tip_cm']
    changed['speech_voice']['posture']['tongue_tip_cm'] = baseline['speech_voice']['posture']['tongue_tip_cm']
    audio = [matched_mfa.wave_samples(root / f'{mode}-clean.wav', cfg['sample_rate_hz'], np.float32)
             for mode in again_tip.MODES]
    preroll = matched_mfa.describe_delta(*(wave[:cfg['initial_frames']] for wave in audio))
    boundaries, values, verified_windows, _ = again_mfa_windows(definition, root, 'old_tip')
    prior_offset = values['matched_prior_window'] - values['matched']
    tip_offset = values['old_tip_realigned'] - values['matched']
    checks = {
        'again_single_initial_tip_change_and_preroll': (changed == baseline and changed_tip !=
            baseline['speech_voice']['posture']['tongue_tip_cm'] and preroll == summary['pcm']['preroll']
            and (preroll['max_absolute_delta'] > cfg['early_pcm_difference_minimum']) == scope['preroll_differs']),
        'again_initial_tip_boundaries_from_mfa': boundaries == summary['eh1_end_seconds']
            and boundaries['old_tip'] == scope['old_tip_eh1_end_seconds'],
        'again_initial_tip_windows_from_mfa': (verified_windows and values == summary['last_window_start_12khz']
            and prior_offset == cfg['expected_previous_90_percent_offset_samples']
            and tip_offset == scope['old_tip_window_offset_samples']),
    }
    return {'run': run.name, 'eh1_end_seconds': boundaries, 'preroll_pcm': preroll,
            'prior_window_offset_samples': prior_offset, 'old_tip_window_offset_samples': tip_offset}, checks


def audit_again_jitter_mfa(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    cycle = definition['cycle']
    root = run / 'artifacts'
    baseline = read_json(root / 'matched-case.json')
    changed = read_json(root / 'jitter_zero-case.json')
    source = changed['speech_voice']['source_variation']
    coefficient = source['period_jitter']
    source['period_jitter'] = cycle['jitter_active']
    with np.load(root / 'cycle-traces.npz', allow_pickle=False) as trace:
        modes = again_tip.JITTER_MODES
        left, right = (trace[f'{mode}_phase'] for mode in modes)
        indices = np.flatnonzero(left != right)
        first = int(indices[0]) if len(indices) else None
        wraps = [np.flatnonzero(np.diff(phase) < 0) + 1 for phase in (left, right)]
        count = min(map(len, wraps))
        left_amp, right_amp = (trace[f'{mode}_amplitude'][rows[:count]] for mode, rows in zip(modes, wraps))
        aligned_amplitude = count > 0 and np.array_equal(left_amp, right_amp)
        same_pitch = np.array_equal(*(trace[f'{mode}_f0_hz'] for mode in modes))
    boundaries, values, verified, native = again_mfa_windows(definition, root, 'jitter_zero')
    offsets = values['jitter_zero_realigned'] - values['matched']
    differences = again_fixed_f2_differences(native, 'jitter_zero')
    prefix = 'again_male_jitter' if 'baseline_intervention' in definition else 'again_jitter'
    checks = {
        f'{prefix}_only_coefficient_and_phase': (changed == baseline and coefficient == cycle['jitter_inactive']
            and first == scope['first_phase_difference'] == summary['first_changes']['first_different_internal_sample']['phase']
            and same_pitch and aligned_amplitude and first == int(wraps[0][0]) + 1),
        f'{prefix}_alignment_recounted': (verified and boundaries == summary['eh1_end_seconds']
            and boundaries['jitter_zero'] == scope['jitter_zero_eh1_end_seconds']
            and values == summary['last_window_start_12khz'] and offsets == scope['jitter_window_offset_samples']),
        f'{prefix}_fixed_window_f2_recounted': differences == summary['fixed_window_f2_differences_hz'],
    }
    result = {'run': run.name, 'first_phase_difference': first, 'eh1_end_seconds': boundaries,
              'jitter_window_offset_samples': offsets, 'fixed_window_f2_differences_hz': differences}
    if spec := definition.get('baseline_intervention'):
        reference = RUNS / spec['run'] / 'artifacts'
        before = read_json(reference / spec['outputs']['matched_case'])
        recreated = again_old_windows_recreated(native, 'jitter_zero')
        uid = definition['utterance']
        archive = RUNS / definition['previous_alignment']['run'] / 'artifacts/aligned-1-synth'
        old = matched_mfa.mfa.tiers(archive / f'{uid}-candidate/{uid}-candidate.json')
        observed = matched_mfa.mfa.tiers(root / f'aligned/{uid}-jitter_zero/{uid}-jitter_zero.json')
        checks['again_male_jitter_recreated_old_window_starts'] = (
            before == baseline and recreated == summary['old_window_starts_recreated'] == scope['old_window_starts_recreated']
            and (old == observed) == scope['old_intervals_match'])
        result['old_window_starts_recreated'] = recreated
        result['old_intervals_match'] = old == observed
    return result, checks


def again_old_windows_recreated(native, variant):
    old = native['matched_prior_window'][0]['windows']
    new = native[f'{variant}_realigned'][0]['windows']
    return sum(a['start_sample'] == b['start_sample'] for a, b in zip(old, new, strict=True))


def again_fixed_f2_differences(native, variant):
    matched = native['matched'][0]['windows']
    compared = native[f'{variant}_fixed_window'][0]['windows']
    return [None if a['f1_f2_hz'] is None or b['f1_f2_hz'] is None else b['f1_f2_hz'][1] - a['f1_f2_hz'][1]
            for a, b in zip(matched, compared, strict=True)]


def audit_again_drift_mfa(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    root = run / 'artifacts'
    baseline = read_json(root / 'matched-case.json')
    changed = read_json(root / 'drift_zero-case.json')
    settings = definition['drift']
    source = changed['speech_voice']['source_variation']
    depth = source['pitch_drift_cents']
    source['pitch_drift_cents'] = settings['default_cents']
    with np.load(root / 'cycle-traces.npz', allow_pickle=False) as cycles:
        active, disabled = (cycles[f'{mode}_f0_hz'] for mode in again_tip.DRIFT_MODES)
        initial_phase = [cycles[f'{mode}_phase'][0] for mode in again_tip.DRIFT_MODES]
    ratio = 1200 * np.log2(active / disabled)
    expected = again_tip.drift_cents(settings, definition['cycle']['internal_sample_rate_hz'], len(ratio))
    step = settings['control_interval_samples']
    with np.load(root / 'pitch-ratio.npz', allow_pickle=False) as saved:
        ratio_reproduced = (np.array_equal(ratio[::step], saved['observed_cents'])
                            and np.array_equal(expected[::step], saved['independent_cents'])
                            and np.array_equal(np.arange(0, len(ratio), step), saved['sample']))
    error = float(np.max(abs(ratio - expected)))
    boundaries, values, verified, native = again_mfa_windows(definition, root, 'drift_zero')
    offset = values['drift_zero_realigned'] - values['matched']
    differences = again_fixed_f2_differences(native, 'drift_zero')
    uid = definition['utterance']
    prior = RUNS / definition['previous_alignment']['run'] / 'artifacts/aligned-1-synth'
    observed = matched_mfa.mfa.tiers(root / f'aligned/{uid}-drift_zero/{uid}-drift_zero.json')
    archived = matched_mfa.mfa.tiers(prior / f'{uid}-candidate/{uid}-candidate.json')
    within_prediction = (abs(boundaries['drift_zero'] - boundaries['matched'])
                         <= definition['limits']['maximum_predicted_boundary_shift_s'])
    checks = {
        'again_only_drift_depth_changes': (changed == baseline and depth == settings['disabled_cents']
                                          and bool(active[0] != disabled[0] and initial_phase[0] != initial_phase[1])),
        'again_drift_ratio_recomputed': (ratio_reproduced and error == summary['pitch_ratio']['maximum_error_cents']
                                         and error <= definition['limits']['pitch_ratio_agreement_cents']),
        'again_drift_alignment_and_fixed_f2_recounted': (verified and boundaries == summary['eh1_end_seconds']
            and boundaries['drift_zero'] == scope['drift_zero_eh1_end_seconds']
            and values == summary['last_window_start_12khz'] and offset == scope['drift_window_offset_samples']
            and differences == summary['fixed_window_f2_differences_hz'] and observed == archived
            and within_prediction == summary['predictions']['boundary_shift_at_most_one_mfa_step']),
    }
    return {'run': run.name, 'maximum_pitch_error_cents': error, 'eh1_end_seconds': boundaries,
            'drift_window_offset_samples': offset, 'fixed_window_f2_differences_hz': differences}, checks


def audit_again_shimmer_mfa(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    root = run / 'artifacts'
    active, disabled = again_tip.SHIMMER_MODES
    baseline = read_json(root / f'{active}-case.json')
    changed = read_json(root / f'{disabled}-case.json')
    variation = changed['speech_voice']['source_variation']
    depth = variation['amplitude_shimmer']
    variation['amplitude_shimmer'] = definition['cycle']['amplitude_shimmer']
    amplitudes = again_tip.shimmer_amplitudes(root)
    with np.load(root / 'cycle-traces.npz', allow_pickle=False) as cycles:
        phase = cycles[f'{active}_phase']
        wraps = np.flatnonzero(np.diff(phase) < 0) + 1
        same_phase = np.array_equal(phase, cycles[f'{disabled}_phase'])
        same_f0 = np.array_equal(*(cycles[f'{mode}_f0_hz'] for mode in again_tip.SHIMMER_MODES))
        unit_amplitude = bool(np.all(cycles[f'{disabled}_amplitude'] == 1))
    boundaries, starts, verified, native = again_mfa_windows(definition, root, disabled)
    differences = again_fixed_f2_differences(native, disabled)
    recreated = again_old_windows_recreated(native, disabled)
    checks = {
        'again_shimmer_only_amplitude_changes': (changed == baseline and depth == definition['shimmer']['disabled']
            and unit_amplitude and same_f0 and same_phase and len(wraps) > 0
            and amplitudes == summary['cycle_amplitude']
            and amplitudes['first_changed_internal_sample'] == int(wraps[0]) == scope['first_amplitude_difference']),
        'again_shimmer_alignment_recounted': (verified and boundaries == summary['eh1_end_seconds']
            and boundaries[disabled] == scope['shimmer_zero_eh1_end_seconds']
            and starts == summary['last_window_start_12khz']
            and recreated == scope['old_window_starts_recreated'] == summary['old_window_starts_recreated']),
        'again_shimmer_fixed_window_f2_recounted': differences == summary['fixed_window_f2_differences_hz'],
    }
    return {'run': run.name, 'first_amplitude_difference': amplitudes['first_changed_internal_sample'],
            'eh1_end_seconds': boundaries, 'old_window_starts_recreated': recreated,
            'fixed_window_f2_differences_hz': differences}, checks


def cohort_drift_alignment_paths(definition, root):
    archive = RUNS / definition['old_alignment']['run'] / 'artifacts/aligned-1-synth'
    variant = cohort_drift.variant_name(definition)
    return {uid: {'matched': root / f'aligned/{uid}-candidate/{uid}-candidate.json',
                  variant: root / f'aligned/{uid}-{variant}/{uid}-{variant}.json',
                  'old': archive / f'{uid}-candidate/{uid}-candidate.json'} for uid in definition['utterances']}


def drift_only_alignment_path(definition):
    tag = f"{definition['outside_window_boundary']['utterance']}-drift_zero"
    return RUNS / definition['drift_only_reference']['run'] / 'artifacts/aligned' / tag / f'{tag}.json'


def audit_cohort_drift(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    variant = cohort_drift.variant_name(definition)
    root = run / 'artifacts'
    historical = RUNS / definition['matched_alignment']['run'] / 'artifacts/window-comparisons.json'
    observed = {uid: {mode: matched_mfa.mfa.tiers(path) for mode, path in variants.items()}
                for uid, variants in cohort_drift_alignment_paths(definition, root).items()}
    rows = cohort_drift.window_starts(definition, read_json(historical), observed)
    published = read_json(root / 'window-comparisons.json')
    basic = [{key: row[key] for key in ('utterance', 'phone_index', 'word', 'ipa', 'center', 'start_samples')}
             for row in published]
    totals = cohort_drift.summarize_windows(rows, variant)
    by_uid = {uid: cohort_drift.summarize_windows([row for row in rows if row['utterance'] == uid], variant) for uid in observed}
    centers = definition['measurement']['centers']
    native = read_json(root / 'upstream-formants.json')
    index = {uid: {source: {entry['index']: entry['windows'] for entry in entries}
                   for source, entries in native[uid]['sources'].items()} for uid in observed}
    verified = True
    for row in published:
        uid, phone, center = row['utterance'], row['phone_index'], row['center']
        for source, (_, mode) in cohort_drift.comparison_routes(variant).items():
            fixed = index[uid][source][phone][centers.index(center)]
            f2 = None if fixed['f1_f2_hz'] is None else fixed['f1_f2_hz'][1]
            verified &= (fixed['start_sample'] == row['start_samples'][mode] and row['f2_hz'][source] == f2)
    case_values = []
    disabled = definition.get('variation', {'pitch_drift_cents': 0})
    for uid in observed:
        matched, zero = [read_json(root / uid / f'{mode}.json') for mode in ('matched', variant)]
        variation = zero['speech_voice']['source_variation']
        matches = all(variation[key] == value for key, value in disabled.items())
        variation.update({key: matched['speech_voice']['source_variation'][key] for key in disabled})
        case_values.append(matches and zero == matched)
    prefix = 'cohort_drift' if variant == 'drift_zero' else 'cohort_variation_zero'
    settings_check = 'cohort_drift_cases_change_only_pitch_drift' if variant == 'drift_zero' else 'cohort_variation_zero_cases'
    checks = {
        settings_check: all(case_values),
        f'{prefix}_mfa_window_reproduction': (rows == basic and by_uid == summary['windows_by_utterance']
            and totals == summary['overall'] and totals == scope['windows']),
        f'{prefix}_f2_recounted': verified,
    }
    result = {'run': run.name, 'overall': totals, 'by_utterance': by_uid}
    if 'outside_window_boundary' in definition:
        outside = cohort_drift.outside_boundary(definition, observed, drift_only_alignment_path(definition))
        full = {uid: {mode: matched_mfa.compare_intervals(tiers[mode], tiers[variant]) for mode in ('old', 'matched')}
                for uid, tiers in observed.items()}
        checks['cohort_variation_zero_full_boundaries'] = (full == summary['boundaries']
            and outside == summary['outside_window_boundary'] and outside[variant] == scope['outside_window_boundary'])
        result['outside_window_boundary'] = outside
    return result, checks


def tall_gain_alignment_paths(definition, root):
    uid = definition['utterance']
    archive = RUNS / definition['previous_alignment']['run'] / 'artifacts/aligned-1-synth'
    return {'matched': root / f'aligned/{uid}-candidate/{uid}-candidate.json',
            'old_gain': root / f'aligned/{uid}-old_gain/{uid}-old_gain.json',
            'prior': archive / f'{uid}-candidate/{uid}-candidate.json'}


def tall_gain_prior_tape(definition):
    tag = f"{definition['utterance']}-candidate"
    return RUNS / definition['previous_alignment']['run'] / 'artifacts/corpus/synth' / tag / f'{tag}.wav'


def audit_tall_output_gain(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    root = run / 'artifacts'
    cfg = definition['measurement']
    base, changed = (read_json(root / f'{mode}-case.json') for mode in tall_gain.MODES)
    settings = changed['speech_voice']['voice']
    new_gain = settings['output_gain']
    settings['output_gain'] = definition['base_gain']
    rate = definition['sample_rate_hz']
    stage = definition['stage']
    pole = math.exp(-math.tau * stage['dc_hz'] / rate)
    with np.load(root / 'decimated.npz', allow_pickle=False) as source:
        decimated = source['decimated']
    replay = {}
    for mode, gain in (('matched', definition['base_gain']), ('old_gain', new_gain)):
        dc = lfilter([1, -1], [1, -pole], decimated * gain)
        envelope, _ = envelope_response(dc, rate, stage)
        threshold, clip = stage['peak_threshold'], stage['clip_threshold']
        limited = dc * (threshold / np.maximum(envelope, threshold))
        values = np.where(abs(limited) > clip, np.sign(limited) *
                          (clip + (1 - clip) * np.tanh((abs(limited) - clip) / (1 - clip))), limited)
        wav = matched_mfa.wave_samples(root / f'{mode}-clean.wav', rate, np.float32)
        replay[mode] = (np.max(np.abs(values.astype(np.float32) - wav)) <= cfg['linear_pcm_absolute_tolerance']
                        and int(np.count_nonzero(envelope > threshold)) == summary['output_stage'][mode]['peak_limited_frames'])
    tiers = {mode: matched_mfa.mfa.tiers(path) for mode, path in tall_gain_alignment_paths(definition, root).items()}
    intervals = {mode: tier['phones'][again_tip.phone_at_word(tier, cfg)] for mode, tier in tiers.items()}
    boundaries = {mode: item[1] for mode, item in intervals.items()}
    published = read_json(root / 'window-comparisons.json')
    native = read_json(root / 'upstream-formants.json')[definition['utterance']]['sources']
    verified_windows = True
    for name, (_, bounds) in tall_gain.ROUTES.items():
        start, end, _ = intervals[bounds]
        expected = [int((start + q * (end - start)) * (rate // 4)) - 150 for q in cfg['analysis_centers']]
        fixed = native[name][0]['windows']
        verified_windows &= expected == [row['start_sample'] for row in fixed]
        verified_windows &= [(row['start_sample'], row['f1_f2_hz']) for row in fixed] == [
            (row['start_sample'], row['f1_f2_hz']) for row in published[name]]
    tag = f"{definition['utterance']}-old_gain"
    new_tape = matched_mfa.wave_samples(root / 'corpus' / tag / f'{tag}.wav', rate, np.int16)
    prior_tape = matched_mfa.wave_samples(tall_gain_prior_tape(definition), rate, np.int16)
    different = np.flatnonzero(new_tape != prior_tape)
    last = int(different[-1]) if len(different) else None
    begin, end = cfg['local_frames']
    checks = {
        'tall_gain_only_and_pcm_replay': base == changed and new_gain == definition['old_gain'] and all(replay.values()),
        'tall_gain_alignment_recounted': (boundaries == summary['tall_vowel_end_seconds']
            and boundaries['old_gain'] == scope['old_gain_tall_end_seconds']
            and matched_mfa.compare_intervals(tiers['prior'], tiers['old_gain']) == summary['alignment_vs_old']),
        'tall_gain_fixed_and_realigned_windows_recounted': verified_windows,
        'tall_gain_old_input_local_samples': (last == scope['last_difference_to_prior_pcm16']
            and len(different) == scope['differences_to_prior_pcm16']
            and np.array_equal(new_tape[begin:end], prior_tape[begin:end])),
    }
    return {'run': run.name, 'tall_vowel_end_seconds': boundaries, 'pcm_replay_agrees': all(replay.values()),
            'last_difference_to_prior_pcm16': last, 'differences_to_prior_pcm16': len(different)}, checks


def tall_tip_assets(definition, root):
    uid = definition['utterance']
    tag = f'{uid}-old_tip'
    original = f'{uid}-candidate'
    archive = RUNS / definition['previous_alignment']['run'] / 'artifacts/aligned-1-synth'
    prior = RUNS / definition['previous_render']['run'] / 'artifacts' / uid
    baseline = RUNS / definition['baseline']['run'] / 'artifacts'
    return {
        'matched_tier': root / f'aligned/{original}/{original}.json',
        'old_tip_tier': root / f'aligned/{tag}/{tag}.json',
        'prior_tier': archive / f'{original}/{original}.json',
        'old_tip_tape': root / f'corpus/{tag}/{tag}.wav',
        'prior_tape': tall_gain_prior_tape(definition),
        'old_tip_pcm': root / 'old_tip-clean.wav',
        'prior_pcm': prior / 'candidate.wav',
        'old_tip_case': root / 'old_tip-case.json',
        'matched_case': root / 'matched-case.json',
        'baseline_case': baseline / 'old_gain-case.json',
        'windows': root / 'window-comparisons.json',
        'native': root / 'upstream-formants.json',
    }


def audit_tall_initial_tip(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    files = tall_tip_assets(definition, run / 'artifacts')
    cfg = definition['measurement']
    rate = cfg['sample_rate_hz']
    intervention = definition['intervention']
    control, adjusted = (read_json(files[f'{mode}_case'])['speech_voice'] for mode in ('matched', 'old_tip'))
    expected = control | {'posture': control['posture'] | {'tongue_tip_cm': intervention['historical_tip_cm']}}
    pcm, tape = {}, {}
    for mode in ('old_tip', 'prior'):
        pcm[mode] = matched_mfa.wave_samples(files[f'{mode}_pcm'], rate, np.float32).view(np.uint32)
        tape[mode] = matched_mfa.wave_samples(files[f'{mode}_tape'], rate, np.int16)
    differences = {name: int(np.count_nonzero(values['old_tip'] != values['prior']))
                   for name, values in (('float32_pcm', pcm), ('alignment_pcm16', tape))}
    tiers = {mode: matched_mfa.mfa.tiers(files[f'{mode}_tier']) for mode in ('matched', 'old_tip', 'prior')}
    intervals = {mode: tier['phones'][again_tip.phone_at_word(tier, cfg)] for mode, tier in tiers.items()}
    boundaries = {mode: interval[1] for mode, interval in intervals.items()}
    counts = {kind: len(tiers['old_tip'][kind]) for kind in ('words', 'phones')}
    windows = read_json(files['windows'])
    native = read_json(files['native'])[definition['utterance']]['sources']
    verified_windows = True
    for name, (_, bound) in tall_tip.ROUTES.items():
        start, end, _ = intervals[bound]
        starts = [int((start + q * (end - start)) * (rate // 4)) - 150 for q in cfg['analysis_centers']]
        verified_windows &= starts == [row['start_sample'] for row in windows[name]]
        verified_windows &= [(row['start_sample'], row['f1_f2_hz']) for row in windows[name]] == [
            (row['start_sample'], row['f1_f2_hz']) for row in native[name][0]['windows']]
    checks = {
        'tall_tip_only_case_difference': (control == read_json(files['baseline_case'])['speech_voice']
            and adjusted == expected and control['posture']['tongue_tip_cm'] == intervention['control_tip_cm']
            and control['voice']['output_gain'] == intervention['old_gain']
            and control['source_variation'] == intervention['source_variation']),
        'tall_tip_historical_pcm_recounted': (differences == scope['pcm_differences']
            and pcm['old_tip'].size == tape['old_tip'].size == scope['frames']),
        'tall_tip_historical_intervals_recounted': (tiers['old_tip'] == tiers['prior'] and counts == scope['intervals']
            and boundaries == summary['tall_vowel_end_seconds']
            and boundaries['old_tip'] == scope['old_tip_tall_end_seconds']),
        'tall_tip_fixed_and_realigned_windows_recounted': verified_windows,
    }
    return {'run': run.name, 'tall_vowel_end_seconds': boundaries, 'pcm_differences': differences, 'intervals': counts}, checks


def tall_preroll_assets(definition, root):
    uid = definition['utterance']
    parent = RUNS / definition['parent']['run'] / 'artifacts'
    assets = {}
    for kind, name in (('control', 'candidate'), ('old_tip', 'old_tip')):
        tag = f'{uid}-{name}'
        assets[f'parent_{kind}_wave'] = parent / f'corpus/{tag}/{tag}.wav'
        assets[f'parent_{kind}_tier'] = parent / f'aligned/{tag}/{tag}.json'
    for name in tall_preroll.SOURCES:
        tag = f'{uid}-{name}'
        assets[f'{name}_wave'] = root / f'corpus/{tag}/{tag}.wav'
        assets[f'{name}_tier'] = root / f'aligned/{tag}/{tag}.json'
    assets['windows'] = root / 'window-comparisons.json'
    assets['native'] = root / 'upstream-formants.json'
    return assets


def audit_tall_preroll(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    files = tall_preroll_assets(definition, run / 'artifacts')
    cfg = definition['measurement']
    rate, cut = cfg['sample_rate_hz'], cfg['cut_frame']
    tapes = {name: matched_mfa.wave_samples(path, rate, np.int16) for name, path in files.items() if name.endswith('_wave')}
    verified_partition = all(
        len(tapes[f'{name}_wave']) == cfg['frames']
        and np.array_equal(tapes[f'{name}_wave'][:cut], tapes[f'parent_{first}_wave'][:cut])
        and np.array_equal(tapes[f'{name}_wave'][cut:], tapes[f'parent_{second}_wave'][cut:])
        for name, (first, second) in tall_preroll.SOURCES.items())
    different = tapes['control_wave'] != tapes['old_tip_wave']
    changes = {'preroll': int(np.count_nonzero(different[:cut])), 'remainder': int(np.count_nonzero(different[cut:]))}
    start, stop = cfg['local_frames']
    tiers = {name: matched_mfa.mfa.tiers(files[f'{name}_tier']) for name in tall_preroll.SOURCES}
    intervals = {name: tier['phones'][again_tip.phone_at_word(tier, cfg)] for name, tier in tiers.items()}
    ends = {name: interval[1] for name, interval in intervals.items()}
    equal_old_tiers = [name for name in tall_preroll.SOURCES if tiers[name] == tiers['old_tip']]
    windows = read_json(files['windows'])
    native = read_json(files['native'])[definition['utterance']]['sources']
    verified_windows = True
    for name, (begin, end, _) in intervals.items():
        starts = [int((begin + q * (end - begin)) * (rate // 4)) - 150 for q in cfg['analysis_centers']]
        verified_windows &= starts == [row['start_sample'] for row in windows[name]]
        verified_windows &= [(row['start_sample'], row['f1_f2_hz']) for row in windows[name]] == [
            (row['start_sample'], row['f1_f2_hz']) for row in native[name][0]['windows']]
    checks = {
        'tall_preroll_pcm16_halves_recounted': (verified_partition and changes == summary['pcm16_differences_by_region']
            and changes == scope['pcm16_differences_by_region'] and not different[start:stop].any()),
        'tall_preroll_full_tiers_recounted': (
            all(tiers[mode] == matched_mfa.mfa.tiers(files[f'parent_{mode}_tier']) for mode in ('control', 'old_tip'))
            and equal_old_tiers == scope['same_tiers_as_old_tip']
            and intervals == summary['tall_vowel_intervals'] and ends == scope['tall_vowel_end_seconds']),
        'tall_preroll_prediction_recounted': summary['predictions'] == {
            'preroll_only_recovers_old_boundary': ends['old_preroll'] == ends['old_tip'],
            'remainder_only_keeps_control_boundary': ends['old_remainder'] == ends['control']},
        'tall_preroll_formant_windows_recounted': verified_windows,
    }
    return {'run': run.name, 'same_tiers_as_old_tip': equal_old_tiers, 'tall_vowel_end_seconds': ends,
            'pcm16_differences_by_region': changes}, checks


def tall_cmvn_assets(definition, root):
    uid = definition['utterance']
    parent = RUNS / definition['parent']['run'] / 'artifacts'
    waves, tiers = {}, {}
    for mode in definition['measurement']['conditions']:
        tag = f'{uid}-{mode}'
        waves[mode] = root / f'corpus/{tag}/{tag}.wav'
        tiers[mode] = root / f'aligned/{tag}/{tag}.json'
    originals = {}
    for mode in ('control', 'old_preroll'):
        tag = f'{uid}-{mode}'
        originals[mode] = parent / f'aligned/{tag}/{tag}.json'
    return waves, tiers, originals


def audit_tall_cmvn(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    root = run / 'artifacts'
    cfg = definition['measurement']
    wave_paths, tier_paths, originals = tall_cmvn_assets(definition, root)
    tiers = {mode: matched_mfa.mfa.tiers(path) for mode, path in tier_paths.items()}
    intervals = {mode: tier['phones'][again_tip.phone_at_word(tier, cfg)] for mode, tier in tiers.items()}
    ends = {mode: row[1] for mode, row in intervals.items()}
    matrices = tall_cmvn.read_features(root / 'features.npz', cfg)
    checks = {}
    checks['tall_cmvn_only_statistics_source_exchanged'] = all(
        sha256(wave_paths[mode]) == sha256(wave_paths[source['audio']])
        and all(np.array_equal(matrices[f'{mode}_{stage}'], matrices[f"{source['audio']}_{stage}"])
                for stage in ('uncompressed', 'input'))
        and np.array_equal(matrices[f'{mode}_used_stats'], matrices[f"{source['statistics']}_own_stats"])
        for mode, source in cfg['conditions'].items())
    sums_match = True
    normalized_match = True
    for mode in cfg['conditions']:
        data = matrices[f'{mode}_input']
        stored = matrices[f'{mode}_own_stats']
        used = matrices[f'{mode}_used_stats']
        sums_match &= (stored[0, -1] == len(data) and stored[1, -1] == 0
            and np.max(np.abs(stored[0, :-1] - data.sum(axis=0, dtype=np.float64))) <= cfg['statistics_absolute_tolerance']
            and np.max(np.abs(stored[1, :-1] - (data * data).sum(axis=0, dtype=np.float64))) <= cfg['statistics_absolute_tolerance'])
        expected = data.astype(float) - used[0, :-1] / used[0, -1]
        normalized_match &= np.max(np.abs(expected - matrices[f'{mode}_normalized'])) <= cfg['normalized_absolute_tolerance']
    checks['tall_cmvn_independent_accumulation_and_normalization'] = bool(sums_match and normalized_match)
    first, stop = cfg['local_feature_frames']
    local = {}
    frame_counts = {}
    for name, (left, right) in tall_cmvn.PAIRS.items():
        differences = {stage: matrices[f'{left}_{stage}'].astype(float) - matrices[f'{right}_{stage}']
                       for stage in tall_cmvn.STAGES}
        local[name] = {stage: float(np.max(np.abs(value[first:stop]))) for stage, value in differences.items()}
        frame_counts[name] = {stage: int(np.count_nonzero(np.any(value, axis=1))) for stage, value in differences.items()}
    checks['tall_cmvn_feature_stages_recounted'] = (frame_counts['own_stats'] == scope['own_stats_changed_frames']
        and all(value == summary['feature_differences'][name][stage]['local_maximum']
                and frame_counts[name][stage] == summary['feature_differences'][name][stage]['changed_frames']
                for name, rows in local.items() for stage, value in rows.items()))
    expected = {
        'uncompressed_mfccs_equal_near_tall': local['own_stats']['uncompressed'] == 0,
        'shared_statistics_reduce_local_difference': local['both_control_stats']['normalized'] < local['own_stats']['normalized'],
        'control_statistics_restore_control_boundary': ends['preroll_control_stats'] == ends['control'],
        'preroll_statistics_move_control_boundary': ends['control_preroll_stats'] == ends['old_preroll'],
    }
    checks['tall_cmvn_full_tiers_and_prediction_recounted'] = (
        ends == scope['tall_vowel_end_seconds'] and intervals == summary['tall_vowel_intervals']
        and expected == summary['predictions']
        and all(tiers[mode] == matched_mfa.mfa.tiers(path) for mode, path in originals.items())
        and all(tiers[mode] == tiers['old_preroll'] for mode in scope['same_tiers_as_preroll']))
    failed = scope['initial_failure']
    before = RUNS / failed['run']
    original, files = read_record(before.name, definition['upstream_revision'], expected_failure=True,
                                  expected_failed_checks=('independent_cmvn_statistics',))
    before_summary = read_json(before / 'summary.json')
    before_manifest = read_json(before / 'manifest.json')
    before_case = read_json(before / before_manifest['source_snapshot'] / records[run.name]['case_definition'])
    method = before_case | {'revision': definition['revision'],
                            'measurement': before_case['measurement'] | {'statistics_square_dtype': 'float32'}}
    checks['tall_cmvn_first_precision_failure_retained'] = (not original['errors']
        and sha256(before / 'manifest.json') == failed['manifest_sha256'] and before_case['revision'] == 1
        and definition['revision'] == 2 and definition == method
        and files['artifacts/features.npz'] == sha256(root / 'features.npz')
        and before_summary['predictions'] == expected and before_summary['tall_vowel_intervals'] == intervals)
    return {'run': run.name, 'initial_failure': before.name, 'tall_vowel_end_seconds': ends,
            'local_feature_differences': local, 'own_stats_changed_frames': frame_counts['own_stats']}, checks


def tall_mfcc_assets(root, definition, parent_case, *, parent_storage=None):
    parent = RUNS / definition['parent']['run'] / 'artifacts'
    if parent_storage is not None:
        parent = parent / parent_storage
    saved = {mode: parent / f'aligned/{parent_case["utterance"]}-{mode}/{parent_case["utterance"]}-{mode}.json'
             for mode in parent_case['measurement']['conditions']}
    archives = {}
    for storage in definition['archive_tokens']:
        target = root / storage
        archives[storage] = {
            'features': target / 'features.npz',
            'formats': target / 'archive-formats.json',
            **{mode: target / 'aligned' / path.parent.name / path.name for mode, path in saved.items()},
        }
    return archives, saved


def audit_tall_mfcc_input(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    parent = RUNS / definition['parent']['run']
    parent_case = saved_definition(parent, records)
    cfg = parent_case['measurement']
    sources, saved_tiers = tall_mfcc_assets(run / 'artifacts', definition, parent_case)
    parent_features = tall_cmvn.read_features(parent / 'artifacts/features.npz', cfg)
    arrays = {storage: tall_cmvn.read_features(files['features'], cfg) for storage, files in sources.items()}
    tiers = {storage: {mode: matched_mfa.mfa.tiers(files[mode]) for mode in cfg['conditions']}
             for storage, files in sources.items()}
    boundaries = {storage: {mode: tier['phones'][again_tip.phone_at_word(tier, cfg)][1] for mode, tier in group.items()}
                  for storage, group in tiers.items()}
    forms = {storage: read_json(paths['formats']) for storage, paths in sources.items()}
    columns = ('input', 'normalized', 'final')
    first, last = cfg['local_feature_frames']
    counts, local_max = {}, {}
    published_differences_match = True
    for name, features in arrays.items():
        delta = {stage: features[f'control_{stage}'].astype(float) - features[f'preroll_control_stats_{stage}']
                 for stage in columns}
        counts[name] = {stage: int(np.count_nonzero(np.any(value != 0, axis=1))) for stage, value in delta.items()}
        local_max[name] = {stage: float(np.max(np.abs(value[first:last]))) for stage, value in delta.items()}
        expected = summary['observations'][name]['feature_differences']['both_control_stats']
        published_differences_match &= all(counts[name][stage] == expected[stage]['changed_frames']
                                           and local_max[name][stage] == expected[stage]['local_maximum']
                                           for stage in columns)
    checks = {
        'tall_mfcc_standard_reproduces_saved_features_and_tiers': (
            all(np.array_equal(value, parent_features[key]) for key, value in arrays['compressed'].items())
            and tiers['compressed'] == {mode: matched_mfa.mfa.tiers(path) for mode, path in saved_tiers.items()}),
        'tall_mfcc_ark_types_and_float32_values_recounted': (
            all(report == dict.fromkeys(cfg['conditions'], definition['archive_tokens'][name])
                for name, report in forms.items())
            and all(np.array_equal(arrays['float32'][f'{mode}_input'], parent_features[f'{mode}_uncompressed'])
                    for mode in cfg['conditions'])),
        'tall_mfcc_shared_stats_stages_recounted': (
            counts == scope['shared_stats_changed_frames'] and published_differences_match),
        'tall_mfcc_tiers_and_control_shift_recounted': (
            boundaries == scope['tall_vowel_end_seconds']
            and all(tier == tiers['compressed']['old_preroll'] for tier in tiers['float32'].values())
            and all(seconds == summary['observations'][name]['tall_vowel_intervals'][mode][1]
                    for name, group in boundaries.items() for mode, seconds in group.items())),
    }
    return {'run': run.name, 'shared_stats_changed_frames': counts, 'shared_stats_local_maxima': local_max,
            'tall_vowel_end_seconds': boundaries}, checks


def audit_tall_mfcc_final(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    parent = RUNS / definition['parent']['run']
    parent_case = saved_definition(parent, records)
    cmvn_case = saved_definition(RUNS / parent_case['parent']['run'], records)
    cfg = cmvn_case['measurement']
    base, lossless = tall_mfcc_final.BASELINE, tall_mfcc_final.LOSSLESS
    sources, saved_tiers = tall_mfcc_assets(run / 'artifacts', definition, cmvn_case, parent_storage=base)
    archived = tall_cmvn.read_features(parent / 'artifacts' / base / 'features.npz', cfg)
    arrays = {storage: tall_cmvn.read_features(files['features'], cfg) for storage, files in sources.items()}
    tiers = {storage: {mode: matched_mfa.mfa.tiers(files[mode]) for mode in cfg['conditions']}
             for storage, files in sources.items()}
    boundaries = {storage: {mode: tier['phones'][again_tip.phone_at_word(tier, cfg)][1] for mode, tier in group.items()}
                  for storage, group in tiers.items()}
    modes = cfg['conditions']
    before, after = arrays[base], arrays[lossless]
    start, stop = cfg['local_feature_frames']
    final_differences = {}
    for storage, features in arrays.items():
        delta = features['control_final'].astype(float) - features['preroll_control_stats_final']
        changed = np.flatnonzero(np.any(delta != 0, axis=1))
        final_differences[storage] = {'changed_frames': int(changed.size),
                                      'first_frame': int(changed[0]) if changed.size else None,
                                      'last_frame': int(changed[-1]) if changed.size else None,
                                      'local_maximum': float(np.max(np.abs(delta[start:stop])))}
    now = boundaries[lossless]
    count = definition['measurement']['expected_preroll_difference_frames']
    predicted = {
        'shared_stats_final_difference_is_local_to_preroll': final_differences[lossless] == {
            'changed_frames': count, 'first_frame': 0, 'last_frame': count - 1, 'local_maximum': 0.0},
        'shared_stats_tall_boundaries_match': now['control'] == now['preroll_control_stats'],
        'tall_control_returns_to_legacy_boundary':
            now['control'] == definition['measurement']['legacy_control_end_seconds'],
    }
    checks = {
        'tall_final_mfcc_compressed_reproduces_previous_archives_and_tiers': (
            all(value.tobytes() == archived[key].tobytes() for key, value in before.items())
            and tiers[base] == {mode: matched_mfa.mfa.tiers(path) for mode, path in saved_tiers.items()}),
        'tall_final_mfcc_encoding_and_lossless_readback_recounted': (
            all(read_json(files['formats']) == dict.fromkeys(modes, definition['archive_tokens'][name])
                for name, files in sources.items())
            and all(before[key].tobytes() == after[key].tobytes() for key in before if not key.endswith('_final'))
            and all(after[f'{mode}_normalized'].tobytes() == after[f'{mode}_final'].tobytes() for mode in modes)),
        'tall_final_mfcc_preroll_effect_recounted': (
            final_differences == scope['shared_stats_final_differences']
            and all(value == summary['observations'][name]['feature_differences']['both_control_stats']['final'][key]
                    for name, metrics in final_differences.items() for key, value in metrics.items())),
        'tall_final_mfcc_intervals_and_predictions_recounted': (
            boundaries == scope['tall_vowel_end_seconds'] and predicted == summary['predictions']
            and all(matched_mfa.compare_intervals(tiers[base][mode], tiers[lossless][mode]) == result
                    for mode, result in summary['tier_changes_when_final_encoding_changes'].items())),
    }
    return {'run': run.name, 'shared_stats_final_differences': final_differences,
            'tall_vowel_end_seconds': boundaries, 'predictions': predicted}, checks


def tall_gmm_assets(root, definition):
    result = {'scores': root / 'path-scores.json', 'acoustics': root / 'path-scores.npz'}
    for mode in definition['measurement']['modes']:
        tag = 'FK61_02-control'
        for key, filename in (('decoder', 'decoder.npz'), ('meta', 'decoder.json'), ('graph', 'graph.fst'),
                              ('tier', f'aligned/{tag}/{tag}.json')):
            result[f'{mode}_{key}'] = root / mode / filename
    return result


def audit_tall_gmm_paths(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    cfg = definition['measurement']
    early, late = cfg['modes']
    modes = (early, late)
    files = tall_gmm_assets(run / 'artifacts', definition)
    raw = {mode: tall_gmm.read_npz(files[f'{mode}_decoder']) for mode in modes}
    metadata = {mode: read_json(files[f'{mode}_meta']) for mode in modes}
    tiers = {mode: matched_mfa.mfa.tiers(files[f'{mode}_tier']) for mode in modes}
    boundaries = {mode: tier['phones'][again_tip.phone_at_word(tier, {'word': 'tall', 'phones': ['AO1', 'L']})][1]
                  for mode, tier in tiers.items()}
    arrays = tall_gmm.read_npz(files['acoustics'])
    published = read_json(files['scores'])
    changed = np.flatnonzero(arrays[f'{early}_on_{early}_phone_ids'] != arrays[f'{early}_on_{late}_phone_ids']).tolist()
    margins, acoustic_local, score_checks = {}, {}, []
    start, end = cfg['local_feature_frames']
    for mode in modes:
        options = metadata[mode]['weight_options']
        scale = options['acoustic_scale']
        totals = {}
        for path in modes:
            label = f'{mode}_on_{path}'
            native = arrays[f'{label}_acoustic']
            total = scale * math.fsum(native) - published[mode][path]['graph_cost']
            totals[path] = total
            score_checks.append(abs(total - published[mode][path]['total_scaled_score']) < 1e-8
                and np.max(np.abs(native - arrays[f'{label}_independent'])) <= cfg['frame_likelihood_tolerance'])
        metrics = summary['score_comparisons'][mode]
        reference_frames = raw[mode]['frame_likelihood'].astype(float)
        if metrics['frame_units'] == 'scaled':
            reference_frames /= scale
        reference_total = metadata[mode]['reported_total']
        if metrics['total_units'] == 'unscaled':
            reference_total *= scale
        score_checks.append(np.max(np.abs(reference_frames - arrays[f'{mode}_on_{mode}_acoustic']))
                            <= cfg['frame_likelihood_tolerance']
                            and abs(reference_total - totals[mode]) <= cfg['total_scaled_score_tolerance'])
        margins[mode] = totals[late] - totals[early]
        acoustic_local[mode] = scale * math.fsum(arrays[f'{mode}_on_{late}_acoustic'][start:end]
                                                - arrays[f'{mode}_on_{early}_acoustic'][start:end])
    failed = scope['initial_failure']
    before = RUNS / failed['run']
    before_manifest = read_json(before / 'manifest.json')
    initial, stored = read_record(before.name, definition['upstream_revision'], expected_failure=True,
                                  expected_error=before_manifest['error'])
    checks = {
        'tall_gmm_features_models_and_graph_recounted': (
            sha256(files[f'{early}_graph']) == sha256(files[f'{late}_graph'])
            and metadata[early]['effective_model_sha256'] == metadata[late]['effective_model_sha256']
            and metadata[early]['weight_options'] == metadata[late]['weight_options']
            and [list(raw[mode]['features'].shape) for mode in modes] == [scope['feature_shape']] * 2),
        'tall_gmm_cross_scores_recounted': all(score_checks)
            and all(abs(margins[mode] - scope['late_path_advantage'][mode]) < 1e-8
                    and abs(acoustic_local[mode] - summary['late_minus_early_acoustic'][mode]['scaled_acoustic_near_tall']) < 1e-8
                    for mode in modes),
        'tall_gmm_intervals_and_preds_recounted': (
            boundaries == cfg['expected_end_seconds'] == summary['tall_vowel_end_seconds']
            and changed == summary['different_phone_frames'] == scope['different_phone_frames']
            and summary['predictions'] == {
                'phone_disagreement_matches_three_tall_frames': changed == cfg['expected_phone_difference_frames'],
                'each_input_favors_its_selected_path': margins[early] < 0 < margins[late]}),
        'tall_gmm_initial_probe_failure_retained': (
            not initial['errors'] and sha256(before / 'manifest.json') == failed['manifest_sha256']
            and 'TypeError: from_numpy()' in (before / 'artifacts/cargo.log').read_text()
            and all(stored[f'artifacts/{mode}/decoder.npz'] == sha256(files[f'{mode}_decoder']) for mode in modes)),
    }
    return {'run': run.name, 'initial_failure': before.name, 'late_path_advantage': margins,
            'local_acoustic_late_path_advantage': acoustic_local, 'different_phone_frames': changed}, checks


def tall_gmm_swap_assets(root, definition):
    files = {'inputs': root / 'decoder-inputs.npz', 'formats': root / 'archive-formats.json'}
    for mode in definition['measurement']['rows_from_float32']:
        tag = f'FK61_02-{mode}'
        files[f'{mode}_tier'] = root / 'aligned' / tag / f'{tag}.json'
        files[f'{mode}_decoder'] = root / mode / 'decoder.npz'
        files[f'{mode}_meta'] = root / mode / 'decoder.json'
        files[f'{mode}_graph'] = root / mode / 'graph.fst'
    return files


def audit_tall_gmm_swap(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    cfg = definition['measurement']
    parent = RUNS / definition['parent']['run']
    parent_case = saved_definition(parent, records)
    previous = tall_gmm_assets(parent / 'artifacts', parent_case)
    files = tall_gmm_swap_assets(run / 'artifacts', definition)
    modes = tuple(cfg['rows_from_float32'])
    early, late = tall_gmm_swap.CONTROLS
    originals = {mode: tall_gmm.read_npz(previous[f'{mode}_decoder']) for mode in (early, late)}
    observed = {mode: tall_gmm.read_npz(files[f'{mode}_decoder']) for mode in modes}
    inputs = tall_gmm.read_npz(files['inputs'])
    start, stop = cfg['tall_range']
    cuts = (slice(0, start), slice(start, stop), slice(stop, None))
    donors = {early: (early, early, early), late: (late, late, late),
              'float32_at_tall': (early, late, early), 'float32_outside_tall': (late, early, late)}
    tiers = {mode: matched_mfa.mfa.tiers(files[f'{mode}_tier']) for mode in modes}
    selection = {'word': 'tall', 'phones': cfg['tall_both_phones']}
    bounds = {mode: tier['phones'][again_tip.phone_at_word(tier, selection)][1] for mode, tier in tiers.items()}
    selections = {mode: next((source for source, raw in originals.items()
                  if raw['transition_ids'].tobytes() == current['transition_ids'].tobytes()
                  and raw['words'].tobytes() == current['words'].tobytes()), 'other')
                  for mode, current in observed.items()}
    after = {mode: read_json(files[f'{mode}_meta']) for mode in modes}
    before = read_json(previous[f'{early}_meta'])
    weights = before['weight_options']
    scale = weights['acoustic_scale']
    scores = read_json(previous['scores'])
    acoustics = tall_gmm.read_npz(previous['acoustics'])
    graph_advantage = scores[early][early]['graph_cost'] - scores[early][late]['graph_cost']
    terms = {mode: acoustics[f'{mode}_on_{late}_acoustic'] - acoustics[f'{mode}_on_{early}_acoustic'] for mode in (early, late)}
    margins = {mode: scale * math.fsum(value for span, source in zip(cuts, sources, strict=True)
                                     for value in terms[source][span]) + graph_advantage
               for mode, sources in donors.items()}
    checks = {
        'tall_gmm_swap_row_sources_recounted': all(
            observed[mode]['features'].tobytes() == inputs[mode].tobytes()
            and inputs[mode].tobytes() == b''.join(originals[source]['features'][span].tobytes()
                                                 for span, source in zip(cuts, donors[mode], strict=True)) for mode in modes),
        'tall_gmm_swap_same_graph_model_and_settings_recounted': (
            all(sha256(files[f'{mode}_graph']) == sha256(previous[f'{early}_graph'])
                and row['weight_options'] == weights and row['effective_model_sha256'] == before['effective_model_sha256']
                for mode, row in after.items())),
        'tall_gmm_swap_two_path_margins_recounted': all(
            abs(value - summary['margins_for_two_fixed_paths'][mode]) <= cfg['margin_agreement']
            for mode, value in margins.items()),
        'tall_gmm_swap_full_intervals_and_transition_ids_recounted': (
            selections == summary['selected_paths'] == scope['selected_paths']
            and bounds == summary['tall_vowel_end_seconds'] == scope['tall_vowel_end_seconds']
            and all(tiers[mode] == matched_mfa.mfa.tiers(previous[f'{mode}_tier']) for mode in (early, late))
            and all(tiers[mode] == tiers[source] for mode, source in selections.items())),
    }
    return {'run': run.name, 'selected_paths': selections, 'tall_vowel_end_seconds': bounds,
            'margins_for_two_fixed_paths': margins}, checks


def tall_gmm_subsets_assets(root, definition):
    files = {'inputs': root / 'decoder-inputs.npz', 'formats': root / 'archive-formats.json'}
    groups = tall_gmm_subsets.subsets(definition['measurement']['frames'])
    for mode in groups:
        tag = f'FK61_02-{mode}'
        files[f'{mode}_tier'] = root / 'aligned' / tag / f'{tag}.json'
        files[f'{mode}_decoder'] = root / mode / 'decoder.npz'
        files[f'{mode}_meta'] = root / mode / 'decoder.json'
        files[f'{mode}_graph'] = root / mode / 'graph.fst'
    return files


def audit_tall_gmm_subsets(scope, records, summary):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    cfg = definition['measurement']
    swap = RUNS / definition['parent']['run']
    swap_case = saved_definition(swap, records)
    parent = RUNS / swap_case['parent']['run']
    prior = tall_gmm_assets(parent / 'artifacts', saved_definition(parent, records))
    prior_swap = tall_gmm_swap_assets(swap / 'artifacts', swap_case)
    files = tall_gmm_subsets_assets(run / 'artifacts', definition)
    inputs = tall_gmm.read_npz(files['inputs'])
    options = read_json(prior['compressed_meta'])
    graph_sha = sha256(prior['compressed_graph'])
    early, late = ('compressed', 'float32')
    baseline = {mode: tall_gmm.read_npz(prior[f'{mode}_decoder']) for mode in (early, late)}
    scores = read_json(prior['scores'])
    acoustic = tall_gmm.read_npz(prior['acoustics'])
    scale = options['weight_options']['acoustic_scale']
    graph_advantage = scores[early][early]['graph_cost'] - scores[early][late]['graph_cost']
    early_advantage = acoustic['compressed_on_float32_acoustic'] - acoustic['compressed_on_compressed_acoustic']
    late_advantage = acoustic['float32_on_float32_acoustic'] - acoustic['float32_on_compressed_acoustic']
    base_margin = scale * math.fsum(early_advantage) + graph_advantage
    influence = scale * (late_advantage - early_advantage)
    five = cfg['frames']
    expected_subsets = {tuple(frame for j, frame in enumerate(five) if i & (1 << j)) for i in range(2 ** len(five))}
    observed_subsets = {tuple(row['frames']) for row in summary['subsets']}
    correct_inputs, matching_scores, same_settings = True, True, True
    decisions = []
    prev = swap_case['measurement']
    selection = {'word': 'tall', 'phones': prev['tall_both_phones']}
    late_boundary = prev['accepted_control_end_seconds'][late]
    for row in summary['subsets']:
        mode, frames = row['mode'], row['frames']
        computed, native = (tall_gmm.read_npz(files[f'{mode}_decoder']), read_json(files[f'{mode}_meta']))
        reconstructed = baseline[early]['features'].copy()
        reconstructed[frames] = baseline[late]['features'][frames]
        correct_inputs &= (inputs[mode].tobytes() == reconstructed.tobytes() == computed['features'].tobytes())
        same_settings &= (native['weight_options'] == options['weight_options']
                          and native['effective_model_sha256'] == options['effective_model_sha256']
                          and sha256(files[f'{mode}_graph']) == graph_sha)
        rank = base_margin + math.fsum(influence[index] for index in frames)
        pred = late if rank > 0 else early if rank < 0 else 'tie'
        matching_scores &= abs(rank - row['margin']) <= cfg['margin_agreement'] and pred == row['predicted_path']
        variants = [name for name, data in baseline.items() if all(
            computed[key].tobytes() == data[key].tobytes() for key in ('transition_ids', 'words'))]
        actual = variants[0] if variants else 'other'
        tiers = matched_mfa.mfa.tiers(files[f'{mode}_tier'])
        end = tiers['phones'][again_tip.phone_at_word(tiers, selection)][1]
        if not frames:
            correct_inputs &= tiers == matched_mfa.mfa.tiers(prior_swap['compressed_tier'])
        if frames == five:
            correct_inputs &= tiers == matched_mfa.mfa.tiers(prior_swap['float32_at_tall_tier'])
        decisions.append((frames, end, actual, pred))
    moving = [frames for frames, end, _, _ in decisions if end == late_boundary]
    minimum = min(map(len, moving), default=None)
    minimal = [group for group in moving if not any(set(other) < set(group) for other in moving)]
    mismatches = [frames for frames, _, actual, pred in decisions if actual != pred]
    total_by_size = Counter(len(frames) for frames, _, _, _ in decisions)
    moved_by_size = Counter(map(len, moving))
    breakdown = {str(size): {'conditions': count, 'late_boundary': moved_by_size[size]}
                 for size, count in total_by_size.items()}
    failed = scope['cmvn_failure']
    stopped = RUNS / failed['run']
    failed_manifest = read_json(stopped / 'manifest.json')
    failure, stored = read_record(stopped.name, definition['upstream_revision'], expected_failure=True,
                                  expected_error=failed_manifest['error'])
    checks = {
        'tall_gmm_subsets_all_rows_recounted': observed_subsets == expected_subsets
            and len(decisions) == cfg['subset_count'] and correct_inputs and same_settings,
        'tall_gmm_subsets_score_and_paths_recounted': matching_scores and all(
            end == row['end_seconds'] and actual == row['selected_path'] and expected == row['predicted_path']
            for (_, end, actual, expected), row in zip(decisions, summary['subsets'], strict=True)),
        'tall_gmm_subsets_minimum_and_differences_recounted': (
            minimum == scope['minimum_count'] == summary['counts']['minimum_count']
            and breakdown == summary['counts']['by_size'] and len(moving) == scope['moved_conditions']
            and [group for group in moving if len(group) == minimum] == scope['minimum_frame_sets']
            and minimal == scope['inclusion_minimal_frame_sets'] == summary['counts']['inclusion_minimal_frame_sets']
            and mismatches == scope['different_from_margin_prediction'] == summary['different_from_margin_prediction']),
        'tall_gmm_subsets_cmvn_failure_retained': (not failure['errors']
            and sha256(stopped / 'manifest.json') == failed['manifest_sha256']
            and 'Error opening RandomAccessTableReader' in (stopped / 'artifacts/cargo.log').read_text()
            and stored['artifacts/decoder-inputs.npz'] == sha256(files['inputs'])),
    }
    return {'run': run.name, 'minimum_count': minimum, 'moved_conditions': len(moving),
            'inclusion_minimal_frame_sets': minimal, 'different_from_margin_prediction': mismatches}, checks


def tall_f2_grid_inputs(definition):
    root = RUNS / definition['boundary_runs']['run'] / 'artifacts'
    assets = {}
    for end, mode in definition['measurement']['observed_modes'].items():
        tag = f"{definition['utterance']}-{mode}"
        assets[end] = (root / 'aligned' / tag / f'{tag}.json', root / 'corpus' / tag / f'{tag}.wav')
    wave = RUNS / definition['clean_render']['run'] / 'artifacts/matched-clean.wav'
    return wave, assets


def recount_f2_grid(definition, run, wave, voice, cfg):
    settings, uid = definition['measurement'], definition['utterance']
    lo = tall_f2_grid.formants.filtered_wave(wave, voice, cfg)
    fixed = read_json(run / 'artifacts/upstream-formants.json')[uid]['sources']
    report = read_json(run / 'artifacts/window-comparisons.json')
    intervals = tall_f2_grid.interval_grid(settings)
    centers = settings['centers']
    recomputed, window_count = [], 0
    window_match, medians_match = True, True
    for key, interval in intervals.items():
        raw, = fixed[key]
        local = tall_f2_grid.formants.token_measurement(lo, interval, cfg['order'][uid[0]], centers, raw, cfg)
        window_count += len(raw['windows'])
        window_match &= all(row['first_different_stage'] is None for row in local['window_comparison'])
        window_match &= local == (report[key] | {'interval': tuple(report[key]['interval'])})
        selections = [formants.select(window['poles'], cfg) for window in raw['windows']]
        f2s = [p['f2'][0] for center, p in zip(centers, selections, strict=True)
               if center in cfg['reference_centers'] and p['f2'] is not None]
        middle = median(f2s) if f2s else None
        medians_match &= middle == raw['baseline_hz'][1]
        recomputed.append({
            'end_ms': int(key), 'origin': settings['observed_modes'].get(key, 'assigned'),
            'median_f2_hz': middle, 'median_support': len(f2s),
            'late_f2_hz': selections[-1]['f2'][0] if selections[-1]['f2'] is not None else None,
            'late_outside_phone_ms': local['windows'][-1]['outside_phone_ms'],
            'late_reason': selections[-1]['reason'],
            'start_samples': [row['start_sample'] for row in local['windows']],
        })
    steps = [[b - a for a, b in zip(left['start_samples'], right['start_samples'], strict=True)]
             for left, right in zip(recomputed, recomputed[1:])]
    return (fixed, intervals, recomputed, window_count, steps, window_match and medians_match)


def audit_tall_f2_grid(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    settings = definition['measurement']
    wave, observed = tall_f2_grid_inputs(definition)
    fixed, intervals, recomputed, window_count, steps, window_match = recount_f2_grid(definition, run, wave, 'clean', cfg)
    anchor_intervals, wave_hashes = {}, set()
    for key, (alignment, pcm) in observed.items():
        tier = matched_mfa.mfa.tiers(alignment)
        anchor_intervals[key] = tuple(tier['phones'][again_tip.phone_at_word(tier, settings)])
        wave_hashes.add(sha256(pcm))
    previous = RUNS / definition['endpoint_formants']['run']
    previous_centers = saved_definition(previous, records)['measurement']['analysis_centers']
    endpoint_data = read_json(previous / 'artifacts/upstream-formants.json')[definition['utterance']]['sources']
    endpoints_match = True
    for key, mode in settings['endpoint_routes'].items():
        raw, = fixed[key]
        prior, = endpoint_data[mode]
        prior_by_center = dict(zip(previous_centers, prior['windows'], strict=True))
        endpoints_match &= prior['baseline_hz'] == raw['baseline_hz'] and raw['windows'] == [
            prior_by_center[center] for center in settings['centers']]

    spans, sensitivity = tall_f2_grid.f2_spans(recomputed), settings['sensitivity_threshold_hz']
    median_span, late_span = spans['median_f2_hz'], spans['late_f2_hz']
    monotone = late_span is not None and all(left['late_f2_hz'] <= right['late_f2_hz']
                                           for left, right in zip(recomputed, recomputed[1:]))
    predictions = {
        'median_span_below_threshold': median_span is not None and median_span < sensitivity,
        'late_span_meets_threshold': late_span is not None and late_span >= sensitivity,
        'late_f2_nondecreasing': monotone,
    }
    checks = {
        'tall_f2_grid_from_alignment_and_pcm': len(wave_hashes) == 1
            and all(intervals[key] == anchor for key, anchor in anchor_intervals.items())
            and {k: list(v) for k, v in intervals.items()} == summary['intervals'],
        'tall_f2_grid_window_recomputed_from_clean_wave': window_match
            and window_count == scope['windows'] and steps == summary['window_start_steps']
            and all(step == settings['start_sample_step'] for step in steps),
        'tall_f2_grid_endpoints_replayed': endpoints_match,
        'tall_f2_grid_ranges_and_predictions_recounted': (recomputed == summary['trajectories']
            and spans == summary['f2_spans_hz'] and predictions == scope['predictions'] == summary['predictions']),
    }
    return {'run': run.name, 'windows': window_count, 'f2_spans_hz': spans, 'predictions': predictions}, checks


def audit_tall_recording_f2_grid(scope, records, summary, cfg):
    run = RUNS / scope['run']
    definition = saved_definition(run, records)
    settings, uid = definition['measurement'], definition['utterance']
    root = RUNS / definition['alignment']['run']
    paths = {name: root / file for name, file in tall_recording_grid.recording_paths(uid).items()}
    fixed, intervals, rows, count, steps, window_match = recount_f2_grid(
        definition, run, paths['recording'], 'recording', cfg)
    observed, = settings['observed_modes']
    tiers = [matched_mfa.mfa.tiers(paths[f'aligned_{n}']) for n in (1, 2)]
    anchor = tuple(tiers[0]['phones'][again_tip.phone_at_word(tiers[0], settings)])
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    window_length = int(cfg['frame_seconds'] * rate)
    for row in rows:
        late = fixed[str(row['end_ms'])][0]['windows'][-1]
        selected = formants.select(late['poles'], cfg)['f2']
        row['late_selected_pole_rank'] = None if selected is None else late['poles'].index(selected) + 1
        row['late_after_mfa_boundary_ms'] = 1000 * max(0, (late['start_sample'] + window_length) / rate - anchor[1])

    spans = tall_f2_grid.f2_spans(rows)
    mid_span, late_span = spans['median_f2_hz'], spans['late_f2_hz']
    limit = settings['sensitivity_threshold_hz']
    predictions = {
        'median_span_below_threshold': mid_span is not None and mid_span < limit,
        'late_span_meets_threshold': late_span is not None and late_span >= limit,
        'late_span_exceeds_median_span': mid_span is not None and late_span is not None and late_span > mid_span,
    }
    synth = RUNS / definition['synth_grid']['run']
    failed = scope['initial_failure']
    before = RUNS / failed['run']
    failure, outputs = read_record(before.name, definition['upstream_revision'], expected_failure=True,
                                   expected_failed_checks=failed['failed_checks'])
    manifest = read_json(before / 'manifest.json')
    original = read_json(before / manifest['source_snapshot'] / tall_recording_grid.CASE.relative_to(ROOT))
    old_summary = read_json(before / 'summary.json')
    signal_artifacts = ('artifacts/upstream-formants.json', 'artifacts/window-comparisons.json')
    checks = {
        'tall_recording_f2_grid_from_alignment': tiers[0] == tiers[1] and anchor == intervals[observed]
            and list(anchor) == summary['mfa_interval'] and {k: list(v) for k, v in intervals.items()} == summary['intervals'],
        'tall_recording_f2_grid_windows_from_pcm16': window_match and count == scope['windows']
            and steps == summary['window_start_steps'] and all(
                row['start_samples'] == settings['start_samples_by_end'][str(row['end_ms'])] for row in rows),
        'tall_recording_f2_grid_ranges_and_poles_recounted': rows == summary['trajectories']
            and spans == summary['f2_spans_hz'] and predictions == scope['predictions'] == summary['predictions']
            and read_json(synth / 'summary.json')['f2_spans_hz'] == summary['synth_f2_spans_hz'],
        'tall_recording_f2_grid_initial_sample_step_failure_retained': (not failure['errors']
            and definition['previous_attempt'] == failed and original['revision'] == manifest['case_revision'] == 1
            and sha256(before / 'manifest.json') == failed['manifest_sha256']
            and any(step != original['measurement']['start_sample_step'] for step in steps)
            and {key: old_summary[key] for key in ('trajectories', 'window_start_steps', 'f2_spans_hz')}
            == {key: summary[key] for key in ('trajectories', 'window_start_steps', 'f2_spans_hz')}
            and all(outputs[path] == sha256(run / path) for path in signal_artifacts)),
    }
    return {'run': run.name, 'windows': count, 'f2_spans_hz': spans, 'predictions': predictions}, checks


def audit_f2_followup(case, records, summaries):
    expected = case['f2_followup']
    material = RUNS / expected['annotation_material']
    annotation, checks = audit_annotation_material(material, RUNS / expected['annotation_fixture'],
                                                  saved_definition(material, records), expected)
    reference = RUNS / 'tsp-stressed-vowel-formants-held-out-20261122-repeat'
    cfg = saved_definition(reference, records)['measurement']
    order_run = RUNS / expected['recording_order']
    config = saved_definition(order_run, records)
    order = summaries[order_run.name]
    narrow = summaries[expected['harmonic_spacing']]
    paired = summaries[expected['harmonic_bandwidth']]
    counts = {}
    for key, report, length in (('harmonic_spacing', narrow, expected['narrow_windows']),
                                ('harmonic_bandwidth', paired, expected['paired_bandwidth_windows'])):
        raw = read_json(RUNS / expected[key] / 'artifacts/upstream-envelopes.json')
        rows = report['windows']
        public_key = 'selected' if key == 'harmonic_spacing' else 'fixed_selection'
        counts[key] = {'windows': len(rows), 'missing_f2': sum(formants.select(p['poles'], cfg)['f2'] is None for p in raw)}
        checks[f'f2_{key}_from_public_poles'] = len(raw) == len(rows) == length and all(
            formants.select(poles['poles'], cfg) == row[public_key] for row, poles in zip(rows, raw))
    if scope := expected.get('intervening_resonance'):
        counts['intervening_resonance'], selection_checks = audit_f2_intervening_resonance(
            scope, records, summaries[scope['run']], cfg)
        checks.update(selection_checks)
    if scope := expected.get('intervening_excitation'):
        counts['intervening_excitation'], excitation_checks = audit_f2_intervening_excitation(
            scope, records, summaries[scope['run']], cfg)
        checks.update(excitation_checks)
    if scope := expected.get('intervening_phase'):
        counts['intervening_phase'], phase_checks = audit_f2_intervening_phase(scope, records, summaries[scope['run']], cfg)
        checks.update(phase_checks)
    if scope := expected.get('intervening_phase_midpoint'):
        counts['intervening_phase_midpoint'], midpoint_checks = audit_f2_intervening_phase_midpoint(
            scope, records, summaries, cfg)
        checks.update(midpoint_checks)
    if scope := expected.get('recording_window_shift'):
        counts['recording_window_shift'], window_checks = audit_f2_recording_window_shift(
            scope, records, summaries[scope['run']], cfg)
        checks.update(window_checks)
    if scope := expected.get('annotation_w06_window_shift'):
        counts['annotation_w06_window_shift'], w06_checks = audit_f2_annotation_window_shift(
            scope, records, summaries[scope['run']], cfg)
        checks.update(w06_checks)
    if scope := expected.get('annotation_w06_pre_emphasis'):
        counts['annotation_w06_pre_emphasis'], pre_checks = audit_f2_annotation_pre_emphasis(
            scope, records, summaries[scope['run']], cfg)
        checks.update(pre_checks)
    if scope := expected.get('annotation_again_pre_emphasis'):
        counts['annotation_again_pre_emphasis'], again_checks = audit_f2_annotation_again_pre_emphasis(
            scope, records, summaries[scope['run']], cfg)
        checks.update(again_checks)
    if scope := expected.get('again_f2_term_effect'):
        counts['again_f2_term_effect'], cost_checks = audit_again_f2_term_effect(scope, records, summaries[scope['run']], cfg)
        checks.update(cost_checks)
    if scope := expected.get('training_reference_sensitivity'):
        counts['training_reference_sensitivity'], reference_checks = audit_f2_training_reference(
            scope, records, summaries[scope['run']])
        checks.update(reference_checks)
    if scope := expected.get('training_reference_ten_speakers'):
        counts['training_reference_ten_speakers'], reference_checks = audit_f2_ten_speakers(
            scope, records, summaries[scope['run']], cfg)
        checks.update(reference_checks)
    if scope := expected.get('reference_centre_width'):
        counts['reference_centre_width'], centre_width_checks = audit_f2_centre_width(
            scope, records, summaries[scope['run']])
        checks.update(centre_width_checks)
    if scope := expected.get('reference_pooled_sexes'):
        counts['reference_pooled_sexes'], pooled_checks = audit_f2_pooled_sexes(
            scope, records, summaries[scope['run']], cfg)
        checks.update(pooled_checks)
    if scope := expected.get('pooled_reference_sweep'):
        counts['pooled_reference_sweep'], pooled_sweep_checks = audit_f2_pooled_sweep(
            scope, records, summaries[scope['run']])
        checks.update(pooled_sweep_checks)
    if scope := expected.get('pooled_reference_held_fl'):
        counts['pooled_reference_held_fl'], held_fl_checks = audit_f2_held_fl(
            scope, records, summaries[scope['run']], cfg)
        checks.update(held_fl_checks)
    if scope := expected.get('held_synth_over_sets'):
        counts['held_synth_over_sets'], over_sets_checks = audit_f2_over_sets(
            scope, records, summaries[scope['run']])
        checks.update(over_sets_checks)
    if scope := expected.get('full_held_women'):
        counts['full_held_women'], full_held_checks = audit_f2_full_held(
            scope, records, summaries[scope['run']], cfg)
        checks.update(full_held_checks)
    if scope := expected.get('full_held_candidate'):
        counts['full_held_candidate'], full_candidate_checks = audit_f2_full_candidate(
            scope, records, summaries[scope['run']], cfg)
        checks.update(full_candidate_checks)
    if scope := expected.get('fk61_pcm_first_difference'):
        counts['fk61_pcm_first_difference'], fk61_checks = audit_fk61_pcm(
            scope, records, summaries[scope['run']])
        checks.update(fk61_checks)
    if scope := expected.get('fk61_lip_onset'):
        counts['fk61_lip_onset'], fk61_lip_checks = audit_fk61_lip(scope, records, summaries[scope['run']])
        checks.update(fk61_lip_checks)
    if scope := expected.get('fk61_lip_volume_increment'):
        counts['fk61_lip_volume_increment'], fk61_volume_checks = audit_fk61_volume(
            scope, records, summaries[scope['run']])
        checks.update(fk61_volume_checks)
    if scope := expected.get('fk61_lip_area_origin'):
        counts['fk61_lip_area_origin'], fk61_area_checks = audit_fk61_area(scope, records, summaries[scope['run']])
        checks.update(fk61_area_checks)
    if scope := expected.get('fk61_lip_front_origin'):
        counts['fk61_lip_front_origin'], fk61_front_checks = audit_fk61_front(scope, records, summaries[scope['run']])
        checks.update(fk61_front_checks)
    if scope := expected.get('fk61_centerline_length_origin'):
        counts['fk61_centerline_length_origin'], fk61_centerline_checks = audit_fk61_centerline(
            scope, records, summaries[scope['run']])
        checks.update(fk61_centerline_checks)
    if scope := expected.get('fk61_lip_front_radiation'):
        counts['fk61_lip_front_radiation'], fk61_residual_checks = audit_fk61_residual(
            scope, records, summaries[scope['run']])
        checks.update(fk61_residual_checks)
    if scope := expected.get('fk61_lip_front_terminal_branch'):
        counts['fk61_lip_front_terminal_branch'], fk61_terminal_checks = audit_fk61_terminal(
            scope, records, summaries[scope['run']])
        checks.update(fk61_terminal_checks)
    if scope := expected.get('fk61_node42_volume_source'):
        counts['fk61_node42_volume_source'], node42_checks = audit_fk61_node42(scope, records, summaries[scope['run']])
        checks.update(node42_checks)
    if scope := expected.get('fk61_node42_area_origin'):
        counts['fk61_node42_area_origin'], node42_area_checks = audit_fk61_node42_area(
            scope, records, summaries[scope['run']])
        checks.update(node42_area_checks)
    if scope := expected.get('fk61_ray43_intersection'):
        counts['fk61_ray43_intersection'], ray43_checks = audit_fk61_ray43(scope, records, summaries[scope['run']])
        checks.update(ray43_checks)
    if scope := expected.get('fk61_lower_lip_bernstein_render'):
        counts['fk61_lower_lip_bernstein_render'], bernstein_checks = audit_fk61_bernstein(
            scope, records, summaries[scope['run']])
        checks.update(bernstein_checks)
    if scope := expected.get('fk61_pcm2937_output'):
        counts['fk61_pcm2937_output'], pcm2937_checks = audit_fk61_pcm2937(
            scope, records, summaries[scope['run']])
        checks.update(pcm2937_checks)
    if scope := expected.get('fk61_pcm2937_lip_window'):
        counts['fk61_pcm2937_lip_window'], lip_window_checks = audit_fk61_lip_window(
            scope, records, summaries[scope['run']])
        checks.update(lip_window_checks)
    if scope := expected.get('fk61_pcm2937_terminal_load'):
        counts['fk61_pcm2937_terminal_load'], terminal_load_checks = audit_fk61_terminal_load(
            scope, records, summaries[scope['run']])
        checks.update(terminal_load_checks)
    if scope := expected.get('fk61_pcm2937_branch_drive'):
        counts['fk61_pcm2937_branch_drive'], branch_drive_checks = audit_fk61_branch_drive(
            scope, records, summaries[scope['run']])
        checks.update(branch_drive_checks)
    if scope := expected.get('fk61_pcm2937_branch_seed'):
        counts['fk61_pcm2937_branch_seed'], branch_seed_checks = audit_fk61_branch_seed(
            scope, records, summaries[scope['run']])
        checks.update(branch_seed_checks)
    if scope := expected.get('fk61_branch_first_difference'):
        counts['fk61_branch_first_difference'], branch_first_checks = audit_fk61_branch_first(
            scope, records, summaries[scope['run']])
        checks.update(branch_first_checks)
    if scope := expected.get('fk61_oral_onset_inflow'):
        counts['fk61_oral_onset_inflow'], oral_inflow_checks = audit_fk61_oral_inflow(
            scope, records, summaries[scope['run']])
        checks.update(oral_inflow_checks)
    if scope := expected.get('fk61_node40_expanded_volume'):
        counts['fk61_node40_expanded_volume'], expanded_volume_checks = audit_fk61_node40_expanded(
            scope, records, summaries[scope['run']])
        checks.update(expanded_volume_checks)
    if scope := expected.get('fk61_control5632_mouth_flow'):
        counts['fk61_control5632_mouth_flow'], control5632_checks = audit_fk61_control5632(
            scope, records, summaries[scope['run']])
        checks.update(control5632_checks)
    if scope := expected.get('fk61_control5632_upstream_drive'):
        counts['fk61_control5632_upstream_drive'], upstream_drive_checks = audit_fk61_upstream_drive(
            scope, records, summaries[scope['run']])
        checks.update(upstream_drive_checks)
    if scope := expected.get('fk61_control5632_oral_inlet'):
        counts['fk61_control5632_oral_inlet'], oral_inlet_checks = audit_fk61_oral_inlet(
            scope, records, summaries[scope['run']])
        checks.update(oral_inlet_checks)
    if scope := expected.get('fk61_control5632_oral_geometry'):
        counts['fk61_control5632_oral_geometry'], oral_geometry_checks = audit_fk61_oral_geometry(
            scope, records, summaries[scope['run']])
        checks.update(oral_geometry_checks)
    if scope := expected.get('fk61_control5504_oral_history'):
        counts['fk61_control5504_oral_history'], oral_history_checks = audit_fk61_oral_history(
            scope, records, summaries[scope['run']])
        checks.update(oral_history_checks)
    if scope := expected.get('fk61_onset_to_control5504_volume_history'):
        counts['fk61_onset_to_control5504_volume_history'], onset_history_checks = audit_fk61_onset_history(
            scope, records, summaries[scope['run']])
        checks.update(onset_history_checks)
    if scope := expected.get('fk61_control4992_5120_area_targets'):
        counts['fk61_control4992_5120_area_targets'], area_targets_checks = audit_fk61_area_targets(
            scope, records, summaries[scope['run']])
        checks.update(area_targets_checks)
    if scope := expected.get('fk61_control4992_5120_indexed_area'):
        counts['fk61_control4992_5120_indexed_area'], indexed_area_checks = audit_fk61_indexed_area(
            scope, records, summaries[scope['run']])
        checks.update(indexed_area_checks)
    if scope := expected.get('fk61_control4992_5120_indexed_area_paired'):
        counts['fk61_control4992_5120_indexed_area_paired'], paired_area_checks = audit_fk61_paired_area(
            scope, records, summaries[scope['run']])
        checks.update(paired_area_checks)
    if scope := expected.get('fk61_control4992_5120_expanded_volume_paired'):
        counts['fk61_control4992_5120_expanded_volume_paired'], paired_volume_checks = audit_fk61_paired_volume(
            scope, records, summaries[scope['run']])
        checks.update(paired_volume_checks)
    if scope := expected.get('fk61_pcm16682_rounding'):
        counts['fk61_pcm16682_rounding'], pcm16682_checks = audit_fk61_pcm16682(
            scope, records, summaries[scope['run']])
        checks.update(pcm16682_checks)
    if scope := expected.get('fk61_full_pcm_rounding'):
        counts['fk61_full_pcm_rounding'], full_pcm_checks = audit_fk61_full_pcm(
            scope, records, summaries[scope['run']])
        checks.update(full_pcm_checks)
    for label, measurement, extra_fields in MATCHED_PCM_ROUNDING:
        key = f'{label}_rounding'
        if scope := expected.get(key):
            counts[key], matched_pcm_checks = audit_matched_pcm_rounding(
                scope, records, summaries[scope['run']], label, measurement, extra_fields)
            checks.update(matched_pcm_checks)
    if scope := expected.get('held_out_pcm_rounding'):
        counts['held_out_pcm_rounding'], held_out_pcm_checks = audit_held_out_pcm_rounding(
            scope, records, summaries[scope['run']])
        checks.update(held_out_pcm_checks)
    if scope := expected.get('candidate_report'):
        counts['candidate_report'], report_checks = audit_f2_candidate_report(scope, summaries[scope['run']], cfg)
        checks.update(report_checks)
    if scope := expected.get('source_comparison'):
        counts['source_comparison'], source_checks = audit_f2_source_comparison(scope, records, summaries[scope['run']], cfg)
        checks.update(source_checks)
    if scope := expected.get('seems_tract_transfer'):
        counts['seems_tract_transfer'], tract_checks = audit_seems_tract_transfer(scope, records, summaries[scope['run']])
        checks.update(tract_checks)
    if scope := expected.get('seems_spectrum_stages'):
        counts['seems_spectrum_stages'], spectrum_checks = audit_seems_spectrum_stages(scope, records, summaries[scope['run']], cfg)
        checks.update(spectrum_checks)
    if scope := expected.get('seems_drift_only'):
        counts['seems_drift_only'], drift_checks = audit_seems_drift_only(scope, records, summaries[scope['run']], cfg)
        checks.update(drift_checks)
    if scope := expected.get('seems_pressure_replay'):
        counts['seems_pressure_replay'], pressure_checks = audit_seems_pressure_replay(scope, records, summaries[scope['run']], cfg)
        checks.update(pressure_checks)
    if scope := expected.get('seems_period_jitter'):
        counts['seems_period_jitter'], jitter_checks = audit_seems_period_jitter(scope, records, summaries[scope['run']], cfg)
        checks.update(jitter_checks)
    if scope := expected.get('seems_amplitude_shimmer'):
        counts['seems_amplitude_shimmer'], shimmer_checks = audit_seems_amplitude_shimmer(scope, records, summaries[scope['run']], cfg)
        checks.update(shimmer_checks)
    if scope := expected.get('seems_initial_tip'):
        counts['seems_initial_tip'], tip_checks = audit_seems_initial_tip(scope, records, summaries[scope['run']])
        checks.update(tip_checks)
    if scope := expected.get('matched_held_out_speech'):
        counts['matched_held_out_speech'], matched_checks = audit_matched_held_out_speech(scope, records, summaries[scope['run']])
        checks.update(matched_checks)
    if scope := expected.get('matched_speech_formants'):
        counts['matched_speech_formants'], formant_checks = audit_matched_speech_formants(scope, records, summaries[scope['run']], cfg)
        checks.update(formant_checks)
    if scope := expected.get('matched_speech_mfa'):
        counts['matched_speech_mfa'], mfa_checks = audit_matched_speech_mfa(scope, records, summaries[scope['run']])
        checks.update(mfa_checks)
    if scope := expected.get('again_initial_tip_mfa'):
        counts['again_initial_tip_mfa'], tip_checks = audit_again_tip_mfa(scope, records, summaries[scope['run']])
        checks.update(tip_checks)
    if scope := expected.get('again_period_jitter_mfa'):
        counts['again_period_jitter_mfa'], jitter_checks = audit_again_jitter_mfa(scope, records, summaries[scope['run']])
        checks.update(jitter_checks)
    if scope := expected.get('again_pitch_drift_mfa'):
        counts['again_pitch_drift_mfa'], drift_checks = audit_again_drift_mfa(scope, records, summaries[scope['run']])
        checks.update(drift_checks)
    if scope := expected.get('cohort_pitch_drift_mfa'):
        counts['cohort_pitch_drift_mfa'], cohort_checks = audit_cohort_drift(scope, records, summaries[scope['run']])
        checks.update(cohort_checks)
    if scope := expected.get('cohort_source_variation_zero_mfa'):
        counts['cohort_source_variation_zero_mfa'], zero_checks = audit_cohort_drift(scope, records, summaries[scope['run']])
        checks.update(zero_checks)
    if scope := expected.get('tall_output_gain_mfa'):
        counts['tall_output_gain_mfa'], gain_checks = audit_tall_output_gain(scope, records, summaries[scope['run']])
        checks.update(gain_checks)
    if scope := expected.get('tall_initial_tip_mfa'):
        counts['tall_initial_tip_mfa'], tip_checks = audit_tall_initial_tip(scope, records, summaries[scope['run']])
        checks.update(tip_checks)
    if scope := expected.get('tall_mfa_preroll'):
        counts['tall_mfa_preroll'], preroll_checks = audit_tall_preroll(scope, records, summaries[scope['run']])
        checks.update(preroll_checks)
    if scope := expected.get('tall_mfa_cmvn'):
        counts['tall_mfa_cmvn'], cmvn_checks = audit_tall_cmvn(scope, records, summaries[scope['run']])
        checks.update(cmvn_checks)
    if scope := expected.get('tall_mfcc_input_compression'):
        counts['tall_mfcc_input_compression'], compression_checks = audit_tall_mfcc_input(scope, records, summaries[scope['run']])
        checks.update(compression_checks)
    if scope := expected.get('tall_mfcc_final_compression'):
        counts['tall_mfcc_final_compression'], final_checks = audit_tall_mfcc_final(scope, records, summaries[scope['run']])
        checks.update(final_checks)
    if scope := expected.get('tall_gmm_paths'):
        counts['tall_gmm_paths'], paths_checks = audit_tall_gmm_paths(scope, records, summaries[scope['run']])
        checks.update(paths_checks)
    if scope := expected.get('tall_gmm_frame_swap'):
        counts['tall_gmm_frame_swap'], swap_checks = audit_tall_gmm_swap(scope, records, summaries[scope['run']])
        checks.update(swap_checks)
    if scope := expected.get('tall_gmm_frame_subsets'):
        counts['tall_gmm_frame_subsets'], subset_checks = audit_tall_gmm_subsets(scope, records, summaries[scope['run']])
        checks.update(subset_checks)
    if scope := expected.get('tall_f2_boundary_grid'):
        counts['tall_f2_boundary_grid'], grid_checks = audit_tall_f2_grid(scope, records, summaries[scope['run']], cfg)
        checks.update(grid_checks)
    if scope := expected.get('tall_recording_f2_boundary_grid'):
        counts['tall_recording_f2_boundary_grid'], grid_checks = audit_tall_recording_f2_grid(
            scope, records, summaries[scope['run']], cfg)
        checks.update(grid_checks)
    if scope := expected.get('again_amplitude_shimmer_mfa'):
        counts['again_amplitude_shimmer_mfa'], shimmer_checks = audit_again_shimmer_mfa(scope, records, summaries[scope['run']])
        checks.update(shimmer_checks)
    if scope := expected.get('again_male_period_jitter_mfa'):
        counts['again_male_period_jitter_mfa'], male_jitter_checks = audit_again_jitter_mfa(scope, records, summaries[scope['run']])
        checks.update(male_jitter_checks)

    fixed = read_json(order_run / 'artifacts/upstream-envelopes.json')
    pairs = order['windows']
    shifts, near_counts = {}, Counter()
    matched = len(fixed) == 2 * len(pairs) == 2 * expected['recording_trials']
    for index, row in enumerate(pairs):
        by_order = dict(zip(config['orders'], fixed[2 * index:2 * index + 2]))
        original = formants.select(by_order[row['default_order']]['poles'], cfg)
        changed = formants.select(by_order[row['comparison_order']]['poles'], cfg)
        matched = matched and all(formants.select(item['poles'], cfg) == row['by_order'][str(p)]['selected']
                                  for p, item in by_order.items())
        if original['f2'] is None or changed['f2'] is None:
            matched = False
            continue
        change = changed['f2'][0] - original['f2'][0]
        shifts.setdefault(row['word'], []).append(change)
        band = config['neighborhood_hz']
        rate = cfg['sample_rate_hz'] / cfg['decimation']
        roots = by_order[row['comparison_order']]['roots']
        near = sum(im > 0 and abs(math.atan2(im, re) * rate / (2 * math.pi) - original['f2'][0]) < band for re, im in roots)
        near_counts[row['word']] += near
        matched = matched and change == row['change']['signed_f2_change_hz'] and near == len(row['change']['near_default_f2_raw_hz'])
    limit = config['large_difference_hz']
    checks['f2_recording_order_from_raw_roots'] = (matched and set(shifts) == {'seems', 'again'}
        and len(shifts['seems']) == len(shifts['again']) == 3 and near_counts['seems'] == 0
        and all(delta >= limit for delta in shifts['seems']) and all(abs(delta) < limit for delta in shifts['again']))

    failed = expected['retained_failure']
    before = RUNS / failed['run']
    manifest = read_json(before / 'manifest.json')
    failure, outputs = read_record(before.name, case['upstream_revision'], expected_failure=True,
                                   expected_failed_checks=failed['failed_checks'])
    definition = matched_case(before, manifest, failed, failure['case_inputs'])
    failed_summary = read_json(before / 'summary.json')
    outcome_fields = ('word', 'center', 'start_sample', 'default_order', 'change')
    changes = [[row[key] for key in outcome_fields] for row in order['windows']]
    old_changes = [[row[key] for key in outcome_fields] for row in failed_summary['windows']]
    poles_path = 'artifacts/upstream-envelopes.json'
    checks['f2_failed_root_audit_is_preserved'] = (not failure['errors'] and definition is not None
        and manifest['case_revision'] == failed['case_revision']
        and sha256(before / 'manifest.json') == failed['manifest_sha256']
        and outputs.get(poles_path) == sha256(order_run / poles_path) and 'summary.json' in outputs
        and old_changes == changes)
    return ({'annotation': annotation, 'synthetic_controls': counts, 'recording_f2_shifts_hz': shifts,
             'retained_failure': {'run': before.name, 'failed_checks': failed['failed_checks'], **failure}}, checks)


def followup_coverage(summaries):
    midi = summaries['worklet-midi-permission-20261122-repeat']
    permission_panels = {}
    for panel, observed in midi['candidate'].items():
        accepted = [row for row in observed['disconnected']['requests'] if row['outcome'] == 'granted']
        permission_panels[panel] = {'permissions': observed['permissions'],
                                    'inputs_on_granted': [row['inputs'] for row in accepted],
                                    'sysex_on_granted': [row['sysexEnabled'] for row in accepted]}
    duet = summaries['duet-turbulence-body-20261122-repeat']
    body_duet = {
        'layout_count': len(duet['candidate_layouts']),
        'viewports_css_px': sorted(row['width'] for row in duet['viewports']),
        'candidate_glottal_cm': [row['glottal']['s_cm'] for row in duet['candidate_selection']],
        'candidate_oral_cm': [row['oral']['s_cm'] for row in duet['candidate_selection']],
    }
    formants = summaries['tsp-stressed-vowel-formants-held-out-20261122-repeat']
    matched = formants['tokens']
    voices = ('recording', 'upstream', 'candidate')
    f2 = summaries['tsp-lpc-pre-emphasis-recordings-20261122-repeat']
    tsp = {
        'utterances': len(matched),
        'matched_vowels': sum(len(tokens) for tokens in matched.values()),
        'complete_baseline_vowels': sum(token[voice]['baseline_support'] == 3
                                       for tokens in matched.values() for token in tokens for voice in voices),
        'windows_compared_including_edges': formants['comparison']['windows'],
        'f2_sensitivity_windows': len(f2['windows']),
        'f2_sensitivity_utterances': len({row['utterance'] for row in f2['windows']}),
        'large_f2_changes': len(f2['large_change_indexes']),
        'new_missing_windows': len(f2['new_missing_indexes']),
    }
    checks = {
        'permission_responses_for_six_panels': set(permission_panels) == {'voice', 'beat', 'songbird', 'seal', 'alligator', 'elephant'}
        and all(pan['permissions'] == ['denied', 'granted', 'denied', 'granted'] and pan['inputs_on_granted'] == [0]
                and pan['sysex_on_granted'] == [False] for pan in permission_panels.values()),
        'duet_distinct_layouts_and_two_viewports': body_duet['layout_count'] == 2
        and duet['candidate_layouts'][0] != duet['candidate_layouts'][1]
        and body_duet['viewports_css_px'] == [390, 960]
        and body_duet['candidate_glottal_cm'] == [0.2, 0.2] and len(body_duet['candidate_oral_cm']) == 2,
        'tsp_formant_corpus_and_recorded_control': tsp['utterances'] == 4 and tsp['matched_vowels'] == 12
        and tsp['complete_baseline_vowels'] == formants['comparison']['token_medians'] == 36
        and tsp['windows_compared_including_edges'] == 180
        and tsp['f2_sensitivity_utterances'] == 2 and tsp['f2_sensitivity_windows'] == 6,
    }
    return {'midi_permission_panels': permission_panels, 'body_duet': body_duet, 'tsp_formants': tsp}, checks


def audit_passive_midi(run, registered):
    folder = run / 'artifacts'
    browser = read_json(folder / 'coremidi-browser.json')
    candidate = browser['targets']['candidate']
    reception = [entry for entry in candidate['received'] if entry['action'] == 'note']
    messages = candidate['disconnected']['messages']
    packets = [entry['bytes'] for entry in reception]
    report = read_json(folder / 'candidate.json')
    rate, pcm = wavfile.read(folder / 'candidate.wav')
    cli_rate, cli = wavfile.read(folder / 'candidate-cli.wav')
    note = registered['measurement']['midi_note']
    channel = registered['measurement']['midi_channel'] - 1
    hold_ms = ((int(reception[1]['arrivalUptimeNs']) - int(reception[0]['arrivalUptimeNs'])) / 1e6
               if len(reception) == 2 else 0)
    notes = report['midiNotes']
    checks = {
        'passive_midi_receive_bytes_and_provenance':
            browser['inputKind'] == 'virtual_fixture' and candidate['selectedInput']['device'] == 0
            and len(packets) == 2 and packets[0][:2] == [0x90 | channel, note] and packets[0][2] > 0
            and packets[1] == [0x90 | channel, note, 0]
            and packets == [entry['bytes'] for entry in messages] and all(entry['trusted'] for entry in messages)
            and hold_ms >= registered['measurement']['minimum_hold_ms'],
        'passive_midi_applied_note_and_pcm':
            [row['note'] for row in notes] == [note, None]
            and 0 <= notes[0]['frame'] < notes[1]['frame'] < report['outputFrames']
            and all(row['frame'] % 128 == 0 for row in notes)
            and rate == cli_rate == report['workletSampleRate'] == 48000
            and len(pcm) == len(cli) == report['outputFrames'] and pcm.dtype == cli.dtype == np.float32
            and bool(np.isfinite(pcm).all()) and pcm.tobytes() == cli.tobytes(),
    }
    return checks, {'source_kind': browser['inputKind'], 'note_bytes': packets,
                    'native_hold_ms': hold_ms, 'applied_notes': notes, 'pcm_frames': len(pcm)}


def audit_midi_aliases(scope, revision, records):
    run, before = (RUNS / scope[key] for key in ('run', 'before_run'))
    checks, result = audit_passive_midi(run, saved_definition(run, records))
    failure, _ = read_record(before.name, revision, expected_failure=True, expected_failed_checks=('capture_completed',))
    targets = [read_json(item / 'artifacts/coremidi-browser.json')['targets']['candidate'] for item in (before, run)]
    aliases = [target['inputNameAliases'] for target in targets]
    ports = [targets[0]['atError']['ports'], targets[1]['connected']['ports']]
    checks.update(
        one_open_port_for_two_names=all(
            len(set(names)) == len(names) == scope['expected_aliases'] and len(inputs) == scope['expected_ports']
            and all(port['name'] in names and port['connection'] == 'open' for port in inputs)
            for names, inputs in zip(aliases, ports, strict=True)),
        preserves_timeout_before_note=(
            not failure['errors'] and sha256(before / 'manifest.json') == scope['before_manifest_sha256']
            and f"Timeout {scope['timeout_ms']}ms exceeded" in targets[0]['error']
            and [event['action'] for event in targets[0]['received']] == ['listening']
            and not (before / 'artifacts/candidate.wav').exists()))
    return {f'midi_aliases/{name}': passed for name, passed in checks.items()}, {
        **result, 'run': run.name, 'before_run': before.name, 'names': len(aliases[1]), 'open_ports': len(ports[1]),
    }


def audit_midi_idle_input(scope, revision, records):
    run, before = (RUNS / scope[key] for key in ('run', 'before_run'))
    definition = saved_definition(run, records)
    checks, result = audit_passive_midi(run, definition)
    baseline, _ = audit_passive_midi(before, definition)
    failure, _ = read_record(before.name, revision, expected_failure=True,
                             expected_failed_checks=('page_and_subscriptions_are_clean',))
    remaining = {}
    for item in (before, run):
        row = read_json(item / 'artifacts/coremidi-browser.json')['targets']['candidate']
        connected, disconnected = row['connected'], row['disconnected']
        inputs = connected['inputPorts']
        idle = row['idleFixture']['native']
        idle_ids = [port['id'] for port in inputs if port['name'] == idle[0]['name']]
        checks[f'{item.name}/idle_input_connected_without_notes'] = (
            len(inputs) == scope['expected_ports'] and len(idle_ids) == 1
            and all(port['connection'] == 'open' for port in inputs)
            and sorted(connected['subscribedPortIds']) == sorted(port['id'] for port in inputs)
            and connected['subscriptions'] == scope['expected_ports']
            and [event['action'] for event in idle] == ['add', 'remove']
            and all(message['port']['id'] not in idle_ids for message in disconnected['messages']))
        remaining[item.name] = disconnected['subscriptions']
        checks[f'{item.name}/subscription_cleanup'] = (
            disconnected['subscribedPortIds'] == (idle_ids if item == before else [])
            and remaining[item.name] == int(item == before))
    checks['preserves_failure_after_pcm_capture'] = (
        not failure['errors'] and sha256(before / 'manifest.json') == scope['before_manifest_sha256']
        and all(baseline.values()))
    return {f'midi_idle_input/{name}': passed for name, passed in checks.items()}, {
        **result, 'run': run.name, 'before_run': before.name,
        'subscriptions_after_disconnect': remaining,
    }


def audit_midi_same_name(scope, revision, records):
    run, before = (RUNS / scope[key] for key in ('run', 'before_run'))
    checks, result = audit_passive_midi(run, saved_definition(run, records))
    failure, _ = read_record(before.name, revision, expected_failure=True, expected_failed_checks=('capture_completed',))
    old, current = (read_json(item / 'artifacts/coremidi-browser.json')['targets']['candidate']
                    for item in (before, run))
    for capture, state in ((old, 'atError'), (current, 'connected')):
        ports = capture[state]['ports']
        checks[f'{state}/same_name_distinct_open_ports'] = (
            len(ports) == len({port['id'] for port in ports}) == 2
            and str(capture['selectedInput']['uid']) in {port['id'] for port in ports}
            and all(port['name'] == capture['selectedInput']['name'] and port['connection'] == 'open' for port in ports))
    port_id = str(current['selectedInput']['uid'])
    idle_id = str(current['idleFixture']['uid'])
    checks['messages_match_the_selected_uid'] = (
        {port['id'] for port in current['connected']['ports']} == {port_id, idle_id} and port_id != idle_id
        and [message['port']['id'] for message in current['disconnected']['messages']] == [port_id, port_id]
        and read_json(run / 'summary.json')['web_midi_port_id'] == port_id)
    checks['preserves_timeout_with_two_open_ports'] = (
        not failure['errors'] and sha256(before / 'manifest.json') == scope['before_manifest_sha256']
        and f"Timeout {scope['timeout_ms']}ms exceeded" in old['error']
        and [event['action'] for event in old['received']] == ['listening']
        and not (before / 'artifacts/candidate.wav').exists())
    return {f'midi_same_name/{name}': passed for name, passed in checks.items()}, {
        **result, 'run': run.name, 'before_run': before.name,
        'web_midi_port_id': port_id, 'idle_port_id': idle_id, 'candidate_ports': len(current['connected']['ports']),
    }


def audit_listening_intake(runs, summaries):
    packet_dir = runs['csd_packet'] / 'artifacts'
    identity = read_json(packet_dir / 'listening-packet.json')
    packet_id = identity.pop('packet_id')
    definition = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    old_dir = RUNS / 'csd-listening-20261121-verified' / 'artifacts'
    key = read_json(packet_dir / 'listening-key.json')
    media = sorted((packet_dir / 'listening').glob('*.wav'))
    audio_hashes = {path.name: sha256(path) for path in media}
    fixture_summary = summaries[runs['csd_fixture'].name]
    verify_summary = summaries[runs['csd_verification'].name]
    originals = sorted((runs['csd_fixture'] / 'artifacts/responses').glob('*.csv'))
    grouped_votes = {row['split']: Counter() for row in key.values()}
    specials = {'': 'unanswered', '差なし': 'no_difference', '判定不能': 'unable_to_judge'}
    csv_matches = len(originals) == 2
    for path in originals:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = csv.DictReader(stream)
            entries = {str(int(row['trial'])).zfill(2): row for row in rows}
            csv_matches = csv_matches and rows.fieldnames == identity['columns']
        csv_matches = (csv_matches and entries.keys() <= key.keys()
                       and all(row['packet_id'] == packet_id for row in entries.values()))
        for trial, source in key.items():
            voice = entries.get(trial, {}).get('naturalness_preference', '')
            grouped_votes[source['split']][specials[voice] if voice in specials else source['labels'][voice]] += 1
    checks = {
        'csd_packet_id_from_archived_wavs_and_key':
            packet_id == hash_bytes(definition).hexdigest() and len(audio_hashes) == 18
            and audio_hashes == identity['wave_sha256']
            and identity['key_sha256'] == sha256(packet_dir / 'listening-key.json')
            == sha256(old_dir / 'listening-key.json')
            and all(sha256(old_dir / 'listening' / name) == digest for name, digest in audio_hashes.items()),
        'csd_fixture_intake_bound_to_packet_and_votes':
            csv_matches and packet_id == fixture_summary['packet_id'] == verify_summary['packet_id']
            and verify_summary['data_kind'] == 'synthetic' and fixture_summary['data_kind'] == 'response_csv'
            and fixture_summary['by_split'] == verify_summary['by_split']
            and all(votes == Counter(fixture_summary['by_split'][split]['naturalness_preference'])
                    for split, votes in grouped_votes.items()),
    }
    return checks, {'packet_id': packet_id, 'audio_files': len(media), 'fixture_csvs': len(originals)}


def audit_intake_followup(case, records, summaries):
    scope = case['intake_followup']
    runs = {name: RUNS / scope[name] for name in ('passive_midi', 'csd_packet', 'csd_verification', 'csd_fixture', 'f2_fixture')}
    checks, midi = audit_passive_midi(runs['passive_midi'], saved_definition(runs['passive_midi'], records))
    listening_checks, listening = audit_listening_intake(runs, summaries)
    checks.update(listening_checks)

    registered = case['f2_followup']
    material = RUNS / registered['annotation_material']
    f2, f2_checks = audit_annotation_material(material, runs['f2_fixture'], saved_definition(material, records), registered)
    checks.update(f2_checks)
    fixture = summaries[runs['f2_fixture'].name]
    recorded = Counter({status: 0 for status in ('measured', 'ambiguous', 'unusable')})
    for trial in fixture['trials'].values():
        if trial['reference']['kind'] == 'recording':
            recorded.update({status: trial['counts'][status] for status in recorded})
    checks['f2_recorded_fixture_counts_match'] = recorded == fixture['recording_judgments']
    f2['fixture_recording_judgments'] = dict(recorded)

    rejected = {}
    for name, expected in scope['retained_failures'].items():
        root = RUNS / name
        manifest = read_json(root / 'manifest.json')
        ok = (sha256(root / 'manifest.json') == expected['manifest_sha256']
              and manifest['upstream_revision'] == case['upstream_revision'] and manifest['status'] == 'fail')
        for entry in manifest['outputs']:
            verified_file(root, manifest, entry['path'])
        if 'failed_check' in expected:
            result = read_json(root / 'summary.json')
            reason = expected['failed_check']
            ok = (ok and result['checks'] == {reason: False} and result['evidence'] == 'unobserved'
                  and result['coremidi_inventory'] == [] and not (root / 'artifacts/candidate.wav').exists())
        else:
            reason = expected['error_contains']
            ok = (ok and reason in manifest.get('error', '')
                  and not any((root / 'artifacts' / file).exists() for file in ('responses.json', 'responses-by-source.json')))
        checks[f'archived_intake_failure/{name}'] = ok
        rejected[name] = reason
    return checks, {'passive_midi': midi, 'csd_packet': listening, 'f2_fixture': f2, 'retained_failures': rejected}


def evaluation_evidence(listening, human_f2, physical_midi, response_kind, human_returned, registered_f2_count):
    pending = {
        'tsp_recorded_f2': {'status': 'unverified', 'required_observation': 'human_f2_annotation',
                            'registered_human_annotations': registered_f2_count},
        'tsp_csd_listening': {'status': 'unverified', 'required_observation': 'human_listening_responses',
                              'registered_fixture_kind': response_kind, 'human_response_in_csd_package': human_returned},
        'physical_midi': {'status': 'unverified', 'required_observation': 'physical_source_events_and_audio',
                          'registered_source_kind': 'virtual_coremidi'},
    }
    observed = sum(entry['status'] == 'observed' for entry in listening.values())
    if observed:
        pending['tsp_csd_listening']['status'] = 'observed' if observed == len(CORPORA) else 'partial'
    if human_f2['status'] in ('partial', 'observed'):
        pending['tsp_recorded_f2'].update(status=human_f2['status'],
                                         registered_human_annotations=sum(human_f2['recording_judgments'].values()))
    if physical_midi['status'] in ('partial', 'observed'):
        pending['physical_midi'].update(status=physical_midi['status'], registered_source_kind='attached_device')
    return pending


def audit(case, out, execute, listening_runs=None, f2_annotation_run=None, physical_midi_run=None):
    revision = case['upstream_revision']
    selected = listening_runs or {}
    checks, listening = listening_observations(case, selected)
    f2_checks, human_f2 = annotation_observations(case, f2_annotation_run)
    checks.update(f2_checks)
    midi_checks, physical_midi = physical_midi_observations(case, physical_midi_run)
    checks.update(midi_checks)
    submitted = {'human_listening': listening, 'human_f2_annotations': human_f2,
                 'physical_midi_capture': physical_midi}
    if not all(checks.values()):
        return {'checks': checks, 'coverage': submitted}
    records, summaries = {}, {}
    for item in case['evidence']:
        name = item['run']
        run = RUNS / name
        manifest_path = run / 'manifest.json'
        original = read_json(manifest_path)
        summary = read_json(run / 'summary.json')
        record, hashes = read_record(name, revision, expected_failure=False)
        missing_checks = [k for k in item['checks'] if summary['checks'].get(k) is not True]
        missing_outputs = [path for path in item.get('outputs', []) if path not in hashes]
        definition = matched_case(run, original, item, record['case_inputs'])
        registered = (original.get('run_id') == name and original.get('case_id') == item['expected_case']
                      and original.get('upstream_revision') == revision and definition is not None)
        if 'manifest_sha256' in item:
            registered = registered and sha256(manifest_path) == item['manifest_sha256']
        checks[name] = registered and not (record['errors'] or missing_checks or missing_outputs)
        summaries[name] = summary
        records[name] = {'topic': item['topic'], 'case_id': original.get('case_id'), 'record_matches': registered,
                         'case_definition': definition,
                         'required_checks': item['checks'], 'missing_checks': missing_checks,
                         'missing_outputs': missing_outputs, **record}

    topic_counts = Counter(item['topic'] for name, item in records.items() if checks[name])
    checks['all_plan_topics_have_verified_runs'] = set(topic_counts) == set(case['required_topics'])
    checks['previous_audit_evidence_kept'] = keeps_previous_evidence(case, records)
    followups, followup_checks = followup_coverage(summaries)
    checks.update(followup_checks)
    raw_followups = {}
    checks['raw_followup_inputs_verified'] = all(checks[item['run']] for item in case['evidence']
                                                if 'manifest_sha256' in item)
    if checks['raw_followup_inputs_verified']:
        raw_followups, raw_checks = raw_followup_coverage(case, records)
        checks.update(raw_checks)
    f2_followup = {}
    if checks['raw_followup_inputs_verified'] and 'f2_followup' in case:
        f2_followup, f2_checks = audit_f2_followup(case, records, summaries)
        checks.update(f2_checks)
    intake_followup = {}
    if 'intake_followup' in case and all(checks.values()):
        new_checks, intake_followup = audit_intake_followup(case, records, summaries)
        checks.update(new_checks)
    renewal = {}
    if 'renewal' in case and all(checks.values()):
        new_checks, renewal = audit_renewal(case, summaries)
        checks.update(new_checks)
    songbird_followup = {}
    if 'songbird_followup' in case and checks['raw_followup_inputs_verified']:
        scope = case['songbird_followup']
        definitions = {scope[key]: saved_definition(RUNS / scope[key], records) for key in ('short_run', 'full_run')}
        new_checks, songbird_followup = audit_songbird(scope, revision, definitions)
        checks.update(new_checks)
    csd_rounding_followup = {}
    if (scope := case.get('csd_rounding_followup')) and checks['raw_followup_inputs_verified']:
        csd_rounding_followup, new_checks = audit_csd_two_phrase_rounding(scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_held_out_rounding_followup = {}
    if (scope := case.get('csd_held_out_rounding_followup')) and checks['raw_followup_inputs_verified']:
        csd_held_out_rounding_followup, new_checks = audit_csd_held_out_output_rounding(
            scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_interval_rounding = {}
    for song in ('en035a', 'en012a', 'en001a'):
        key = f'csd_{song}_rounding_followup'
        if (scope := case.get(key)) and checks['raw_followup_inputs_verified']:
            csd_interval_rounding[key], new_checks = audit_csd_interval_output_rounding(
                scope, records, summaries[scope['run']])
            checks.update(new_checks)
        elif key in case:
            csd_interval_rounding[key] = {}
    csd_first_lip_followup = {}
    if (scope := case.get('csd_first_lip_followup')) and checks['raw_followup_inputs_verified']:
        csd_first_lip_followup, new_checks = audit_csd_first_lip_load(scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_initial_oral_followup = {}
    if (scope := case.get('csd_initial_oral_followup')) and checks['raw_followup_inputs_verified']:
        csd_initial_oral_followup, new_checks = audit_csd_initial_oral_geometry(scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_centerline_swap_followup = {}
    if (scope := case.get('csd_centerline_swap_followup')) and checks['raw_followup_inputs_verified']:
        csd_centerline_swap_followup, new_checks = audit_csd_centerline_coordinate_swap(scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_pharynx_cell7_followup = {}
    if (scope := case.get('csd_pharynx_cell7_followup')) and checks['raw_followup_inputs_verified']:
        csd_pharynx_cell7_followup, new_checks = audit_csd_pharynx_cell7_source(scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_pharynx_first_block_followup = {}
    if (scope := case.get('csd_pharynx_first_block_followup')) and checks['raw_followup_inputs_verified']:
        csd_pharynx_first_block_followup, new_checks = audit_csd_pharynx_cell7_first_block(
            scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_pharynx_pulse_followup = {}
    if (scope := case.get('csd_pharynx_pulse_followup')) and checks['raw_followup_inputs_verified']:
        csd_pharynx_pulse_followup, new_checks = audit_csd_pharynx_cell7_compliance_pulse(
            scope, records, summaries[scope['run']])
        checks.update(new_checks)
    csd_pharynx_history_followup = {}
    if (scope := case.get('csd_pharynx_history_followup')) and checks['raw_followup_inputs_verified']:
        csd_pharynx_history_followup, new_checks = audit_csd_pharynx_cell7_branch_history(
            scope, records, summaries[scope['run']])
        checks.update(new_checks)
    midi_aliases = {}
    if (scope := case.get('midi_aliases_followup')) and checks['raw_followup_inputs_verified']:
        new_checks, midi_aliases = audit_midi_aliases(scope, revision, records)
        checks.update(new_checks)
    midi_idle_input = {}
    if (scope := case.get('midi_idle_input_followup')) and checks['raw_followup_inputs_verified']:
        new_checks, midi_idle_input = audit_midi_idle_input(scope, revision, records)
        checks.update(new_checks)
    midi_same_name = {}
    if (scope := case.get('midi_same_name_followup')) and checks['raw_followup_inputs_verified']:
        new_checks, midi_same_name = audit_midi_same_name(scope, revision, records)
        checks.update(new_checks)
    refuted_hypotheses = {}
    for name, summary in summaries.items():
        refuted = [key for field in ('hypotheses', 'predictions') for key, value in summary.get(field, {}).items()
                   if value is False]
        if refuted:
            refuted_hypotheses[name] = refuted

    for name, topic in [('postalveolar-affricate-20261120-repeat', 'night-wind'),
                        ('glottal-stop-20261120-repeat', 'diagnostic')]:
        path = f'artifacts/{topic}/settings.json'
        checks[f'{topic}_scope_is_archived'] = any(
            row['path'] == path for row in read_json(RUNS / name / 'manifest.json')['outputs'])
    russian, checks['russian_demo_has_all_16_syllables'] = completed_score(
        'postalveolar-affricate-20261120-repeat', 'night-wind', 16)
    mandarin, checks['mandarin_diagnostic_has_all_6_syllables'] = completed_score(
        'glottal-stop-20261120-repeat', 'diagnostic', 6)
    tsp = {k: len(v) for k, v in summaries['tsp-active-duration-original-20261121-repeat']['splits'].items()}
    held_out_phones = len(summaries['tsp-phone-boundaries-held-out-20261121-a']['pairs'])
    long_notes = {k: len(v['notes']) for k, v in summaries['csd-long-note-vibrato-20261121-theta']['songs'].items()}
    csd_windows = summaries['csd-f0-yin-threshold-20261122-repeat']['totals']['windows']
    human_returned = summaries['csd-listening-20261121-verified']['listener_returned']
    response_kind = summaries['csd-listening-responses-20261122-repeat']['data_kind']
    checks.update(tsp_calibration_and_held_out_sizes=tsp == {'calibration': 6, 'held_out': 12} and held_out_phones == 4,
                  csd_note_and_window_coverage=long_notes == {'en012a': 185, 'en035a': 109} and csd_windows == 88344,
                  listening_fixture_is_labeled=human_returned is False and response_kind == 'synthetic')
    checks['upstream_tree'] = (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() == revision
                               and not subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True))

    execute(['cargo', 'test', '--locked', '--offline', '--workspace'], stdout=out / 'candidate-cargo-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'upstream-compare-tests.log')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    midi_test_log = out / 'upstream-midi-tests.log'
    execute([*bun, 'test', str(UPSTREAM / 'tests/live-control.test.ts')], cwd=UPSTREAM, stdout=midi_test_log)
    # Bun はテスト件数を標準エラーに出す実行環境がある。
    midi_log = midi_test_log.read_text() + (out / 'cargo.log').read_text()
    passed = re.search(r'^\s*(\d+) pass\s*$', midi_log, flags=re.MULTILINE)
    failed = re.search(r'^\s*0 fail\s*$', midi_log, flags=re.MULTILINE)
    with TemporaryDirectory(dir=out.parent) as build_tmp:
        execute([*bun, 'run', 'build', '--outDir', build_tmp], cwd=WEB, stdout=out / 'candidate-web-build.log')
    test_counts = {}
    for run, file in [('candidate_workspace', 'candidate-cargo-tests.log'), ('fixed_upstream_compare', 'upstream-compare-tests.log')]:
        results = re.findall(r'test result: ok\. (\d+) passed; 0 failed', (out / file).read_text())
        test_counts[run] = sum(map(int, results))
        checks[f'{run}_tests_ran'] = test_counts[run] > 0
    test_counts['fixed_upstream_midi'] = int(passed[1]) if passed else 0
    checks['fixed_upstream_midi_tests_ran'] = test_counts['fixed_upstream_midi'] > 0 and failed is not None
    checks['current_web_build'] = True

    totals = Counter()
    for result in records.values():
        totals['recorded_passes'] += len(result['passed_checks'])
        totals['bytes'] += result['bytes']
        for disk, count in result['verified_outputs'].items():
            totals[f'outputs_{disk}'] += count
        totals['case_snapshot_entries'] += len(result['case_inputs'])
    pending = evaluation_evidence(listening, human_f2, physical_midi, response_kind, human_returned,
                                  f2_followup.get('annotation', {}).get('human_annotations_recorded_in_material'))
    return {'checks': checks, 'records': records, 'totals': totals, 'current_test_counts': test_counts,
            'verified_runs_by_topic': dict(topic_counts), 'refuted_hypotheses': refuted_hypotheses,
            'coverage': {'russian_demo': russian, 'mandarin_diagnostic': mandarin,
                         'tsp_splits': tsp, 'tsp_held_out_phone_pairs': held_out_phones,
                         'csd_songs': long_notes, 'csd_windows': csd_windows,
                         'native_midi_endpoints': midi_endpoint_counts(),
                         'listening_response_kind': response_kind, 'listening_package_human_returned': human_returned,
                         'verified_followup_observations': raw_followups,
                         'f2_followup': f2_followup, 'intake_followup': intake_followup,
                         'renewal': renewal,
                         **({'songbird_followup': songbird_followup} if 'songbird_followup' in case else {}),
                         **({'csd_rounding_followup': csd_rounding_followup} if 'csd_rounding_followup' in case else {}),
                         **({'csd_held_out_rounding_followup': csd_held_out_rounding_followup}
                            if 'csd_held_out_rounding_followup' in case else {}),
                         **csd_interval_rounding,
                         **({'csd_first_lip_followup': csd_first_lip_followup} if 'csd_first_lip_followup' in case else {}),
                         **({'csd_initial_oral_followup': csd_initial_oral_followup} if 'csd_initial_oral_followup' in case else {}),
                         **({'csd_centerline_swap_followup': csd_centerline_swap_followup}
                            if 'csd_centerline_swap_followup' in case else {}),
                         **({'csd_pharynx_cell7_followup': csd_pharynx_cell7_followup}
                            if 'csd_pharynx_cell7_followup' in case else {}),
                         **({'csd_pharynx_first_block_followup': csd_pharynx_first_block_followup}
                            if 'csd_pharynx_first_block_followup' in case else {}),
                         **({'csd_pharynx_pulse_followup': csd_pharynx_pulse_followup}
                            if 'csd_pharynx_pulse_followup' in case else {}),
                         **({'csd_pharynx_history_followup': csd_pharynx_history_followup}
                            if 'csd_pharynx_history_followup' in case else {}),
                         **({'midi_aliases_followup': midi_aliases} if 'midi_aliases_followup' in case else {}),
                         **({'midi_idle_input_followup': midi_idle_input} if 'midi_idle_input_followup' in case else {}),
                         **({'midi_same_name_followup': midi_same_name} if 'midi_same_name_followup' in case else {}),
                         **submitted,
                         'unverified_evaluation_evidence': pending,
                         **followups}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--tsp-listening-run', help='人手で取り込んだTSP試聴回答の実行ID')
    parser.add_argument('--csd-listening-run', help='人手で取り込んだCSD試聴回答の実行ID')
    parser.add_argument('--f2-annotation-run', help='人手で取り込んだTSPのF2注釈の実行ID')
    parser.add_argument('--physical-midi-run', help='接続済み機器のCoreMIDI受動計測の実行ID')
    args = parser.parse_args()
    listening = {corpus: value for corpus in CORPORA if (value := getattr(args, f'{corpus}_listening_run'))}
    identifiers = list(listening.values())
    identifiers.extend(run for run in (args.f2_annotation_run, args.physical_midi_run) if run is not None)
    if not all(RUN_ID.fullmatch(name) for name in identifiers):
        parser.error('観測の実行IDには英数字、ハイフン、アンダースコアを使用してください')
    case = read_json(CASE)
    plan = ROOT / 'docs/plans/chimera-research-rebuild-plan.md'
    inputs = [CASE, plan, Path(__file__).resolve(), WORKSPACE / 'tools/audit_plan_evidence.py',
              Path(formants.__file__), WORKSPACE / 'tools/measure_tsp_stressed_vowel_formants.py']
    inputs.extend(RUNS / case['previous']['run'] / file for file in ('manifest.json', 'summary.json'))
    inputs.extend(RUNS / item['run'] / file for item in case['evidence'] for file in ('manifest.json', 'summary.json'))
    inputs.extend((WORKSPACE / 'tools/audit_stage7_listening_runs.py',
                   WORKSPACE / 'tools/audit_stage7_f2_annotations.py',
                   WORKSPACE / 'tools/audit_stage7_physical_midi.py',
                   WORKSPACE / 'tools/measure_worklet_midi_coremidi.py',
                   WORKSPACE / 'tools/measure_worklet_midi.py',
                   WORKSPACE / 'tools/measure_worklet_songbird.py',
                   WORKSPACE / 'tools/measure_wasm_fixed.py',
                   WORKSPACE / 'tools/measure_tsp_f2_annotation.py',
                   WORKSPACE / 'tools/measure_tsp_listening.py',
                   WORKSPACE / 'tools/collect_csd_listening_responses.py', *evaluation_run_inputs(identifiers)))
    if 'f2_followup' in case:
        before = RUNS / case['f2_followup']['retained_failure']['run']
        inputs.extend(before / file for file in ('manifest.json', 'summary.json'))
        for name in ('intervening_resonance', 'intervening_excitation', 'intervening_phase',
                     'intervening_phase_midpoint', 'recording_window_shift', 'source_comparison'):
            if reference := case['f2_followup'].get(name):
                inputs.append(RUNS / reference['run'] / 'artifacts/upstream-envelopes.json')
        if contrast := case['f2_followup'].get('annotation_w06_window_shift'):
            run = RUNS / contrast['run']
            definition = read_json(WORKSPACE / 'cases/tsp-f2-annotation-w06-window-shift.json')
            recording, key_path, clip, _ = annotation_shift_assets(run, definition)
            inputs.extend((recording, key_path, clip, run / 'artifacts/upstream-envelopes.json',
                           run / 'artifacts/decimated-segment.npz'))
        if contrast := case['f2_followup'].get('annotation_w06_pre_emphasis'):
            run = RUNS / contrast['run']
            definition = read_json(w06_pre_emphasis.CASE)
            inputs.extend((w06_pre_emphasis.CASE, Path(w06_pre_emphasis.__file__),
                           *annotation_pre_emphasis_assets(definition),
                           run / 'artifacts/frame.npy', run / 'artifacts/upstream-pre-emphasis.json'))
        if contrast := case['f2_followup'].get('annotation_again_pre_emphasis'):
            run = RUNS / contrast['run']
            definition = read_json(again_pre_emphasis.CASE)
            inputs.extend((again_pre_emphasis.CASE, Path(again_pre_emphasis.__file__),
                           *again_pre_emphasis_assets(run, definition).values(), run / 'artifacts/frames.npz'))
            inputs.extend(run / 'artifacts' / f'upstream-pre-emphasis-{i:02d}.json'
                          for i in range(len(definition['measurement']['target_trials'])))
        if contrast := case['f2_followup'].get('again_f2_term_effect'):
            run = RUNS / contrast['run']
            definition = read_json(again_f2_term.CASE)
            inputs.extend((again_f2_term.CASE, Path(again_f2_term.__file__), *again_f2_term_assets(definition),
                           run / 'artifacts/native.json', run / 'artifacts/recordings.json'))
        if contrast := case['f2_followup'].get('training_reference_sensitivity'):
            run = RUNS / contrast['run']
            definition = read_json(f2_training_reference.CASE)
            source = RUNS / definition['cohort']['run']
            stopped = RUNS / contrast['compile_failure']['run']
            inputs.extend((f2_training_reference.CASE, Path(f2_training_reference.__file__),
                           source / 'artifacts/native.json', source / 'summary.json',
                           run / 'artifacts/inputs.json', run / 'artifacts/native.json',
                           stopped / 'manifest.json', stopped / 'artifacts/cargo.log',
                           stopped / 'artifacts/inputs.json'))
        if contrast := case['f2_followup'].get('training_reference_ten_speakers'):
            run = RUNS / contrast['run']
            definition = read_json(f2_ten_speakers.CASE)
            source = RUNS / definition['baseline']['run']
            inputs.extend((f2_ten_speakers.CASE, Path(f2_ten_speakers.__file__),
                           source / 'artifacts/inputs.json', source / 'summary.json',
                           WORKSPACE / 'cases' / definition['archive_case'],
                           *(run / 'artifacts' / name for name in ('inputs.json', 'native.json',
                             'collection/native.json', 'collection/recordings.json'))))
        if contrast := case['f2_followup'].get('reference_centre_width'):
            definition = read_json(f2_centre_width.CASE)
            inputs.extend((f2_centre_width.CASE, Path(f2_centre_width.__file__)))
            for run_id in (contrast['run'], *(definition[name]['run'] for name in f2_centre_width.COHORTS)):
                inputs.extend(RUNS / run_id / 'artifacts' / name for name in ('inputs.json', 'native.json'))
        if contrast := case['f2_followup'].get('reference_pooled_sexes'):
            run = RUNS / contrast['run']
            definition = read_json(f2_pooled.CASE)
            inputs.extend((f2_pooled.CASE, Path(f2_pooled.__file__), WORKSPACE / 'cases' / definition['archive_case'],
                           *(run / 'artifacts' / name for name in ('inputs.json', 'native.json',
                             'collection/native.json', 'collection/recordings.json'))))
            for key in ('centre_width', 'female_reference'):
                inputs.append(RUNS / definition[key]['run'] / 'artifacts/inputs.json')
        if contrast := case['f2_followup'].get('pooled_reference_sweep'):
            definition = read_json(f2_pooled_sweep.CASE)
            inputs.extend((f2_pooled_sweep.CASE, Path(f2_pooled_sweep.__file__), Path(f2_pooled.__file__)))
            for run_id in (contrast['run'], *(definition[key]['run'] for key in ('pooled_source', 'female_source'))):
                inputs.extend(RUNS / run_id / 'artifacts' / name for name in ('inputs.json', 'native.json'))
            inputs.append(RUNS / definition['original_interventions']['run'] / 'artifacts/inputs.json')
        if contrast := case['f2_followup'].get('pooled_reference_held_fl'):
            run = RUNS / contrast['run']
            definition = read_json(f2_held_fl.CASE)
            source = RUNS / definition['sweep']['run']
            inputs.extend((f2_held_fl.CASE, Path(f2_held_fl.__file__), WORKSPACE / 'cases' / definition['archive_case'],
                           source / 'artifacts/inputs.json', source / 'artifacts/native.json',
                           *(run / 'artifacts' / name for name in ('inputs.json', 'native.json',
                             'collection/native.json', 'collection/recordings.json'))))
        if contrast := case['f2_followup'].get('held_synth_over_sets'):
            definition = read_json(f2_over_sets.CASE)
            inputs.extend((f2_over_sets.CASE, Path(f2_over_sets.__file__)))
            for run_id in (contrast['run'], definition['fk']['run'], definition['fl']['run']):
                inputs.extend(RUNS / run_id / 'artifacts' / name for name in ('inputs.json', 'native.json'))
        if contrast := case['f2_followup'].get('full_held_women'):
            run = RUNS / contrast['run']
            definition = read_json(f2_full_held.CASE)
            source = RUNS / definition['partial']['run']
            inputs.extend((f2_full_held.CASE, Path(f2_full_held.__file__),
                           WORKSPACE / 'cases' / definition['archive_case'],
                           source / 'artifacts/inputs.json', source / 'summary.json',
                           RUNS / definition['fk_recordings']['run'] / 'artifacts/native.json',
                           RUNS / definition['fl_recordings']['run'] / 'artifacts/collection/native.json',
                           *(run / 'artifacts' / name for name in ('inputs.json', 'native.json',
                             'collection/native.json', 'collection/recordings.json'))))
        if contrast := case['f2_followup'].get('full_held_candidate'):
            run = RUNS / contrast['run']
            definition = read_json(f2_full_candidate.CASE)
            source = RUNS / definition['baseline']['run']
            matched = RUNS / definition['matched_settings']['run']
            inputs.extend((f2_full_candidate.CASE, Path(f2_full_candidate.__file__), f2_full_candidate.SENTENCES,
                           matched / definition['render_template'], matched / 'artifacts/matched-pcm.npz',
                           source / 'artifacts/inputs.json', source / 'summary.json',
                           source / 'artifacts/collection/native.json', source / 'artifacts/collection/recordings.json',
                           *(run / 'artifacts' / name for name in ('inputs.json', 'native.json', 'render-inputs.json',
                             'renders.json', 'f2-frame-index.json', 'f2-frames.npz', 'collection/native.json',
                             'collection/recordings.json'))))
        if contrast := case['f2_followup'].get('fk61_pcm_first_difference'):
            run = RUNS / contrast['run']
            definition = read_json(fk61_pcm.CASE)
            matched = RUNS / definition['matched']['run']
            uid = definition['measurement']['recording_id']
            inputs.extend((fk61_pcm.CASE, Path(fk61_pcm.__file__), matched / 'artifacts/matched-pcm.npz',
                           matched / 'artifacts' / uid / 'matched-case.json',
                           *(run / 'artifacts' / name for name in ('prefix.npz', 'coefficients.json', 'ordinary-pcm.json'))))
        if contrast := case['f2_followup'].get('fk61_lip_onset'):
            run = RUNS / contrast['run']
            definition = read_json(fk61_lip.CASE)
            previous = RUNS / definition['previous']['run']
            matched = RUNS / definition['matched']['run']
            inputs.extend((fk61_lip.CASE, Path(fk61_lip.__file__), Path(fk61_lip.observer.__file__),
                           previous / 'artifacts/prefix.npz', matched / 'artifacts/matched-pcm.npz',
                           *(run / 'artifacts' / name for name in ('columns.json', 'pcm-digests.json',
                                                                 'upstream-lip.f64le', 'candidate-lip.f64le'))))
        if contrast := case['f2_followup'].get('fk61_lip_volume_increment'):
            run = RUNS / contrast['run']
            definition = read_json(fk61_volume.CASE)
            prior = RUNS / definition['lip']['run'] / 'artifacts'
            output = RUNS / definition['output']['run'] / 'artifacts'
            matched = RUNS / definition['matched']['run'] / 'artifacts'
            uid = definition['measurement']['recording_id']
            inputs.extend((fk61_volume.CASE, Path(fk61_volume.__file__), fk61_volume.PATCH,
                           prior / 'candidate-lip.f64le', output / 'prefix.npz', output / 'coefficients.json',
                           matched / 'matched-pcm.npz', matched / uid / 'matched-case.json',
                           *(run / 'artifacts' / name for name in ('render.npz', 'lip.f64le', 'pcm-digests.json'))))
        if contrast := case['f2_followup'].get('fk61_lip_area_origin'):
            run = RUNS / contrast['run']
            definition = read_json(fk61_area.CASE)
            prior = RUNS / definition['lip']['run'] / 'artifacts'
            matched = RUNS / definition['matched']['run'] / 'artifacts'
            inputs.extend((fk61_area.CASE, Path(fk61_area.__file__), Path(fk61_area.observer.__file__),
                           fk61_area.observer.SNAPSHOT, matched / 'matched-pcm.npz',
                           *(prior / f'{name}-lip.f64le' for name in fk61_lip.MODES),
                           *(run / 'artifacts' / name for name in ('upstream.jsonl', 'candidate.jsonl',
                                                                 'grid-columns.json', 'pcm-digests.json'))))
        if contrast := case['f2_followup'].get('fk61_lip_front_origin'):
            run = RUNS / contrast['run']
            definition = read_json(fk61_front.CASE)
            previous = RUNS / definition['geometry']['run'] / 'artifacts'
            matched = RUNS / definition['matched']['run'] / 'artifacts'
            inputs.extend((fk61_front.CASE, Path(fk61_front.__file__), Path(fk61_front.observer.__file__),
                           matched / 'matched-pcm.npz',
                           *(previous / f'{name}.jsonl' for name in fk61_lip.MODES),
                           *(run / 'artifacts' / f'{name}.jsonl' for name in fk61_front.MODES),
                           run / 'artifacts/trial-pcm.npz', run / 'artifacts/pcm-digests.json'))
        if contrast := case['f2_followup'].get('fk61_centerline_length_origin'):
            run = RUNS / contrast['run']
            definition = read_json(fk61_centerline.CASE)
            geometry = RUNS / definition['geometry']['run']
            previous = geometry / 'artifacts'
            source = RUNS / read_json(fk61_front.CASE)['geometry']['run'] / 'artifacts'
            matched = RUNS / definition['matched']['run'] / 'artifacts'
            inputs.extend((fk61_centerline.CASE, Path(fk61_centerline.__file__), matched / 'matched-pcm.npz',
                           *(previous / f'{name}.jsonl' for name in fk61_lip.MODES),
                           *(source / f'{name}.jsonl' for name in fk61_lip.MODES),
                           *(run / 'artifacts' / f'{name}.jsonl' for name in fk61_centerline.MODES),
                           run / 'artifacts/trial-pcm.npz', run / 'artifacts/pcm-digests.json'))
        if contrast := case['f2_followup'].get('fk61_lip_front_radiation'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_residual.CASE)
            baselines = {name: RUNS / definition[name]['run'] / 'artifacts' for name in ('front', 'lip', 'output', 'matched')}
            uid = definition['measurement']['recording_id']
            inputs.extend((fk61_residual.CASE, Path(fk61_residual.__file__), Path(fk61_residual.observer.__file__),
                           baselines['front'] / 'trial-pcm.npz', baselines['output'] / 'prefix.npz',
                           baselines['output'] / 'coefficients.json', baselines['matched'] / 'matched-pcm.npz',
                           baselines['matched'] / uid / 'matched-case.json',
                           *(baselines['lip'] / f'{name}-lip.f64le' for name in fk61_lip.MODES),
                           *(run / f'{name}-{suffix}' for name in fk61_residual.MODES for suffix in ('lip.f64le', 'nodes.csv')),
                           *(run / name for name in ('prefix.npz', 'pcm-digests.json', 'node-columns.json'))))
        if contrast := case['f2_followup'].get('fk61_lip_front_terminal_branch'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_terminal.CASE)
            prior, output, matched = (RUNS / definition[key]['run'] / 'artifacts'
                                      for key in ('radiation', 'output', 'matched'))
            uid = definition['measurement']['recording_id']
            initial = RUNS / contrast['retained_failure']['run']
            inputs.extend((fk61_terminal.CASE, Path(fk61_terminal.__file__), Path(fk61_terminal.observer.__file__),
                           output / 'coefficients.json', matched / uid / 'matched-case.json',
                           initial / 'manifest.json', initial / 'summary.json',
                           prior / 'pcm-digests.json', run / 'pcm-digests.json',
                           *(prior / name for name in fk61_terminal.RETAINED),
                           *(run / name for name in fk61_terminal.RETAINED),
                           *(run / f'{mode}-{tag}.csv' for mode in fk61_terminal.MODES
                             for tag in fk61_terminal.observer.FIELDS)))
        if contrast := case['f2_followup'].get('fk61_node42_volume_source'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_node42.CASE)
            prior, output, matched = (RUNS / definition[key]['run'] / 'artifacts'
                                      for key in ('terminal', 'output', 'matched'))
            uid = definition['measurement']['recording_id']
            inputs.extend((fk61_node42.CASE, Path(fk61_node42.__file__), Path(fk61_node42.observer.__file__),
                           output / 'coefficients.json', matched / uid / 'matched-case.json',
                           prior / 'pcm-digests.json', run / 'pcm-digests.json',
                           *(prior / name for name in fk61_terminal.RETAINED),
                           *(run / name for name in fk61_terminal.RETAINED),
                           *(prior / f'{mode}-{tag}.csv' for mode in ('upstream', 'trial')
                             for tag in fk61_terminal.observer.FIELDS),
                           *(run / f'{mode}-{tag}.csv' for mode in fk61_node42.MODES for tag in fk61_node42.observer.FIELDS)))
        if contrast := case['f2_followup'].get('fk61_node42_area_origin'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_node42_area.CASE)
            front = RUNS / definition['front']['run'] / 'artifacts'
            volume = RUNS / definition['volume']['run']
            modes = fk61_node42_area.front.MODES
            inputs.extend((fk61_node42_area.CASE, Path(fk61_node42_area.__file__),
                           Path(fk61_node42_area.observer.__file__), Path(fk61_node42_area.area.__file__),
                           volume / 'summary.json',
                           *(volume / 'artifacts' / f'{mode}-geometry.csv' for mode in modes),
                           *(path / name for path in (run, front) for name in
                             ('pcm-digests.json', 'trial-pcm.npz', *(f'{mode}.jsonl' for mode in modes)))))
        if contrast := case['f2_followup'].get('fk61_ray43_intersection'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_ray43.CASE)
            prior = RUNS / definition['area']['run'] / 'artifacts'
            modes = fk61_ray43.front.MODES
            inputs.extend((fk61_ray43.CASE, Path(fk61_ray43.__file__), Path(fk61_ray43.observer.__file__),
                           *(path / name for path in (run, prior) for name in
                             ('pcm-digests.json', 'trial-pcm.npz', *(f'{mode}.jsonl' for mode in modes)))))
        if contrast := case['f2_followup'].get('fk61_lower_lip_bernstein_render'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_bernstein.CASE)
            intersection, volume, output, matched = (RUNS / definition[key]['run']
                                                      for key in ('intersection', 'volume', 'output', 'matched'))
            uid = definition['measurement']['recording_id']
            label = fk61_bernstein.LABEL
            before = [RUNS / failed['run'] for failed in contrast['retained_failures']]
            inputs.extend((fk61_bernstein.CASE, Path(fk61_bernstein.__file__), Path(fk61_bernstein.observer.__file__),
                           matched / 'artifacts/matched-pcm.npz', matched / 'artifacts' / uid / 'matched-case.json',
                           volume / 'summary.json', volume / 'artifacts/prefix.npz', output / 'artifacts/coefficients.json',
                           *(intersection / 'artifacts' / name for name in ('trial-pcm.npz', 'trial.jsonl', 'upstream.jsonl')),
                           *(run / name for name in ('render.npz', 'lower-lip-evaluation.patch', 'pcm-digests.json',
                              f'{label}.jsonl', f'{label}-lip.f64le', f'{label}-nodes.csv',
                              *(f'{label}-{tag}.csv' for tag in fk61_bernstein.volume.observer.FIELDS))),
                           *(initial / name for initial in before
                             for name in ('manifest.json', 'artifacts/cargo.log', 'artifacts/lower-lip-evaluation.patch',
                                          'artifacts/grid-tests.log'))))
        if contrast := case['f2_followup'].get('fk61_pcm2937_output'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_pcm2937.CASE)
            bernstein, output, volume, matched = (RUNS / definition[key]['run']
                                                  for key in ('bernstein', 'output', 'volume', 'matched'))
            uid = definition['measurement']['recording_id']
            inputs.extend((fk61_pcm2937.CASE, Path(fk61_pcm2937.__file__), Path(fk61_pcm2937.pcm.__file__),
                           matched / 'artifacts/matched-pcm.npz', matched / 'artifacts' / uid / 'matched-case.json',
                           bernstein / 'artifacts/render.npz', output / 'artifacts/coefficients.json',
                           volume / 'artifacts/prefix.npz',
                           *(run / name for name in ('upstream-prefix.npz', 'upstream-coefficients.json',
                                                      'pcm-digests.json', 'upstream-engine-test.log'))))
        if contrast := case['f2_followup'].get('fk61_pcm2937_lip_window'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_lip_window.CASE)
            measured, bernstein, output, matched = (RUNS / definition[key]['run']
                                                     for key in ('comparison', 'bernstein', 'output', 'matched'))
            uid = definition['measurement']['recording_id']
            inputs.extend((fk61_lip_window.CASE, Path(fk61_lip_window.__file__), Path(fk61_lip_window.pcm.__file__),
                           matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json', measured / 'summary.json',
                           measured / 'artifacts/upstream-prefix.npz', measured / 'artifacts/pcm-digests.json',
                           bernstein / 'artifacts/render.npz', bernstein / 'artifacts/pcm-digests.json',
                           run / 'window-scan.npz',
                           *(RUNS / failed['run'] / name for failed in contrast['retained_failures']
                             for name in ('manifest.json', 'artifacts/window-scan.npz'))))
        if contrast := case['f2_followup'].get('fk61_pcm2937_terminal_load'):
            run = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(fk61_terminal_load.CASE)
            sources = (RUNS / definition[key]['run'] / path
                       for key, paths in fk61_terminal_load.REFERENCE_FILES.items() for path in paths)
            uid = definition['measurement']['recording_id']
            matched = RUNS / definition['matched']['run']
            retained = (*fk61_terminal_load.terminal.RETAINED, 'pcm-digests.json',
                        *(f'{mode}-{tag}.csv' for mode in fk61_terminal_load.MODES
                          for tag in fk61_terminal_load.observer.FIELDS))
            inputs.extend((fk61_terminal_load.CASE, Path(fk61_terminal_load.__file__),
                           Path(fk61_terminal_load.terminal.__file__), Path(fk61_terminal_load.observer.__file__),
                           matched / 'artifacts' / uid / 'matched-case.json', *sources,
                           *(run / name for name in retained),
                           *(RUNS / failed['run'] / name for failed in contrast.get('retained_failures', ())
                             for name in ('manifest.json', *(f'artifacts/{path}' for path in retained)))))
        if contrast := case['f2_followup'].get('fk61_pcm2937_branch_drive'):
            definition = read_json(fk61_branch_drive.CASE)
            source, matched, output = (RUNS / definition[key]['run'] for key in ('terminal_load', 'matched', 'output'))
            uid = definition['measurement']['recording_id']
            earlier = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_branch_drive.CASE, Path(fk61_branch_drive.__file__),
                           matched / 'artifacts' / uid / 'matched-case.json', output / 'artifacts/coefficients.json',
                           source / 'summary.json', earlier / 'manifest.json', earlier / 'summary.json',
                           *(source / 'artifacts' / name for name in fk61_branch_drive.CAPTURE_FILES)))
        if contrast := case['f2_followup'].get('fk61_pcm2937_branch_seed'):
            definition = read_json(fk61_branch_seed.CASE)
            source, prior, matched, output = (RUNS / definition[key]['run']
                                               for key in ('terminal_load', 'branch_drive', 'matched', 'output'))
            uid = definition['measurement']['recording_id']
            earlier = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_branch_seed.CASE, Path(fk61_branch_seed.__file__),
                           matched / 'artifacts' / uid / 'matched-case.json', output / 'artifacts/coefficients.json',
                           prior / 'summary.json', earlier / 'manifest.json', earlier / 'summary.json',
                           *(source / 'artifacts' / name for name in fk61_branch_drive.CAPTURE_FILES)))
        if contrast := case['f2_followup'].get('fk61_branch_first_difference'):
            definition = read_json(fk61_branch_first.CASE)
            prior = RUNS / definition['terminal_load']['run'] / 'artifacts'
            run = RUNS / contrast['run']
            earlier = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_branch_first.CASE, Path(fk61_branch_first.__file__),
                           earlier / 'manifest.json', earlier / 'summary.json',
                           *(directory / name for directory in (prior, run / 'artifacts', earlier / 'artifacts')
                             for name in fk61_branch_first.SAVED_FILES)))
        if contrast := case['f2_followup'].get('fk61_oral_onset_inflow'):
            definition = read_json(fk61_oral_inflow.CASE)
            prior = RUNS / definition['branch_first']['run'] / 'artifacts'
            run = RUNS / contrast['run']
            earlier = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_oral_inflow.CASE, Path(fk61_oral_inflow.__file__),
                           earlier / 'manifest.json', earlier / 'summary.json',
                           *(directory / name for directory in (prior, run / 'artifacts', earlier / 'artifacts')
                             for name in fk61_oral_inflow.SAVED_FILES)))
        if contrast := case['f2_followup'].get('fk61_node40_expanded_volume'):
            definition = read_json(fk61_node40_expanded.CASE)
            matched, bernstein, prior, output = (RUNS / definition[key]['run']
                                                 for key in ('matched', 'bernstein', 'oral_inflow', 'coefficients'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            earlier = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_node40_expanded.CASE, Path(fk61_node40_expanded.__file__),
                           earlier / 'manifest.json', earlier / 'summary.json',
                           matched / 'artifacts' / uid / 'matched-case.json',
                           matched / 'artifacts/matched-pcm.npz', bernstein / 'artifacts/render.npz',
                           output / 'artifacts/coefficients.json',
                           *(prior / 'artifacts' / name for name in fk61_oral_inflow.SAVED_FILES),
                           *(directory / name for directory in (run / 'artifacts', earlier / 'artifacts')
                             for name in fk61_node40_expanded.SAVED_FILES)))
        if contrast := case['f2_followup'].get('fk61_control5632_mouth_flow'):
            definition = read_json(fk61_control5632.CASE)
            matched, output, source, previous, early = (RUNS / definition[key]['run'] for key in
                                                       ('matched', 'output', 'branch_first', 'previous_focus', 'early_expansion'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            earlier = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_control5632.CASE, Path(fk61_control5632.__file__),
                           earlier / 'manifest.json', earlier / 'summary.json',
                           earlier / 'artifacts/trajectories.npz', run / 'artifacts/trajectories.npz',
                           matched / 'artifacts' / uid / 'matched-case.json', output / 'artifacts/coefficients.json',
                           previous / 'summary.json', early / 'summary.json',
                           *(source / 'artifacts' / name for name in fk61_control5632.RETAINED)))
        if contrast := case['f2_followup'].get('fk61_control5632_upstream_drive'):
            definition = read_json(fk61_upstream_drive.CASE)
            matched, output, earlier, previous = (RUNS / definition[key]['run']
                                                   for key in ('matched', 'coefficients', 'branch_first', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_upstream_drive.CASE, Path(fk61_upstream_drive.__file__), first / 'manifest.json',
                           first / 'summary.json', first / 'artifacts/trajectories.npz',
                           run / 'artifacts/trajectories.npz',
                           matched / 'artifacts' / uid / 'matched-case.json', output / 'artifacts/coefficients.json',
                           previous / 'summary.json', *(directory / name for directory in
                               (earlier / 'artifacts', run / 'artifacts', first / 'artifacts')
                               for name in fk61_upstream_drive.SAVED_FILES)))
        if contrast := case['f2_followup'].get('fk61_control5632_oral_inlet'):
            definition = read_json(fk61_oral_inlet.CASE)
            matched, output, previous = (RUNS / definition[key]['run'] for key in
                                         ('matched', 'coefficients', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_oral_inlet.CASE, Path(fk61_oral_inlet.__file__), first / 'manifest.json',
                           first / 'summary.json', first / 'artifacts/trajectories.npz',
                           run / 'artifacts/trajectories.npz',
                           matched / 'artifacts' / uid / 'matched-case.json', output / 'artifacts/coefficients.json',
                           previous / 'summary.json', *(directory / name for directory in
                               (previous / 'artifacts', run / 'artifacts', first / 'artifacts')
                               for name in fk61_oral_inlet.SAVED_FILES)))
        if contrast := case['f2_followup'].get('fk61_control5632_oral_geometry'):
            definition = read_json(fk61_oral_geometry.CASE)
            matched, output, previous = (RUNS / definition[key]['run'] for key in
                                         ('matched', 'coefficients', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_oral_geometry.CASE, Path(fk61_oral_geometry.__file__),
                           Path(fk61_oral_geometry.observer.__file__), first / 'manifest.json', first / 'summary.json',
                           matched / 'artifacts' / uid / 'matched-case.json', output / 'artifacts/coefficients.json',
                           previous / 'summary.json', *(directory / name for directory in
                               (first / 'artifacts', run / 'artifacts') for name in fk61_oral_geometry.SAVED_FILES),
                           *(previous / 'artifacts' / name for name in fk61_oral_inlet.SAVED_FILES)))
        if contrast := case['f2_followup'].get('fk61_control5504_oral_history'):
            definition = read_json(fk61_oral_history.CASE)
            matched, output, previous = (RUNS / definition[key]['run'] for key in
                                         ('matched', 'coefficients', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_oral_history.CASE, Path(fk61_oral_history.__file__), first / 'manifest.json',
                           first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json', previous / 'summary.json',
                           *(directory / name for directory in (first / 'artifacts', run / 'artifacts')
                             for name in fk61_oral_history.SAVED_FILES),
                           *(previous / 'artifacts' / name for name in fk61_oral_history.PRIOR_FILES)))
        if contrast := case['f2_followup'].get('fk61_onset_to_control5504_volume_history'):
            definition = read_json(fk61_onset_history.CASE)
            matched, output, prior = (RUNS / definition[key]['run'] for key in
                                      ('matched', 'coefficients', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_onset_history.CASE, Path(fk61_onset_history.__file__), first / 'manifest.json',
                           first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json', prior / 'summary.json',
                           *(directory / name for directory in (first / 'artifacts', run / 'artifacts')
                             for name in fk61_onset_history.SAVED_FILES),
                           *(prior / 'artifacts' / name for name in fk61_onset_history.PRIOR_FILES)))
        if contrast := case['f2_followup'].get('fk61_control4992_5120_area_targets'):
            definition = read_json(fk61_area_targets.CASE)
            matched, output, prior = (RUNS / definition[key]['run'] for key in
                                      ('matched', 'coefficients', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_area_targets.CASE, Path(fk61_area_targets.__file__), first / 'manifest.json',
                           first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json', prior / 'summary.json',
                           *(directory / name for directory in (first / 'artifacts', run / 'artifacts')
                             for name in fk61_area_targets.SAVED_FILES),
                           *(prior / 'artifacts' / name for name in fk61_area_targets.PRIOR_FILES)))
        if contrast := case['f2_followup'].get('fk61_control4992_5120_indexed_area'):
            definition = read_json(fk61_indexed_area.CASE)
            matched, bernstein, output, prior = (RUNS / definition[key]['run'] for key in
                                                 ('matched', 'bernstein', 'coefficients', 'previous_focus'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_indexed_area.CASE, Path(fk61_indexed_area.__file__),
                           Path(fk61_indexed_area.volume.__file__), first / 'manifest.json', first / 'summary.json',
                           matched / 'artifacts' / uid / 'matched-case.json', matched / 'artifacts/matched-pcm.npz',
                           bernstein / 'artifacts/render.npz', output / 'artifacts/coefficients.json',
                           *(directory / name for directory in (first / 'artifacts', run / 'artifacts')
                             for name in fk61_indexed_area.SAVED_FILES),
                           *(prior / 'artifacts' / name for name in fk61_indexed_area.PRIOR_FILES)))
        if contrast := case['f2_followup'].get('fk61_control4992_5120_indexed_area_paired'):
            definition = read_json(fk61_paired_area.CASE)
            matched, output, research, prior = (RUNS / definition[key]['run'] for key in
                                                ('matched', 'coefficients', 'previous_focus', 'original_observation'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_paired_area.CASE, Path(fk61_paired_area.__file__), first / 'manifest.json',
                           first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           matched / 'artifacts/matched-pcm.npz', output / 'artifacts/coefficients.json',
                           *(directory / name for directory in (first / 'artifacts', run / 'artifacts')
                             for name in fk61_paired_area.SAVED_FILES),
                           *(research / name for name in fk61_paired_area.RESEARCH_FILES),
                           *(prior / name for name in (*fk61_paired_area.UPPER_FILES, 'artifacts/prefix.npz'))))
        if contrast := case['f2_followup'].get('fk61_control4992_5120_expanded_volume_paired'):
            definition = read_json(fk61_paired_volume.CASE)
            matched, output = (RUNS / definition[key]['run'] for key in ('matched', 'coefficients'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_paired_volume.CASE, Path(fk61_paired_volume.__file__), first / 'manifest.json',
                           first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json',
                           *(directory / 'artifacts' / side / name for directory in (first, run)
                             for side in fk61_paired_volume.SIDES for name in fk61_paired_volume.SAVED),
                           *(RUNS / definition[f'indexed_{side}']['run'] / 'artifacts' / name
                             for side in fk61_paired_volume.SIDES for name in fk61_paired_volume.ARCHIVED)))
        if contrast := case['f2_followup'].get('fk61_pcm16682_rounding'):
            definition = read_json(fk61_pcm16682.CASE)
            matched, output = (RUNS / definition[key]['run'] for key in ('matched', 'coefficients'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_pcm16682.CASE, Path(fk61_pcm16682.__file__), first / 'manifest.json',
                           first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json',
                           *(directory / 'artifacts' / name for directory in (first, run)
                             for name in fk61_pcm16682.SAVED_FILES),
                           *(RUNS / definition[key]['run'] / 'artifacts' / name
                             for key, names in fk61_pcm16682.ARCHIVED.items() for name in names)))
        if contrast := case['f2_followup'].get('fk61_full_pcm_rounding'):
            definition = read_json(fk61_full_pcm.CASE)
            matched, output, observed = (RUNS / definition[key]['run'] for key in
                                         ('matched', 'coefficients', 'observed_prefix'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((fk61_full_pcm.CASE, Path(fk61_full_pcm.__file__), Path(fk61_pcm16682.__file__),
                           first / 'manifest.json', first / 'summary.json', matched / 'artifacts' / uid / 'matched-case.json',
                           output / 'artifacts/coefficients.json', observed / 'artifacts/prefix.npz',
                           *(directory / 'artifacts' / name for directory in (first, run)
                             for name in fk61_full_pcm.SAVED_FILES),
                           *(RUNS / definition[key]['run'] / 'artifacts' / name
                             for key, names in fk61_pcm16682.ARCHIVED.items() for name in names)))
        for label, measurement, _ in MATCHED_PCM_ROUNDING:
            contrast = case['f2_followup'].get(f'{label}_rounding')
            if contrast is None:
                continue
            definition = read_json(measurement.CASE)
            matched, output, previous = (RUNS / definition[key]['run'] for key in
                                         ('matched', 'coefficients', 'comparison'))
            uid = definition['measurement']['recording_id']
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            inputs.extend((measurement.CASE, Path(measurement.__file__), Path(fk61_02_full_pcm.__file__),
                           Path(fk61_full_pcm.__file__),
                           Path(fk61_pcm16682.__file__), first / 'manifest.json', first / 'summary.json',
                           matched / 'artifacts' / uid / 'matched-case.json', matched / 'artifacts/matched-pcm.npz',
                           matched / 'summary.json', output / 'artifacts/coefficients.json', previous / 'summary.json',
                           *(directory / 'artifacts' / name for directory in (first, run)
                             for name in measurement.SAVED_FILES)))
        if contrast := case['f2_followup'].get('held_out_pcm_rounding'):
            definition = read_json(held_out_pcm_rounding.CASE)
            matched, output = (RUNS / definition[key]['run'] for key in ('matched', 'coefficients'))
            run = RUNS / contrast['run']
            first = RUNS / contrast['first_run']['run']
            initial = RUNS / contrast['initial_run']['run']
            inputs.extend((held_out_pcm_rounding.CASE, Path(held_out_pcm_rounding.__file__),
                           Path(fk61_02_full_pcm.__file__), Path(fk61_full_pcm.__file__), Path(fk61_pcm16682.__file__),
                           Path(mk61_02_full_pcm.__file__), initial / 'manifest.json', initial / 'summary.json',
                           first / 'manifest.json', first / 'summary.json', matched / 'artifacts/matched-pcm.npz',
                           matched / 'summary.json', output / 'artifacts/coefficients.json',
                           *(matched / 'artifacts' / row['recording_id'] / 'matched-case.json'
                             for row in definition['measurement']['cases']),
                           *(RUNS / reference['run'] / 'summary.json' for reference in definition['reproductions'].values()),
                           *(directory / 'artifacts' / name for directory in (initial, first, run)
                             for name in held_out_pcm_rounding.retained_files(definition))))
        if report := case['f2_followup'].get('candidate_report'):
            inputs.append(RUNS / report['diagnostic_run'] / 'artifacts/f2-candidates.json')
        if transfer := case['f2_followup'].get('seems_tract_transfer'):
            inputs.extend(RUNS / transfer['run'] / f'artifacts/{voice}-linear.json' for voice in ('upstream', 'candidate'))
        if spectrum := case['f2_followup'].get('seems_spectrum_stages'):
            inputs.extend(RUNS / spectrum['run'] / 'artifacts' / name for name in ('stage-spectra.npz', 'upstream-envelopes.json'))
        if drift := case['f2_followup'].get('seems_drift_only'):
            inputs.append(Path(seems_drift.__file__))
            inputs.extend(RUNS / drift['run'] / 'artifacts' / name for name in
                          ('pitch-trace.npz', 'drift-spectra.npz', 'upstream-envelopes.json'))
        if pressure := case['f2_followup'].get('seems_pressure_replay'):
            inputs.append(Path(seems_pressure.__file__))
            inputs.extend(RUNS / pressure['run'] / 'artifacts' / name for name in
                          ('pressure-traces.npz', 'drift-spectra.npz', 'upstream-envelopes.json'))
        if jitter := case['f2_followup'].get('seems_period_jitter'):
            inputs.append(Path(seems_jitter.__file__))
            inputs.extend(RUNS / jitter['run'] / 'artifacts' / name for name in
                          ('cycle-traces.npz', 'drift-spectra.npz', 'upstream-envelopes.json'))
        if shimmer := case['f2_followup'].get('seems_amplitude_shimmer'):
            inputs.append(Path(seems_shimmer.__file__))
            inputs.extend(RUNS / shimmer['run'] / 'artifacts' / name for name in
                          ('cycle-traces.npz', 'drift-spectra.npz', 'drift-windows.npz', 'upstream-envelopes.json'))
        if tip := case['f2_followup'].get('seems_initial_tip'):
            inputs.append(Path(seems_tip.__file__))
            inputs.extend(RUNS / tip['run'] / 'artifacts' / name for name in (
                'pre-roll.npz', 'lpc-windows.npz', *(f'{mode}-initial-geometry.json' for mode in seems_tip.MODES)))
        if matched := case['f2_followup'].get('matched_held_out_speech'):
            root = RUNS / matched['run'] / 'artifacts'
            inputs.extend((Path(matched_speech.__file__), root / 'matched-pcm.npz'))
            inputs.extend(root / uid / filename for uid in read_json(matched_speech.CASE)['recording_ids']
                          for filename in ('upstream-plan.json', 'matched-plan.json'))
        if matched := case['f2_followup'].get('matched_speech_formants'):
            root = RUNS / matched['run'] / 'artifacts'
            inputs.extend((Path(matched_formants.__file__), root / 'upstream-formants.json', root / 'window-comparisons.json',
                           root / 'f2-candidates.json'))
        if matched := case['f2_followup'].get('matched_speech_mfa'):
            run = RUNS / matched['run']
            definition = read_json(matched_mfa.CASE)
            inputs.extend((matched_mfa.CASE, Path(matched_mfa.__file__), Path(matched_mfa.mfa.__file__),
                           run / 'artifacts/window-comparisons.json', run / 'artifacts/synth.dict',
                           RUNS / definition['alignment']['run'] / 'artifacts/synth.dict'))
            inputs.extend(path for paths in matched_mfa_paths(definition, run).values() for path in paths)
        for key, case_path, modes in (('again_initial_tip_mfa', again_tip.CASE, again_tip.MODES),
                                      ('again_period_jitter_mfa', again_tip.JITTER_CASE, again_tip.JITTER_MODES),
                                      ('again_pitch_drift_mfa', again_tip.DRIFT_CASE, again_tip.DRIFT_MODES),
                                      ('again_amplitude_shimmer_mfa', again_tip.SHIMMER_CASE, again_tip.SHIMMER_MODES),
                                      ('again_male_period_jitter_mfa', again_tip.MALE_JITTER_CASE, again_tip.JITTER_MODES)):
            contrast = case['f2_followup'].get(key)
            if contrast is None:
                continue
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(case_path)
            uid = definition['utterance']
            prior = RUNS / definition['previous_alignment']['run'] / 'artifacts/aligned-1-synth'
            inputs.extend((case_path, Path(again_tip.__file__), prior / f'{uid}-candidate/{uid}-candidate.json',
                           root / 'upstream-formants.json', root / 'window-comparisons.json',
                           *(root / f'aligned/{uid}-{tag}/{uid}-{tag}.json' for tag in ('candidate', modes[1])),
                           *(root / f'{mode}-{suffix}' for mode in modes for suffix in ('case.json', 'clean.wav'))))
            if modes != again_tip.MODES:
                inputs.append(root / 'cycle-traces.npz')
            if modes == again_tip.DRIFT_MODES:
                inputs.extend((root / 'pitch-ratio.npz', WORKSPACE / 'tools/measure_tsp_seems_drift_only.py'))
            if (spec := definition.get('baseline_intervention')) and 'outputs' in spec:
                inputs.append(RUNS / spec['run'] / 'artifacts' / spec['outputs']['matched_case'])
        for key, case_path in (('cohort_pitch_drift_mfa', cohort_drift.CASE),
                               ('cohort_source_variation_zero_mfa', cohort_drift.VARIATION_CASE)):
            contrast = case['f2_followup'].get(key)
            if contrast is None:
                continue
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(case_path)
            inputs.extend((case_path, Path(cohort_drift.__file__), root / 'window-comparisons.json',
                           root / 'upstream-formants.json',
                           RUNS / definition['matched_alignment']['run'] / 'artifacts/window-comparisons.json'))
            inputs.extend(path for conditions in cohort_drift_alignment_paths(definition, root).values()
                          for path in conditions.values())
            inputs.extend(root / uid / f'{mode}.json' for uid in definition['utterances']
                          for mode in ('matched', cohort_drift.variant_name(definition)))
            if 'outside_window_boundary' in definition:
                inputs.append(drift_only_alignment_path(definition))
        if contrast := case['f2_followup'].get('tall_output_gain_mfa'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_gain.CASE)
            inputs.extend((tall_gain.CASE, Path(tall_gain.__file__), WORKSPACE / 'tools/measure_duet_child_output_gain.py',
                           root / 'decimated.npz', root / 'upstream-formants.json', root / 'window-comparisons.json',
                           *tall_gain_alignment_paths(definition, root).values()))
            inputs.extend(root / f'{mode}-{suffix}' for mode in tall_gain.MODES for suffix in ('clean.wav', 'case.json'))
            tag = f"{definition['utterance']}-old_gain"
            inputs.extend((root / 'corpus' / tag / f'{tag}.wav', tall_gain_prior_tape(definition)))
        if contrast := case['f2_followup'].get('tall_initial_tip_mfa'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_tip.CASE)
            inputs.extend((tall_tip.CASE, Path(tall_tip.__file__), *tall_tip_assets(definition, root).values()))
        if contrast := case['f2_followup'].get('tall_mfa_preroll'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_preroll.CASE)
            inputs.extend((tall_preroll.CASE, Path(tall_preroll.__file__), *tall_preroll_assets(definition, root).values()))
        if contrast := case['f2_followup'].get('tall_mfa_cmvn'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_cmvn.CASE)
            before = RUNS / contrast['initial_failure']['run']
            inputs.extend((tall_cmvn.CASE, Path(tall_cmvn.__file__), root / 'features.npz',
                           before / 'manifest.json', before / 'summary.json', before / 'artifacts/features.npz'))
            inputs.extend(path for assets in tall_cmvn_assets(definition, root) for path in assets.values())
        if contrast := case['f2_followup'].get('tall_mfcc_input_compression'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_mfcc.CASE)
            parent = RUNS / definition['parent']['run']
            manifest = read_json(parent / 'manifest.json')
            parent_snapshot = parent / manifest['source_snapshot'] / tall_cmvn.CASE.relative_to(ROOT)
            archives, tiers = tall_mfcc_assets(root, definition, read_json(parent_snapshot))
            inputs.extend((tall_mfcc.CASE, Path(tall_mfcc.__file__), tall_mfcc.PROBE, parent_snapshot,
                           parent / 'artifacts/features.npz', *tiers.values()))
            inputs.extend(path for files in archives.values() for path in files.values())
        if contrast := case['f2_followup'].get('tall_mfcc_final_compression'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_mfcc_final.CASE)
            parent = RUNS / definition['parent']['run']
            parent_manifest = read_json(parent / 'manifest.json')
            parent_snapshot = parent / parent_manifest['source_snapshot'] / tall_mfcc.CASE.relative_to(ROOT)
            cmvn = RUNS / read_json(parent_snapshot)['parent']['run']
            cmvn_manifest = read_json(cmvn / 'manifest.json')
            cmvn_snapshot = cmvn / cmvn_manifest['source_snapshot'] / tall_cmvn.CASE.relative_to(ROOT)
            base = tall_mfcc_final.BASELINE
            archives, tiers = tall_mfcc_assets(root, definition, read_json(cmvn_snapshot), parent_storage=base)
            inputs.extend((tall_mfcc_final.CASE, Path(tall_mfcc_final.__file__), parent_snapshot, cmvn_snapshot,
                           parent / 'artifacts' / base / 'features.npz', *tiers.values()))
            inputs.extend(path for files in archives.values() for path in files.values())
        if contrast := case['f2_followup'].get('tall_gmm_paths'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_gmm.CASE)
            failed = RUNS / contrast['initial_failure']['run']
            inputs.extend((tall_gmm.CASE, Path(tall_gmm.__file__), tall_gmm.PROBE,
                           *tall_gmm_assets(root, definition).values(), failed / 'manifest.json', failed / 'artifacts/cargo.log'))
            inputs.extend(failed / 'artifacts' / mode / 'decoder.npz' for mode in definition['measurement']['modes'])
        if contrast := case['f2_followup'].get('tall_gmm_frame_swap'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_gmm_swap.CASE)
            parent = RUNS / definition['parent']['run']
            manifest = read_json(parent / 'manifest.json')
            snapshot = parent / manifest['source_snapshot'] / tall_gmm.CASE.relative_to(ROOT)
            parent_assets = tall_gmm_assets(parent / 'artifacts', read_json(snapshot))
            inputs.extend((tall_gmm_swap.CASE, Path(tall_gmm_swap.__file__), tall_gmm_swap.PROBE,
                           snapshot, *parent_assets.values(), *tall_gmm_swap_assets(root, definition).values()))
        if contrast := case['f2_followup'].get('tall_gmm_frame_subsets'):
            root = RUNS / contrast['run'] / 'artifacts'
            definition = read_json(tall_gmm_subsets.CASE)
            stopped = RUNS / contrast['cmvn_failure']['run']
            parent = RUNS / definition['parent']['run']
            manifest = read_json(parent / 'manifest.json')
            snapshot = parent / manifest['source_snapshot'] / tall_gmm_swap.CASE.relative_to(ROOT)
            swap_definition = read_json(snapshot)
            decoder = RUNS / swap_definition['parent']['run']
            decoder_manifest = read_json(decoder / 'manifest.json')
            decoder_snapshot = decoder / decoder_manifest['source_snapshot'] / tall_gmm.CASE.relative_to(ROOT)
            inputs.extend((tall_gmm_subsets.CASE, Path(tall_gmm_subsets.__file__), snapshot, decoder_snapshot,
                           *tall_gmm_subsets_assets(root, definition).values()))
            inputs.extend(tall_gmm_assets(decoder / 'artifacts', read_json(decoder_snapshot)).values())
            inputs.extend(tall_gmm_swap_assets(parent / 'artifacts', swap_definition).values())
            inputs.extend((stopped / 'manifest.json', stopped / 'artifacts/cargo.log', stopped / 'artifacts/decoder-inputs.npz'))
        if contrast := case['f2_followup'].get('tall_f2_boundary_grid'):
            definition = read_json(tall_f2_grid.CASE)
            root = RUNS / contrast['run'] / 'artifacts'
            wave, observed = tall_f2_grid_inputs(definition)
            prior = RUNS / definition['endpoint_formants']['run'] / 'artifacts'
            inputs.extend((tall_f2_grid.CASE, Path(tall_f2_grid.__file__), wave,
                           root / 'upstream-formants.json', root / 'window-comparisons.json',
                           prior / 'upstream-formants.json'))
            inputs.extend(path for pair in observed.values() for path in pair)
        if contrast := case['f2_followup'].get('tall_recording_f2_boundary_grid'):
            definition = read_json(tall_recording_grid.CASE)
            run = RUNS / contrast['run']
            before = RUNS / contrast['initial_failure']['run']
            alignment = RUNS / definition['alignment']['run']
            manifest = read_json(before / 'manifest.json')
            inputs.extend((tall_recording_grid.CASE, Path(tall_recording_grid.__file__),
                           before / manifest['source_snapshot'] / tall_recording_grid.CASE.relative_to(ROOT)))
            inputs.extend(alignment / path for path in tall_recording_grid.recording_paths(definition['utterance']).values())
            inputs.extend(base / file for base in (run, before) for file in (
                'manifest.json', 'summary.json', 'artifacts/upstream-formants.json', 'artifacts/window-comparisons.json'))
    for name in case.get('intake_followup', {}).get('retained_failures', {}):
        root = RUNS / name
        inputs.extend(root / file for file in ('manifest.json', 'summary.json') if (root / file).is_file())
    if 'renewal' in case:
        renewal = case['renewal']
        inputs.append(WORKSPACE / 'tools/audit_stage7_renewal.py')
        inputs.extend(RUNS / name / 'manifest.json'
                      for group in ('beak_failure_runs', 'response_rejections') for name in renewal[group])
    if 'songbird_followup' in case:
        inputs.extend(songbird_inputs(case['songbird_followup']))
    if scope := case.get('csd_rounding_followup'):
        definition = read_json(csd_two_phrase_rounding.CASE)
        reference, stage, coeff = (RUNS / definition[key]['run'] for key in ('reference', 'config', 'coefficients'))
        run, first, initial = (RUNS / name for name in (scope['run'], scope['first_run']['run'], scope['initial_run']['run']))
        _, config_path = csd_two_phrase_rounding.radiation.saved_case(
            (stage, read_json(stage / 'manifest.json')), csd_two_phrase_rounding.lip.CONFIG)
        inputs.extend((csd_two_phrase_rounding.CASE, Path(csd_two_phrase_rounding.__file__),
                       Path(fk61_02_full_pcm.__file__), Path(fk61_full_pcm.__file__), Path(fk61_pcm16682.__file__),
                       Path(csd_two_phrase_rounding.pcm.__file__), config_path,
                       first / 'manifest.json', first / 'summary.json', coeff / 'artifacts/coefficients.json',
                       initial / 'manifest.json', initial / 'summary.json',
                       *(directory / 'manifest.json' for directory in (reference, stage, coeff)),
                       *csd_two_phrase_rounding.reference_paths(reference).values(),
                       *(directory / 'artifacts' / name for directory in (initial, first, run)
                         for name in csd_two_phrase_rounding.SAVED_FILES)))
    if scope := case.get('csd_first_lip_followup'):
        definition = read_json(csd_first_lip_load.CASE)
        reference = RUNS / definition['reference']['run']
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_first_lip_load.CASE, Path(csd_first_lip_load.__file__),
                       Path(csd_first_lip_load.lip.__file__), Path(csd_first_lip_load.lip.replay.__code__.co_filename),
                       first / 'manifest.json', first / 'summary.json', reference / 'manifest.json',
                       *(reference / 'artifacts' / name for name in ('output-trace.npz', 'pcm-digests.json',
                                                                    'upstream-plan.json', 'research-plan.json')),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_first_lip_load.SAVED_FILES)))
    if scope := case.get('csd_initial_oral_followup'):
        definition = read_json(csd_initial_oral.CASE)
        reference = RUNS / definition['lip_load']['run']
        run, first, initial = (RUNS / name for name in (scope['run'], scope['first_run']['run'], scope['initial_run']['run']))
        inputs.extend((csd_initial_oral.CASE, Path(csd_initial_oral.__file__), Path(csd_initial_oral.area.__file__),
                       Path(csd_initial_oral.replay_lengths.__code__.co_filename),
                       first / 'manifest.json', first / 'summary.json', reference / 'manifest.json',
                       initial / 'manifest.json',
                       *(initial / 'artifacts' / name for name in ('cargo.log', 'upstream.jsonl', 'upstream-observation.patch')),
                       *(reference / 'artifacts' / name for name in ('lip-observations.json', 'pcm-digests.json')),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_initial_oral.FILES)))
    if scope := case.get('csd_centerline_swap_followup'):
        definition = read_json(csd_centerline_swap.CASE)
        geom, lip = (RUNS / definition[key]['run'] for key in ('geometry', 'lip_load'))
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_centerline_swap.CASE, Path(csd_centerline_swap.__file__),
                       Path(csd_centerline_swap.geometry.__file__), Path(csd_centerline_swap.load.__file__),
                       first / 'manifest.json', first / 'summary.json', geom / 'manifest.json', lip / 'manifest.json',
                       lip / 'artifacts/lip-observations.json',
                       *(geom / 'artifacts' / name for name in ('upstream.jsonl', 'candidate.jsonl', 'pcm-digests.json')),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_centerline_swap.FILES)))
    if scope := case.get('csd_pharynx_cell7_followup'):
        definition = read_json(csd_pharynx_cell7.CASE)
        reference = RUNS / definition['centerline']['run']
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_pharynx_cell7.CASE, Path(csd_pharynx_cell7.__file__),
                       Path(csd_pharynx_cell7.area.__file__), Path(csd_pharynx_cell7.lip.__file__),
                       Path(csd_pharynx_cell7.prior.full.__file__), first / 'manifest.json', first / 'summary.json',
                       reference / 'manifest.json',
                       *(reference / 'artifacts' / name for name in ('observations.json', 'pcm-digests.json')),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_pharynx_cell7.FILES)))
    if scope := case.get('csd_pharynx_first_block_followup'):
        definition = read_json(csd_pharynx_block.CASE)
        reference = RUNS / definition['cell_source']['run']
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_pharynx_block.CASE, Path(csd_pharynx_block.__file__), Path(csd_pharynx_block.volume.__file__),
                       Path(csd_pharynx_block.volume.terminal.__file__),
                       *(Path(mod.__file__) for mod in (csd_pharynx_block.source, csd_pharynx_block.observe_cells,
                                                        csd_pharynx_block.observe_branches,
                                                        csd_pharynx_block.observe_volume)),
                       Path(csd_pharynx_block.volume.terminal.solve_branch.__code__.co_filename),
                       Path(csd_pharynx_block.volume.terminal.wall_values.__code__.co_filename),
                       first / 'manifest.json', first / 'summary.json', reference / 'manifest.json',
                       *(reference / 'artifacts' / name for name in ('observations.json', 'pcm-digests.json')),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_pharynx_block.FILES)))
    if scope := case.get('csd_pharynx_pulse_followup'):
        definition = read_json(csd_pharynx_pulse.CASE)
        baseline, _, _, _, paths = csd_pharynx_pulse.study_inputs(definition)
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_pharynx_pulse.CASE, *paths.values(), baseline[0] / 'manifest.json',
                       *(Path(mod.__file__) for mod in (csd_pharynx_pulse, csd_pharynx_block,
                                                        csd_pharynx_pulse.output, csd_pharynx_pulse.output.pcm,
                                                        csd_pharynx_pulse.output.full,
                                                        csd_pharynx_pulse.radiation)),
                       first / 'manifest.json', first / 'summary.json',
                       *(baseline[0] / 'artifacts' / f'{name}_{condition}-block.csv' for name in csd_pharynx_pulse.MODES
                         for condition in csd_pharynx_pulse.CONDITIONS[:2]),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_pharynx_pulse.FILES)))
    if scope := case.get('csd_held_out_rounding_followup'):
        definition = read_json(csd_held_out_rounding.CASE)
        _, paths = csd_held_out_rounding.study_inputs(definition)
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_held_out_rounding.CASE, *paths.values(),
                       *(Path(mod.__file__) for mod in (csd_held_out_rounding, csd_two_phrase_rounding,
                                                        csd_two_phrase_rounding.full, csd_two_phrase_rounding.pcm,
                                                        csd_two_phrase_rounding.matched_pcm)),
                       first / 'manifest.json', first / 'summary.json',
                       *(RUNS / acquisition['run'] / 'manifest.json' for acquisition in scope['capture_runs']),
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_held_out_rounding.SAVED_FILES)))
    for song in ('en035a', 'en012a', 'en001a'):
        scope = case.get(f'csd_{song}_rounding_followup')
        if scope is None:
            continue
        definition_path = csd_en035a_rounding.CASE.with_name(f'csd-{song}-full-pcm-rounding.json')
        definition = read_json(definition_path)
        _, paths = csd_en035a_rounding.study_inputs(definition)
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((definition_path, *paths.values(),
                       *(Path(mod.__file__) for mod in (csd_en035a_rounding, csd_held_out_rounding, csd_two_phrase_rounding,
                                                        csd_two_phrase_rounding.full, csd_two_phrase_rounding.pcm,
                                                        csd_two_phrase_rounding.matched_pcm)),
                       first / 'manifest.json', first / 'summary.json',
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_en035a_rounding.SAVED_FILES)))
    if scope := case.get('csd_pharynx_history_followup'):
        definition = read_json(csd_pharynx_history.CASE)
        _, _, paths = csd_pharynx_history.study_inputs(definition)
        run, first = (RUNS / name for name in (scope['run'], scope['first_run']['run']))
        inputs.extend((csd_pharynx_history.CASE, *paths.values(),
                       *(Path(mod.__file__) for mod in (csd_pharynx_history, csd_pharynx_pulse, csd_pharynx_block,
                                                        csd_pharynx_block.observe_branches, csd_pharynx_block.volume,
                                                        csd_pharynx_pulse.output.full)),
                       first / 'manifest.json', first / 'summary.json',
                       *(directory / 'artifacts' / name for directory in (first, run)
                         for name in csd_pharynx_history.FILES)))
    if aliases := case.get('midi_aliases_followup'):
        before = RUNS / aliases['before_run']
        after = RUNS / aliases['run'] / 'artifacts'
        inputs.extend(before / name for name in ('manifest.json', 'summary.json', 'artifacts/coremidi-browser.json'))
        inputs.extend(after / name for name in ('coremidi-browser.json', 'candidate.json', 'candidate.wav', 'candidate-cli.wav'))
    if idle := case.get('midi_idle_input_followup'):
        before = RUNS / idle['before_run']
        inputs.extend(before / name for name in ('manifest.json', 'summary.json'))
        inputs.extend(RUNS / idle[key] / 'artifacts' / name for key in ('before_run', 'run')
                      for name in ('coremidi-browser.json', 'candidate.json', 'candidate.wav', 'candidate-cli.wav'))
    if names := case.get('midi_same_name_followup'):
        before = RUNS / names['before_run']
        after = RUNS / names['run'] / 'artifacts'
        inputs.extend(before / name for name in ('manifest.json', 'summary.json', 'artifacts/coremidi-browser.json'))
        inputs.extend(after / name for name in ('coremidi-browser.json', 'candidate.json', 'candidate.wav', 'candidate-cli.wav'))
    candidate_sources = [WORKSPACE / 'Cargo.toml', WORKSPACE / 'Cargo.lock', WEB / 'package.json',
                         WEB / 'bun.lock', WEB / 'index.html', WEB / 'vite.config.ts', WEB / 'tsconfig.json',
                         ROOT / 'web/shared/audio/fft.ts', WORKSPACE / 'data/cmudict.txt.gz',
                         WORKSPACE / 'data/mandarin.txt.gz', UPSTREAM / 'tests/live-control.test.ts']
    candidate_sources.extend(sorted(WORKSPACE.glob('crates/*/Cargo.toml')))
    for source in (WORKSPACE / 'crates', WEB / 'src'):
        candidate_sources.extend(sorted(path for path in source.rglob('*')
                                        if path.is_file() and path.suffix in {'.rs', '.ts', '.tsx', '.css', '.json'}))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'listening_runs': listening, 'f2_annotation_run': args.f2_annotation_run,
               'physical_midi_run': args.physical_midi_run}
    return record_measurement(args.run_id, CASE, inputs + candidate_sources, details,
                              lambda out, execute: audit(case, out, execute, listening, args.f2_annotation_run,
                                                         args.physical_midi_run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
