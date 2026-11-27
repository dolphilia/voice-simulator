"""使い捨ての発声状態でWASM関数本体の遅延コンパイルを先に通す。"""

import argparse
from pathlib import Path

import measure_worklet_release_alignment as release
import measure_worklet_shared_context as shared


CASE = release.WORKSPACE / 'cases/worklet-wasm-dsp-warmup.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = release.stored.read(CASE)
    shared_path = release.WORKSPACE / 'cases' / study['shared_case']
    baseline = release.stored.read(shared_path)
    prior, manifest = release.saved.load_saved_run(
        study['shared_run'], baseline['id'], study['upstream_revision'], ['summary.json', 'artifacts/vocal_wasm.wasm'])
    saved_input, = (item['sha256'] for item in release.stored.read(manifest)['inputs']
                    if item['path'].endswith('/' + shared_path.name))
    previous = release.stored.read(prior['summary.json'])
    if (saved_input != release.sha256(shared_path) or not all(previous['checks'].values())
            or release.sha256(prior['artifacts/vocal_wasm.wasm']) != study['wasm_sha256']):
        parser.error('共有Contextの比較記録またはWASMを照合できません')
    measurement = {**baseline['measurement'], **study['measurement'],
                   'registered_wasm_sha256': study['wasm_sha256']}
    registered = {**baseline, **study, 'measurement': measurement}
    return shared.run_shared_study(args.run_id, CASE, registered,
                                   extra_inputs=(Path(__file__).resolve(), shared_path, manifest, *prior.values()))


if __name__ == '__main__':
    raise SystemExit(main())
