"""封印済み93波形の局所測定だけを比較。旧係数・合否は変えない。"""
import sys
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, REPO, PILOT, WAVE, read, save, digest
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld
sys.path.insert(0,str(WAVE))
from objective import extract_local


def main():
    inputs=read(RESULT/'regression-inputs.json')
    assert digest(REPO/inputs['cached_harvest_file'])==inputs['cached_harvest_sha256']
    cached={(r['text_id'],r['attempt']):r for r in read(REPO/inputs['cached_harvest_file'])['rows']}
    rows=[]
    for number,source in enumerate(inputs['rows']):
        path=RESULT/'regression'/(source['id']+'.json')
        record={**source,'status':'failed','new_generation_calls':0,'new_ai_calls':0,'primary_decisions_modified':False}
        try:
            with LocalBudget().job('audit','既存日本語波形の局所測定/'+source['id'],100000):
                for p,sha in [(source['wav'],source['wav_sha256']),(source['metadata'],source['metadata_sha256']),
                              (source['npz'],source['npz_sha256']),(source['snapshot_source'],source['snapshot_sha256']),
                              (source['support_contract'],source['support_contract_sha256'])]:assert digest(REPO/p)==sha
                a=np.load(REPO/source['npz']);dio,t=a['dio_f0'],a['dio_times']
                snapshot=read(REPO/source['snapshot_source'])['snapshot'];support=read(REPO/source['support_contract'])['indices']
                key=(source['text_id'],source['attempt'])
                if source['harvest_reused']:
                    previous=cached[key];assert previous['wav_sha256']==source['wav_sha256']
                    harvest,ht=np.array(previous['harvest_f0']),np.array(previous['harvest_times'])
                else:
                    fs,audio=wavfile.read(REPO/source['wav']);assert fs==24000
                    harvest,ht=pyworld.harvest(audio.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                methods={}
                for method,f0,times in [('dio',dio,t),('harvest',harvest,ht)]:
                    local,missing=extract_local(f0,times,snapshot,support)
                    shifts={str(shift):extract_local(f0,times-shift,snapshot,support)[1] for shift in (-.01,0.,.01)}
                    methods[method]={'local':local,'missing_support':missing,'boundary_shift_missing_support':shifts,
                        'boundary_support_changes':len(set(tuple(v) for v in shifts.values()))>1}
                bounds=np.r_[0,np.cumsum(snapshot['duration'])];internal=[]
                for i in support:
                    values=a['generated_lf0'][bounds[i*5]:bounds[(i+1)*5]]
                    voiced=values[(values>=np.log(70))&(values<=np.log(800))]
                    internal.append({'label_index':i,'frames':len(values),'voiced_frames':len(voiced),
                        'median_f0_hz':float(np.exp(np.median(voiced))) if len(voiced) else None})
                record.update(status='completed',methods=methods,internal=internal,
                    harvest_f0=harvest.tolist(),harvest_times=ht.tolist(),harvest_new_measurement=not source['harvest_reused'])
                save(path,record)
        except Exception as exc:
            record.update(status='failed',error=repr(exc))
            if not path.exists():save(path,record)
        rows.append(record)
        if (number+1)%15==0:print('保存済み波形',number+1,'/93を照合',flush=True)
    save(RESULT/'regression-summary.json',{'expected_waves':93,'completed':sum(r['status']=='completed' for r in rows),
        'harvest_reused':sum(r['harvest_reused'] for r in rows),'harvest_new_measurements':sum(r.get('harvest_new_measurement',False) for r in rows),
        'methods':{method:{'waves_with_missing_support':sum(bool(r['methods'][method]['missing_support']) for r in rows if r['status']=='completed'),
            'missing_support_intervals':sum(len(r['methods'][method]['missing_support']) for r in rows if r['status']=='completed'),
            'waves_with_boundary_support_changes':sum(r['methods'][method]['boundary_support_changes'] for r in rows if r['status']=='completed')}
            for method in ('dio','harvest')},'new_generation_calls':0,'new_ai_calls':0,'new_fit_calls':0,
        'japanese_human_boundaries_qualified':False,'internal_values_are_not_acoustic_ground_truth':True,'primary_decisions_modified':False})
    assert all(r['status']=='completed' for r in rows)
    print('93波形の局所回帰診断を保存。旧合否を変更しない',flush=True)

if __name__=='__main__':main()
