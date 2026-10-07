"""固定12文の120最終波形と96初回波形を、1実生成ずつ計数して保存する。"""
import time
import sys
from campaign import FactorialBudget, ROOT, RESULT, BUNDLE, read, save, digest, PILOT
from controlled_axes import initial_settings, refined_settings


def main():
    budget = FactorialBudget()
    protocol = read(RESULT/'protocol.json')
    for name, sha in protocol['source_hashes'].items():
        assert digest(ROOT/name) == sha
    sys.path.insert(0, str(BUNDLE))
    import numpy as np
    from scipy.io import wavfile
    from hts_core import render_hts
    from acoustic_control import measure_wide
    from acoustics import evaluate
    sys.path.insert(0, str(PILOT/'.cache/packages'))
    import pyworld

    def attempt(row, condition, variant, phase, settings, target):
        path = RESULT/'render'/row['id']/condition/(variant+('-initial' if phase == 'initial' else '')+'.json')
        if path.exists():
            record = read(path)
            if record.get('wav'):
                assert digest(ROOT/record['wav']) == record['wav_sha256']
            return record
        started = time.monotonic()
        record = {'id': row['id']+'/'+condition+'/'+variant, 'text': row['text'], 'length': row['length'],
            'challenge_group': row['challenge_group'], 'condition': condition, 'variant': variant,
            'phase': phase, 'requested': row['requests'][condition], 'settings': settings, 'target': target,
            'status': 'failed', 'synthesis_calls': 1, 'runtime_neural': False, 'quality_certified': False}
        label = str(path.relative_to(RESULT))
        try:
            with budget.job('render', label, 2_000_000):
                audio = render_hts(row, BUNDLE/'mei_normal.htsvoice', settings['speed'], settings['half_tone'])
                peak = float(np.max(abs(audio)))
                gain = min(1., .95/peak) if peak else 1.
                audio = (audio*gain).astype(np.float32)
                evaluation = evaluate(audio, {}, 24000)
                measured = measure_wide(audio)
                f0, times = pyworld.dio(audio.astype(float), 24000, f0_floor=70., f0_ceil=800., frame_period=5.)
                f0 = pyworld.stonemask(audio.astype(float), f0, times, 24000)
                measured['dio_f0_hz'] = float(np.median(f0[f0 > 0])) if np.any(f0 > 0) else None
                if not evaluation['E0_pass']:
                    raise ValueError('信号の健全性条件に不通過')
                path.parent.mkdir(parents=True, exist_ok=True)
                wav = path.with_suffix('.wav')
                if wav.exists():
                    raise FileExistsError('未記録の波形を上書きしません')
                wavfile.write(wav, 24000, audio)
                record.update(status='completed', measurement=measured, evaluation=evaluation,
                    raw_peak=peak, output_gain=gain, wav=str(wav.relative_to(ROOT)), wav_sha256=digest(wav),
                    seconds=time.monotonic()-started)
                save(path, record)
        except Exception as exc:
            tickets = [e for e in budget.events() if e['event'] == 'start' and e['label'] == label]
            if not tickets:
                raise
            record.update(error=repr(exc), seconds=time.monotonic()-started)
            if not path.exists():
                save(path, record)
        return record

    final_rows = []
    for row in protocol['rows']:
        neutral = attempt(row, 'neutral', 'native', 'final', initial_settings('native', row['requests']['neutral']), None)
        calibration = neutral.get('measurement')
        for condition in ('neutral', 'challenge'):
            for variant in protocol['variants']:
                if variant == 'native':
                    result = neutral if condition == 'neutral' else attempt(row, condition, variant, 'final',
                        initial_settings('native', row['requests'][condition]), None)
                elif calibration is None:
                    result = {'id': row['id']+'/'+condition+'/'+variant, 'text': row['text'], 'condition': condition,
                        'variant': variant, 'length': row['length'], 'challenge_group': row['challenge_group'],
                        'status': 'missing', 'reason': '既定校正の失敗で生成できない'}
                else:
                    model = 'distilled_non_neural' if variant == 'distilled_joint' else 'direct_non_neural'
                    target = row['targets'][condition][model]
                    initial = initial_settings(variant, row['requests'][condition], target, calibration)
                    first = attempt(row, condition, variant, 'initial', initial, target)
                    if first['status'] != 'completed':
                        result = {**first, 'status': 'missing', 'reason': '初回生成が失敗したため補正しない'}
                    else:
                        settings = refined_settings(variant, row['requests'][condition], target, initial, first['measurement'])
                        result = attempt(row, condition, variant, 'final', settings, target)
                final_rows.append(result)
            print(row['id'], condition, '完了', flush=True)
    assert len(final_rows) == 120
    save(RESULT/'render-manifest.json', {'rows': final_rows, 'planned_wavs': 120,
        'completed': sum(r['status'] == 'completed' for r in final_rows),
        'protocol_sha256': digest(RESULT/'protocol.json'), 'no_retries': True})


if __name__ == '__main__':
    main()
