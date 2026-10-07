"""同じ音響検査文で一回の測定補正を検査する。独立品質確認には数えない。"""
import json
import sys
import numpy as np
from scipy.io import wavfile
from campaign import ROOT,PILOT,PRIOR,digest,save
from revision_budget import RevisionBudget,REVISION
from acoustic_control import refine_hts,measure_wide
sys.path.insert(0,str(PRIOR/'hts-bundle-v2'))
from hts_core import render_hts
from acoustics import evaluate
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld


def main():
    budget=RevisionBudget();protocol=json.loads((REVISION/'render-protocol.json').read_text())
    target=REVISION/'refinement-protocol.json'
    if not target.exists():
        with budget.job('setup','残るレンダー枠で一回の測定補正と3回生成の単独検査を固定',1000000):
            save(target,{'iterations':1,'models':['direct_non_neural','distilled_non_neural'],
                'cached_first_render_reused':True,'additional_refinement_calls':32,'runtime_calls':24,
                'expected_total_campaign_calls':396,'same_rows_used_for_engineering_repair':True,
                'independent_quality_confirmation':False,'content_and_naturalness':'未検証',
                'original_plan_count':128,'revised_remaining_plan_count':168,
                'reason':'一回の補正で音響目標への追従を確認。campaign上限400は変更しない'})
    for row in protocol['rows']:
        for condition in ['neutral','challenge']:
            for variant in ['direct_non_neural','distilled_non_neural']:
                prior=REVISION/'render'/row['id']/condition/(variant+'.json')
                record=json.loads(prior.read_text())
                if digest(ROOT/record['wav'])!=record['wav_sha256']:raise ValueError('補正前出力の変更')
                path=REVISION/'refined'/row['id']/condition/(variant+'.json')
                if path.exists():continue
                with budget.job('render','一回補正/'+row['id']+'/'+condition+'/'+variant,2000000):
                    settings=refine_hts(record['target'],record['settings'],record['measurement'])
                    audio=render_hts(row,PRIOR/'hts-bundle-v2/mei_normal.htsvoice',settings['speed'],settings['half_tone'])
                    peak=float(np.max(abs(audio)));gain=min(1.,.95/peak) if peak else 1.
                    audio=(audio*gain).astype(np.float32);measured=measure_wide(audio)
                    f0,t=pyworld.dio(audio.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                    f0=pyworld.stonemask(audio.astype(float),f0,t,24000)
                    measured['dio_f0_hz']=float(np.median(f0[f0>0])) if np.any(f0>0) else None
                    path.parent.mkdir(parents=True,exist_ok=True);wav=path.with_suffix('.wav')
                    if wav.exists():raise FileExistsError('未記録の波形を上書きしません')
                    wavfile.write(wav,24000,audio)
                    save(path,{'id':row['id'],'text':row['text'],'variant':variant,'condition':condition,
                        'target':record['target'],'requested':record['requested'],'settings':settings,'measurement':measured,
                        'evaluation':evaluate(audio,{},24000),'raw_peak':peak,'output_gain':gain,
                        'wav':str(wav.relative_to(ROOT)),'wav_sha256':digest(wav),'source_record_sha256':digest(prior),
                        'additional_calls':1,'full_runtime_calls':3,'quality_certified':False})
                print(row['id'],condition,variant,flush=True)


if __name__=='__main__':main()
