"""承認済み局所F0比較の契約・費用・旧成果の保存。"""
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PILOT = ROOT.parent/'neural-control-distillation'
OLD = ROOT.parent/'autonomous-speech-synthesis'
EXT = ROOT.parent/'neural-control-extension'
REV = EXT/'results/nas-extension-20261002-v1/acoustic-revision'
BUNDLE = REV/'bundle'
FACT = ROOT.parent/'acoustic-control-factorial'
FRES = FACT/'results/nas-factorial-20261003-v1'
RESULT = ROOT/'results/nas-local-f0-20261003-v1'
sys.path.insert(0, str(PILOT))
from budget import Budget, digest, save


def read(path):
    return json.loads(Path(path).read_text())


def check_seal(path):
    seal = read(path)
    base = Path(seal['path_base'])
    assert all((base/n).is_file() and digest(base/n) == sha for n, sha in seal['files'].items())
    return {'seal': str(path.relative_to(REPO)), 'sha256': digest(path), 'verified_files': len(seal['files'])}


class LocalBudget(Budget):
    def __init__(self):
        super().__init__(ROOT, RESULT)

    def reserve(self, kind, label, reserve_bytes=0, count=1):
        if (RESULT/'artifact-seal.json').exists():
            raise RuntimeError('終了封印後の処理を認めません')
        if kind == 'teacher':
            raise RuntimeError('追加教師生成を認めません')
        return super().reserve(kind, label, reserve_bytes, count)


def main():
    b = LocalBudget()
    if (RESULT/'contract.json').exists():
        raise FileExistsError('新campaignは開始済みです')
    save(RESULT/'contract.json', {'campaign': RESULT.name, 'started_epoch': time.time(),
        'limits': {'seconds': 7200, 'bytes': 200_000_000, 'render': 192, 'ai': 128, 'teacher': 0, 'train': 4},
        'authorization': '2026-10-03ユーザー「承認します。作業を続けてください。」による局所F0追加計画の承認',
        'proposal_sha256': digest(REPO/'docs/plans/local-f0-transfer-proposal-2026-10-03.md'),
        'source_download_limit_bytes': 5_000_000, 'source_only_downloads': True,
        'no_new_models_audio_dependencies': True, 'paid_api': False, 'automatic_extension': False,
        'scope': '新実験ディレクトリ全体。旧資産は読み取り再利用', 'unattended': True})
    with b.job('setup', '旧9封印と局所比較の承認範囲を固定', 2_000_000):
        items = read(FRES/'input-preservation.json')['seals']
        verified = [check_seal(REPO/p['seal']) for p in items]
        assert verified == items
        verified.append(check_seal(FRES/'artifact-seal.json'))
        save(RESULT/'input-preservation.json', {'seals': verified, 'all_verified': True})
        p = read(FRES/'protocol.json')
        save(RESULT/'engine-contract.json', {k: p[k] for k in ('asr_model_hashes', 'whisper_path',
            'engine_settings', 'normalizer_source_sha256', 'reading_diagnostic')})
    print('局所F0の新campaignを承認範囲内で開始しました')


if __name__ == '__main__':
    main()
