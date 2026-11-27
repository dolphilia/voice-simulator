"""TSPの既知の試験回答を別の書式で取り込む対照を再実行する。"""

import argparse
import csv
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType

import measure_tsp_listening as current
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/tsp-listening-intake-equivalence.json'
SOURCE = Path(current.__file__).relative_to(ROOT)


def fixture_inputs(case):
    audit = WORKSPACE / 'runs' / case['previous_audit']
    reference = read(verified_file(audit, read(audit / 'manifest.json'), 'summary.json'))
    packet_dir = WORKSPACE / 'runs' / case['packet_run']
    manifest_path = packet_dir / 'manifest.json'
    manifest = read(manifest_path)
    if (manifest['upstream_revision'] != case['upstream_revision'] or manifest['status'] != 'pass'
            or not reference['records'][case['packet_run']]['record_matches']):
        raise ValueError('前回の監査に通過した試聴資料が必要です')
    old_code = packet_dir / manifest['source_snapshot'] / SOURCE
    if [row['sha256'] for row in manifest['inputs'] if row['path'] == str(SOURCE)] != [sha256(old_code)]:
        raise ValueError('試聴資料を生成した処理が記録と一致しません')
    paths = {name: verified_file(packet_dir, manifest, f'artifacts/{name}') for name in (
        'reference.json', 'browser-fixture.csv', 'manual-fixture.csv', 'listening/observations.csv')}
    return paths, [audit / 'manifest.json', audit / 'summary.json', manifest_path, old_code], old_code


def variants(out, inputs, packet):
    with inputs['browser-fixture.csv'].open(encoding='utf-8-sig', newline='') as stream:
        header, *browser = csv.reader(stream)
    with inputs['manual-fixture.csv'].open(encoding='utf-8-sig', newline='') as stream:
        _, *manual = csv.reader(stream)
    assert header == list(current.COLUMNS)
    answered = [row for row in browser if any(row[2:])]
    formatted = [row[:4] + [' ' + row[4].replace('\n', '\r\n') + ' '] for row in reversed(answered)]
    controls = {
        'browser-no-empty': answered,
        'manual-extra-empty': [*manual, [packet['packet_id'], '18', '', '', '']],
        'browser-formatted': formatted,
        'changed-choice': [answered[0][:2] + ['B'] + answered[0][3:], *answered[1:]],
        'changed-comment': [*manual[:-1], manual[-1][:4] + ['語末まで一定の速さに聞こえた']],
    }
    paths = {}
    for name, rows in controls.items():
        path = out / f'{name}.csv'
        with path.open('x', encoding='utf-8-sig' if name == 'browser-formatted' else 'utf-8', newline='') as stream:
            csv.writer(stream).writerows([header, *rows])
        paths[name] = path
    return paths


def attempt(collect, packet, responses, fixtures, scratch):
    with TemporaryDirectory(dir=scratch) as work:
        out = Path(work)
        try:
            collect(packet, responses, 'human', fixtures, out)
        except ValueError as error:
            return {'outcome': 'rejected', 'reason': str(error), 'aggregate_written': (out / 'responses-by-source.json').exists()}
        return {'outcome': 'accepted', 'aggregate_written': (out / 'responses-by-source.json').is_file()}


def verify(inputs, old_code, reference_only, out):
    legacy = ModuleType('tsp_listening_saved_collector')
    legacy.__file__ = str(old_code)
    exec(compile(old_code.read_bytes(), str(old_code), 'exec'), legacy.__dict__)
    packet = read(inputs['reference.json'])
    paths = variants(out, inputs, packet)
    fixtures = [inputs[f'{name}-fixture.csv'].read_bytes() for name in ('browser', 'manual')]
    equivalent = ('browser-no-empty', 'manual-extra-empty', 'browser-formatted')
    changed = ('changed-choice', 'changed-comment')
    old = {name: attempt(legacy.collect, packet, {name: paths[name]}, fixtures, out) for name in equivalent}
    checks = {'previous_intake_accepts_reformatted_fixture': all(
        report['outcome'] == 'accepted' and report['aggregate_written'] for report in old.values())}
    revised = {}
    if not reference_only:
        blobs = {name: path.read_bytes() for name, path in paths.items()}
        blank = inputs['listening/observations.csv'].read_bytes()
        for name in (*equivalent, *changed):
            revised[name] = attempt(current.collect, packet, {name: blobs[name]}, fixtures, out)
        revised['blank'] = attempt(current.collect, packet, {'blank': blank}, fixtures, out)
        revised['batch'] = attempt(current.collect, packet, {
            'changed-choice': blobs['changed-choice'], 'browser-formatted': blobs['browser-formatted'],
        }, fixtures, out)
        checks.update(
            known_observations_rejected=all(revised[name]['outcome'] == 'rejected'
                and '試験用回答' in revised[name]['reason'] and not revised[name]['aggregate_written'] for name in equivalent),
            changed_observations_remain_distinct=all(revised[name]['outcome'] == 'accepted' for name in changed),
            blank_rejected='記入済みの観測' in revised['blank'].get('reason', '')
                and not revised['blank']['aggregate_written'],
            batch_rejected_before_publication='browser-formatted' in revised['batch'].get('reason', '')
                and not revised['batch']['aggregate_written'])
    return {'checks': checks, 'data_kind': 'synthetic', 'packet_id': packet['packet_id'], 'legacy': old, 'candidate': revised}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--reference-only', action='store_true', help='修正前の処理で対照を記録する')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    paths, provenance, legacy = fixture_inputs(case)
    inputs = [CASE, Path(__file__).resolve(), ROOT / SOURCE, *paths.values(), *provenance,
              WORKSPACE / 'tools/measure_uniform_tube.py', UPSTREAM / 'crates/chimera-cli/src/compare/tsp.rs']
    flags = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
             'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()), 'data_kind': 'synthetic'}

    def measure(out, execute):
        if not args.reference_only:
            execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
                    cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
        return verify(paths, legacy, args.reference_only, out)

    return record_measurement(args.run_id, CASE, inputs, flags, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
