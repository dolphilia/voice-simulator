"""教師の時間/F0制御を実VTLで補正する。声道・声質を同時に変えない。"""
import argparse
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from budget import Budget, ROOT, RESULT, save, digest
from renderer import render, baseline
sys.path.insert(0, str(ROOT.parent/'autonomous-speech-synthesis/src'))
from autonomous_speech_synthesis.backends import VTL
from acoustics import evaluate, estimate_f0, acoustic_features


def measure(audio, fs=24000):
    audio = np.asarray(audio, dtype=float)
    hop = round(.01*fs)
    rms = np.array([np.sqrt(np.mean(audio[i:i+hop]**2)) for i in range(0, len(audio), hop)])
    active = np.flatnonzero(rms > max(1e-5, rms.max()*.05))
    if not len(active):
        raise ValueError('活動区間がありません')
    start, end = active[0]*hop, min(len(audio), (active[-1]+1)*hop)
    f0, conf = estimate_f0(audio[start:end], fs)
    if f0 is None or conf < .4:
        raise ValueError('全体F0推定の信頼度が不足しています')
    return {'f0_hz': f0, 'confidence': conf, 'active_seconds': (end-start)/fs,
            'total_seconds':len(audio)/fs, 'active_start':start/fs, 'active_end':end/fs,
            'acoustic': acoustic_features(audio[start:end], fs)}


def loss(measured, target):
    return float(np.log(measured['f0_hz']/target['f0_hz'])**2 +
                 np.log(measured['active_seconds']/target['active_seconds'])**2)


def trial(vtl, budget, label, phones, durations, f0, target, path):
    if path.with_suffix('.json').exists():
        prior = json.loads(path.with_suffix('.json').read_text())
        if (digest(ROOT/prior['wav']) != prior['sha256'] or
                prior['controls']['phones'] != phones or
                not np.allclose(prior['controls']['durations_seconds'],durations,rtol=0,atol=1e-12) or
                not np.allclose(prior['controls']['f0_hz'],f0,rtol=0,atol=1e-9)):
            raise ValueError('再開時の既存レンダーと要求制御が一致しません')
        return prior
    with budget.job('render', label, 3_000_000) as ticket:
        t = time.monotonic()
        audio, log = render(vtl, phones, durations, f0)
        seconds = time.monotonic()-t
        evaluation = evaluate(audio, {}, 24000)
        measured = measure(audio)
        path.parent.mkdir(parents=True, exist_ok=True)
        wavfile.write(path.with_suffix('.wav'), 24000, audio.astype(np.float32))
        record = {'label': label, 'ticket': ticket['id'], 'controls': log, 'measurement': measured,
                  'evaluation': evaluation, 'objective': loss(measured, target), 'seconds':seconds,
                  'wav':str(path.with_suffix('.wav').relative_to(ROOT)), 'sha256':digest(path.with_suffix('.wav'))}
        save(path.with_suffix('.json'), record)
        return record


