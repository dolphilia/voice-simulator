"""実際のChrome許可ダイアログと、Web MIDIの応答・画面の遷移を照合する。"""

import argparse
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from measure_uniform_tube import record_measurement
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-midi-browser-prompt.json'
CAPTURE = WEB / 'tools/capture-midi-browser-prompt.mjs'
HELPER = WORKSPACE / 'tools/midi_permission_browser_ui.swift'
UPPER_TEST = UPSTREAM / 'tests/live-control.test.ts'


def checks_for_target(name, row):
    before = row.get('before', {})
    denied = row.get('denied', {})
    repeated = row.get('repeatedDenial', {})
    reset = row.get('afterReset', {})
    granted = row.get('granted', {})
    disconnected = row.get('disconnected', {})
    requests = disconnected.get('probe', {}).get('requests', [])
    if name == 'candidate-voice':
        denied_ui = denied.get('ui', {})
        granted_ui = granted.get('ui', {})
        detached_ui = disconnected.get('ui', {})
        ui_works = (denied_ui.get('button') == 'MIDIを接続' and bool(denied_ui.get('alert'))
                    and granted_ui.get('status') == 'MIDI入力なし'
                    and not granted_ui.get('alert') and detached_ui.get('status') == 'MIDI未接続')
    else:
        ui_works = (denied.get('ui') == 'MIDI: Blocked by the browser'
                    and granted.get('ui') == 'MIDI: Plug one in' and disconnected.get('ui') == 'MIDI')
    dialogs = row['dialogs']
    return {
        'two_browser_dialogs': [d['requested'] for d in dialogs if d.get('pressed')] == ['deny', 'allow']
        and all(d.get('snapshot', {}).get('frontmost') and d.get('screenshot') for d in dialogs),
        'permission_states': [r.get('permission') for r in (before, denied, repeated, reset, granted)] ==
        ['prompt', 'denied', 'denied', 'prompt', 'granted'] and repeated.get('hasDialog') is False,
        'standard_request_outcomes': (len(requests) == 3
            and all(r['options'] == {'sysex': False} for r in requests)
            and [r['outcome'] for r in requests[:2]] == ['NotAllowedError', 'NotAllowedError']
            and requests[2]['outcome'] == 'granted' and requests[2]['inputs'] == 0
            and requests[2]['sysexEnabled'] is False),
        'ui_and_disconnect': ui_works and granted.get('probe', {}).get('subscriptions') == [1]
        and disconnected.get('probe', {}).get('subscriptions') == [0],
        'no_page_or_capture_errors': not row.get('error') and not row['errors']
        and not any(d.get('captureError') for d in dialogs),
    }


def measure(case, bun, out, execute):
    with TemporaryDirectory(prefix='midi-prompt-', dir=out.parent) as directory:
        scratch = Path(directory)
        dist, executable = scratch / 'dist', scratch / 'browser-ui'
        execute(['xcrun', 'swiftc', str(HELPER), '-o', str(executable)])
        execute([*bun, 'run', 'build', '--outDir', str(dist)], cwd=WEB, stdout=out / 'browser-build.log')
        output = out / 'native-prompts.json'
        execute(['node', str(CAPTURE), str(CASE), str(dist), str(UPSTREAM), str(scratch), str(out), str(executable)],
                cwd=WEB, stdout=output)
    execute([*bun, 'test', str(UPPER_TEST)], cwd=UPSTREAM, stdout=out / 'upstream-midi-tests.log')
    data = read_json(output)
    checks = {'dedicated_browser_targets': list(data['reports']) == case['targets']
              and data['mode'] == case['browser']['mode']}
    checks.update({f'{target}/{name}': value for target, row in data['reports'].items()
                   for name, value in checks_for_target(target, row).items()})
    return {'checks': checks, **data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    previous = case['previous']
    manifest = WORKSPACE / 'runs' / previous['run'] / 'manifest.json'
    source = read_json(manifest)
    if sha256(manifest) != previous['manifest_sha256'] or source['case_id'] != previous['case'] or source['status'] != 'pass':
        parser.error('以前の権限応答の実行が登録と一致しません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), CAPTURE, HELPER, manifest, *web_sources(),
              *(UPSTREAM / 'src/ui' / name for name in ('midi.ts', 'store.ts', 'components/Keys.tsx')),
              UPPER_TEST, WORKSPACE / 'tools/measure_worklet_fixed.py', WORKSPACE / 'tools/measure_uniform_tube.py',
              WORKSPACE / 'tools/upstream_baseline.py']
    settings = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'comparison_run': previous['run'], 'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, inputs, settings,
                              lambda out, run: measure(case, bun, out, run), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
