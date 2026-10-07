"""外部VOT連続体で局所イベント候補を点検する。候補合成やAI推論はしない。"""
import argparse
import json
import numpy as np
from scipy.io import wavfile
from post_pilot import PostBudget,POST
from budget import save,digest
from local_events import event_candidates


def nominal(name):
    if name=='lab0000':return 0
    return int(name[-3:])*(-1 if name[3]=='m' else 1)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    out=POST/'local-events';source=POST/'local-measurement-references-2/wav';budget=PostBudget()
    if args.prepare_only:
        with budget.job('setup','局所イベント診断の事前条件を固定',1000000):
            files=sorted(source.glob('*.wav'))
            save(out/'protocol.json',{'estimator_sha256':digest(__import__('pathlib').Path(__file__).with_name('local_events.py')),
                'files':[{'path':str(p),'sha256':digest(p),'nominal_vot_ms':nominal(p.stem)} for p in files],
                'source':'https://www.haskinslaboratories.org/vot','reference_kind':'外部の人工VOT連続体、公称パラメータ',
                'source_caveat':'実波形の独立した人手境界ではない。資料説明に録音の数msの差がある',
                'algorithm':'25ms窓/1ms hop。70〜450Hzの正規化自己相関0.75以上が10ms継続する開始と、高域エネルギー増加最大点の差',
                'diagnostic_tolerance_ms':15,'tolerance_scope':'窓幅と資料注記を踏まえた工学診断値。日本語の知覚的許容幅ではない',
                'scope':'取得済み30音声を一度計測し、結果を見て閾値を調整しない',
                'zero_is_not_negative_control':'0ms音声も真の破裂を含み、母音だけの偽陽性検査とは別',
                'no_target_quality_qualification':True})
        return
    protocol=json.loads((out/'protocol.json').read_text())
    if digest(__import__('pathlib').Path(__file__).with_name('local_events.py'))!=protocol['estimator_sha256']:raise ValueError('測定器が変わりました')
    rows=[]
    with budget.job('audit','外部VOT連続体の局所測定',3000000):
        for row in protocol['files']:
            if digest(row['path'])!=row['sha256']:raise ValueError('外部波形の不一致')
            fs,a=wavfile.read(row['path']);a=a.astype(float)/32768
            result=event_candidates(a,fs)
            value=result.get('candidate_vot_ms')
            rec={**row,**result,'error_ms':None if value is None else value-row['nominal_vot_ms']}
            save(out/'frames'/(__import__('pathlib').Path(row['path']).stem+'.json'),rec)
            rows.append({k:v for k,v in rec.items() if k not in ('frame_times','rms','high_energy','periodicity')})
        groups={}
        for name,predicate in [('positive',lambda v:v>0),('zero',lambda v:v==0),('negative',lambda v:v<0)]:
            group=[r for r in rows if predicate(r['nominal_vot_ms'])];errors=[abs(r['error_ms']) for r in group if r['error_ms'] is not None]
            groups[name]={'count':len(group),'missing':len(group)-len(errors),
                          'mean_absolute_error_ms':float(np.mean(errors)) if errors else None,
                          'max_absolute_error_ms':max(errors,default=None),
                          'within_15ms':sum(e<=15 for e in errors)}
        passed=all(g['within_15ms']==g['count'] for g in groups.values())
        save(out/'summary.json',{'groups':groups,'external_signal_check_pass':passed,
            'target_domain_qualified':False,'rows':rows,'decision':'診断に限定。日本語VOT・破裂認識・自然さの合否には使わない',
            'next':'エネルギー立上りと口腔放出を区別できる独立注釈資料が必要。今の30件で閾値を再調整しない'})
        print(json.dumps({'groups':groups,'passed':passed},ensure_ascii=False))


if __name__=='__main__':main()
