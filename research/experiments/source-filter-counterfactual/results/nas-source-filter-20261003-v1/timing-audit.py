"""保存列の整数フレーム・有声イベントを追加生成なしで対照する。"""
import sys
from pathlib import Path
sys.path.insert(0,'/Users/dolphilia/github/voice-simulator/research/experiments/source-filter-counterfactual')
from campaign import *
import numpy as np

def intervals(mask):
    mask=np.asarray(mask,dtype=bool);changes=np.diff(np.r_[False,mask,False].astype(int))
    return list(zip(np.flatnonzero(changes==1).tolist(),np.flatnonzero(changes==-1).tolist()))

def main():
    with LocalBudget().job('audit','保存された整数フレームと有声イベントを対照',500000):
        protocol=read(RESULT/'protocol.json');rows=[]
        assert intervals([False,True,True,False,True])==[(1,3),(4,5)]
        for i,row in enumerate(protocol['rows']):
            original=read(REPO/row['source_record']);state=original['state_snapshot_after']
            arrays=np.load(RESULT/'parameters'/f'{i:02d}.npz');lf0=arrays['lf0'][:,0]
            boundaries=np.r_[0,np.cumsum(state['duration'])];expected=np.repeat(np.asarray(state['msd'])>.5,state['duration'])
            mask=(lf0>=np.log(70))&(lf0<=np.log(800));assert np.array_equal(mask,expected)
            support=read(REPO/row['support_contract'])['indices']
            for index in sorted(set(support)|set(row['focus_indices'])):
                lo,hi=map(int,(boundaries[index*5],boundaries[(index+1)*5]));core=mask[lo:hi]
                counts={}
                for mode in protocol['modes']:
                    saved=np.load(RESULT/'render'/mode/f'{i:02d}.npz');f0,t=saved['dio_f0'],saved['dio_times']
                    ticks=np.rint(t/.005).astype(int);assert np.max(abs(t-ticks*.005))<1e-12
                    integer=(ticks>=lo)&(ticks<hi);floating=(t>=lo*.005)&(t<hi*.005)
                    v=(f0>=70)&(f0<=800)
                    counts[mode]={'integer_frames':int(integer.sum()),'integer_voiced':int((integer&v).sum()),
                        'floating_frames':int(floating.sum()),'floating_voiced':int((floating&v).sum()),
                        'different_membership_frames':int((integer!=floating).sum())}
                rows.append({'id':row['id'],'variant':row['variant'],'phase':row['phase'],'index':index,'focus':index in row['focus_indices'],
                    'frame_start':lo,'frame_end':hi,'nominal_frames':hi-lo,'generated_voiced_frames':int(core.sum()),
                    'generated_voiced_fraction':float(core.mean()),'native_driving_events_relative_frames':intervals(core),
                    'generated_mask_matches_msd_state_schedule':True,'dio_masks':counts})
        focus=[r for r in rows if r['focus']];partial=[r for r in focus if r['generated_voiced_fraction']<.5]
        save(RESULT/'timing-audit.json',{'rows':rows,'focus_rows':len(focus),'focus_partial_driving_conditions':len(partial),
            'focus_partial_candidate_conditions':sum(r['variant']!='native' for r in partial),
            'all_msd_schedules_match_saved_mlpg':True,'new_render_ai_estimation_fit_calls':0,
            'original_float_mask_or_primary_support_modified':False,
            'interpretation':'駆動の有声域と音素全体の有声率は異なる量。整数格子による再集計は時刻診断だけで、旧主指標の再判定ではない。',
            'quality_certified':False})
    print({'focus_partial_driving_conditions':len(partial),'partial_candidate_conditions':sum(r['variant']!='native' for r in partial),'stored_intervals_checked':len(rows)},flush=True)

if __name__=='__main__':main()
