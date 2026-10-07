"""0.4.1のsubmodule固定版からヘッダ・実装・来歴だけを取得する。"""
import urllib.request
from campaign import LocalBudget, ROOT, RESULT, read, save, digest, OLD
COMMIT = '214e26dfb7f728ff9db39c14a59db709abcc121d'


def main():
    out = ROOT/'vendor'
    out.mkdir(exist_ok=True)
    with LocalBudget().job('setup', '著者HTSの固定版ヘッダと実装を取得', 1_000_000):
        rows = []
        for path in ('src/include/HTS_engine.h', 'src/lib/HTS_engine.c'):
            url = f'https://raw.githubusercontent.com/r9y9/hts_engine_API/{COMMIT}/{path}'
            target = out/path.rsplit('/', 1)[1]
            if not target.exists():
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read(250_001)
                if len(data) > 250_000 or b'Copyright' not in data:
                    raise ValueError('ソース容量または来歴の検査に不通過')
                target.write_bytes(data)
            rows.append({'path': str(target.relative_to(ROOT)), 'url': url, 'bytes': target.stat().st_size, 'sha256': digest(target)})
        assert sum(r['bytes'] for r in rows) <= 5_000_000
        lib = OLD/'.venv-eval/lib/python3.11/site-packages/pyopenjtalk/htsengine.cpython-311-darwin.so'
        save(RESULT/'source-provenance.json', {'rows': rows, 'download_bytes': sum(r['bytes'] for r in rows),
            'submodule_commit': COMMIT, 'package_version': '0.4.1',
            'submodule_source': 'https://github.com/r9y9/pyopenjtalk/tree/v0.4.1/lib',
            'binary': str(lib.relative_to(ROOT.parents[0])), 'binary_sha256': digest(lib),
            'license': 'HTS_engine.h・HTS_engine.c冒頭の三条項BSD通知を保持',
            'abi_status': '対応版ヘッダを使用。入口の実動作照合は次の検査で行う。'})
    print('固定版HTSソース取得完了')


if __name__ == '__main__':
    main()
