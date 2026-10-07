"""未承認実験の静的準備。文章・固定係数・制御設定のみを検査する。"""
from pathlib import Path
import importlib.abc
import json
import math
import sys
import time
from controlled_axes import AXES, initial_settings, refined_settings

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
EXT = ROOT.parent/'neural-control-extension'
ERES = EXT/'results/nas-extension-20261002-v1'
REV = ERES/'acoustic-revision'
PILOT = ROOT.parent/'neural-control-distillation'
PRIOR = PILOT/'results/nas-pilot-20261002-v1'
BUNDLE = REV/'bundle'
PREP = ROOT/'preparation-20261003-v2'
sys.path.insert(0, str(PILOT))
from budget import digest, save

TEXTS = ['靴が濡れた。', '笛が鳴る。', '窓が開く。', '旗を振る。', '砂が乾く。', '月が昇る。',
         '庭の隅に置いた鉢へ朝早く水を注ぎました。', '新しい椅子を机の横へ静かに並べました。',
         '急な坂を下りながら遠くの山を眺めました。', '窓の外から聞こえる笛の音に耳を澄ませました。',
         '夕方の広場で友達と明日の予定を話しました。', '細い道の先にある古い橋をゆっくり渡りました。']
CHALLENGES = [(180., .85), (180., 1.15), (260., .85), (260., 1.15)]
HISTORY = [PRIOR/'splits.json', PRIOR/'hts-transfer/protocol.json',
           PRIOR/'hts-transfer-gain-v2/protocol.json', PRIOR/'runtime-audit/contract.json',
           PRIOR/'hts-runtime-audit-v2/contract.json', ERES/'protocol.json',
           ERES/'relative-protocol.json', ERES/'bounded-protocol.json',
           REV/'render-protocol.json', REV/'pending-content-evaluation.json']


def read(path):
    return json.loads(path.read_text())


