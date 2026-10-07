"""既存評価環境を変更せず、教師の必要部分のみを別領域へ導入する。"""
import subprocess
import sys
import argparse
import os
from budget import Budget, ROOT, RESULT, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repair', action='store_true')
    parser.add_argument('--world', action='store_true')
    parser.add_argument('--apple-sdk', action='store_true')
    parser.add_argument('--world-compat', action='store_true')
    args = parser.parse_args()
    packages = ['kokoro==0.9.4', 'misaki==0.9.4', 'loguru==0.7.3', 'addict==2.4.0',
                'fugashi==1.5.2', 'jaconv==0.4.0', 'mojimoji==0.0.13', 'unidic-lite==1.0.8']
    if args.repair:
        packages = ['attrs==25.4.0']
    if args.world:
        packages = ['pyworld==0.3.5']
    if args.world_compat:
        packages = ['setuptools==80.9.0']
    with Budget().job('setup', '教師の分離依存を導入', 800_000_000):
        command = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', '--no-deps',
                   '--target', str(ROOT / '.cache/packages'), *packages]
        env=os.environ.copy()
        if args.apple_sdk:
            sdk=subprocess.check_output(['/usr/bin/xcrun','--show-sdk-path'],text=True).strip()
            env.update(CC='/usr/bin/clang',CXX='/usr/bin/clang++',SDKROOT=sdk,
                       CFLAGS=f'-isysroot {sdk}',CXXFLAGS=f'-isysroot {sdk}',CPPFLAGS='',LDFLAGS='')
        result = subprocess.run(command, text=True, capture_output=True, timeout=600,env=env)
        filename = 'dependency-world.json' if args.world else 'dependency-repair.json' if args.repair else 'dependency-install.json'
        if args.apple_sdk:filename=filename.replace('.json','-apple-sdk.json')
        if args.world_compat:filename='dependency-world-compat.json'
        save(RESULT / filename, {'packages': packages, 'command': command,
             'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
             'scope': '教師model.pyを直接読み込み、未使用の英語pipeline依存は導入しない'})
        print(result.stdout[-4000:])
        print(result.stderr[-2000:])
        result.check_returncode()


if __name__ == '__main__':
    main()
