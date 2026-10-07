"""公式の固定revisionから必要な教師資産だけを上限付きで取得する。"""
import json
import urllib.request
from budget import Budget, ROOT, RESULT, save, digest

REVISION = 'f3ff3571791e39611d31c381e3a41a3af07b4987'
BASE = f'https://huggingface.co/hexgrad/Kokoro-82M/resolve/{REVISION}/'
FILES = {'config.json': 100_000, 'README.md': 100_000, 'VOICES.md': 100_000,
         'kokoro-v1_0.pth': 350_000_000, 'voices/jf_alpha.pt': 1_000_000}


def main():
    budget = Budget()
    records = []
    for name, limit in FILES.items():
        path = ROOT / '.cache/teacher' / name
        if path.exists():
            raise FileExistsError(f'取得済みのファイルは上書きしません: {name}')
        with budget.job('setup', '教師取得:' + name, limit):
            path.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with urllib.request.urlopen(BASE + name, timeout=60) as r, path.open('xb') as f:
                while chunk := r.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise RuntimeError('ファイル容量の上限を超えました')
                    f.write(chunk)
            sha = digest(path)
            if name.endswith('.pth') and sha != '496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4':
                raise ValueError('公式に記載されたモデルhashと一致しません')
            if name.endswith('jf_alpha.pt') and not sha.startswith('1bf4c9dc'):
                raise ValueError('公式の声hashと一致しません')
            records.append({'path': str(path.relative_to(ROOT)), 'url': BASE + name,
                            'bytes': total, 'sha256': sha})
            print(name, total, flush=True)
    save(RESULT / 'teacher-provenance.json', {
        'model': 'hexgrad/Kokoro-82M', 'revision': REVISION, 'voice': 'jf_alpha',
        'license': 'Apache-2.0（公式モデルカードの記載）',
        'purpose': 'ローカル研究教師。最終生成経路には含めない',
        'limitations': ['日本語学習量は限定的', '短文の品質は別途診断する',
                       '教師出力は自然音声の正解ラベルではない'],
        'rejected_candidates': [{'id': 'facebook/mms-tts-jpn', 'status': 'unavailable',
                                'evidence': '公式API URLがHTTP 401を返した。実在・公開性を確認できず採択しない'}],
        'files': records})


if __name__ == '__main__':
    main()
