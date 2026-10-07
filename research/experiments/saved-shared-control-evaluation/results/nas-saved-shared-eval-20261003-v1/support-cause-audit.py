"""保存済みDIO・MLPG LF0列の欠損区間を再推定せず対照する。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path('/Users/dolphilia/github/voice-simulator/research/experiments/saved-shared-control-evaluation')))
from campaign import *
import numpy as np
import re

def stats(arrays,snapshot,index):
    boundaries=np.r_[0,np.cumsum(snapshot['duration'])]*.005
    lo,hi=boundaries[index*5],boundaries[(index+1)*5]
    t=arrays['dio_times'];f0=arrays['dio_f0'];mask=(t>=lo)&(t<hi);v=mask&(f0>=70)&(f0<=800)
    lf0=arrays['generated_lf0'];gt=np.arange(len(lf0))*.005;gm=(gt>=lo)&(gt<hi)
    gv=gm&np.isfinite(lf0)&(lf0>=np.log(70))&(lf0<=np.log(800))
    return {'interval_start_seconds':float(lo),'interval_end_seconds':float(hi),
        'dio_interval_frames':int(mask.sum()),'dio_voiced_frames':int(v.sum()),
        'dio_voiced_fraction':float(v.sum()/mask.sum()),'dio_median_hz':float(np.median(f0[v])) if v.any() else None,
        'generated_lf0_interval_frames':int(gm.sum()),'generated_lf0_in_range_frames':int(gv.sum()),
        'generated_lf0_median_hz':float(np.exp(np.median(lf0[gv]))) if gv.any() else None,
        'msd':snapshot['msd'][index*5:(index+1)*5],
        'state_delta_half_tones':arrays['state_deltas'][index*5:(index+1)*5].tolist()}

def main():
    with LocalBudget().job('audit','保存DIO・MLPG列のみで支持域欠損を切り分ける',500000):
        p=read(RESULT/'protocol.json');labels={r['id']:r['full_context_labels'] for r in p['selection_rows']+p['rows']}
        details=[]
        for row in read(RESULT/'render-manifest.json')['rows']:
            path=REPO/row['source_record'];assert digest(path)==row['source_record_sha256'];r=read(path)
            if r['support_complete']:continue
            native=read(path.with_name('native.json'));arrays=np.load(path.with_suffix('.npz'));na=np.load(path.with_name('native.npz'))
            for index in r['missing_support']:
                a=stats(arrays,r['state_snapshot_after'],index);n=stats(na,native['state_snapshot_after'],index)
                assert a['msd']==n['msd'] and a['interval_start_seconds']==n['interval_start_seconds'] and a['interval_end_seconds']==n['interval_end_seconds']
                assert n['dio_voiced_frames']>=3 and n['dio_voiced_fraction']>=.5
                details.append({'id':r['id'],'split':r['split'],'index':index,'phone':re.search(r'-(.*?)\+',labels[r['id'].split('/')[0]][index]).group(1),
                    'candidate':a,'native':n,'candidate_source_sha256':row['source_record_sha256'],
                    'saved_dio_npz_sha256':digest(path.with_suffix('.npz')),
                    'generated_lf0_retains_voicing':a['generated_lf0_in_range_frames']==n['generated_lf0_in_range_frames'],
                    'duration_msd_unchanged':True})
        save(RESULT/'support-cause-audit.json',{'rows':details,'missing_conditions':len({r['id'] for r in details}),
            'saved_sequences_only':True,'new_f0_estimations':0,'new_render_calls':0,'new_ai_calls':0,'new_fit_calls':0,
            'fixed_support_or_primary_metrics_modified':False,
            'interpretation':'DIOの脱落と内部LF0・有声状態の変化を対照する診断。内部列の保持だけでは実励起の正しさや計測誤りを証明しない。',
            'quality_certified':False})
    print({'missing_conditions':len(details),'generated_lf0_retains_voicing':sum(r['generated_lf0_retains_voicing'] for r in details)},flush=True)

if __name__=='__main__':main()
