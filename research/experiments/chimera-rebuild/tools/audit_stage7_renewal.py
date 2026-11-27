"""第7段階の鳴禽と試聴の追加観測を一次ファイルから照合する。"""

from collections import Counter
import csv
from hashlib import sha256 as hash_bytes
from io import StringIO
import json
import math
from struct import pack

import numpy as np
from scipy.io import wavfile

from audit_plan_evidence import RUNS, read_json
from measure_csd_envelope_timing import verified_file
from upstream_baseline import sha256


SIDES = ('candidate', 'upstream')


def csv_records(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        return reader.fieldnames, list(reader)


def identified_rows(path, columns, packet_id, key, trial_field):
    header, rows = csv_records(path)
    if header != columns:
        raise ValueError(f'{path.name} の回答列が資料と一致しません')
    entries = {}
    for row in rows:
        trial = str(int(row[trial_field])).zfill(2)
        if row['packet_id'] != packet_id or trial not in key or trial in entries:
            raise ValueError(f'{path.name} の資料IDまたは区間が一致しません')
        entries[trial] = row
    return entries


def first_delta(left, right, field):
    return next((i for i, (a, b) in enumerate(zip(left, right, strict=True))
                 if pack('d', float(a[field])) != pack('d', float(b[field]))), None)


def audit_chirps(scope, revision):
    old = RUNS / scope['chirps'] / 'artifacts'
    beak = RUNS / scope['beak'] / 'artifacts'
    setting = read_json(old / 'archived.json')['songbird_airway']
    start = setting['events'][0]['sample']
    count = setting['sample_count']
    rate = setting['sample_rate_hz']
    checks = {}
    traces = {}
    for side in SIDES:
        original_columns, original = csv_records(old / f'archived-{side}.csv')
        columns, rows = csv_records(beak / f'archived-{side}.csv')
        traces[side] = rows[start:count]
        checks[f'beak_archived_observation/{side}'] = (
            len(rows) == len(original) == count and (count - start, start, rate) == (16, 256, 192000)
            and [int(row['sample']) for row in rows] == list(range(count))
            and [{field: row[field] for field in original_columns} for row in rows] == original)
        _, quiet = csv_records(beak / f'no-tracking-{side}.csv')
        checks[f'beak_no_tracking_quiet/{side}'] = all(
            float(row[field]) == 0 for row in quiet for field in columns
            if field.startswith('beak_') and not field.endswith('_area_cm2'))
        flow = 'radiation_flow_cm3_s'
        delta = [float(row[flow]) - float(prev[flow]) for prev, row in zip(rows[start - 1:count - 1], rows[start:count])]
        scaled = [value / (1 / rate) if side == 'candidate' else value * rate for value in delta]
        checks[f'beak_radiation_derivative_from_flow/{side}'] = (
            pack('16d', *scaled) == pack('16d', *(float(row['radiation_derivative_cm3_s2']) for row in rows[start:count])))

        dt = 1 / rate
        area = float(rows[start]['beak_5_area_cm2'])
        inductance = 8 * 0.00114 / (3 * math.pi * math.sqrt(math.pi * area))
        resistance = 128 * 0.00114 * 35000 / (9 * math.pi ** 2 * area)
        old_pressure = old_inductive = peak = 0.0
        for row in rows[start:count]:
            pressure = float(row['beak_5_pressure_dyn_cm2'])
            midpoint = (old_pressure + pressure) / 2
            new_inductive = old_inductive + dt * midpoint / inductance
            expected_flow = midpoint / resistance + (old_inductive + new_inductive) / 2
            peak = max(peak, abs(expected_flow - float(row[flow])))
            old_pressure, old_inductive = pressure, new_inductive
        checks[f'beak_load_from_recorded_pressure/{side}'] = peak <= 2e-17

    offsets = {name: first_delta(*traces.values(), field) for name, field in (
        ('inlet_flow', 'beak_0_inflow_cm3_s'), ('tip_pressure', 'beak_5_pressure_dyn_cm2'),
        ('radiated_flow', 'radiation_flow_cm3_s'), ('tip_inflow', 'beak_5_inflow_cm3_s'))}
    checks['beak_first_differences_from_raw'] = offsets == {
        'inlet_flow': 4, 'tip_pressure': 6, 'radiated_flow': 8, 'tip_inflow': 9}

    for name, digest in scope['beak_failure_runs'].items():
        run = RUNS / name
        manifest = read_json(run / 'manifest.json')
        ok = (sha256(run / 'manifest.json') == digest and manifest['status'] == 'fail'
              and manifest['upstream_revision'] == revision and 'not JSON serializable' in manifest['error']
              and not (run / 'summary.json').exists())
        for entry in manifest['outputs']:
            verified_file(run, manifest, entry['path'])
        traces_match = all(sha256(run / f'artifacts/{variant}-{side}.csv') == sha256(beak / f'{variant}-{side}.csv')
                           for variant in ('archived', 'no-tracking') for side in SIDES)
        checks[f'preserved_beak_failure/{name}'] = ok and traces_match
    return checks, {'first_differences': offsets, 'samples': count - start}


def audit_tsp_listening(scope, summaries):
    material = RUNS / scope['tsp_material'] / 'artifacts'
    fixture = RUNS / scope['tsp_fixture'] / 'artifacts'
    definition = read_json(material / 'reference.json')
    packet_id = definition.pop('packet_id')
    key = definition['pairs']
    columns = ['packet_id', 'pair', 'tempo', 'pauses', 'observations']
    clips = Counter()
    same_waves = True
    for pair, item in key.items():
        for letter in 'AB':
            path = material / 'listening' / f'{pair}-{letter}.wav'
            rate, pcm = wavfile.read(path)
            clip = item['clips'][letter]
            same_waves = (same_waves and rate == 48000 and pcm.dtype == np.float32
                          and pcm.shape == (clip['frames'],) and sha256(path) == clip['sha256'])
            clips[item['split']] += 1
    rows = {name: identified_rows(fixture / 'responses' / f'{name}.csv', columns, packet_id, key, 'pair')
            for name in ('browser', 'manual')}
    summary = count_tsp_rows(rows.values(), key)
    prepared = summaries[scope['tsp_material']]
    collected = summaries[scope['tsp_fixture']]
    checks = {
        'tsp_listening_packet_from_wave_and_metadata': same_waves and clips == {'calibration': 12, 'held_out': 24}
        and packet_id == hash_bytes(json.dumps(definition, sort_keys=True).encode('utf-8')).hexdigest()
        and definition['licence_sha256'] == sha256(material / 'listening/TSP-licence.txt'),
        'tsp_csv_responses_remain_trial_fixtures': packet_id == prepared['packet_id'] == collected['packet_id']
        and prepared['human_responses'] == 0 and collected['data_kind'] == 'synthetic' and collected['by_split'] == summary,
    }
    return checks, {'packet_id': packet_id, 'audio_files': sum(clips.values()), 'test_responses': len(rows),
                    'recorded_human_responses': prepared['human_responses'], 'by_split': summary}


def count_tsp_rows(rows, key):
    choices = ('candidate', 'recording', 'same', 'unsure', 'unanswered')
    summary = {item['split']: {'rows': [0, 0, 0], 'tempo': dict.fromkeys(choices, 0), 'pauses': dict.fromkeys(choices, 0)}
               for item in key.values()}
    for response in rows:
        for pair, item in key.items():
            source = response.get(pair, {})
            group = summary[item['split']]
            group['rows'][0] += 1
            group['rows'][1] += pair in response
            group['rows'][2] += any(source.get(field, '').strip() for field in ('tempo', 'pauses', 'observations'))
            for dimension in ('tempo', 'pauses'):
                answer = source.get(dimension, '')
                group[dimension][item.get(answer, answer or 'unanswered')] += 1
    return summary


def count_csd_rows(responses, key):
    labels = ('recording', 'upstream', 'candidate')
    pitch_choices = ('0', '1', '2', '3', 'unable_to_judge', 'unanswered')
    special = {'': 'unanswered', '判定不能': 'unable_to_judge', '差なし': 'no_difference'}
    summary = {item['split']: {'expected_rows': 0, 'received_rows': 0, 'answered_rows': 0,
                              'periodic_pitch': {label: dict.fromkeys(pitch_choices, 0) for label in labels},
                              'naturalness_preference': dict.fromkeys((*labels, *special.values()), 0)}
               for item in key.values()}
    for rows in responses:
        for trial, item in key.items():
            row = rows.get(trial, {})
            group = summary[item['split']]
            group['expected_rows'] += 1
            group['received_rows'] += trial in rows
            read_fields = ('a_periodic_pitch', 'b_periodic_pitch', 'c_periodic_pitch',
                           'naturalness_preference', 'observations')
            scores = [row.get(field, '').strip() for field in read_fields]
            group['answered_rows'] += any(scores)
            for letter, score in zip('ABC', scores[:3], strict=True):
                group['periodic_pitch'][item['labels'][letter]][special.get(score, score)] += 1
            vote = scores[3]
            group['naturalness_preference'][item['labels'].get(vote, special.get(vote))] += 1
    return summary


def audit_csd_responses(scope, packet_run, revision, summaries):
    material = RUNS / packet_run / 'artifacts'
    reference = RUNS / scope['csd_verify'] / 'artifacts'
    fixture = RUNS / scope['csd_fixture'] / 'artifacts'
    identity = read_json(material / 'listening-packet.json')
    key = read_json(material / 'listening-key.json')
    packet_id = identity['packet_id']
    response_manifest = read_json(fixture.parent / 'manifest.json')
    same_files = set(response_manifest['response_files']) == {'fixture-browser', 'fixture-manual'}
    responses = []
    for name in ('browser', 'manual'):
        path = fixture / 'responses' / f'fixture-{name}.csv'
        original = (reference / f'{name}-fixture.csv').read_bytes()
        same_files = (same_files and path.read_bytes() == original
                      and response_manifest['response_files'][f'fixture-{name}'] == file_fingerprint(original))
        responses.append(identified_rows(path, identity['columns'], packet_id, key, 'trial'))
    summary = count_csd_rows(responses, key)
    checks = {'csd_fixture_input_hashes_and_all_ratings': same_files and all(
        summaries[scope[run]]['data_kind'] == 'synthetic' and summaries[scope[run]]['packet_id'] == packet_id
        and summaries[scope[run]]['by_split'] == summary for run in ('csd_verify', 'csd_fixture'))}

    zero = StringIO(newline='')
    writer = csv.writer(zero)
    writer.writerow(identity['columns'])
    writer.writerow((packet_id, '06', '0', '', '', '', ''))
    original = {'control': zero.getvalue().encode('utf-8'),
                'browser-fixture.csv': (reference / 'browser-fixture.csv').read_bytes(),
                'observations.csv': (material / 'listening/observations.csv').read_bytes()}
    for name, expected in scope['response_rejections'].items():
        run = RUNS / name
        manifest = read_json(run / 'manifest.json')
        valid = (sha256(run / 'manifest.json') == expected['manifest_sha256'] and manifest['status'] == 'fail'
                 and manifest['upstream_revision'] == revision and manifest['data_kind'] == 'human'
                 and expected['error_contains'] in manifest['error'] and not manifest['outputs']
                 and not (run / 'summary.json').exists() and not (run / 'artifacts/responses').exists())
        if 'responses' in expected:
            valid = valid and manifest['response_files'] == {
                label: file_fingerprint(original[source]) for label, source in expected['responses'].items()}
        checks[f'preserved_listening_rejection/{name}'] = valid
    return checks, {'packet_id': packet_id, 'test_responses': len(response_manifest['response_files']),
                    'by_split': summary, 'recorded_rejections': len(scope['response_rejections'])}


def file_fingerprint(data):
    return {'bytes': len(data), 'sha256': hash_bytes(data).hexdigest()}


def audit_renewal(case, summaries):
    scope = case['renewal']
    revision = case['upstream_revision']
    chirp_checks, chirps = audit_chirps(scope, revision)
    tsp_checks, tsp = audit_tsp_listening(scope, summaries)
    csd_checks, csd = audit_csd_responses(scope, case['intake_followup']['csd_packet'], revision, summaries)
    return chirp_checks | tsp_checks | csd_checks, {'chirps': chirps, 'tsp_listening': tsp, 'csd_listening': csd}
