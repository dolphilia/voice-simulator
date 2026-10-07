"""保存済み音声だけを評価する、承認済みの独立した追加枠。"""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PILOT = ROOT.parent / 'neural-control-distillation'
OLD = ROOT.parent / 'autonomous-speech-synthesis'
EXT = ROOT.parent / 'neural-control-extension'
ERES = EXT / 'results/nas-extension-20261002-v1'
REV = ERES / 'acoustic-revision'
RESULT = ROOT / 'results/nas-content-20261002-v1'
sys.path.insert(0, str(PILOT))
from budget import Budget, save, digest

LIMITS = {'seconds': 3600, 'bytes': 100_000_000, 'ai': 200,
          'teacher': 0, 'render': 0, 'train': 0}


class ContentBudget(Budget):
    def __init__(self):
        super().__init__(ROOT, RESULT)

    def initialize(self):
        with self.locked():
            path = self.result / 'contract.json'
            if not path.exists():
                save(path, {'campaign': RESULT.name, 'started_epoch': time.time(),
                     'limits': LIMITS, 'campaign_count': 1,
                     'authorization': 'ユーザー「承認します。計画を続行してください。」による保存済み100音声・追加AI評価200回の承認',
                     'proposal': 'docs/plans/acoustic-revision-content-evaluation-proposal-2026-10-02.md',
                     'scope': '新規実験ディレクトリ全体を容量に含む。旧資産は読み取り再利用。失敗も計数し再試行しない',
                     'downloads': 0, 'paid_api': False, 'unattended': True,
                     'previous_campaign_unchanged': True,
                     'final_generator_non_neural': True})
            return json.loads(path.read_text())

    def reserve(self, kind, label, reserve_bytes=0, count=1):
        if kind in ('teacher', 'render', 'train'):
            raise RuntimeError('この枠では生成・学習を認めません')
        return super().reserve(kind, label, reserve_bytes, count)


def read(path):
    return json.loads(Path(path).read_text())


def verify_seal(path):
    seal = read(path)
    base = Path(seal['path_base'])
    bad = [name for name, sha in seal['files'].items()
           if not (base/name).is_file() or digest(base/name) != sha]
    if bad:
        raise ValueError('旧成果物のハッシュ不一致: ' + repr(bad))
    return {'seal': str(path.relative_to(REPO)), 'seal_sha256': digest(path),
            'verified_files': len(seal['files']), 'mismatches': bad}


def initialize():
    budget = ContentBudget()
    budget.initialize()
    if (RESULT/'protocol.json').exists():
        raise RuntimeError('このcampaignは既に初期化されています')
    with budget.job('audit', '入力・旧成果物の固定と評価契約', 2_000_000):
        seals = [PILOT/'results/nas-pilot-20261002-v1/artifact-seal.json',
                 PILOT/'results/nas-pilot-20261002-v1/post-pilot/artifact-seal.json',
                 ERES/'artifact-seal.json', ERES/'post-analysis/artifact-seal.json',
                 REV/'artifact-seal.json']
        verified = [verify_seal(p) for p in seals]
        manifest = read(REV/'pending-content-evaluation.json')
        rows = manifest['rows']
        assert len(rows) == 100 and len({r['wav_sha256'] for r in rows}) == 100
        for row in rows:
            assert digest(EXT/row['wav']) == row['wav_sha256']
            if 'record_sha256' in row:
                assert digest((EXT/row['wav']).with_suffix('.json')) == row['record_sha256']
        snapshot = next((OLD/'.cache/ai/whisper').rglob('model.bin')).parent
        models = list(snapshot.iterdir()) + list((PILOT/'.cache/reazonspeech').glob('*.onnx')) + [PILOT/'.cache/reazonspeech/tokens.txt']
        models = [p for p in models if p.is_file()]
        hashes = {str(p.relative_to(REPO)): digest(p) for p in sorted(models)}
        dependency = read(PILOT/'results/nas-pilot-20261002-v1/dependency-manifest.json')
        previous_models = dependency.get('new_dependency_files', {})
        for path, sha in hashes.items():
            rel = str((REPO/path).relative_to(PILOT)) if (REPO/path).is_relative_to(PILOT) else None
            if rel in previous_models:
                assert sha == previous_models[rel]
        protocol_rows = read(REV/'render-protocol.json')['rows']
        groups = {r['id']: {'text': r['text'], 'length': 'short' if i < 4 else 'long',
                    'challenge_group': i % 4, 'challenge': r['challenge']} for i, r in enumerate(protocol_rows)}
        save(RESULT/'protocol.json', {'manifest_sha256': digest(REV/'pending-content-evaluation.json'),
             'rows': rows, 'groups': groups, 'model_hashes': hashes,
             'whisper_path': str(snapshot),
             'engine_settings': {'whisper': {'device': 'cpu', 'compute_type': 'int8', 'cpu_threads': 4,
                   'language': 'ja', 'beam_size': 5, 'initial_prompt': None,
                   'condition_on_previous_text': False, 'vad_filter': False},
                 'reazon': {'provider': 'cpu', 'num_threads': 2, 'sample_rate': 16000,
                   'feature_dim': 80, 'decoding_method': 'greedy_search'}},
             'normalizer_source_sha256': digest(OLD/'diagnostics.py'),
             'normalization': '従来のpyopenjtalkかな読み＋NFKC＋句読点・空白・制御文字除去',
             'comparison_rule': '両認識器それぞれで、全8文・短4文・長4文・指定条件4群のneutral/challenge/combinedを集計。全群の誤り数差が0以下なら内容非悪化を観測。欠損・失敗は合格にしない',
             'rule_scope': '非劣性幅の資格がないため保守的な観測診断。統計的非劣性・自然さ・最終独立確認を認定しない',
             'native_reuse': 'refinedの対照は同じrender/nativeの認識結果を再利用',
             'runtime_scope': '対照なしの2未知文・4独立WAVの診断。同一通常/隔離WAVは一回だけ認識',
             'no_optimization_on_results': True, 'no_retries': True,
             'source_hashes': {p.name: digest(p) for p in sorted(ROOT.glob('*.py'))}})
        save(RESULT/'input-preservation-audit.json', {'seals': verified, 'models': hashes,
             'manifest_rows': len(rows), 'all_verified': True})
    print('100音声の固定と旧成果物の照合が完了しました', flush=True)


if __name__ == '__main__':
    initialize()
