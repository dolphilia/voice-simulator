"""旧封印から固定資産を再利用し、未知文・語彙・音素文脈を生成前に固定する。"""
import shutil
import sys
from campaign import LocalBudget, ROOT, RESULT, REPO, BUNDLE, LRES, read, save, digest
sys.path.insert(0, str(BUNDLE))
from japanese_frontend import analyze
from local_control import FEATURES
from export_runtime import collect
NEW = ['鹿が跳ねる。', '霧が晴れる。', '蓋を外す。', '雪が積もる。',
       '坂の途中で立ち止まり遠くの海を見ました。', '小さな灯りを頼りに暗い廊下を進みました。',
       '庭に置いたかごから赤いりんごを取りました。', '夕日が沈むころ湖のほとりへ着きました。']
RUNTIME = ['雫が落ちる。', '小さな丘の向こうから白い船が見えました。']

def vocabulary(row):
    return {f['orig'] for f in row['features'] if f['pos'] != '記号'}

def triples(row):
    p = ['sil', *row['phonemes'], 'sil']
    return {tuple(p[i:i+3]) for i in range(len(p)-2)}

def main():
    with LocalBudget().job('setup', '係数・全履歴・新文・射影修正を固定', 3_000_000):
        previous = read(LRES/'protocol.json')
        history = [REPO/p for p in previous['history']] + [LRES/'protocol.json', LRES/'runtime-audit/contract.json']
        known = set().union(*(collect(read(p)) for p in history))
        assert not set(NEW+RUNTIME)&known and len(set(NEW+RUNTIME)) == 10
        oldrows = [analyze(t) for t in sorted(known)]
        words = set().union(*(vocabulary(r) for r in oldrows))
        contexts = set().union(*(triples(r) for r in oldrows))
        challenges = [(180., .85), (180., 1.15), (260., .85), (260., 1.15)]
        rows, novelty = [], []
        for i, text in enumerate(NEW+RUNTIME):
            row = analyze(text)
            novelty.append({'text': text, 'new_words': sorted(vocabulary(row)-words),
                'new_phoneme_triples': sorted(triples(row)-contexts), 'total_unique_words': len(vocabulary(row)),
                'total_unique_phoneme_triples': len(triples(row)), 'exact_collision': False})
            if i >= 8:
                continue
            f0, speed = challenges[i%4]
            rows.append({**row, 'id': f'projection-new-{i:02d}', 'split': 'diagnostic',
                'length': 'short' if i < 4 else 'long', 'challenge_group': i%4,
                'requests': {'neutral': {'requested_f0': 220., 'speed': 1.}, 'challenge': {'requested_f0': f0, 'speed': speed}}})
        save(RESULT/'novelty-audit.json', {'old_unique_texts': len(known), 'rows': novelty,
            'runtime_texts_prechecked': RUNTIME, 'no_wave_generation': True})
        save(RESULT/'protocol.json', {'rows': rows, 'development_rows': [],
            'variants': previous['variants'], 'history': {str(p.relative_to(REPO)): digest(p) for p in history},
            'features': FEATURES, 'content_rule': previous['content_rule'], 'control_unchanged': previous['control_unchanged'],
            'centering': '予測を発話内中心化してから最大絶対値3に一様縮尺。先行クリップなし。',
            'source_hashes': {n: digest(ROOT/n) for n in ('local_control.py','local_renderer.py','centered_projection.py','shim.c','local_hts-v2.dylib','prepare.py')},
            'only_changed_mechanism': '局所半音残差の射影順', 'new_training_calls': 0,
            'no_optimization_after_asr': True, 'independent_final_confirmation': False, 'quality_certified': False})
        (RESULT/'models').mkdir(exist_ok=False)
        hashes = read(LRES/'model-comparison.json')['model_hashes']
        for name, sha in hashes.items():
            assert digest(LRES/'models'/name) == sha
            shutil.copyfile(LRES/'models'/name, RESULT/'models'/name)
        save(RESULT/'model-comparison.json', {'model_hashes': hashes, 'reused_from': str(LRES.relative_to(REPO)),
            'previous_comparison_sha256': digest(LRES/'model-comparison.json'),
            'old_losses_not_current_projection_quality': True, 'new_training_calls': 0, 'no_model_selection_from_asr': True})
        provenance = read(LRES/'source-provenance.json')
        save(RESULT/'source-provenance.json', {**provenance, 'download_bytes': 0,
            'reused_source_provenance_sha256': digest(LRES/'source-provenance.json'), 'new_source_acquisition': False})
    print('固定モデル、新8文と単独実行2文、履歴', len(known), '文を固定', flush=True)

if __name__ == '__main__':
    main()
