"""固定した未知文でHMMと固定回帰の制御応答を測定する。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from campaign import ExtensionBudget, ROOT, PRIOR, RESULT, save, digest
sys.path.insert(0, str(PRIOR/'hts-bundle-v2'))
from hts_core import render_hts, measure
from shared_control import predict
from acoustics import evaluate


def main():
    budget = ExtensionBudget()
    protocol = json.loads((RESULT/'protocol.json').read_text())
    bundle = PRIOR/'hts-bundle-v2'
    for name, sha in json.loads((bundle/'manifest.json').read_text())['files'].items():
        if digest(bundle/name) != sha:
            raise ValueError('固定資産のハッシュ不一致: '+name)
    for row in protocol['rows']:
        for condition in protocol['conditions']:
            requested = protocol['neutral'] if condition == 'neutral' else row['challenge']
            for variant in protocol['models']:
                target = RESULT/'render'/row['id']/condition/(variant+'.json')
                if target.exists():
                    rec = json.loads(target.read_text())
                    if digest(ROOT/rec['wav']) != rec['wav_sha256']:
                        raise ValueError('既存出力のハッシュ不一致')
                    continue
                calls = 1 if variant == 'native' else 2
                with budget.job('render', '/'.join([row['id'], condition, variant]), 3000000, count=calls):
                    start = time.monotonic()
                    base_measurement = None
                    if variant == 'native':
                        settings = {'speed': requested['speed'], 'half_tone': float(12*np.log2(requested['requested_f0']/220)), 'saturated': False}
                    else:
                        model = json.loads((bundle/(variant+'.json')).read_text())
                        base_measurement = measure(render_hts(row, bundle/'mei_normal.htsvoice'))
                        d, f, bounds = predict(model, row, **requested)
                        desired = {'active_seconds': float(sum(d)), 'f0_hz': float(np.exp(np.sum(d*np.log(f))/sum(d)))}
                        speed = base_measurement['active_seconds']/desired['active_seconds']
                        half_tone = float(12*np.log2(desired['f0_hz']/base_measurement['f0_hz']))
                        settings = {'speed': float(np.clip(speed, .6, 1.6)), 'half_tone': float(np.clip(half_tone, -6, 6)),
                                    'unbounded_speed': speed, 'unbounded_half_tone': half_tone, 'desired': desired,
                                    'phone_bounds': bounds, 'saturated': bool(not .6 <= speed <= 1.6 or not -6 <= half_tone <= 6)}
                    audio = render_hts(row, bundle/'mei_normal.htsvoice', settings['speed'], settings['half_tone'])
                    peak = float(np.max(abs(audio)))
                    gain = min(1., .95/peak) if peak else 1.
                    audio = (audio*gain).astype(np.float32)
                    evaluation = evaluate(audio, {}, 24000)
                    measurement = measure(audio)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    wav = target.with_suffix('.wav')
                    if wav.exists():
                        raise FileExistsError('未記録の波形を上書きしません')
                    wavfile.write(wav, 24000, audio)
                    save(target, {'id': row['id'], 'text': row['text'], 'variant': variant, 'condition': condition,
                                  'requested': requested, 'settings': settings, 'base_measurement': base_measurement,
                                  'measurement': measurement, 'evaluation': evaluation, 'raw_peak': peak, 'output_gain': gain,
                                  'wav': str(wav.relative_to(ROOT)), 'wav_sha256': digest(wav),
                                  'synthesis_calls': calls, 'seconds': time.monotonic()-start, 'runtime_neural': False})
                print(row['id'], condition, variant, evaluation['E0_pass'], settings['saturated'], flush=True)


if __name__ == '__main__':
    main()
