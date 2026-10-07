"""承認された軸別比較の契約と追記台帳。旧campaignは再開しない。"""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PILOT = ROOT.parent/'neural-control-distillation'
OLD = ROOT.parent/'autonomous-speech-synthesis'
EXT = ROOT.parent/'neural-control-extension'
ERES = EXT/'results/nas-extension-20261002-v1'
REV = ERES/'acoustic-revision'
BUNDLE = REV/'bundle'
PREP = ROOT/'preparation-20261003-v2'
CONTENT = ROOT.parent/'acoustic-revision-content-evaluation'
RESULT = ROOT/'results/nas-factorial-20261003-v1'
LIMITS = {'seconds': 7200, 'bytes': 200_000_000, 'render': 256, 'ai': 240, 'teacher': 0, 'train': 0}
sys.path.insert(0, str(PILOT))
from budget import Budget, digest, save


def read(path):
    return json.loads(Path(path).read_text())


class FactorialBudget(Budget):
    def __init__(self):
        super().__init__(ROOT, RESULT)

    def initialize(self):
        with self.locked():
            path = self.result/'contract.json'
            if not path.exists():
                save(path, {'campaign': RESULT.name, 'started_epoch': time.time(), 'limits': LIMITS,
                    'authorization': 'ユーザー「承認します。作業を続けてください。」による追加枠・入力補足の承認',
                    'campaign_count': 1, 'previous_campaigns_unchanged': True,
                    'scope': '当実験全領域を容量に含む。固定モデル・前段・辞書・ASRは読み取り再利用',
                    'teacher_generation': False, 'training': False, 'downloads': False,
                    'paid_api': False, 'unattended': True, 'automatic_extension': False})
            return read(path)

    def reserve(self, kind, label, reserve_bytes=0, count=1):
        if kind in ('teacher', 'train'):
            raise RuntimeError('この枠では教師生成・学習を認めません')
        return super().reserve(kind, label, reserve_bytes, count)


def check_seal(path):
    seal = read(path)
    base = Path(seal['path_base'])
    bad = [n for n, sha in seal['files'].items() if not (base/n).is_file() or digest(base/n) != sha]
    if bad:
        raise ValueError('旧封印の変更: '+repr(bad))
    return {'seal': str(path.relative_to(REPO)), 'sha256': digest(path), 'verified_files': len(seal['files'])}


def main():
    budget = FactorialBudget()
    budget.initialize()
    with budget.job('setup', '入力・比較・辞書・認識器を実行前に固定', 2_000_000):
        if (RESULT/'protocol.json').exists():
            raise RuntimeError('初期化済みです')
        seals = [PILOT/'results/nas-pilot-20261002-v1/artifact-seal.json',
            PILOT/'results/nas-pilot-20261002-v1/post-pilot/artifact-seal.json',
            ERES/'artifact-seal.json', ERES/'post-analysis/artifact-seal.json', REV/'artifact-seal.json',
            CONTENT/'results/nas-content-20261002-v1/artifact-seal.json',
            CONTENT/'post-evaluation/artifact-seal.json', PREP/'artifact-seal.json']
        preservation = [check_seal(p) for p in seals]
        draft = read(PREP/'protocol-draft.json')
        for name, sha in draft['source_hashes'].items():
            assert digest(ROOT/name) == sha
        for name, sha in draft['model_hashes'].items():
            assert digest(BUNDLE/(name+'.json')) == sha
        prior = read(CONTENT/'results/nas-content-20261002-v1/protocol.json')
        for name, sha in prior['model_hashes'].items():
            assert digest(REPO/name) == sha
        reading = read(CONTENT/'post-evaluation/reading-audit-20261003-v2/contract.json')
        for name, sha in reading['dictionary_files'].items():
            assert digest(Path(reading['dictionary_path'])/name) == sha
        save(RESULT/'protocol.json', {**draft, 'generation_authorized': True, 'campaign_started': True,
            'preparation_sha256': digest(PREP/'protocol-draft.json'),
            'source_hashes': {p.name: digest(p) for p in sorted(ROOT.glob('*.py'))},
            'asr_model_hashes': prior['model_hashes'], 'whisper_path': prior['whisper_path'],
            'engine_settings': prior['engine_settings'], 'normalizer_source_sha256': prior['normalizer_source_sha256'],
            'reading_diagnostic': {'contract': reading, 'source_sha256': digest(CONTENT/'reading_audit.py'),
                'rule': '上位16経路、同一分割・品詞・活用・原形。原稿を読み候補選択に使わない。主CERは補正しない'},
            'content_rule': '各ASRで全12文・短6文・長6文・変更指定4群の通常/変更/合算を比較。全比較群で既定HMM以下の誤り数、欠損0を観測保護条件とする',
            'scope': '診断の保護条件。自然さ・統計的非劣性・最終品質を認定しない',
            'no_retries': True, 'no_optimization_after_asr': True,
            'factorial_rule': '直接方式の誤り数について共同−F0単独−継続長単独＋既定HMMの差を記録。因果は固定文章・設定の介入範囲に限定し、ASRの実発音資格は仮定しない'})
        save(RESULT/'input-preservation.json', {'seals': preservation, 'all_verified': True})
    print('承認済み新campaignの比較契約を固定しました')


if __name__ == '__main__':
    main()
