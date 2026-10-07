"""既存教師の有声区間と既定HMMの局所形状を比較する資料を固定する。"""
from pathlib import Path
import sys
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, BUNDLE, PILOT, EXT, REV, FRES, REPO, read, save, digest
sys.path.insert(0, str(EXT))
from teacher_alignment import align_saved
sys.path.insert(0, str(BUNDLE))
from japanese_frontend import analyze
sys.path.insert(0, str(PILOT/'.cache/packages'))
import pyworld
sys.path.insert(0, str(ROOT))
from local_renderer import StateEngine
from local_control import describe, ELIGIBLE, FEATURES

NEW = ['鳥が羽ばたく。', '雲が消える。', '薪を積む。', '波が砕ける。',
       '朝の市場で熟した桃を三つ選びました。', '雨上がりの歩道に小さな水たまりが残りました。',
       '棚の奥から見つけた本を窓辺で読みました。', '港へ向かう汽車の中で遠くの景色を眺めました。']


def collect(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            found.add(value['text'])
        found.update(t for t in value.get('tests', []) if isinstance(t, str))
        for v in value.values():
            found.update(collect(v))
    elif isinstance(value, list):
        for v in value:
            found.update(collect(v))
    return found


def main():
    b = LocalBudget()
    assert read(RESULT/'entry-audit.json')['passed']
    sources = read(REV/'targets.json')['rows']
    with b.job('setup', '学習・新8文・測定条件を実行前に固定', 2_000_000):
        old = read(FRES/'protocol.json')
        history = [REPO/p for p in old['history']]+[FRES/'protocol.json', FRES/'solo-runtime-audit/contract.json', REV/'runtime-audit/contract.json']
        known = set().union(*(collect(read(p)) for p in history))
        assert not set(NEW)&known
        challenges = [(180., .85), (180., 1.15), (260., .85), (260., 1.15)]
        rows = []
        for i, text in enumerate(NEW):
            f0, speed = challenges[i % 4]
            row = analyze(text)
            rows.append({**row, 'id': f'local-new-{i:02d}', 'split': 'diagnostic', 'length': 'short' if i < 4 else 'long',
                'challenge_group': i % 4, 'requests': {'neutral': {'requested_f0': 220., 'speed': 1.},
                'challenge': {'requested_f0': f0, 'speed': speed}}})
        selection = [s for s in sources if s['split'] == 'selection']
        selected = selection[:4]+selection[6:10]
        assert len(selected) == 8
        development = [{**analyze(s['text']), 'id': 'local-dev-'+str(i), 'source_id': s['id'], 'split': 'selection',
            'length': 'short' if i < 4 else 'long', 'challenge_group': i % 4,
            'requests': {'neutral': {'requested_f0': 220., 'speed': 1.},
                         'challenge': {'requested_f0': challenges[i % 4][0], 'speed': challenges[i % 4][1]}}}
            for i, s in enumerate(selected)]
        save(RESULT/'protocol.json', {'rows': rows, 'development_rows': development,
            'variants': ['native', 'direct_non_neural', 'neural', 'distilled_non_neural'],
            'history': {str(p.relative_to(REPO)): digest(p) for p in history}, 'text_collisions': [],
            'training_texts': [s['text'] for s in sources if s['split'] == 'development'],
            'selection_texts': [s['text'] for s in sources if s['split'] == 'selection'],
            'features': FEATURES, 'maximum_coefficients': 16, 'residual_half_tone_limit': 3.,
            'centering': '実行時は対象有声音素ごとの単純平均で発話内中心化後、最大絶対値3に縮尺。句別中心化はしない。',
            'target_rule': '母音・鼻音、DIO有声3フレーム以上かつ区間の50%以上。補間なし。教師内部区間は人手境界ではない。',
            'training_rule': {'ridge_lambda': 10., 'mlp_width': 16, 'mlp_hidden_layers': 2, 'mlp_steps': 500,
                              'learning_rate': .005, 'weight_decay': .001, 'seed': 20261003, 'utterance_equal_weight': True},
            'content_rule': '認識器別の全体・短・長・4指定群×通常/変更/合算21群で対照以下、欠損0。観測診断のみ。',
            'control_unchanged': ['global_speed', 'global_half_tone', 'state_durations', 'msd', 'spectral_streams', 'lf0_dynamic_means'],
            'source_hashes': {n: digest(ROOT/n) for n in ('local_control.py', 'local_renderer.py', 'shim.c', 'local_hts-v2.dylib', 'prepare_data.py')},
            'no_optimization_after_asr': True, 'independent_final_confirmation': False, 'quality_certified': False})
    output = []
    for s in sources:
        row = analyze(s['text'])
        teacher_path = Path(s['source'])
        teacher = read(teacher_path)
        base = PILOT if 'nas-pilot' in str(teacher_path) else EXT
        wav = base/teacher['wav']
        assert digest(wav) == teacher['wav_sha256'] == s['wav_sha256']
        try:
            intervals, gaps, equivalents = align_saved(row, teacher)
        except ValueError as exc:
            output.append({**s, 'status': 'unavailable', 'error': str(exc)})
            continue
        fs, audio = wavfile.read(wav)
        audio = audio.astype(float)/(32768 if audio.dtype == np.int16 else 1)
        f0, times = pyworld.dio(audio, fs, f0_floor=70., f0_ceil=800., frame_period=5.)
        f0 = pyworld.stonemask(audio, f0, times, fs)
        target_path = RESULT/'training-inputs'/s['split']/(s['id']+'.json')
        with b.job('render', '教師対照用HMM状態列/'+s['split']+'/'+s['id'], 1_000_000):
            with StateEngine(row, BUNDLE/'mei_normal.htsvoice') as engine:
                snapshot = engine.snapshot()
            descriptions = [d for d in describe(row) if d['phone'] not in ('sil', 'pau')]
            assert len(descriptions) == len(intervals)
            usable = []
            for d, interval in zip(descriptions, intervals):
                assert d['phone'] == interval['phone'] or (d['phone'] == 'cl' and interval['phone'] == 'Q')
                inside = (times >= interval['start']) & (times < interval['end'])
                voiced = f0[inside & (f0 >= 70) & (f0 <= 800)]
                state_indices = [j for j in range(d['label_index']*5, (d['label_index']+1)*5) if snapshot['msd'][j] > .5]
                if d['phone'] not in ELIGIBLE or len(voiced) < 3 or len(voiced) < inside.sum()*.5 or not state_indices:
                    continue
                baseline = np.average([snapshot['means'][1][j][0] for j in state_indices],
                                      weights=[snapshot['duration'][j] for j in state_indices])
                usable.append({'label_index': d['label_index'], 'phone': d['phone'], 'x': d['x'],
                    'teacher_log_f0': float(np.log(np.median(voiced))), 'baseline_log_f0': float(baseline),
                    'voiced_frames': len(voiced), 'interval_frames': int(inside.sum())})
            if len(usable) >= 3:
                teacher_center = np.mean([p['teacher_log_f0'] for p in usable])
                native_center = np.mean([p['baseline_log_f0'] for p in usable])
                for p in usable:
                    p['target_half_tone'] = float(((p['teacher_log_f0']-teacher_center)-(p['baseline_log_f0']-native_center))*12/np.log(2))
                status = 'available'
            else:
                status = 'unavailable'
            record = {'id': s['id'], 'text': s['text'], 'split': s['split'], 'status': status, 'phones': usable,
                'teacher_source_sha256': digest(teacher_path), 'teacher_wav_sha256': digest(wav), 'equivalences': equivalents,
                'snapshot': snapshot, 'row': row, 'not_manual_boundary': True, 'baseline_f0_source': 'HMM状態LF0平均の継続長加重',
                'warning': '状態分布平均と波形DIOは同じ測定量ではない。教師内部区間と実音素境界の一致は未資格。'}
            save(target_path, record)
        output.append({k: record[k] for k in ('id', 'text', 'split', 'status')})
        print(s['id'], status, len(usable), flush=True)
    with b.job('audit', '訓練入力の独立文数と前段を監査', 1_000_000):
        counts = {split: sum(r['split'] == split and r['status'] == 'available' for r in output) for split in ('development', 'selection')}
        save(RESULT/'training-input-manifest.json', {'rows': output, 'available_utterances': counts,
            'source_targets_sha256': digest(REV/'targets.json'), 'quality_certified': False})
        assert counts['development'] >= 12 and counts['selection'] >= 6
    print(counts)


if __name__ == '__main__':
    main()
