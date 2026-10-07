"""生成結果を見る前に分割と制御の検証範囲を保存する。"""
import json
import sys
from pathlib import Path
from budget import Budget, ROOT, RESULT, save, digest

OLD = ROOT.parent / 'autonomous-speech-synthesis'
sys.path.insert(0, str(OLD))
from japanese_frontend import analyze

TEXTS = {
    'development': ['赤い傘。', '鳥が鳴く。', '犬が走る。', '山を見る。',
                    '豆を煮る。', '星が光る。', '窓を閉める。', '紙を折る。',
                    '坂を登る。', '笛を吹く。', '音を聞く。', '歌を歌う。'],
    'selection': ['白い雲。', '波が寄せる。', '箱を運ぶ。', '糸を結ぶ。',
                  '旗が揺れる。', '道を進む。'],
    'audit': ['小さな鈴。', '船が戻る。', '桃を包む。', '鍵を探す。',
              '砂を集める。', '声が響く。'],
}


def main():
    budget = Budget()
    budget.initialize()
    with budget.job('setup', '事前分割・制御schema', 2_000_000):
        rows = []
        for split, texts in TEXTS.items():
            for i, text in enumerate(texts):
                rows.append({'id': f'{split}-{i:02d}', 'split': split, **analyze(text)})
        save(RESULT / 'splits.json', {'rows': rows, 'created_before_generation': True,
             'independence_unit': '文章。共通の助詞・音素は含むため全語彙非重複ではない',
             'old_confirmation_access': False,
             'limitations': '監査6文は小規模な実現可能性検査。日本語全体の品質保証ではない。'})
        save(RESULT / 'control-schema.json', {
            'version': 1, 'renderer': 'VTL JD3',
            'initial_scope': '継続長と低次元F0軌跡。閉鎖・声質の拡張は比較結果で判断',
            'inputs': ['音素', '前後の音素特徴', 'モーラ位置', 'アクセント', '句位置', '指定速度', '指定F0'],
            'forbidden_runtime_inputs': ['参照音声', '教師音声', 'SSL特徴', '発話ID', '話者埋め込み'],
            'outputs': ['音素継続長', 'F0標的'],
            'final_models': ['固定サイズの回帰係数', '上限を固定した決定木', '補間規則'],
            'controls_generated_at_runtime': True,
            'storing_per_utterance_trajectories_in_final_model': False,
            'frontend_hash': digest(OLD / 'japanese_frontend.py')})
        print(json.dumps({'rows': len(rows), 'split_counts': {k: len(v) for k,v in TEXTS.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
