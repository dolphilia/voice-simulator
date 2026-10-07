"""教師の文字タイミングを音素へ対応させ、F0は実波形で測定する。"""
import json
import argparse
import sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from budget import Budget, ROOT, RESULT, save

sys.path.insert(0, str(ROOT.parent/'autonomous-speech-synthesis/src'))
from autonomous_speech_synthesis.evaluation import estimate_f0

IPA = {'ɯ':'u', 'ɨ':'u', 'ɡ':'g', 'ɕ':'sh', 'ʨ':'ch', 'ʥ':'j', 'ʣ':'z',
       'ʦ':'ts', 'ɸ':'f', 'ɲ':'n', 'ç':'h', 'ɾ':'r', 'ɴ':'N', 'ŋ':'N', 'ʔ':'Q', 'j':'y'}


def canonical(phone):
    if phone in ('I','U'):
        return phone.lower()
    if phone in ('ky','gy','ny','hy','my','ry','by','py'):
        return phone[0]
    return phone


def align(analysis, teacher):
    chars = teacher['phonemes']
    frames = teacher['predicted_duration_frames']
    if len(frames) != len(chars)+2:
        raise ValueError('教師のtoken数と継続長が不一致です')
    step = teacher['duration_seconds']/sum(frames)
    cursor = frames[0]*step
    items, gaps = [], []
    for char, frame in zip(chars, frames[1:-1]):
        start, end = cursor, cursor+frame*step
        cursor = end
        if char in ' .,!?:;':
            gaps.append({'symbol': char, 'start': start, 'end': end})
            continue
        if char == 'ʲ':
            if not items:
                raise ValueError('口蓋化記号の先行音素がありません')
            items[-1]['end'] = end
            continue
        if char == 'ː':
            if not items or items[-1]['phone'] not in 'aiueo':
                raise ValueError('長音の先行母音がありません')
            phone = items[-1]['phone']
        else:
            phone = IPA.get(char, char)
        items.append({'phone': phone, 'start': start, 'end': end})
    expected = [canonical(p) for p in analysis['phonemes']]
    observed = [p['phone'] for p in items]
    if expected != observed:
        raise ValueError(f'音素対応が一致しません: expected={expected}, observed={observed}')
    # 単語間spaceの予測時間を隣接音へ半分ずつ割り当てる。句読点・前後silenceは含めない。
    for left, right in zip(items, items[1:]):
        middle = (left['end']+right['start'])/2
        left['end'] = middle
        right['start'] = middle
    return items, gaps


def measured_pitch(audio, fs):
    times, values, confidence = [], [], []
    for center in np.arange(.03, len(audio)/fs-.03, .0125):
        segment = audio[round((center-.03)*fs):round((center+.03)*fs)]
        f0, conf = estimate_f0(segment, fs, minimum=70, maximum=450)
        times.append(center)
        values.append(float(f0) if f0 is not None else 0.)
        confidence.append(float(conf))
    times, values, confidence = map(np.asarray, (times, values, confidence))
    good = (confidence >= .65) & (values >= 70) & (values <= 450)
    if good.sum() < 3:
        raise ValueError('信頼できるF0窓が不足しています')
    return times, values, confidence, good


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--v2', action='store_true')
    args = parser.parse_args()
    with Budget().job('setup', '教師の音素対応と実波形F0抽出', 5_000_000):
        rows = json.loads((RESULT/'splits.json').read_text())['rows']
        output = []
        for row in rows:
            source = RESULT/'teacher'/f"{row['id']}.json"
            corrected = RESULT/'teacher-corrected'/f"{row['id']}.json"
            if args.v2 and corrected.exists():
                source = corrected
            teacher = json.loads(source.read_text())
            try:
                items, gaps = align(row, teacher)
                fs, audio = wavfile.read(ROOT/teacher['wav'])
                times, values, confidence, good = measured_pitch(audio, fs)
                controls = []
                for phone, interval in zip(row['phonemes'], items):
                    mask = good & (times >= interval['start']) & (times <= interval['end'])
                    interpolated = not mask.any()
                    target = float(np.median(values[mask])) if mask.any() else float(np.interp(
                        (interval['start']+interval['end'])/2, times[good], values[good]))
                    controls.append({**interval, 'phone': phone, 'canonical_phone': interval['phone'],
                                     'duration_seconds': interval['end']-interval['start'],
                                     'f0_hz': target, 'f0_interpolated': interpolated})
                output.append({'id': row['id'], 'split': row['split'], 'status': 'available',
                               'controls': controls, 'gaps': gaps, 'teacher_source': str(source.relative_to(ROOT)),
                               'leading_seconds': items[0]['start'], 'trailing_seconds': teacher['duration_seconds']-items[-1]['end'],
                               'voiced_windows': int(good.sum()), 'windows': len(times)})
            except Exception as exc:
                output.append({'id': row['id'], 'split': row['split'], 'status': 'unavailable', 'error': repr(exc)})
        save(RESULT/('teacher-controls-v2.json' if args.v2 else 'teacher-controls.json'), {'rows': output,
             'method': '教師の内部durationを厳密な音素列照合で対応。波形自己相関F0を音素区間で集計',
             'limitations': ['内部durationは強制整列の正解ではない', '無声区間のF0は周辺の有声窓から補間',
                            '非学習F0推定器の誤差・倍音誤りがあり、後続の実レンダー検査が必要']})
        print(json.dumps({'available':sum(r['status']=='available' for r in output),
                          'unavailable':[r for r in output if r['status']!='available']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
