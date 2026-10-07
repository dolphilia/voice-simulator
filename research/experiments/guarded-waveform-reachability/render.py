"""教師が必要な4次元逆推定を実レンダラーで検証する。最終共有モデルではない。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from scipy.optimize import least_squares
from campaign import LocalBudget, ROOT, RESULT, REPO, BUNDLE, PILOT, WRES, read, save, digest
sys.path.insert(0,str(BUNDLE))
from acoustics import evaluate
from acoustic_control import measure_wide
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld
sys.path.insert(0,str(ROOT))
from local_renderer import StateEngine
from local_control import describe, deltas, ELIGIBLE
from guarded_derivative import column, shrink
from objective import INDICES, centered_semitones, phone_residuals, coefficients, extract_local, residual, objective, update, accept


def normalized_snapshot(snapshot):
    return json.loads(json.dumps(snapshot))


def state_values(snapshot, indices):
    values=[]
    for i in indices:
        states=[j for j in range(i*5,(i+1)*5) if snapshot['msd'][j]>.5]
        if not states:raise ValueError('支持域の有声状態がありません')
        values.append(float(np.average([snapshot['means'][1][j][0] for j in states],weights=[snapshot['duration'][j] for j in states])))
    return values


class Search:
    def __init__(self,row):
        self.row=row; self.training=read(REPO/row['source_training_input'])
        self.snapshot=self.training['snapshot'];self.target_phones=self.training['phones']
        support=read(WRES/'render'/row['id']/'support-contract.json')
        self.support=support['indices']; self.target_shape=np.asarray(support['teacher_shape_semitones']);self.cache={};self.attempts=[]

    def generate(self, c, label):
        c=coefficients(c); key=tuple(c.tolist())
        if key in self.cache:return self.cache[key]
        path=RESULT/'render'/self.row['id']/(label+'.json')
        record={'text_id':self.row['id'],'text':self.row['text'],'coefficients':c.tolist(),'attempt':label,
                'status':'failed','synthesis_calls':1,'runtime_neural':False,'teacher_required_for_search':True,'quality_certified':False}
        started=time.monotonic()
        try:
            with LocalBudget().job('render',self.row['id']+'/'+label,2000000):
                with StateEngine(self.row,BUNDLE/'mei_normal.htsvoice') as engine:
                    before=engine.snapshot();assert normalized_snapshot(before)==self.snapshot
                    correction, phones=deltas(self.row,before,lambda x: np.asarray(x)[:,INDICES]@c)
                    engine.modify(correction);after=engine.snapshot()
                    assert before['duration']==after['duration'] and before['msd']==after['msd']
                    assert before['means'][0]==after['means'][0] and before['means'][2]==after['means'][2]
                    assert all(a[1:]==z[1:] for a,z in zip(before['means'][1],after['means'][1]))
                    assert all(before['means'][1][j]==after['means'][1][j] for j in range(engine.count) if correction[j]==0)
                    audio,lf0=engine.generate()
                peak=float(np.max(abs(audio)));gain=min(1.,.95/peak) if peak else 1.
                audio=(audio*gain).astype(np.float32)
                path.parent.mkdir(parents=True,exist_ok=True)
                wav=path.with_suffix('.wav');wavfile.write(wav,24000,audio)
                f0,times=pyworld.dio(audio.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                f0=pyworld.stonemask(audio.astype(float),f0,times,24000)
                np.savez_compressed(path.with_suffix('.npz'),generated_lf0=lf0,state_deltas=correction,dio_f0=f0,dio_times=times)
                e=evaluate(audio,{},24000);m=measure_wide(audio)
                voiced=f0[f0>0];m.update(dio_f0_hz=float(np.median(voiced)) if len(voiced) else None,dio_voiced_fraction=float(np.mean(f0>0)))
                record.update(wav=str(wav.relative_to(ROOT)),wav_sha256=digest(wav),evaluation=e,measurement=m,
                    E0_pass=e['E0_pass'],internal_unchanged=True,maximum_abs_half_tone=float(np.max(abs(correction))),
                    state_snapshot_after=normalized_snapshot(after),phone_residuals=phones,raw_peak=peak,output_gain=gain)
                assert e['E0_pass'] and m['f0_hz'] is not None and m['dio_f0_hz'] is not None
                indices=self.support if self.support is not None else [p['label_index'] for p in self.target_phones]
                local,missing=extract_local(f0,times,before,indices)
                record.update(local_measurements=local,missing_support=missing)
                if missing or [p['label_index'] for p in local]!=self.support:
                    raise ValueError('固定局所有声支持域が欠損しました')
                wave_shape=centered_semitones([p['wave_log_f0'] for p in local])
                state_shape=centered_semitones(state_values(after,self.support))
                record.update(status='completed',support_complete=True,wave_shape=wave_shape.tolist(),state_shape=state_shape.tolist(),
                    wave_mse=float(np.mean((wave_shape-self.target_shape)**2)),state_mse=float(np.mean((state_shape-self.target_shape)**2)),
                    objective=objective(self.target_shape,wave_shape,c),seconds=time.monotonic()-started)
                save(path,record)
        except Exception as exc:
            if not any(e['event']=='start' and e['label']==self.row['id']+'/'+label for e in LocalBudget().events()):
                raise
            record.update(status='failed',error=repr(exc),seconds=time.monotonic()-started,support_complete=False)
            if not path.exists():save(path,record)
        self.attempts.append(record);self.cache[key]=record
        return record

    def state_candidate(self):
        native_shape=centered_semitones(state_values(self.snapshot,self.support))
        descriptions=describe(self.row)
        eligible=[d for d in descriptions if d['phone'] in ELIGIBLE and any(self.snapshot['msd'][j]>.5 for j in range(d['label_index']*5,(d['label_index']+1)*5))]
        x=np.array([d['x'] for d in eligible]);lookup={d['label_index']:i for i,d in enumerate(eligible)}
        positions=[lookup[i] for i in self.support]
        def function(c):
            values=phone_residuals(x,c)[positions]
            predicted=native_shape+values-values.mean()
            return residual(self.target_shape,predicted,c)
        solution=least_squares(function,np.zeros(4),bounds=(-3.,3.),method='trf',max_nfev=200,ftol=1e-10,xtol=1e-10,gtol=1e-10)
        save(RESULT/'render'/self.row['id']/'state-inverse.json',{'coefficients':solution.x.tolist(),'success':bool(solution.success),
            'nfev':solution.nfev,'cost':float(solution.cost),'method':'固定4係数の発話別逆推定。共有モデルのfitではない。'})
        if not solution.success:return {'status':'failed','error':'状態逆推定が規定内で収束しません'}
        return self.generate(solution.x,'statefit')

    def run(self, native, state):
        current=native;history=[];extra=0
        for iteration in range(3):
            c=np.array(current['coefficients']);columns=[];probes=[];methods=[]
            entry={'iteration':iteration,'previous_attempt':current['attempt'],'accepted':False}
            for j in range(4):
                pair=[]
                for sign,name in [(1.,'plus'),(-1.,'minus')]:
                    cc=c.copy();cc[j]+=.25*sign
                    probe=self.generate(cc,f'iteration-{iteration}-axis-{j}-{name}')
                    probes.append(probe['attempt']);pair.append(probe)
                derivative,method=column(current,pair[0],pair[1]);methods.append(method)
                if derivative is None:break
                columns.append(derivative)
            entry.update(probes=probes,derivative_methods=methods)
            if len(columns)!=4:
                entry['stop_reason']='両側無効の軸があり差分未取得';history.append(entry);break
            jacobian=np.column_stack(columns)
            candidate_c=update(jacobian,self.target_shape-np.array(current['wave_shape']),c)
            candidate=self.generate(candidate_c,f'iteration-{iteration}-update')
            accepted=accept(current,candidate);recoveries=[]
            entry.update(jacobian=jacobian.tolist(),jacobian_rank=int(np.linalg.matrix_rank(jacobian)),
                candidate_attempt=candidate['attempt'],candidate_coefficients=candidate_c.tolist(),
                previous_objective=current['objective'],candidate_objective=candidate.get('objective'))
            if not accepted:
                for factor in (.5,.25):
                    shrunk=shrink(c,candidate_c,factor);cached=tuple(shrunk.tolist()) in self.cache
                    if not cached and extra>=3:break
                    proposal=self.generate(shrunk,f'iteration-{iteration}-shrink-{factor}')
                    if not cached:extra+=1
                    ok=accept(current,proposal)
                    recoveries.append({'factor':factor,'attempt':proposal['attempt'],'new_render':not cached,
                        'status':proposal['status'],'objective':proposal.get('objective'),'accepted':ok})
                    if ok:candidate=proposal;accepted=True;break
            entry.update(accepted=accepted,recoveries=recoveries,accepted_attempt=candidate['attempt'] if accepted else None)
            history.append(entry)
            if not accepted:
                entry['stop_reason']='通常・許可縮小更新で実波形目的が改善しないか支持域不通過';break
            current=candidate
        assert len(self.attempts)<=32 and extra<=3
        return {'native':native,'statefit':state,'wavefit':current,'iterations':history,
            'wavefit_is_accepted_previous_wave':True,'new_attempts':len(self.attempts),'extra_shrink_renders':extra,
            'failed_attempts':sum(r['status']!='completed' for r in self.attempts)}


def main():
    p=read(RESULT/'protocol.json')
    for n,sha in p['source_hashes'].items():assert digest(ROOT/n)==sha
    with LocalBudget().job('setup','片側差分・縮小更新の生成前契約',1000000):
        save(RESULT/'render-contract.json',{'source_hashes':p['source_hashes'],'protocol_sha256':digest(RESULT/'protocol.json'),
            'maximum_render_calls':128,'maximum_extra_shrink_per_text':3,'no_asr_during_optimization':True,
            'all_eight_baselines_match_before_search':True,'searches':4,'shared_model_fits':0})
    searches=[];entrance=[]
    old_manifest={r['id']:r for r in read(WRES/'render-manifest.json')['rows']}
    for row in p['rows']:
        search=Search(row)
        native=search.generate(np.zeros(4),'native');state=search.state_candidate()
        checks=[]
        for variant,record in [('native',native),('statefit',state)]:
            prior=old_manifest[row['id']+'/neutral/'+variant]
            same=record['status']=='completed' and record.get('wav_sha256')==prior['wav_sha256']
            checks.append({'variant':variant,'new_sha256':record.get('wav_sha256'),
                'old_sha256':prior['wav_sha256'],'matched':same})
        entrance.append({'id':row['id'],'checks':checks});searches.append((row,search,native,state))
        print('入口',row['id'],all(c['matched'] for c in checks),flush=True)
    passed=all(c['matched'] for e in entrance for c in e['checks'])
    save(RESULT/'entrance-audit.json',{'rows':entrance,'all_eight_matched':passed,'before_new_optimization_and_asr':True})
    assert passed,'旧対照と不一致のため新規探索・認識は禁止'
    manifest=[];counts=[]
    for row,search,native,state in searches:
        result=search.run(native,state);save(RESULT/'searches'/(row['id']+'.json'),result)
        counts.append({'id':row['id'],'new_attempts':len(search.attempts),'extra_shrink_renders':result['extra_shrink_renders'],
            'failed_attempts':sum(r['status']!='completed' for r in search.attempts)})
        for variant in p['variants']:
            r=result[variant]
            manifest.append({**r,**{k:row[k] for k in ('text','length','challenge_group')},'id':row['id']+'/neutral/'+variant,
                'variant':variant,'condition':'neutral','split':'development','search_source_attempt':r.get('attempt')})
        print(row['id'],{v:(result[v]['status'],result[v].get('wave_mse')) for v in p['variants']},flush=True)
    save(RESULT/'render-manifest.json',{'rows':manifest,'searches':counts,'completed':sum(r['status']=='completed' for r in manifest),
        'planned_final_rows':12,'protocol_sha256':digest(RESULT/'protocol.json'),'search_completed_before_asr':True})

if __name__=='__main__':main()
