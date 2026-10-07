"""F0範囲の不足を別の非学習解析器で診断する。主比較を改訂しない。"""
import json
import sys
import numpy as np
from scipy.io import wavfile
from campaign import ExtensionBudget, ROOT, PILOT, PRIOR, RESULT, save, digest
sys.path.insert(0, str(PILOT/'.cache/packages'))
import pyworld
sys.path.insert(0, str(PRIOR/'hts-bundle-v2'))
from acoustics import estimate_f0


def measure(audio, fs):
    x = np.asarray(audio, dtype=np.float64)
    f0, t = pyworld.dio(x, fs, f0_floor=70., f0_ceil=800., frame_period=5.)
    f0 = pyworld.stonemask(x, f0, t, fs)
    voiced = f0[f0 > 0]
    return {'f0_hz': float(np.median(voiced)) if len(voiced) else None,
            'voiced_fraction': float(len(voiced)/len(f0)),
            'above_450_fraction_of_voiced': float(np.mean(voiced > 450)) if len(voiced) else None}


def main():
    budget = ExtensionBudget()
    protocol = RESULT/'pitch-audit-protocol.json'
    if not protocol.exists():
        with budget.job('setup', '広いF0範囲の補助診断を固定', 100000):
            save(protocol, {'method': 'WORLD DIO + StoneMask', 'f0_floor': 70, 'f0_ceil': 800, 'frame_period_ms': 5,
                            'selfcheck': {'frequencies': [80, 180, 220, 360, 450, 600, 750], 'signals': ['sine', 'harmonics'], 'seconds': 1},
                            'scope': '範囲と倍音の補助診断のみ。独立な日本語正解F0の資格ではない',
                            'primary_unchanged': True, 'source': 'https://github.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder'})
    for hz in [80, 180, 220, 360, 450, 600, 750]:
        for kind in ['sine', 'harmonics']:
            target = RESULT/'pitch-audit/selfcheck'/f'{hz}-{kind}.json'
            if target.exists():
                continue
            with budget.job('render', f'F0測定用既知信号/{hz}/{kind}', 300000):
                t = np.arange(24000)/24000
                audio = .2*np.sin(2*np.pi*hz*t)
                if kind == 'harmonics':
                    audio += .1*np.sin(4*np.pi*hz*t)+.05*np.sin(6*np.pi*hz*t)
                dio = measure(audio, 24000)
                acf450, conf450 = estimate_f0(audio, 24000)
                acf800, conf800 = estimate_f0(audio, 24000, maximum=800)
                save(target, {'expected_f0': hz, 'signal': kind, 'dio': dio,
                              'dio_relative_error': abs(dio['f0_hz']/hz-1) if dio['f0_hz'] else None,
                              'acf450': acf450, 'acf800': acf800, 'confidence450': conf450, 'confidence800': conf800})
    for source in ['render', 'relative', 'teacher']:
        for path in sorted((RESULT/source).rglob('*.json')):
            record = json.loads(path.read_text())
            if 'wav' not in record:
                continue
            target = RESULT/'pitch-audit'/source/path.relative_to(RESULT/source)
            wav = ROOT/record['wav']
            sha = digest(wav)
            if sha != record['wav_sha256']:
                raise ValueError('F0診断対象のハッシュ不一致')
            if target.exists():
                if json.loads(target.read_text())['wav_sha256'] != sha:
                    raise ValueError('F0診断済み波形の変更')
                continue
            with budget.job('audit', 'F0補助診断/'+str(path.relative_to(RESULT)), 300000):
                fs, raw = wavfile.read(wav)
                audio = raw.astype(float)/(32768 if raw.dtype == np.int16 else 1)
                dio = measure(audio, fs)
                acf800, confidence = estimate_f0(audio, fs, maximum=800)
                save(target, {'id': record['id'], 'variant': record['variant'], 'condition': record['condition'],
                              'wav_sha256': sha, 'dio': dio, 'acf800': acf800, 'acf800_confidence': confidence,
                              'primary_f0': record.get('measurement', {}).get('f0_hz'), 'qualified_ground_truth': False})
    print('F0補助診断を保存しました', flush=True)


if __name__ == '__main__':
    main()
