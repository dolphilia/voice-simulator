"""F2の人手注釈を、元の観測窓とLPCの採択に照合する。"""

import csv
from hashlib import sha256 as hash_bytes
import json
from pathlib import Path
from statistics import median

from audit_plan_evidence import ROOT, RUNS, read_json, read_record
from audit_stage7_listening_runs import RUN_ID
from audit_stage7_renewal import file_fingerprint
from measure_csd_envelope_timing import verified_file
from upstream_baseline import sha256


def material_reference(case, collected):
    packet_id = collected['packet_run']
    if not RUN_ID.fullmatch(packet_id):
        raise ValueError('注釈資料の実行IDが不正です')
    packet = RUNS / packet_id
    manifest_path = packet / 'manifest.json'
    manifest = read_json(manifest_path)
    upstream = case['upstream_revision']
    recorded = [entry['sha256'] for entry in collected['inputs']
                if entry['path'] == str(manifest_path.relative_to(ROOT))]
    if (manifest['status'], manifest['action'], manifest['upstream_revision'], recorded) != (
        'pass', 'prepare', upstream, [sha256(manifest_path)]
    ):
        raise ValueError('取り込み時の注釈資料のマニフェストと一致しません')
    canonical = RUNS / case['f2_followup']['annotation_material']
    canonical_manifest = read_json(canonical / 'manifest.json')
    configs = [entry for entry in canonical_manifest['inputs'] if Path(entry['path']).name == 'tsp-f2-annotation.json']
    if len(configs) != 1:
        raise ValueError('注釈資料のケース定義を一意に確認できません')
    config_path = canonical / canonical_manifest['source_snapshot'] / configs[0]['path']
    if sha256(config_path) != configs[0]['sha256']:
        raise ValueError('注釈資料のケース定義を照合できません')
    config = read_json(config_path)
    reference = verified_file(packet, manifest, 'artifacts/reference.json')
    canonical_ref = verified_file(canonical, canonical_manifest, 'artifacts/reference.json')
    if reference.read_bytes() != canonical_ref.read_bytes():
        raise ValueError('監査に登録した実録音の注釈資料と一致しません')
    key = read_json(reference)
    if key['packet_id'] != hash_bytes(json.dumps(key['trials'], sort_keys=True).encode()).hexdigest():
        raise ValueError('資料IDを窓の情報から再計算できません')
    for window, info in key['trials'].items():
        for extension, field in (('wav', 'wave_sha256'), ('png', 'plot_sha256')):
            asset = verified_file(packet, manifest, f'artifacts/review/{window}.{extension}')
            if sha256(asset) != info[field]:
                raise ValueError(f'注釈資料の音声または図が一致しません ({window})')
    fixtures = [verified_file(packet, manifest, f'artifacts/{name}-fixture.csv').read_bytes()
                for name in ('browser', 'second')]
    return config, key, fixtures


def lpc_for_recorded_windows(config, key):
    source = config['windows']
    run = RUNS / source['run']
    manifest_path = run / 'manifest.json'
    manifest = read_json(manifest_path)
    if (sha256(manifest_path), manifest['status'], manifest['upstream_revision']) != (
        source['manifest_sha256'], 'pass', config['upstream_revision']
    ):
        raise ValueError('原資料のLPC実行を確認できません')
    rows = read_json(verified_file(run, manifest, 'summary.json'))['windows']
    source_windows = {(row['utterance'], row['start_sample'], row['frame_samples']): row for row in rows}
    estimates = {}
    for trial, info in key['trials'].items():
        if info['kind'] != 'recording':
            continue
        lo, hi = info['analysis_samples']
        row = source_windows.get((info['utterance'], lo, hi - lo))
        if (row is None or row['word'] != info['word'] or row['center'] != info['center']
                or row['interval_seconds'] != info['phone_seconds']
                or hi - lo != config['analysis_window_samples']):
            raise ValueError(f'録音に付けた注釈窓とLPCの計測窓が一致しません ({trial})')
        variants = row['variants']
        if [variant['pre_emphasis_option'] for variant in variants] != [None, 0.0]:
            raise ValueError('原資料のLPC設定が登録済みの条件と一致しません')
        frequencies = [(selection[0] if selection else None)
                       for selection in (variant['fixed_selection']['f2'] for variant in variants)]
        if frequencies != info['held_out_lpc_f2_hz']:
            raise ValueError(f'資料に記録したLPCの採択と一致しません ({trial})')
        estimates[trial] = dict(zip(('upstream_default', 'no_pre_emphasis'), frequencies, strict=True))
    if len(estimates) != config['recording_windows']:
        raise ValueError('実録音の注釈窓数が登録済みの条件と一致しません')
    return estimates