def collect_texts(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            found.add(value['text'])
        if isinstance(value.get('tests'), list):
            found.update(t for t in value['tests'] if isinstance(t, str))
        for item in value.values():
            found.update(collect_texts(item))
    elif isinstance(value, list):
        for item in value:
            found.update(collect_texts(item))
    return found


def triples(row):
    phones = ['^', *row['phonemes'], '$']
    return {tuple(phones[i:i+3]) for i in range(len(phones)-2)}


def words(row):
    return {f['orig'] for f in row['features'] if f['pos'] in ('名詞', '動詞', '形容詞') and f['orig'] != '*'}


class DenyNeural(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] in {'torch', 'tensorflow', 'transformers', 'onnxruntime',
            'faster_whisper', 'ctranslate2', 'sherpa_onnx'}:
            raise RuntimeError('準備処理ではニューラル実行を認めません')
        return None


def forbidden(*args, **kwargs):
    raise RuntimeError('準備処理では音声生成・辞書取得を認めません')


def main():
    started = time.time()
    if PREP.exists():
        raise FileExistsError('準備成果物を上書きしません')
    PREP.mkdir(parents=True)
    source_hashes = {p.name: digest(p) for p in sorted(ROOT.glob('*.py'))}
    for name, sha in read(BUNDLE/'manifest.json')['files'].items():
        assert digest(BUNDLE/name) == sha, '固定bundleのハッシュ不一致'
    sys.meta_path.insert(0, DenyNeural())
    import pyopenjtalk
    assert Path(pyopenjtalk.OPEN_JTALK_DICT_DIR.decode()).is_dir()
    for name in ('tts', 'synthesize', 'HTSEngine', '_extract_dic'):
        setattr(pyopenjtalk, name, forbidden)
    sys.path.insert(0, str(BUNDLE))
    from japanese_frontend import analyze
    from acoustic_control import predict
    history = {str(path.relative_to(REPO)): digest(path) for path in HISTORY}
    known = set().union(*(collect_texts(read(path)) for path in HISTORY))
    collisions = sorted(set(TEXTS) & known)
    if collisions:
        save(PREP/'collision.json', {'collisions': collisions, 'history': history,
            'generation_calls': 0, 'ai_calls': 0, 'action': '認識・生成前に新しい一覧を別版で固定する'})
        raise ValueError('新しい文章が既使用文章と重複しています')
    assert len(set(TEXTS)) == 12
    prior_rows = [analyze(text) for text in sorted(known)]
    known_words = set().union(*(words(row) for row in prior_rows))
    known_contexts = set().union(*(triples(row) for row in prior_rows))
    models = {name: read(BUNDLE/(name+'.json')) for name in ('direct_non_neural', 'distilled_non_neural')}
    rows = []
    for i, text in enumerate(TEXTS):
        row = analyze(text)
        f0, speed = CHALLENGES[i % 4]
        unseen_words = words(row)-known_words
        unseen_contexts = triples(row)-known_contexts
        requests = {'neutral': {'requested_f0': 220., 'speed': 1.},
                    'challenge': {'requested_f0': f0, 'speed': speed}}
        targets = {condition: {name: predict(model, row, **requested) for name, model in models.items()}
                   for condition, requested in requests.items()}
        rows.append({'id': f'factorial-{i:02d}', **row, 'length': 'short' if i < 6 else 'long',
            'challenge_group': i % 4, 'requests': requests, 'targets': targets,
            'novelty': {'unseen_words': sorted(unseen_words),
                        'unseen_triples': sorted(unseen_contexts),
                        'total_words': len(words(row)), 'total_triples': len(triples(row))}})
    save(PREP/'protocol-draft.json', {'rows': rows, 'variants': list(AXES),
        'proposal_sha256': digest(REPO/'docs/plans/acoustic-control-factorial-proposal-2026-10-02.md'),
        'input_amendment_sha256': digest(REPO/'docs/plans/acoustic-control-factorial-input-amendment-2026-10-03.md'),
        'bundle_manifest_sha256': digest(BUNDLE/'manifest.json'), 'history': history,
        'known_text_count': len(known), 'source_hashes': source_hashes,
        'model_hashes': {name: digest(BUNDLE/(name+'.json')) for name in models},
        'input_contract': '利用者文章・音素・韻律・固定回帰のみ。教師音声・発話IDの検索を用いない',
        'generation_authorized': False, 'campaign_started': False,
        'planned_wavs': 120, 'planned_ai_calls': 240, 'planned_render_calls': 216,
        'held_axis_rule': 'F0単独は指定速度を厳密に維持。継続長単独は既定＋指定のhalf_toneを厳密に維持。実音響の干渉は実験後に別途測定',
        'solver_iterations': 1, 'acoustic_diagnostic_tolerance': {'f0_relative': .05, 'duration_relative': .10},
        'not_independent_final_confirmation': True, 'naturalness_qualification': False})
    replay = []
    held_axis_tests = []
    for oldrow in read(REV/'render-protocol.json')['rows']:
        for condition in ('neutral', 'challenge'):
            for variant, oldvariant in [('direct_joint', 'direct_non_neural'), ('distilled_joint', 'distilled_non_neural')]:
                a = read(REV/'render'/oldrow['id']/condition/(oldvariant+'.json'))
                b = read(REV/'refined'/oldrow['id']/condition/(oldvariant+'.json'))
                first = initial_settings(variant, a['requested'], a['target'], a['calibration'])
                final = refined_settings(variant, a['requested'], a['target'], first, a['measurement'])
                assert all(math.isclose(first[k], a['settings'][k], rel_tol=1e-12, abs_tol=1e-12) for k in ('speed', 'half_tone'))
                assert all(math.isclose(final[k], b['settings'][k], rel_tol=1e-12, abs_tol=1e-12) for k in ('speed', 'half_tone'))
                replay.append({'id': oldrow['id'], 'condition': condition, 'variant': variant,
                    'initial': first, 'refined': final, 'matches_frozen_settings': True})
                if variant != 'direct_joint':
                    continue
                for solo in ('direct_f0_only', 'direct_duration_only'):
                    first = initial_settings(solo, a['requested'], a['target'], a['calibration'])
                    # 両軸の測定量を変えても、固定軸の指令を補正しないことを確認する。
                    measured = {'active_seconds': a['target']['active_seconds']*1.4,
                                'f0_hz': a['target']['f0_hz']*.8}
                    final = refined_settings(solo, a['requested'], a['target'], first, measured)
                    held = 'speed' if solo == 'direct_f0_only' else 'half_tone'
                    assert first[held] == final[held]
                    corrupted = {**first, held: first[held]*1.01 if first[held] else .1}
                    try:
                        refined_settings(solo, a['requested'], a['target'], corrupted, measured)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('固定軸の変更を拒否しませんでした')
                    held_axis_tests.append({'id': oldrow['id'], 'condition': condition, 'variant': solo,
                        'held_axis': held, 'held_exactly': True, 'corruption_rejected': True})
    target = {'active_seconds': .1, 'f0_hz': 70.}
    base = {'active_seconds': 3., 'f0_hz': 600.}
    saturated = initial_settings('direct_joint', {'requested_f0': 220., 'speed': 1.}, target, base)
    assert saturated['speed'] == 2 and saturated['half_tone'] == -12 and saturated['saturated']
    invalid_rejected = 0
    for name, value in [('f0_hz', float('nan')), ('active_seconds', 0.)]:
        try:
            initial_settings('direct_joint', {'requested_f0': 220., 'speed': 1.}, {**target, name: value}, base)
        except ValueError:
            invalid_rejected += 1
    assert invalid_rejected == 2
    save(PREP/'static-tests.json', {'joint_replays': replay, 'held_axis_tests': held_axis_tests,
        'saturation_recorded': saturated, 'invalid_target_rejections': invalid_rejected,
        'no_new_audio': True, 'scope': '既存設定の再計算と指令の固定検査。実音響の軸独立性・内容・自然さは未検証'})
    for path in HISTORY:
        assert digest(path) == history[str(path.relative_to(REPO))]
    assert not list(ROOT.rglob('*.wav'))
    save(PREP/'readiness.json', {'prepared_rows': len(rows), 'text_collisions': collisions,
        'frontend_and_fixed_predictions_resolved': True, 'joint_replay_checks': len(replay),
        'held_axis_checks': len(held_axis_tests), 'synthesizer_entrypoints_blocked_during_preparation': True,
        'generation_calls': 0, 'ai_calls': 0, 'train_calls': 0, 'downloads': 0,
        'campaign_started': False, 'authorization_received': False,
        'seconds': time.time()-started, 'quality_goal_completed': False,
        'previous_goal_turn_classification': 'progress', 'current_turn_classification': 'progress',
        'fresh_resumed_turn': 3,
        'remaining': ['実音響での軸間干渉', '新12文・120音声の内容比較',
            '局所イベント・声質の改善', '知覚資格と独立最終確認']})
    print({'prepared_texts': len(rows), 'known_texts': len(known), 'joint_replays': len(replay),
           'held_axis_checks': len(held_axis_tests), 'new_audio': 0, 'new_ai_calls': 0})


if __name__ == '__main__':
    main()
