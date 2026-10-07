"""4方式を同じHMM・全体指令で生成し、局所LF0以外の状態不変を保存する。"""
import math
import sys
import time
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, BUNDLE, PILOT, read, save, digest
sys.path.insert(0, str(BUNDLE))
from acoustics import evaluate
from acoustic_control import measure_wide
sys.path.insert(0, str(PILOT/'.cache/packages'))
import pyworld
sys.path.insert(0, str(ROOT))
from local_renderer import StateEngine
from local_control import deltas, linear_predict


def neural_predictor():
    import torch
    from torch import nn
    model = read(RESULT/'models/neural.json')
    assert digest(RESULT/'models/neural.pt') == model['weights_sha256']
    net = nn.Sequential(nn.Linear(16, 16), nn.Tanh(), nn.Linear(16, 16), nn.Tanh(), nn.Linear(16, 1))
    net.load_state_dict(torch.load(RESULT/'models/neural.pt', map_location='cpu', weights_only=True))
    net.eval()
    torch.set_num_threads(2)
    def predict(x):
        z = (x-np.array(model['x_mean']))/np.array(model['x_scale'])
        with torch.no_grad():
            return net(torch.tensor(z, dtype=torch.float32)).flatten().numpy()
    return predict


def main():
    b = LocalBudget()
    p = read(RESULT/'protocol.json')
    comparison = read(RESULT/'model-comparison.json')
    for name, sha in comparison['model_hashes'].items():
        assert digest(RESULT/'models'/name) == sha
    for name, sha in p['source_hashes'].items():
        assert digest(ROOT/name) == sha
    predictors = {v: (lambda x, m=read(RESULT/'models'/(v+'.json')): linear_predict(m, x))
                  for v in ('direct_non_neural', 'distilled_non_neural')}
    predictors['neural'] = neural_predictor()
    with b.job('setup', '未知生成前にレンダラー・係数・全体指令を固定', 1_000_000):
        save(RESULT/'render-contract.json', {'protocol_sha256': digest(RESULT/'protocol.json'),
            'model_comparison_sha256': digest(RESULT/'model-comparison.json'),
            'source_hashes': {f.name: digest(f) for f in ROOT.glob('*.py')},
            'planned_render_calls': 128, 'planned_diagnostic_wavs': 64, 'no_retries': True,
            'no_optimization_after_asr': True, 'half_tone': '12log2(requested_f0/220)',
            'speed': '利用者指定のまま', 'runtime_neural_variants': ['neural']})
    generated = []
    for row in p['development_rows']+p['rows']:
        for condition, requested in row['requests'].items():
            for variant in p['variants']:
                path = RESULT/'render'/row['id']/condition/(variant+'.json')
                if path.exists():
                    raise FileExistsError('生成結果を上書きしません')
                settings = {'speed': requested['speed'], 'half_tone': 12*math.log2(requested['requested_f0']/220)}
                label = str(path.relative_to(RESULT))
                started = time.monotonic()
                result = {k: row[k] for k in ('text', 'length', 'challenge_group', 'split')}
                result.update(id=row['id']+'/'+condition+'/'+variant, condition=condition, variant=variant,
                    requested=requested, settings=settings, status='failed', synthesis_calls=1,
                    runtime_neural=variant == 'neural', quality_certified=False)
                try:
                    with b.job('render', label, 2_000_000):
                        with StateEngine(row, BUNDLE/'mei_normal.htsvoice', **settings) as engine:
                            before = engine.snapshot()
                            if variant == 'native':
                                correction, phones = np.zeros(engine.count), []
                            else:
                                correction, phones = deltas(row, before, predictors[variant])
                            engine.modify(correction)
                            after = engine.snapshot()
                            assert before['duration'] == after['duration'] and before['msd'] == after['msd']
                            assert before['means'][0] == after['means'][0] and before['means'][2] == after['means'][2]
                            assert all(a[1:] == z[1:] for a, z in zip(before['means'][1], after['means'][1]))
                            audio, lf0 = engine.generate()
                        peak = float(np.max(abs(audio)))
                        gain = min(1., .95/peak) if peak else 1.
                        audio = (audio*gain).astype(np.float32)
                        evaluation = evaluate(audio, {}, 24000)
                        measurement = measure_wide(audio)
                        f0, times = pyworld.dio(audio.astype(float), 24000, f0_floor=70., f0_ceil=800., frame_period=5.)
                        f0 = pyworld.stonemask(audio.astype(float), f0, times, 24000)
                        measurement.update(dio_f0_hz=float(np.median(f0[f0 > 0])) if np.any(f0 > 0) else None,
                                           dio_voiced_fraction=float(np.mean(f0 > 0)))
                        assert evaluation['E0_pass']
                        path.parent.mkdir(parents=True, exist_ok=True)
                        wav = path.with_suffix('.wav')
                        wavfile.write(wav, 24000, audio)
                        np.savez(path.with_suffix('.npz'), generated_lf0=lf0, state_deltas=correction)
                        result.update(status='completed', measurement=measurement, evaluation=evaluation,
                            changed_state_count=int(np.sum(correction != 0)), phone_residuals=phones,
                            maximum_abs_half_tone=float(np.max(abs(correction))), raw_peak=peak, output_gain=gain,
                            wav=str(wav.relative_to(ROOT)), wav_sha256=digest(wav),
                            internal_unchanged=['duration', 'msd', 'spectrum', 'aperiodicity', 'lf0_dynamic_means'],
                            seconds=time.monotonic()-started)
                        save(path, result)
                except Exception as exc:
                    result.update(error=repr(exc), seconds=time.monotonic()-started)
                    if not path.exists():
                        save(path, result)
                generated.append(result)
            print(row['id'], condition, '完了', flush=True)
    diagnostic = [r for r in generated if r['split'] == 'diagnostic']
    save(RESULT/'render-manifest.json', {'rows': diagnostic, 'development_rows': [r for r in generated if r['split'] == 'selection'],
        'protocol_sha256': digest(RESULT/'protocol.json'), 'completed': sum(r['status'] == 'completed' for r in diagnostic),
        'planned_wavs': 64, 'no_retries': True})


if __name__ == '__main__':
    main()
