"""音声観測範囲の拒否を緩めず、SI結合の流れ/共振/不通過を診断して閉じる。"""
import argparse,ast,json,os
from pathlib import Path
from budget import ROOT,read,digest
from volume_waveguide_coupling_20261009 import HERE,NAME,PREV,PORT,TUBE,REPO,PYTHON,Budget,WORKER,job,execute,verify
PREFIX=WORKER[:WORKER.index('rows=[]\nfor row in json.loads')]
DOMAIN=PREFIX+r'''
# 観測器もWAVも呼ばない。源/声道は初回と完全同一。
rows=[]
for row in json.loads((here/'requests.json').read_text()):
 u,a,meta=controls(row['request']);calls+=1;state=np.zeros(34);mouth=[];pressure=[];loss=[];energy=[];start=0;refused=None
 while start<len(u):
  stop=min(len(u),start+4096)
  try:m,p,l,E,state=block(u[start:stop],a[start:stop],state)
  except ValueError as exc:refused=dict(start_sample=start,stop_sample=stop,error=str(exc),unverified_remaining_samples=len(u)-start);calls+=1;break
  mouth.append(m);pressure.append(p);loss.append(l);energy.append(E);calls+=1;start=stop
 if mouth:
  m=np.concatenate(mouth);p=np.concatenate(pressure);l=np.concatenate(loss);E=np.concatenate(energy);rm,rp,rl,rE,_=reference(u[:start],a[:start]);calls+=1
  ue=float(np.max(abs(m-rm)));pe=float(np.max(abs(p-rp)));be=balance(u[:start],p,l,E,np.zeros(34));assert ue<=5e-13 and pe<=5e-8 and be<=1e-16 and np.max(abs(E-rE))<=1e-14
  exceeded=np.flatnonzero(abs(m)>.001);peak=float(np.max(abs(m)));scope=dict(observer_mouth_limit_m3_s=.001,mouth_peak_m3_s=peak,samples_outside_original_observer_domain=len(exceeded),first_outside_sample=int(exceeded[0]) if len(exceeded) else None,within_original_observer_domain=not len(exceeded))
 else:ue=pe=be=None;scope=dict(observer_mouth_limit_m3_s=.001,mouth_peak_m3_s=None,within_original_observer_domain=False)
 rows.append(dict(id=row['id'],kind=row['kind'],request=row['request'],metadata=meta,source_peak_m3_s=float(np.max(abs(u))),source_input_sha256=ah(u),areas_sha256=ah(a),total_samples=len(u),verified_samples=start,source_or_state_refusal=refused,flow_reference_error_m3_s=ue,source_pressure_reference_error_Pa=pe,per_step_energy_balance_error_J=be,observer_domain=scope,microphone_called=False,WAVs_generated=0,E0_evaluated=False,pitch_evaluated=False))
assert len(rows)==43 and calls<=750
off=[r['id'] for r in rows if not r['observer_domain']['within_original_observer_domain'] or r['source_or_state_refusal']]
print(json.dumps(dict(core_rows=core,rows=rows,actual_render_calls=calls,all_43_examined=True,complete_tube_runs=sum(r['source_or_state_refusal'] is None for r in rows),within_original_observer_domain=sum(r['observer_domain']['within_original_observer_domain'] and r['source_or_state_refusal'] is None for r in rows),outside_or_unverified_ids=off,maximum_mouth_peak_m3_s=max(r['observer_domain']['mouth_peak_m3_s'] or 0 for r in rows),diagnostic_WAVs_generated=0,diagnostic_AI=0,original_observer_limit_or_source_gain_or_geometry_or_gates_changed=False,mechanical_limited_reference_passed=True,engineering_all_required_pass=False,adopted=False)))
'''
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract');ast.parse(DOMAIN)
    assert read(HERE/'child-failure.json')['returncode']==1
    with job(b,'setup','観測拒否の原上限を保持した43流量診断と正確な終了経路を事前登録',size=3000000) as j:
        b.write(HERE/'worker-domain-v2.py',DOMAIN.encode(),j)
        b.save(HERE/'domain-diagnostic-amendment-v2.json',dict(controller_sha256=digest(Path(__file__)),original_controller_and_source_contract_and_execution_contract_preserved=True,original_failure_sha256=digest(HERE/'child-failure.json'),original_worker_sha256=digest(HERE/'worker.py'),diagnostic_worker_sha256=digest(HERE/'worker-domain-v2.py'),failure_type='登録済み観測器が入力範囲を拒否。しきい値/ゲイン/源/径で救済しない科学的不通過。技術再試行へ読み替えない。',scope='初回と同じSI源/声道/状態で全43入力の口元流量を確認。元の一様管/8強制列を独立照合。観測器やWAV/ASRを呼ばず、支持/pitchを再判定しない。',render=750,DSP=2000,AI=0,source_amplitude_and_cutoff_and_Pa_to_PCM_and_observer_limit_unchanged=True,initial_failed_render_fee=2000,initial_failed_DSP_fee=3000,refund=False,planned_total_render=2750,planned_total_DSP=5000,individual_limits_not_increased=True,partial_initial_WAVs_not_preserved_and_count_unknown=True,independent_microphone_physics_or_Japanese_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
    print('観測範囲不通過の全43流量診断を追加登録',flush=True)
def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract');c=read(HERE/'domain-diagnostic-amendment-v2.json');assert digest(Path(__file__))==c['controller_sha256'] and digest(HERE/'worker-domain-v2.py')==c['diagnostic_worker_sha256']
    with job(b,'render','原上限を緩めないSI全43流量/一様管/強制列の診断',750,90000000,2200) as r:
        with job(b,'dsp','原源と口元流量の拒否/独立収支/全43分母を保存',2000,10000000,2200) as d:
            with b.workspace(r,'音声を出さない全43口元流量の科学初期化',16000000,32000000) as (work,env):
                try:out=execute([str(PYTHON),'-B',str(HERE/'worker-domain-v2.py'),str(HERE),str(work)],env,2200)
                except Exception as exc:
                    if hasattr(exc,'stdout'):b.save(HERE/'domain-diagnostic-failure-v2.json',dict(error=repr(exc),stdout=exc.stdout,stderr=exc.stderr),d)
                    raise
            v=json.loads(out.stdout);b.save(HERE/'domain-diagnostic-audit-v2.json',v,d)
    with job(b,'audit','SI観測不通過の全分母/費用/回収/旧封印を保持して終了',size=3000000) as j:
        verify('execution-contract')
        for prev in (PREV,PORT,TUBE):
            for n,h in read(prev/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        next='SI源/口元換算の独立一致と観測範囲超過を分離して保持する。全43音声工学は未確認・不通過、採択しない。元源/振幅/径/観測範囲/測定ゲートで救済しない。次は一次の空気の粘性/熱伝導など分布損失を独立資格化し、無損失声道の共振過大を別機構として検証する。'
        result=dict(v,original_generation_failed=True,initial_failure=digest(HERE/'child-failure.json'),complete_43_WAVs_saved=False,pitch_and_content_unverified=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=next);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# SI声道結合の観測範囲拒否と全43流量診断','','理想体積速度源/16区間無損失声道/flanged受動境界を結合した初回実行は、口元の流れを受ける原観測器の登録範囲で拒否された。初回2000render/3000DSPを全保持し、科学的不通過を技術再試行やゲイン調整へ読み替えない。初回の部分WAVは自分一時領域とともに回収され、件数は保存されていない。全43のE0/pitchは未確認・不通過。','',
          f'原source/径/帯域/状態を変えず、WAVや観測器を呼ばない追加750render/2000DSP診断を実施した。一様4半径の解析体積速度伝達と8強制/無強制の独立収支を通過。43入力すべてを調べ、声道計算の完了{v["complete_tube_runs"]}/43、原観測器の流量範囲内{v["within_original_observer_domain"]}/43、口元流量の最大値{v["maximum_mouth_peak_m3_s"]:.6g} m³/s。源/状態拒否がある場合は未確認の残りを明記した。','',
          '範囲外または未確認: '+', '.join(v['outside_or_unverified_ids'])+'。','',
          'SI単位と源の仕事/放射lossの数値収支の限定一致を、日本語のE0/pitch/内容/自然さへ転用しない。観測器0.001m³/s、源RMS3e-5m³/s、PCM換算、径/時刻、測定ゲートを広げたり合わせたりしていない。合計2750render/5000DSP、AI0。全自分一時領域を指定外部から回収し、旧全失敗/凍結/封印を保持。','',next,'','P5未開封・日本語知覚資格なし・品質未達。',''];b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();camp=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=camp['counts'],seconds=s['seconds']-camp['start_seconds'],write_bytes=s['write_bytes']-camp['start_write_bytes'],failed_initial_fees_not_refunded=True,temporary_owned=len(tmp),all_owned_temporary_absent=True),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='volume-waveguide-domain-failed-completed',active_campaign=None,next=next,git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0139.json',dict(latest_completed=NAME,next=next,review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(within_domain=v['within_original_observer_domain'],denominator=43,adopted=False,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','close']);a=p.parse_args();globals()[a.stage]()
