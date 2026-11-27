"""試聴の集計実行を、試聴資料と元CSVの記録に照合する。"""

import csv
from pathlib import Path
import re

from audit_plan_evidence import ROOT, RUNS, read_json, read_record
from audit_stage7_renewal import count_csd_rows, count_tsp_rows, file_fingerprint, identified_rows
from measure_csd_envelope_timing import verified_file
import collect_csd_listening_responses as csd
import measure_tsp_listening as tsp
from upstream_baseline import sha256


CORPORA = ('tsp', 'csd')
RUN_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')


def response_tallies(corpus, definition, key, paths):
    columns = list(tsp.COLUMNS) if corpus == 'tsp' else definition['columns']
    trial = 'pair' if corpus == 'tsp' else 'trial'
    rows = [identified_rows(path, columns, definition['packet_id'], key, trial) for path in paths.values()]
    counter = count_tsp_rows if corpus == 'tsp' else count_csd_rows
    return counter(rows, key)


def check_material(case, corpus, collected):
    tsp_material = corpus == 'tsp'
    package_id = collected['packet_run' if tsp_material else 'listening_run']
    if not RUN_ID.fullmatch(package_id):
        raise ValueError('試聴資料の実行IDが不正です')
    run = RUNS / package_id
    manifest_path = run / 'manifest.json'
    manifest = read_json(manifest_path)
    path = str(manifest_path.relative_to(ROOT))
    inherited = [entry['sha256'] for entry in collected['inputs'] if entry['path'] == path]
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != case['upstream_revision']
            or inherited != [sha256(manifest_path)]):
        raise ValueError('取り込み時に保存した試聴資料のマニフェストと一致しません')
    name = 'reference.json' if tsp_material else 'listening-packet.json'
    expected_run = case['renewal']['tsp_material'] if tsp_material else case['intake_followup']['csd_packet']
    canonical = RUNS / expected_run / 'artifacts'
    descriptor = verified_file(run, manifest, f'artifacts/{name}')
    if descriptor.read_bytes() != (canonical / name).read_bytes():
        raise ValueError('第7段階で照合した試聴資料と一致しません')
    definition = read_json(descriptor)
    if tsp_material:
        key = definition['pairs']
        waves = {f'{pair}-{letter}.wav': clip['sha256'] for pair, item in key.items()
                 for letter, clip in item['clips'].items()}
        licence = verified_file(run, manifest, 'artifacts/listening/TSP-licence.txt')
        if sha256(licence) != definition['licence_sha256']:
            raise ValueError('試聴資料の利用条件が一致しません')
    else:
        source_key = verified_file(run, manifest, 'artifacts/listening-key.json')
        if sha256(source_key) != definition['key_sha256']:
            raise ValueError('試聴資料の音源対応が一致しません')
        key = read_json(source_key)
        waves = definition['wave_sha256']
    locations = {Path(row['path']).name: row for row in manifest['outputs'] if row['path'].endswith('.wav')}
    for file, digest in waves.items():
        entry = locations.get(file, {})
        if entry.get('path') != f'artifacts/listening/{file}' or entry.get('sha256') != digest:
            raise ValueError('資料IDに対応するWAVが実行記録と一致しません')
        verified_file(run, manifest, entry['path'])
    return definition, key


def validate_observations(corpus, definition, key, blobs, fixtures):
    if corpus == 'tsp':
        parsed = {name: tsp.parse(data, definition) for name, data in blobs.items()}
        reference = [tsp.answered_observations(tsp.parse(data, definition)) for data in fixtures]
        for response in parsed.values():
            answered = tsp.answered_observations(response)
            if not answered or answered in reference:
                raise ValueError('TSPの空欄、または既知の試験回答が含まれています')
        return {'data_kind': 'human', 'packet_id': definition['packet_id'], 'responses': parsed}

    columns, scores, packet_id = (definition[field] for field in ('columns', 'scores', 'packet_id'))
    reference = {csd.observation_signature(csd.read_response(data, 'fixture', key, columns, scores, packet_id))
                 for data in fixtures}
    normalized = []
    for name, data in blobs.items():
        response = csd.read_response(data, name, key, columns, scores, packet_id)
        reason = csd.human_intake_error(csd.observation_signature(response), reference)
        if reason:
            raise ValueError(reason)
        normalized.extend(csd.normalize_response(response, name, key))
    return normalized


