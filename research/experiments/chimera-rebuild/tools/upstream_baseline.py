"""固定した上流版のテストと基準音声を再実行する。"""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import platform
import re
import subprocess
import wave

from run_storage import RunStorage


WORKSPACE = Path(__file__).resolve().parents[1]
UPSTREAM = WORKSPACE.parents[2] / 'docs/reference/chimera-vocal-synth/upstream'
MELODY = WORKSPACE / 'cases/upstream-melody.json'
TUBE_CASE = WORKSPACE / 'cases/uniform-tube-rigid.json'


def sha256(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def describe(path, relative_to):
    info = {
        'path': str(path.relative_to(relative_to)),
        'bytes': path.stat().st_size,
        'sha256': sha256(path),
    }
    if path.suffix == '.wav':
        try:
            with wave.open(str(path), 'rb') as audio:
                info.update(sample_rate_hz=audio.getframerate(), frames=audio.getnframes(),
                            channels=audio.getnchannels(), sample_bytes=audio.getsampwidth())
        except wave.Error:
            # 標準ライブラリの wave は IEEE 浮動小数点 WAV を扱えない。
            from scipy.io.wavfile import read
            rate, data = read(path)
            info.update(sample_rate_hz=int(rate), frames=len(data),
                        channels=1 if data.ndim == 1 else data.shape[1],
                        sample_bytes=data.dtype.itemsize, sample_format=str(data.dtype))
    return info


def run_baseline(run_id):
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    expected = json.loads(TUBE_CASE.read_text())['upstream_revision']
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)
    if revision != expected or dirty:
        raise ValueError(f'上流の作業ツリーは変更のない {expected} が必要です')

    storage = RunStorage(WORKSPACE / 'runs', run_id)
    storage.create()
    run = storage.run
    artifacts = storage.artifacts
    paths = {name: str(artifacts / name) for name in (
        'vowels.wav', 'ipa-vcv.wav', 'melody.wav', 'articulators.json', 'voice.tele',
    )}
    build_cli = ['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render']
    cases = [
        ('airway', ['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway', '--', '--nocapture'], []),
        ('vowels', [*build_cli, 'vowels', 'male', paths['vowels.wav']], ['vowels.wav']),
        ('ipa-vcv', [*build_cli, 'speech', paths['ipa-vcv.wav'], 'ɑpɑ / ɑbɑ / ɑsɑ / ɑzɑ / ɑmɑ', 'male'],
         ['ipa-vcv.wav']),
        ('melody', [*build_cli, 'notes', str(MELODY), paths['melody.wav'], 'female',
                    '--artic', paths['articulators.json'], '--tele', paths['voice.tele']],
         ['melody.wav', 'articulators.json', 'voice.tele']),
    ]
    manifest = {
        'schema_version': 1,
        'run_id': run_id,
        'upstream_revision': revision,
        'upstream_dirty': False,
        'environment': {
            'os': platform.system(),
            'os_version': platform.mac_ver()[0] or platform.release(),
            'machine': platform.machine(),
            'python': platform.python_version(),
            'rustc': subprocess.check_output(['rustc', '-V'], text=True).strip(),
            'cargo': subprocess.check_output(['cargo', '-V'], text=True).strip(),
        },
        'inputs': [describe(path, WORKSPACE) for path in (TUBE_CASE, MELODY, Path(__file__).resolve())],
        'cases': [],
    }
    if storage.metadata is not None:
        manifest['storage'] = storage.metadata
    for name, command, outputs in cases:
        log = artifacts / f'{name}.log'
        result = {
            'id': name,
            'cwd': '$UPSTREAM',
            'command': [arg.replace(str(artifacts), '$ARTIFACTS').replace(str(WORKSPACE), '$WORKSPACE')
                        for arg in command],
            'status': 'fail',
            'outputs': [],
        }
        try:
            env = storage.subprocess_env()
            with log.open('wb') as output:
                result['exit_code'] = subprocess.run(command, cwd=UPSTREAM, stdout=output,
                                                     stderr=subprocess.STDOUT, env=env).returncode
            for expected_artifact in outputs:
                path = artifacts / expected_artifact
                if path.is_file():
                    result['outputs'].append(describe(path, artifacts.parent))
            if result['exit_code'] == 0 and len(result['outputs']) == len(outputs):
                result['status'] = 'pass'
            else:
                result['missing_outputs'] = [item for item in outputs if not (artifacts / item).is_file()]
        except (OSError, EOFError, wave.Error) as error:
            result['error'] = str(error)
        try:
            result['log'] = describe(log, artifacts.parent)
        except OSError as error:
            if storage.metadata is None:
                raise
            result['status'] = 'fail'
            result.setdefault('error', str(error))
        manifest['cases'].append(result)
        print(f'{name}: {result["status"]}', flush=True)

    try:
        storage.publish()
    except OSError as error:
        manifest['storage_error'] = str(error)
    (run / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return int('storage_error' in manifest or any(case['status'] != 'pass' for case in manifest['cases']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', help='記録先に使う新しい実行 ID')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    return run_baseline(args.run_id)


if __name__ == '__main__':
    raise SystemExit(main())
