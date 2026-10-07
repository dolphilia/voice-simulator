"""固定3モデルと既定を同じ前段・HMM・指定条件で実生成する。"""
import json
import math
import sys
import time
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, REPO, BUNDLE, PILOT, read, save, digest
sys.path.insert(0,str(BUNDLE))
from acoustics import evaluate
from acoustic_control import measure_wide
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld
sys.path.insert(0,str(ROOT))
from local_renderer import StateEngine
from local_control import describe, ELIGIBLE, deltas, linear_predict
from objective import extract_local, centered_semitones
from checks import invariant


def neural_predictor():
    import torch
    from torch import nn
    model=read(RESULT/'models/neural.json');assert digest(RESULT/'models/neural.pt')==model['weights_sha256']
    net=nn.Sequential(nn.Linear(16,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,1))
    net.load_state_dict(torch.load(RESULT/'models/neural.pt',map_location='cpu',weights_only=True));net.eval();torch.set_num_threads(2)
    def predict(x):
        z=(np.asarray(x)-np.asarray(model['x_mean']))/np.asarray(model['x_scale'])
        with torch.no_grad():return net(torch.tensor(z,dtype=torch.float32)).flatten().numpy()
    return predict


def main():
    b=LocalBudget();p=read(RESULT/'protocol.json');comparison=read(RESULT/'model-comparison.json')
    for n,sha in p['source_hashes'].items():assert digest(ROOT/n)==sha
    for n,sha in comparison['model_hashes'].items():assert digest(RESULT/'models'/n)==sha
    assert not (RESULT/'asr').exists()
    predictors={v:(lambda x,m=read(RESULT/'models'/(v+'.json')):linear_predict(m,x)) for v in ('direct_non_neural','distilled_non_neural')}
    predictors['neural']=neural_predictor()
    with b.job('setup','160診断波形・4方式・支持域の事前固定',1000000):
        save(RESULT/'render-contract.json',{'protocol_sha256':digest(RESULT/'protocol.json'),
            'model_comparison_sha256':digest(RESULT/'model-comparison.json'),'planned_render_calls':160,
            'support_frozen_from_native_per_condition':True,'no_retries':True,'no_optimization_after_asr':True})
    records=[]
    for row in p['selection_rows']+p['rows']:
        training=read(REPO/row['source_training_input']) if row['split']=='selection' else None
        for condition,requested in row['requests'].items():
            support=None;teacher_shape=None;support_available=False
            for variant in p['variants']:
                path=RESULT/'render'/row['id']/condition/(variant+'.json');label=str(path.relative_to(RESULT));started=time.monotonic()
                record={k:row[k] for k in ('text','length','challenge_group','split')}
                settings={'speed':requested['speed'],'half_tone':12*math.log2(requested['requested_f0']/220)}
                record.update(id=row['id']+'/'+condition+'/'+variant,condition=condition,variant=variant,requested=requested,settings=settings,
                    status='failed',synthesis_calls=1,runtime_neural=variant=='neural',quality_certified=False)
                try:
                    with b.job('render',label,2000000):
                        with StateEngine(row,BUNDLE/'mei_normal.htsvoice',**settings) as engine:
                            before=engine.snapshot()
                            correction,phones=(np.zeros(engine.count),[]) if variant=='native' else deltas(row,before,predictors[variant])
                            engine.modify(correction);after=engine.snapshot();invariant(before,after,correction)
                            audio,lf0=engine.generate()
                        peak=float(np.max(abs(audio)));gain=min(1.,.95/peak) if peak else 1.;audio=(audio*gain).astype(np.float32)
                        path.parent.mkdir(parents=True,exist_ok=True);wav=path.with_suffix('.wav');wavfile.write(wav,24000,audio)
                        e=evaluate(audio,{},24000);measurement=measure_wide(audio)
                        f0,times=pyworld.dio(audio.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                        f0=pyworld.stonemask(audio.astype(float),f0,times,24000);voiced=f0[f0>0]
                        measurement.update(dio_f0_hz=float(np.median(voiced)) if len(voiced) else None,dio_voiced_fraction=float(np.mean(f0>0)))
                        np.savez_compressed(path.with_suffix('.npz'),generated_lf0=lf0,state_deltas=correction,dio_f0=f0,dio_times=times)
                        assert e['E0_pass'] and np.isfinite(audio).all()
                        if variant=='native':
                            indices=[t['label_index'] for t in training['phones']] if training else [d['label_index'] for d in describe(row) if d['phone'] in ELIGIBLE and any(before['msd'][j]>.5 for j in range(d['label_index']*5,(d['label_index']+1)*5))]
                            local,excluded=extract_local(f0,times,before,indices);support=[r['label_index'] for r in local];support_available=len(support)>=3
                            if training and support_available:
                                teacher={r['label_index']:r['teacher_log_f0'] for r in training['phones']}
                                teacher_shape=centered_semitones([teacher[i] for i in support])
                            save(path.parent/'support-contract.json',{'indices':support,'excluded_native_intervals':excluded,
                                'minimum_three_intervals_pass':support_available,'frozen_before_candidates':True,
                                'teacher_shape_semitones':teacher_shape.tolist() if teacher_shape is not None else None,
                                'native_wave_sha256':digest(wav),'source_training_input':row.get('source_training_input'),
                                'teacher_available':training is not None,'quality_certified':False})
                        local,missing=extract_local(f0,times,before,support) if support else ([],[])
                        complete=support_available and not missing and [r['label_index'] for r in local]==support
                        shape=centered_semitones([r['wave_log_f0'] for r in local]) if complete else None
                        mse=float(np.mean((shape-teacher_shape)**2)) if complete and teacher_shape is not None else None
                        record.update(status='completed',wav=str(wav.relative_to(ROOT)),wav_sha256=digest(wav),measurement=measurement,evaluation=e,
                            E0_pass=True,internal_unchanged=True,support_complete=complete,missing_support=missing,local_measurements=local,
                            wave_shape=shape.tolist() if shape is not None else None,wave_mse=mse,maximum_abs_half_tone=float(np.max(abs(correction))),
                            phone_residuals=phones,changed_state_count=int(np.sum(correction!=0)),raw_peak=peak,output_gain=gain,
                            state_snapshot_before=json.loads(json.dumps(before)),state_snapshot_after=json.loads(json.dumps(after)),seconds=time.monotonic()-started)
                        save(path,record)
                except Exception as exc:
                    if not any(ev['event']=='start' and ev['label']==label for ev in b.events()):raise
                    record.update(error=repr(exc),seconds=time.monotonic()-started)
                    if not path.exists():save(path,record)
                records.append(record)
            print(row['id'],condition,'4方式完了',flush=True)
    save(RESULT/'render-manifest.json',{'rows':records,'planned_wavs':160,'completed':sum(r['status']=='completed' for r in records),
        'protocol_sha256':digest(RESULT/'protocol.json'),'search_completed_before_asr':True,'all_models_frozen_before_render':True,'no_retries':True})

if __name__=='__main__':main()