def verify_listening_run(case, corpus, run_id):
    run = RUNS / run_id
    manifest = read_json(run / 'manifest.json')
    mode = 'action' if corpus == 'tsp' else 'mode'
    if (manifest.get('data_kind') != 'human' or manifest.get(mode) != 'collect'
            or manifest.get('case_id') != f'{corpus}-listening-responses'):
        raise ValueError('人手区分で取り込んだ試聴回答の実行を指定してください')
    record, _ = read_record(run_id, case['upstream_revision'], expected_failure=False)
    if record['errors'] or manifest['run_id'] != run_id:
        raise ValueError('試聴回答の実行記録が一致しません')
    definition, key = check_material(case, corpus, manifest)
    summary = read_json(verified_file(run, manifest, 'summary.json'))
    response_ids = summary['response_ids']
    if (summary['data_kind'] != 'human' or summary['packet_id'] != definition['packet_id']
            or not response_ids or len(set(response_ids)) != len(response_ids)
            or not all(RUN_ID.fullmatch(name) for name in response_ids)
            or set(response_ids) != set(manifest['response_files'])):
        raise ValueError('資料IDと匿名の回答IDを実行記録に照合できません')
    paths = {name: verified_file(run, manifest, f'artifacts/responses/{name}.csv') for name in response_ids}
    blobs = {name: path.read_bytes() for name, path in paths.items()}
    if manifest['response_files'] != {name: file_fingerprint(data) for name, data in blobs.items()}:
        raise ValueError('元CSVが取り込み時のサイズまたはSHA-256と一致しません')
    reference = (case['renewal']['tsp_material'] if corpus == 'tsp' else case['renewal']['csd_verify'])
    fixtures = RUNS / reference
    fixture_manifest = read_json(fixtures / 'manifest.json')
    controls = [verified_file(fixtures, fixture_manifest, f'artifacts/{kind}-fixture.csv').read_bytes()
                for kind in ('browser', 'manual')]
    normalized = validate_observations(corpus, definition, key, blobs, controls)
    recount = response_tallies(corpus, definition, key, paths)
    if (normalized != read_json(verified_file(run, manifest, 'artifacts/responses-by-source.json'))
            or recount != summary['by_split']):
        raise ValueError('元CSVから再計算した観測または集計が一致しません')
    return {'status': 'observed', 'run': run_id, 'packet_id': summary['packet_id'],
            'response_csvs': len(paths), 'by_split': recount}


def listening_observations(case, selected):
    coverage = {}
    checks = {}
    for corpus in CORPORA:
        if corpus not in selected:
            coverage[corpus] = {'status': 'unregistered'}
            continue
        run_id = selected[corpus]
        try:
            coverage[corpus] = verify_listening_run(case, corpus, run_id)
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
            coverage[corpus] = {'status': 'rejected', 'run': run_id, 'reason': str(error)}
        checks[f'{corpus}_submitted_listening_observations'] = coverage[corpus]['status'] == 'observed'
    return checks, coverage


def evaluation_run_inputs(names):
    inputs = []
    for name in names:
        run = RUNS / name
        manifest_path = run / 'manifest.json'
        if not manifest_path.is_file():
            continue
        inputs.append(manifest_path)
        try:
            manifest = read_json(manifest_path)
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, dict):
            continue
        package = manifest.get('packet_run', manifest.get('listening_run'))
        if isinstance(package, str) and RUN_ID.fullmatch(package):
            material = RUNS / package / 'manifest.json'
            if material.is_file():
                inputs.append(material)
    return inputs
