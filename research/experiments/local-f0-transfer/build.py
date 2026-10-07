"""既存HTS共有ライブラリへ結合する独立shimだけを構築する。"""
import subprocess
from campaign import LocalBudget, ROOT, RESULT, save, digest


def main():
    with LocalBudget().job('setup', '対応ヘッダから独立HTS shimを構築', 2_000_000):
        target = ROOT/'local_hts-v2.dylib'
        if target.exists():
            raise FileExistsError('構築物を上書きしません')
        cmd = ['/usr/bin/clang', '-dynamiclib', '-O2', '-undefined', 'dynamic_lookup', '-I'+str(ROOT/'vendor'),
               str(ROOT/'shim.c'), '-o', str(target)]
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        attempt = len(list(RESULT.glob('build*.json')))+1
        save(RESULT/f'build-attempt-{attempt}.json', {'command': cmd, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
            'shim_source_sha256': digest(ROOT/'shim.c'), 'header_sha256': digest(ROOT/'vendor/HTS_engine.h'),
            'binary_sha256': digest(target) if target.exists() else None, 'existing_environment_modified': False})
        p.check_returncode()


if __name__ == '__main__':
    main()
