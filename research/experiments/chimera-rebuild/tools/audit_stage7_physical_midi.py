"""既存CoreMIDI入力の採取元とデジタルPCMを保存した記録から照合する。"""

import math
import re

from audit_plan_evidence import ROOT, RUNS, read_json, read_record
from measure_worklet_midi_coremidi import CASE, FIXED, LIVE, PASSIVE, passive_checks
from upstream_baseline import sha256


CAPTURE_OUTPUTS = {'summary.json', 'artifacts/coremidi-browser.json', 'artifacts/candidate.json',
                   'artifacts/candidate-case.json', 'artifacts/candidate.wav', 'artifacts/candidate-cli.wav'}


def capture_case(run, manifest, passive_digest):
    paths = [str(path.relative_to(ROOT)) for path in (CASE, PASSIVE, LIVE, FIXED)]
    base, passive, live, fixed = (run / manifest['source_snapshot'] / path for path in paths)
    if sha256(passive) != passive_digest:
        raise ValueError('受動計測のケースが第7段階の登録条件と異なります')
    definition = read_json(base)
    variant = read_json(passive)
    definition.update(variant, measurement=definition['measurement'] | variant['measurement'])
    return definition, live, fixed


def recalculate(browser, definition, artifacts, live, fixed):
    result = passive_checks(browser, definition, artifacts, None, live_case=live, fixed_case=fixed)
    candidate = browser['targets']['candidate']
    notes = [row for row in candidate['received'] if row['action'] == 'note']
    messages = [row for row in candidate['disconnected']['messages']
                if len(row['bytes']) == 3 and row['bytes'][0] & 0xf0 in (0x80, 0x90)]
    browser_hold_ms = None
    if len(notes) == len(messages) == 2:
        browser_hold_ms = messages[1]['eventMs'] - messages[0]['eventMs']
    result['checks']['browser_hold_in_registered_window'] = (
        browser_hold_ms is not None and math.isfinite(browser_hold_ms)
        and browser_hold_ms >= definition['measurement']['minimum_hold_ms'])
    return result, browser_hold_ms


def attached_input(browser, uid):
    if browser['inputKind'] != 'attached_device' or not re.fullmatch(r'-?\d+', uid or ''):
        raise ValueError('接続済み機器をUIDで指定した受動計測の実行を使用してください')
    if 'missingInput' in browser:
        raise ValueError('指定された入力が収録時に見つかりませんでした')
    row = browser['targets']['candidate']
    selected = row['selectedInput']
    matches = [entry for entry in browser['inventory'] if str(entry['uid']) == uid]
    if (matches != [selected] or not all(selected[key] for key in ('device', 'endpoint', 'entity'))
            or row['native'] or 'helper' in row):
        raise ValueError('入力一覧と受信元が一致しないか、送信側の操作が含まれています')
    return selected


def verify_capture(case, run_id):
    run = RUNS / run_id
    manifest = read_json(run / 'manifest.json')
    if (manifest['run_id'] != run_id or manifest['case_id'] != PASSIVE.stem
            or manifest['upstream_revision'] != case['upstream_revision']):
        raise ValueError('実行ID、受動計測ケース、固定上流版を照合できません')
    folder = run / 'artifacts'
    browser_file = folder / 'coremidi-browser.json'
    entry, = (row for row in manifest['outputs'] if row['path'] == 'artifacts/coremidi-browser.json')
    if browser_file.stat().st_size != entry['bytes'] or sha256(browser_file) != entry['sha256']:
        raise ValueError('Web MIDIの採取記録がマニフェストと一致しません')
    browser = read_json(browser_file)
    uid = manifest.get('input_selection')
    selected = attached_input(browser, uid)
    record, hashes = read_record(run_id, case['upstream_revision'], expected_failure=False)
    if record['errors'] or not CAPTURE_OUTPUTS <= hashes.keys() or not {
        str(path.relative_to(ROOT)) for path in (CASE, PASSIVE, LIVE, FIXED)
    } <= set(record['case_inputs']):
        raise ValueError('採取成果とケース定義の保存を照合できません')

    captured = any(
        command['exit_code'] == 0 and command['argv'][:2] ==
        ['node', '$REPOSITORY/web/prototypes/chimera-research/tools/capture-midi-coremidi.mjs']
        and command['argv'][-2:] == ['$WORKSPACE/cases/worklet-midi-coremidi-passive.json', uid]
        for command in manifest['commands'])
    replayed = any(
        command['exit_code'] == 0 and command['argv'][-5:-1] ==
        ['render-pcm', '$ARTIFACTS/candidate-case.json', '$ARTIFACTS/candidate-cli.wav', '$ARTIFACTS/candidate-cli.csv']
        for command in manifest['commands'])
    if not captured or not replayed:
        raise ValueError('指定UIDの採取と保存ケースのCLI再生を実行記録で照合できません')

    definition, live, fixed = capture_case(run, manifest, case['physical_midi_evidence']['passive_case_sha256'])
    if manifest['case_revision'] != definition['revision']:
        raise ValueError('採取時のケース版を照合できません')
    summary = read_json(run / 'summary.json')
    result, browser_hold_ms = recalculate(browser, definition, folder, live, fixed)
    if (summary['evidence'] != 'attached_device' or summary['selected_input'] != selected
            or summary.get('web_midi_port_id', result['web_midi_port_id']) != result['web_midi_port_id']):
        raise ValueError('入力元が採取時の要約と一致しません')
    failed = [key for key, passed in result['checks'].items() if not passed]
    from_capture = {key: passed for key, passed in result['checks'].items()
                    if key != 'browser_hold_in_registered_window'}
    if failed or summary['checks'] != from_capture:
        raise ValueError(f'一次記録の再計算が収録条件を満たしません ({", ".join(failed)})')

    label = manifest.get('operator_device_label')
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError('操作者の機器情報が空です')
    return {**result, 'status': 'observed' if label else 'partial', 'run_id': run_id,
            'browser_hold_ms': browser_hold_ms, 'operator_device_label': label, 'audio_observation': 'worklet_pcm'}


def physical_midi_observations(case, run_id):
    if run_id is None:
        return {}, {'status': 'unregistered'}
    try:
        result = verify_capture(case, run_id)
    except (OSError, KeyError, IndexError, TypeError, ValueError, EOFError) as error:
        return {'submitted_physical_midi_observation': False}, {
            'status': 'rejected', 'run_id': run_id, 'reason': str(error)}
    return {'submitted_physical_midi_observation': True}, result
