"""固定発声Workletの初期化時にJS→WASMラッパーを準備する。"""

import argparse
from pathlib import Path
import shutil
import subprocess

import measure_worklet_release_alignment as release
import measure_worklet_wrapper_threshold as threshold


CASE = release.WORKSPACE / 'cases/worklet-wasm-wrapper-warmup.json'


def previous_pcm(study, threshold_case, threshold_path):
    hashes = set()
    inputs = []
    for name in study['threshold_runs']:
        files, manifest = release.saved.load_saved_run(
            name, threshold_case['id'], study['upstream_revision'], ['summary.json'])
        info = release.stored.read(manifest)
        summary = release.stored.read(files['summary.json'])
        recorded, = (row['sha256'] for row in info['inputs'] if row['path'].endswith('/' + threshold_path.name))
        if (info['status'] != 'pass' or not all(summary['checks'].values())
                or recorded != release.sha256(threshold_path)):
            raise ValueError(f'回数変更の比較記録を照合できません ({name})')
        cold = [trial['browser_pcm_sha256'] for trial in summary['trials']
                if trial['tiering_budget'] is None and trial['profile'] == study['profile']]
        if not cold:
            raise ValueError(f'準備していない既定条件が見つかりません ({name})')
        hashes.update(cold)
        inputs.extend((manifest, *files.values()))
    if len(hashes) != 1:
        raise ValueError('既定条件のPCMのハッシュが一致しません')
    return hashes.pop(), inputs


def run_study(run_id, case_path, study, *, inspect_capture=threshold.inspect_trace,
              extra_inputs=(), prior_state=None):
    threshold_path = release.WORKSPACE / 'cases' / study['threshold_case']
    threshold_case = release.stored.read(threshold_path)
    preceding_path = release.WORKSPACE / 'cases' / threshold_case['release_case']
    preceding = release.stored.read(preceding_path)
    reference_path = release.WORKSPACE / 'cases' / preceding['reference_case']
    reference = release.stored.read(reference_path)
    source = release.WORKSPACE / 'cases' / reference['fixed_voice_case']
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=release.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=release.UPSTREAM, text=True)
            or any(case['upstream_revision'] != revision for case in (threshold_case, preceding, reference))
            or release.sha256(source) != reference['fixed_voice_sha256']):
        raise ValueError('固定上流または固定発声の入力を照合できません')
    spec = study['measurement']
    if (study['profile'] != threshold_case['profile']
            or any(sorted(order) != sorted(spec['warmup_calls']) for order in spec['capture_order'])):
        raise ValueError('比較のプロファイルまたは採取順序を照合できません')
    prior_pcm, inputs = previous_pcm(study, threshold_case, threshold_path)
    release.validate_registration(preceding, reference)
    full_case = {**study, 'measurement': {**threshold_case['measurement'], **spec, 'window_radius_quanta': 0}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs.extend([case_path, Path(__file__).resolve(), threshold_path, preceding_path, reference_path, source,
                   *extra_inputs,
                   *release.web_sources(), *release.shared.candidate_sources(), release.vowel.PROBE,
                   *(Path(module.__file__) for module in (threshold, release, release.stored, release.saved,
                     release.shared, release.wasm, release.realtime, release.realtime.pcm, release.vowel))])
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'prior_cold_pcm_sha256': prior_pcm,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return release.shared.record_measurement(run_id, case_path, inputs, metadata,
        lambda a, run: threshold.measure(full_case, preceding, reference, source, a, run, bun,
            prior_pcm=prior_pcm, prior_state=prior_state, inspect_capture=inspect_capture),
        command=None, input_root=release.ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    try:
        return run_study(args.run_id, CASE, release.stored.read(CASE))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