def fit(vtl, budget, name, phones, d, f, target, directory):
    candidates = []
    d, f = np.asarray(d), np.asarray(f)
    # 許容領域の外へ出ない。クリップして制御破綻を隠すことはしない。
    d_range = (max(.65, .025/float(d.min())), min(1.4, .6/float(d.max())))
    f_range = (max(.7, 70/float(f.min())), min(1.4, 450/float(f.max())))
    if d_range[0] > d_range[1] or f_range[0] > f_range[1]:
        raise ValueError('制御の許容区間が空です')
    scales = np.array([1., 1.])
    for i in range(4):
        scales = np.clip(scales, [d_range[0], f_range[0]], [d_range[1], f_range[1]])
        record = trial(vtl, budget, f'{name}/fit-{i}', phones, d*scales[0], f*scales[1],
                       target, directory/f'fit-{i:02d}')
        candidates.append({**record, 'scales':scales.tolist()})
        measured = record['measurement']
        scales = scales * [target['active_seconds']/measured['active_seconds'], target['f0_hz']/measured['f0_hz']]
    viable = [r for r in candidates if r['evaluation']['E0_pass']]
    if not viable:
        raise ValueError('工学条件を満たす適合候補がありません')
    best = min(viable, key=lambda r:r['objective'])
    return {'best':best, 'candidates':[{'scales':r['scales'],'objective':r['objective']} for r in candidates],
            'bounds':[d_range,f_range], 'count':len(candidates)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qualify', action='store_true')
    parser.add_argument('--include-audit', action='store_true')
    args = parser.parse_args()
    budget = Budget()
    vtl = VTL()
    try:
        if args.qualify:
            with budget.job('setup', '適合器の契約固定', 1_000_000):
                save(RESULT/'fit-contract.json', {
                    'parameters':['global_duration_scale','global_f0_scale'], 'renders_per_utterance':4,
                    'objective':'活動区間長と全体F0のlog比二乗和。波形から独立に計測',
                    'self_recovery_tolerances':{'f0_relative':.03,'active_duration_relative':.03},
                    'scope':'発話全体の韻律。音素ごとの調音・声質・自然さの適合は主張しない',
                    'script_sha256':digest(__file__)})
            with budget.job('render', '自己回復の既知目標', 2_000_000):
                target_audio, _ = render(vtl, ['a','k','a'], [.15,.075,.2], [240.,250.,220.])
                target = measure(target_audio)
            result = fit(vtl, budget, 'self-recovery', ['a','k','a'],
                         np.array([.15,.075,.2])/1.12, np.array([240.,250.,220.])/.88,
                         target, RESULT/'fit-qualification')
            measured = result['best']['measurement']
            errors = {'f0_relative':abs(measured['f0_hz']/target['f0_hz']-1),
                      'active_duration_relative':abs(measured['active_seconds']/target['active_seconds']-1)}
            passed = all(e <= .03 for e in errors.values())
            save(RESULT/'fit-qualification.json', {'passed':passed,'errors':errors,'fit':result,'target':target})
            print(json.dumps({'passed':passed,'errors':errors}))
            if not passed:
                raise RuntimeError('適合器の自己回復検査に不通過')
            return
        if not json.loads((RESULT/'fit-qualification.json').read_text())['passed']:
            raise RuntimeError('自己回復資格がありません')
        rows = json.loads((RESULT/'splits.json').read_text())['rows']
        if args.include_audit:
            if not (RESULT/'model-selection.json').exists():
                raise RuntimeError('モデル選択を凍結する前に監査の適合結果を開きません')
        else:
            rows = [r for r in rows if r['split'] != 'audit']
        targets = {r['id']:r for r in json.loads((RESULT/'teacher-controls-v2.json').read_text())['rows']}
        for row in rows:
            directory = RESULT/'fitted'/row['id']
            summary = directory/'summary.json'
            if summary.exists():
                continue
            target = targets[row['id']]
            if target['status'] != 'available':
                raise ValueError('教師の音素対応が未解決です')
            teacher = json.loads((ROOT/target['teacher_source']).read_text())
            fs, audio = wavfile.read(ROOT/teacher['wav'])
            measured = measure(audio, fs)
            d = np.array([c['duration_seconds'] for c in target['controls']])
            f = np.array([c['f0_hz'] for c in target['controls']])
            bd, bf = baseline(row)
            handwritten = trial(vtl, budget, row['id']+'/handwritten', row['phonemes'], bd, bf,
                                measured, directory/'handwritten')
            result = fit(vtl, budget, row['id'], row['phonemes'], d, f, measured, directory)
            save(summary, {'id':row['id'],'split':row['split'],'target':measured,
                           'handwritten':handwritten,'fit':result,
                           'purpose':'参照条件付きの適合。監査文の制御は学習・選別へ使用しない'})
            print(json.dumps({'id':row['id'],'handwritten':handwritten['objective'],
                              'fitted':result['best']['objective']},ensure_ascii=False),flush=True)
    finally:
        vtl.close()


if __name__ == '__main__':
    main()
