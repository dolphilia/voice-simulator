"""残りの12認識で特徴外挿の抑制を切り分ける。新しい2文だけの診断。"""
import json
import sys
import numpy as np
from scipy.io import wavfile
from campaign import ExtensionBudget, ROOT, PRIOR, RESULT, save, digest
sys.path.insert(0, str(PRIOR/'hts-bundle-v2'))
from shared_control import features, decode
from renderer import baseline
from hts_core import render_hts, measure
from acoustics import evaluate
from japanese_frontend import analyze
from relative import settings


def clipped_correction(model, row, low, high):
    x, _, _ = features(row)
    clipped = np.clip(x, low, high)
    y = ((clipped-np.array(model['x_mean']))/np.array(model['x_scale']))@np.array(model['coefficients'])
    y = y*np.array(model['y_scale'])+np.array(model['y_mean'])
    d, f, bounds = decode(row, y)
    bd, bf = baseline(row)
    return {'log_duration_ratio': float(np.log(sum(d)/sum(bd))),
            'log_f0_ratio': float(np.sum(d*np.log(f))/sum(d)-np.sum(bd*np.log(bf))/sum(bd)),
            'clipped_values': int(np.count_nonzero(x != clipped)), 'total_values': int(x.size), 'phone_bounds': bounds}


def main():
    budget = ExtensionBudget()
    bundle = PRIOR/'hts-bundle-v2'
    model = json.loads((bundle/'direct_non_neural.json').read_text())
    training = [r for r in json.loads((PRIOR/'splits.json').read_text())['rows'] if r['split'] == 'development']
    x = np.concatenate([features(r)[0] for r in training])
    low, high = x.min(axis=0), x.max(axis=0)
    relative_protocol = json.loads((RESULT/'relative-protocol.json').read_text())
    center = relative_protocol['centers']['direct_non_neural']
    target = RESULT/'bounded-protocol.json'
    if not target.exists():
        with budget.job('setup', '最後の12認識枠を特徴外挿の2文診断に固定', 1000000):
            texts = ['本棚の上に小さな時計を置きました。', '姉は赤い自転車で学校へ行きます。']
            known = {r['text'] for r in json.loads((PRIOR/'splits.json').read_text())['rows']}
            for path in [RESULT/'protocol.json', RESULT/'relative-protocol.json', PRIOR/'hts-transfer/protocol.json']:
                known.update(r['text'] for r in json.loads(path.read_text())['rows'])
            for name in ['runtime-audit/contract.json', 'hts-runtime-audit-v2/contract.json']:
                known.update(t if isinstance(t, str) else t['text'] for t in json.loads((PRIOR/name).read_text())['tests'])
            if set(texts)&known:
                raise ValueError('外挿診断の文章が重複')
            save(target, {'rows': [{'id': f'bounded-{i:02d}', **analyze(text)} for i, text in enumerate(texts)],
                          'models': ['native', 'relative_direct', 'bounded_direct'], 'center': center,
                          'feature_low': low.tolist(), 'feature_high': high.tolist(),
                          'training_phone_length': [min(len(r['phonemes']) for r in training), max(len(r['phonemes']) for r in training)],
                          'method': '固定回帰への各特徴を旧開発12文の最小・最大へ制限。係数と平均補正は同じ',
                          'selection_reason': '蒸留版の優位性が確認できず、直接非ニューラルの外挿対策を診断',
                          'render_calls': 6, 'ai_calls': 12, 'no_tuning_on_new2': True,
                          'scope': '原因を調べる2文の対照。一般化や知覚的品質の合否には使わない'})
    protocol = json.loads(target.read_text())
    if protocol['feature_low'] != low.tolist() or protocol['feature_high'] != high.tolist():
        raise ValueError('固定特徴範囲が変わりました')
    for row in protocol['rows']:
        for variant in protocol['models']:
            path = RESULT/'bounded'/row['id']/(variant+'.json')
            if path.exists():
                old = json.loads(path.read_text())
                if digest(ROOT/old['wav']) != old['wav_sha256']:
                    raise ValueError('既存波形の変更')
                continue
            with budget.job('render', row['id']+'/'+variant, 2000000):
                if variant == 'native':
                    controls = {'speed': 1., 'half_tone': 0., 'saturated': False}
                elif variant == 'relative_direct':
                    controls = settings(model, row, center, {'requested_f0': 220., 'speed': 1.})
                else:
                    c = clipped_correction(model, row, low, high)
                    speed = np.exp(-(c['log_duration_ratio']-center['log_duration_ratio']))
                    shift = 12/np.log(2)*(c['log_f0_ratio']-center['log_f0_ratio'])
                    controls = {'speed': float(np.clip(speed, .6, 1.6)), 'half_tone': float(np.clip(shift, -6, 6)),
                                'unbounded_speed': float(speed), 'unbounded_half_tone': float(shift), 'correction': c,
                                'saturated': bool(not .6 <= speed <= 1.6 or not -6 <= shift <= 6)}
                audio = render_hts(row, bundle/'mei_normal.htsvoice', controls['speed'], controls['half_tone'])
                peak = float(np.max(abs(audio)))
                gain = min(1., .95/peak) if peak else 1.
                audio = (audio*gain).astype(np.float32)
                path.parent.mkdir(parents=True, exist_ok=True)
                wav = path.with_suffix('.wav')
                if wav.exists():
                    raise FileExistsError('未記録波形を上書きしません')
                wavfile.write(wav, 24000, audio)
                save(path, {'id': row['id'], 'text': row['text'], 'variant': variant, 'condition': 'neutral',
                            'settings': controls, 'measurement': measure(audio), 'evaluation': evaluate(audio, {}, 24000),
                            'wav': str(wav.relative_to(ROOT)), 'wav_sha256': digest(wav),
                            'raw_peak': peak, 'output_gain': gain, 'runtime_neural': False, 'synthesis_calls': 1})
                print(row['id'], variant, controls['speed'], flush=True)


if __name__ == '__main__':
    main()
