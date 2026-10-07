"""実レンダラーのF0応答・再現性・管理費を測定する。品質認定とは別。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from budget import Budget, ROOT, RESULT, save, digest
from renderer import render
sys.path.insert(0, str(ROOT.parent/'autonomous-speech-synthesis/src'))
from autonomous_speech_synthesis.backends import VTL
from autonomous_speech_synthesis.evaluation import evaluate, estimate_f0


def main():
    budget = Budget()
    vtl = VTL()
    records = []
    try:
        for i, frequency in enumerate([160., 220., 280., 220.]):
            with budget.job('render', f'資格F0-{i}', 1_000_000):
                start = time.monotonic()
                audio, log = render(vtl, ['a'], [.4], [frequency], seed=20261002)
                elapsed = time.monotonic()-start
                f0, confidence = estimate_f0(audio[round(.12*24000):round(.35*24000)], 24000)
                path = RESULT/'qualification'/f'f0-{i}.wav'
                path.parent.mkdir(exist_ok=True)
                wavfile.write(path, 24000, audio.astype(np.float32))
                records.append({'target': frequency, 'measured': f0, 'confidence': confidence,
                                'relative_error': abs(f0/frequency-1) if f0 else None,
                                'seconds': elapsed, 'evaluation': evaluate(audio, {}, 24000),
                                'wav_sha256': digest(path)})
        passed = all(r['evaluation']['E0_pass'] and r['relative_error'] is not None and
                     r['relative_error'] <= .03 and r['confidence'] >= .65 for r in records)
        repeated = records[1]['wav_sha256'] == records[3]['wav_sha256']
        save(RESULT/'renderer-qualification.json', {'records': records, 'backend': vtl.metadata,
             'signal_and_f0_pass': passed, 'same_seed_repeat_equal': repeated,
             'quality_qualification': False, 'inventory': budget.inventory()})
        print(json.dumps({'signal_and_f0_pass':passed, 'same_seed_repeat_equal':repeated,
                          'render_seconds':[r['seconds'] for r in records]}, ensure_ascii=False))
        if not passed or not repeated:
            raise RuntimeError('合成器の資格検査に不通過')
    finally:
        vtl.close()


if __name__ == '__main__':
    main()
