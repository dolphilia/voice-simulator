"""教師が必要な4次元逆推定を実レンダラーで検証する。最終共有モデルではない。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from scipy.optimize import least_squares
from campaign import LocalBudget, ROOT, RESULT, REPO, BUNDLE, PILOT, WRES, GRES, read, save, digest
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
        support_path=GRES/'render'/row['id']/'support-contract.json'
        if support_path.exists():
            support=read(support_path); self.support=support['indices'];self.target_shape=np.asarray(support['teacher_shape_semitones'])
        else:self.support=None;self.target_shape=None
        self.cache={};self.attempts=[]

    def generate(self, c, label):
        c=coefficients(c); key=tuple(c.tolist())
        if key in self.cache:return self.cache[key]
        path=RESULT/'inverse-render'/self.row['id']/(label+'.json')
        record={'text_id':self.row['id'],'text':self.row['text'],'coefficients':c.tolist(),'attempt':label,
                'status':'failed','synthesis_calls':1,'runtime_neural':False,'teacher_required_for_search':True,'quality_certified':False}
        started=time.monotonic()
        try:
            with LocalBudget().job('render',self.row['id']+'/'+label,2000000):
                with StateEngine(self.row,BUNDLE/'mei_normal.htsvoice') as engine:
                    before=engine.snapshot();assert normalized_snapshot(before)==self.snapshot
                    record['snapshot_matched']=True
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
                if self.support is None:
                    assert np.array_equal(c,[0]*4) and len(local)>=3
                    self.support=[p['label_index'] for p in local]
                    targets={p['label_index']:p for p in self.target_phones}
                    self.target_shape=centered_semitones([targets[i]['teacher_log_f0'] for i in self.support])
                    save(path.parent/'support-contract.json',{'indices':self.support,'excluded_from_baseline_intersection':missing,
                        'teacher_shape_semitones':self.target_shape.tolist(),'native_wave_sha256':digest(wav),
                        'baseline_source_snapshot_sha256':digest(REPO/self.row['source_training_input']),
                        'frozen_before_candidates':True,'boundary_qualified':False})
                if [p['label_index'] for p in local]!=self.support:
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
        save(RESULT/'inverse-render'/self.row['id']/'state-inverse.json',{'coefficients':solution.x.tolist(),'success':bool(solution.success),
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


def qualify(native,state,wave):
    completed=all(r.get('status')=='completed' for r in (native,state,wave))
    if not completed:return {'qualified':False,'reason':'既定・状態目標・実波形候補に欠損'}
    diff={f:wave['measurement'][f]/native['measurement'][f]-1 for f in ('f0_hz','dio_f0_hz','active_seconds')}
    checks={'wave_below_native':wave['wave_mse']<native['wave_mse'],'wave_at_most_statefit':wave['wave_mse']<=state['wave_mse'],
        'global_f0':all(abs(diff[f])<=.05 for f in ('f0_hz','dio_f0_hz')),'active_duration':abs(diff['active_seconds'])<=.03,
        'support_E0_internal':all(all(r.get(k) for k in ('support_complete','E0_pass','internal_unchanged')) for r in (native,state,wave))}
    return {'qualified':all(checks.values()),'checks':checks,'relative_to_native':diff}


def main():
    p=read(RESULT/'protocol.json')
    for n,sha in p['source_hashes'].items():assert digest(ROOT/n)==sha
    with LocalBudget().job('setup','21文の逆推定入口と最大672生成を固定',1000000):
        save(RESULT/'inverse-contract.json',{'source_hashes':p['source_hashes'],'protocol_sha256':digest(RESULT/'protocol.json'),
            'maximum_render_calls':672,'maximum_per_text':32,'extra_shrink_per_text':3,'no_asr_during_optimization':True})
    searches=[];entrance=[]
    old={r['id']:r for r in read(GRES/'render-manifest.json')['rows']}
    for row in p['training_rows']:
        search=Search(row);native=search.generate(np.zeros(4),'native')
        if native['status']=='completed':state=search.state_candidate()
        else:state={'status':'missing','reason':'既定支持域が不成立'}
        checks=[]
        for variant,record in [('native',native),('statefit',state)]:
            key=row['id']+'/neutral/'+variant
            if key in old:
                checks.append({'variant':variant,'new_sha256':record.get('wav_sha256'),'old_sha256':old[key]['wav_sha256'],
                    'matched':record['status']=='completed' and record.get('wav_sha256')==old[key]['wav_sha256']})
        technical=all(r.get('snapshot_matched') and r.get('E0_pass') and r.get('internal_unchanged') for r in (native,state) if r.get('status')!='missing')
        entrance.append({'id':row['id'],'checks':checks,'technical_passed':technical,'native_support_available':native['status']=='completed'})
        searches.append((row,search,native,state))
        print('入口',row['id'],technical,native['status'],state['status'],flush=True)
    passed=all(e['technical_passed'] and all(c['matched'] for c in e['checks']) for e in entrance)
    save(RESULT/'entrance-audit.json',{'rows':entrance,'passed':passed,'old_four_eight_matched':all(c['matched'] for e in entrance for c in e['checks']),
        'old_match_checks':sum(len(e['checks']) for e in entrance),'all_21_entrances_before_search':True})
    assert passed,'入口不通過のため探索・学習・認識を禁止'
    manifest=[]
    for row,search,native,state in searches:
        if native['status']=='completed':result=search.run(native,state)
        else:result={'native':native,'statefit':state,'wavefit':{'status':'missing'},'iterations':[],
            'new_attempts':len(search.attempts),'failed_attempts':len(search.attempts),'extra_shrink_renders':0}
        result['qualification']=qualify(result['native'],result['statefit'],result['wavefit'])
        save(RESULT/'searches'/(row['id']+'.json'),result)
        record={k:row[k] for k in ('id','text','length','source_training_input')}
        record.update(qualification=result['qualification'],attempts=result['new_attempts'],failed_attempts=result['failed_attempts'],
            wave_mse={v:result[v].get('wave_mse') for v in ('native','statefit','wavefit')},
            final_coefficients=result['wavefit'].get('coefficients'),accepted_updates=sum(i['accepted'] for i in result['iterations']),
            extra_shrink_renders=result['extra_shrink_renders'])
        manifest.append(record);print('目標',row['id'],result['qualification'],flush=True)
    qualified=[r for r in manifest if r['qualification']['qualified']]
    supported=len(qualified)>=12 and {r['length'] for r in qualified}=={'short','long'}
    save(RESULT/'target-manifest.json',{'rows':manifest,'qualified_utterances':len(qualified),'minimum_required':12,
        'both_lengths_required':True,'fit_supported':supported,'fit_started':False,'status':'ready' if supported else 'insufficient',
        'no_failed_targets_replaced_by_zero':True,'quality_certified':False})
    print({'qualified_utterances':len(qualified),'fit_supported':supported},flush=True)

if __name__=='__main__':main()
