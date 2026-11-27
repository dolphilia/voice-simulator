"""ChromiumのWeb MIDI権限と操作画面の状態遷移を照合する。"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from measure_uniform_tube import record_measurement
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/worklet-midi-permission.json'
CAPTURE = WEB / 'tools/capture-midi-permission.mjs'
UPPER_TEST = UPSTREAM / 'tests/live-control.test.ts'


def outcomes(report):
    return ['denied' if item['outcome'] in ('NotAllowedError', 'SecurityError') else item['outcome']
            for item in report['probe']['requests']]


def candidate_checks(report):
    waiting = report['waiting']
    canceled = report.get('canceled', {})
    rejection = report.get('oldRejection', {})
    retried = report.get('retried', {})
    return {
        'native_permission_and_retry': (report['permissions'][:2] == ['denied', 'granted'] and
                                        outcomes(report)[:2] == ['denied', 'granted'] and
                                        report['denied']['error'] and report['denied']['canConnect'] and
                                        report['granted']['canDisconnect'] and report['granted']['noInputs'] and
                                        not report['granted']['error'] and report['disconnected']['subscriptions'] == [0]),
        'cancel_waiting_and_ignore_late_grant': (waiting['canDisconnect'] and waiting['waiting'] and
                                                 canceled.get('canConnect') is True and canceled.get('error') is False and
                                                 report.get('afterCancel', {}).get('subscriptions') == [0, 0]),
        'old_denial_keeps_new_request_pending': (rejection.get('waiting') is True and rejection.get('error') is False and
                                                 retried.get('canDisconnect') is True and retried.get('noInputs') is True and
                                                 outcomes(report) == ['denied', 'granted', 'granted', 'denied', 'granted'] and
                                                 report['afterRetry']['subscriptions'] == [0, 0, 1]),
    }


def native_checks(report):
    return (not report['errors'] and all(r['options'] == {'sysex': False} and r['delivered']
                and ((r['inputs'], r['sysexEnabled']) == (0, False) if r['outcome'] == 'granted'
                     else (r['inputs'], r['sysexEnabled']) == (None, None))
                for r in report['probe']['requests'])
            and all(n == 0 for n in report['probe']['subscriptions']))


def measure(bun, out, execute):
    with TemporaryDirectory(dir=out.parent) as dist:
        execute([*bun, 'run', 'build', '--outDir', dist], cwd=WEB, stdout=out / 'browser-build.log')
        execute(['node', str(CAPTURE), str(CASE), dist, str(UPSTREAM)], stdout=out / 'midi-permission.json')
    execute([*bun, 'test', str(UPPER_TEST)], cwd=UPSTREAM)
    data = read_json(out / 'midi-permission.json')
    candidate = data['candidate']
    upper = data['upper']
    checks = {f'{panel}/{test}': passed for panel, report in candidate.items()
              for test, passed in candidate_checks(report).items()}
    checks['all_native_requests_and_cleanup'] = all(native_checks(r) for r in (*candidate.values(), upper))
    checks['upper_native_permission_and_retry'] = (
        upper['permissions'] == ['denied', 'granted', 'denied', 'granted'] and
        outcomes(upper) == ['denied', 'granted', 'granted', 'denied', 'granted'] and
        upper['denied'] == 'MIDI: Blocked by the browser' and
        upper['granted'] == upper['retried'] == 'MIDI: Plug one in')
    checks['upper_second_click_and_module_cancel'] = (
        upper['secondClick'] == {'button': 'MIDI: Connecting…', 'requests': 3} and
        upper['canceled'] == 'MIDI' and upper['afterCancel']['subscriptions'] == [0, 0])
    return {'checks': checks, **data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    sources = [CASE, Path(__file__).resolve(), CAPTURE, *web_sources(), UPPER_TEST,
               *(UPSTREAM / 'src/ui' / name for name in ('midi.ts', 'store.ts', 'components/Keys.tsx'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, sources, details, lambda out, run: measure(bun, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