def recount_annotations(config, key, parsed, estimates):
    statuses = ('measured', 'ambiguous', 'unusable', 'unanswered')
    recorded = dict.fromkeys(statuses[:-1], 0)
    collected_trials, paired = {}, {}
    control_annotations = 0
    for trial, reference in key['trials'].items():
        counts = dict.fromkeys(statuses, 0)
        frequencies = []
        for response in parsed.values():
            row = response.get(trial, {'status': 'unanswered'})
            counts[row['status']] += 1
            if row['status'] == 'measured':
                frequencies.append(row['f2_hz'])
        midpoint = median(frequencies) if frequencies else None
        spread = max(frequencies) - min(frequencies) if len(frequencies) >= 2 else None
        agrees = spread <= config['rater_agreement_hz'] if spread is not None else None
        collected_trials[trial] = {'counts': counts, 'median_hz': midpoint, 'range_hz': spread,
                                   'within_rater_agreement': agrees, 'reference': reference}
        if trial not in estimates:
            control_annotations += len(parsed) - counts['unanswered']
            continue
        for status in recorded:
            recorded[status] += counts[status]
        comparison = ('unmeasured' if midpoint is None else 'single_measurement' if agrees is None
                      else 'agreement' if agrees else 'disagreement')
        comparable = midpoint is not None and agrees is not False
        paired[trial] = {'utterance': reference['utterance'], 'word': reference['word'],
                         'analysis_samples': reference['analysis_samples'], 'judgments': counts,
                         'median_hz': midpoint, 'range_hz': spread, 'comparison': comparison,
                         'lpc_hz': estimates[trial],
                         'lpc_minus_annotation_hz': {method: freq - midpoint
                                                    if comparable and freq is not None else None
                                                    for method, freq in estimates[trial].items()}}
    observed = sum(row['judgments']['unanswered'] < len(parsed) for row in paired.values())
    coverage = {'recording_windows': len(estimates), 'annotated_recording_windows': observed,
                'recording_judgments': recorded, 'control_annotations': control_annotations,
                'comparable_recording_windows': sum(any(value is not None for value in row['lpc_minus_annotation_hz'].values())
                                                    for row in paired.values()),
                'windows': paired}
    return collected_trials, coverage


def verify_annotation_run(case, run_id):
    run = RUNS / run_id
    manifest = read_json(run / 'manifest.json')
    if (manifest.get('case_id'), manifest.get('action'), manifest.get('data_kind')) != (
        'tsp-f2-annotation', 'collect', 'human'
    ):
        raise ValueError('人手区分で取り込んだF2注釈の実行を指定してください')
    record, outputs = read_record(run_id, case['upstream_revision'], expected_failure=False)
    if record['errors'] or manifest['run_id'] != run_id:
        raise ValueError('F2注釈の実行記録が一致しません')
    config, key, fixtures = material_reference(case, manifest)
    summary = read_json(verified_file(run, manifest, 'summary.json'))
    if (summary['packet_id'], summary['data_kind'], manifest['packet_id']) != (key['packet_id'], 'human', key['packet_id']):
        raise ValueError('注釈の資料IDまたは登録区分が一致しません')
    normalized = read_json(verified_file(run, manifest, 'artifacts/responses.json'))
    names = {Path(path).stem for path in outputs if Path(path).parent == Path('artifacts/responses')}
    if not names or names != normalized.keys() or not all(RUN_ID.fullmatch(name) for name in names):
        raise ValueError('元CSVと匿名の判定者IDが一致しません')
    blobs = {name: verified_file(run, manifest, f'artifacts/responses/{name}.csv').read_bytes() for name in sorted(names)}
    if 'response_files' in manifest and manifest['response_files'] != {
        name: file_fingerprint(data) for name, data in blobs.items()
    }:
        raise ValueError('元CSVが取り込み時のサイズまたはSHA-256と一致しません')

    # 試聴だけの監査では、図の作成に使うMatplotlibを読み込まない。
    from measure_tsp_f2_annotation import parse_response, validate_human_responses

    limits = config['f2_range_hz']
    parsed = {name: parse_response(data, key, limits) for name, data in blobs.items()}
    validate_human_responses(parsed, [parse_response(data, key, limits) for data in fixtures])
    counted, coverage = recount_annotations(config, key, parsed, lpc_for_recorded_windows(config, key))
    if (parsed != normalized or counted != summary['trials'] or len(names) != summary['rater_count']
            or coverage['recording_judgments'] != summary['recording_judgments']):
        raise ValueError('元CSVから再計算した注釈または集計が一致しません')
    annotated = coverage['annotated_recording_windows']
    status = 'observed' if annotated == coverage['recording_windows'] else 'partial' if annotated else 'unregistered'
    return {'status': status, 'run': run_id, 'packet_id': key['packet_id'], 'response_csvs': len(blobs), **coverage}


def annotation_observations(case, selected):
    if selected is None:
        return {}, {'status': 'unregistered'}
    try:
        coverage = verify_annotation_run(case, selected)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        return {'submitted_f2_annotations': False}, {'status': 'rejected', 'run': selected, 'reason': str(error)}
    return {'submitted_f2_annotations': True}, coverage
