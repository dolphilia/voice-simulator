"""教師の平均的声高・速度を除き、文脈補正をHMMへ移す別版。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from campaign import ExtensionBudget, ROOT, PRIOR, RESULT, save, digest
sys.path.insert(0, str(PRIOR/'hts-bundle-v2'))
from hts_core import render_hts, measure
from shared_control import predict
from renderer import baseline
from japanese_frontend import analyze
from acoustics import evaluate

TEXTS = ['黄色い花が川沿いに咲いています。', '弟は新しい靴を履いて出かけました。',
         '隣の部屋から静かな音楽が聞こえます。', '野菜を洗ってから小さく切ります。',
         '坂の途中で自転車を止めました。', '祖母は暖かいお茶を二杯飲みました。',
         '遠くの空に黒い鳥が飛んでいます。', '明日の朝までに荷物をまとめてください。']


def correction(model, analysis):
    d, f, bounds = predict(model, analysis)
    bd, bf = baseline(analysis)
    # 同一の基準韻律との対数比を発話単位に集約する。
    return {'log_duration_ratio': float(np.log(sum(d)/sum(bd))),
            'log_f0_ratio': float(np.sum(d*np.log(f))/sum(d)-np.sum(bd*np.log(bf))/sum(bd)),
            'phone_bounds': bounds}


def settings(model, analysis, center, requested):
    c = correction(model, analysis)
    speed = requested['speed']*np.exp(-(c['log_duration_ratio']-center['log_duration_ratio']))
    shift = 12*np.log2(requested['requested_f0']/220)+12/np.log(2)*(c['log_f0_ratio']-center['log_f0_ratio'])
    return {'speed': float(np.clip(speed, .6, 1.6)), 'half_tone': float(np.clip(shift, -6, 6)),
            'unbounded_speed': float(speed), 'unbounded_half_tone': float(shift), 'correction': c,
            'saturated': bool(not .6 <= speed <= 1.6 or not -6 <= shift <= 6)}


def prepare(budget):
    target = RESULT/'relative-protocol.json'
    if target.exists():
        return json.loads(target.read_text())
    with budget.job('setup', '相対移植の別版と未知8文を生成前に固定', 1000000):
        old = json.loads((PRIOR/'splits.json').read_text())['rows']
        known = {r['text'] for r in old}
        for path in [RESULT/'protocol.json', PRIOR/'hts-transfer/protocol.json']:
            known.update(r['text'] for r in json.loads(path.read_text())['rows'])
        for name in ['runtime-audit/contract.json', 'hts-runtime-audit-v2/contract.json']:
            known.update(t if isinstance(t, str) else t['text'] for t in json.loads((PRIOR/name).read_text())['tests'])
        if len(set(TEXTS)) != 8 or set(TEXTS)&known:
            raise ValueError('別版未知文の重複')
        development = [r for r in old if r['split'] == 'development']
        if len(development) != 12:
            raise ValueError('旧学習集合の件数不一致')
        centers = {}
        for variant in ['direct_non_neural', 'distilled_non_neural']:
            model = json.loads((PRIOR/'hts-bundle-v2'/(variant+'.json')).read_text())
            corrections = [correction(model, row) for row in development]
            centers[variant] = {key: float(np.mean([r[key] for r in corrections]))
                                for key in ['log_duration_ratio', 'log_f0_ratio']}
        conditions = [(180., .85), (180., 1.15), (260., .85), (260., 1.15)]
        rows = []
        for i, text in enumerate(TEXTS):
            a = analyze(text)
            if not 1 <= len(a['phonemes']) <= 120:
                raise ValueError('音素長が範囲外')
            f0, speed = conditions[i%4]
            rows.append({'id': f'relative-{i:02d}', **a, 'challenge': {'requested_f0': f0, 'speed': speed}})
        protocol = {'rows': rows, 'centers': centers, 'center_rows': [r['id'] for r in development],
                    'models': ['native', 'direct_non_neural', 'distilled_non_neural'],
                    'formula': '旧開発12文の対数補正平均を引く。指定F0比と速度を外から掛ける。波形校正なし',
                    'adaptive_reason': '主比較16文での絶対量移植は内容を悪化。話者・速度の平均差を除く単独機構比較',
                    'no_tuning_on_new8': True, 'render_calls': 48, 'asr_calls': 48,
                    'asr_scope': '変更条件のみ、8文×3方式×2認識器。通常条件24音声は応答測定用',
                    'primary': '両ASR別々に変更条件の全8文および条件別2文でnativeよりかなCERが悪化しない',
                    'engineering': '通常条件からF0相対5%、活動長相対10%。知覚認定ではない',
                    'f0_semantics': '220Hzを基準にした相対指定。HMM絶対F0を保証しない',
                    'naturalness_certification': False}
        save(target, protocol)
    return protocol


def main():
    budget = ExtensionBudget()
    protocol = prepare(budget)
    bundle = PRIOR/'hts-bundle-v2'
    for name, sha in json.loads((bundle/'manifest.json').read_text())['files'].items():
        if digest(bundle/name) != sha:
            raise ValueError('固定資産のハッシュ不一致')
    for row in protocol['rows']:
        for condition in ['neutral', 'challenge']:
            requested = {'requested_f0': 220., 'speed': 1.} if condition == 'neutral' else row['challenge']
            for variant in protocol['models']:
                path = RESULT/'relative'/row['id']/condition/(variant+'.json')
                if path.exists():
                    record = json.loads(path.read_text())
                    if digest(ROOT/record['wav']) != record['wav_sha256']:
                        raise ValueError('既存波形の変更')
                    continue
                with budget.job('render', '相対移植/'+row['id']+'/'+condition+'/'+variant, 2000000):
                    start = time.monotonic()
                    if variant == 'native':
                        controls = {'speed': requested['speed'], 'half_tone': float(12*np.log2(requested['requested_f0']/220)), 'saturated': False}
                    else:
                        model = json.loads((bundle/(variant+'.json')).read_text())
                        controls = settings(model, row, protocol['centers'][variant], requested)
                    audio = render_hts(row, bundle/'mei_normal.htsvoice', controls['speed'], controls['half_tone'])
                    peak = float(np.max(abs(audio)))
                    gain = min(1., .95/peak) if peak else 1.
                    audio = (audio*gain).astype(np.float32)
                    evaluation = evaluate(audio, {}, 24000)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    wav = path.with_suffix('.wav')
                    if wav.exists():
                        raise FileExistsError('未記録の波形を上書きしません')
                    wavfile.write(wav, 24000, audio)
                    save(path, {'id': row['id'], 'text': row['text'], 'condition': condition, 'variant': variant,
                                'requested': requested, 'settings': controls, 'measurement': measure(audio),
                                'evaluation': evaluation, 'raw_peak': peak, 'output_gain': gain,
                                'wav': str(wav.relative_to(ROOT)), 'wav_sha256': digest(wav),
                                'seconds': time.monotonic()-start, 'runtime_neural': False, 'synthesis_calls': 1})
                print(row['id'], condition, variant, evaluation['E0_pass'], flush=True)


if __name__ == '__main__':
    main()
