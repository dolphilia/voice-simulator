"""成功済み128件を再利用し、CLI測定の重複ジョブ名だけを分離する。"""
import argparse,base64,hashlib,json,sys
from pathlib import Path
import waveguide_vowel_comparison_20261008 as m
from budget import read,digest,encode
HERE=m.HERE

def register():
    b=m.Budget();assert not b.snapshot()['jobs'];b.recover();m.verify()
    with m.job(b,'audit','CLI測定ジョブ名の分離と成功128件の再利用を出力前固定',size=2000000) as j:
        files={n:digest(HERE/n) for n in ['registration.json','execution-contract.json','render-plan.json','render-manifest.json']}
        for mode in ('normal','isolated'):
            for variant in ('native','waveguide'):
                n='runtime-batch-'+mode+'-'+variant+'.json';files[n]=digest(HERE/n)
        req=m.requests()[0];path=HERE/'runtime-cli/normal'/(req['id']+'.wav');assert path.is_file();files[str(path.relative_to(HERE))]=digest(path)
        b.save(HERE/'isolation-amendment-v2.json',dict(original_controller_sha256=digest(Path(m.__file__)),effective_finish_sha256=digest(Path(__file__)),files=files,
            failure='4batch128件と最初CLIは成功。CLI E0という同じdspラベルの成功済み再予約が管理側で拒否された。次CLIのrender予約1件は実生成前に失敗し、費用を戻さない。',
            factor_unchanged=True,protocol_and_wave_parameters_unchanged=True,completed_batches_not_repeated=True,completed_CLI_not_repeated=True,
            remaining_CLI=3,remaining_actual_render_calls=25,failed_unused_render_reservation_retained=1,final_charged_render=1275,final_DSP=420,new_ASR=128,quality_goal_completed=False),j)
    print('成功済み128件/CLI1を保持し、残りCLI3だけの再開を固定',flush=True)

def finish():
    b=m.Budget();assert not b.snapshot()['jobs'];b.recover();m.verify();am=read(HERE/'isolation-amendment-v2.json');assert digest(Path(__file__))==am['effective_finish_sha256']
    for n,h in am['files'].items():assert digest(HERE/n)==h,n
    reqs=m.requests();expected={x['id']:read(m.REPO/x['record'])['wav_sha256'] for x in read(HERE/'render-manifest.json')['rows']};pairs=[];cli=[]
    for mode in ('normal','isolated'):
        for variant in ('native','waveguide'):
            value=read(HERE/('runtime-batch-'+mode+'-'+variant+'.json'));assert len(value['rows'])==32
            for x in value['rows']:
                data=base64.b64decode(x['wav_base64']);assert hashlib.sha256(data).hexdigest()==x['meta']['sha256']==expected[x['id']];pairs.append(dict(id=x['id'],mode=mode,sha256=x['meta']['sha256'],bit_match=True,reused=True))
    for q in (reqs[0],reqs[-1]):
        for mode in ('normal','isolated'):
            p=HERE/'runtime-cli'/mode/(q['id']+'.wav');reused=p.exists()
            if not reused:
                variant=q['method'];bundle=HERE/('native-bundle' if variant=='native' else 'runtime-bundle')
                with m.job(b,'render','CLI-v2 '+mode+'/'+q['id'],m.render_cost(q),50000000,600) as r:
                    with m.job(b,'dsp','CLI-v2 E0 '+mode+'/'+q['id'],1,1000000,600):
                        with b.workspace(r,'未実施CLIだけ '+mode+'/'+variant,16000000,32000000) as (work,env):value=m.execute([str(m.PYTHON),'-I','-B',str(bundle/'cli.py')],env,m.profile(b,work,mode=='isolated',variant),json.dumps(q,ensure_ascii=False),timeout=500)
                        data=base64.b64decode(value['wav_base64']);assert hashlib.sha256(data).hexdigest()==value['meta']['sha256']==expected[q['id']];b.write_data(p,data,r)
            assert digest(p)==expected[q['id']];cli.append(dict(id=q['id'],mode=mode,sha256=digest(p),bit_match=True,reused=reused))
    with m.job(b,'audit','CLI-v2全入口一致と実データ/HMM/通信拒否',size=50000000) as j:
        logical=HERE/'render'/read(HERE/'protocol.json')['rows'][0]['id']/'neutral/native.wav';archive=HERE/'runtime-batch-normal-waveguide.json'
        blocked=[logical,logical.resolve(),logical.with_suffix('.npz'),logical.with_suffix('.npz').resolve(),HERE/'protocol.json',HERE/'registration.json',m.PARENT/'protocol.json',archive,archive.resolve(),HERE/'native-bundle/mei_normal.htsvoice'];assert all(p.is_file() for p in blocked)
        with b.workspace(j,'候補の禁止論理/物理/HMM読取と実接続拒否',16000000,32000000) as (work,env):
            proof=m.execute([str(m.PYTHON),'-I','-B','-c',(m.PREV/'runtime-bundle/denial_probe.py').read_text()],env,m.profile(b,work,True),json.dumps([str(p) for p in blocked]),timeout=45);assert proof['all_denied']
        b.save(HERE/'denial-probe.json',dict(proof,paths=[str(p) for p in blocked]),j)
        assert len(pairs)==128 and len(cli)==4
        plan=read(HERE/'render-plan.json');b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,CLI=cli,new_render_calls=2*plan['comparison']+plan['CLI']+1,actual_completed_render_calls=2*plan['comparison']+plan['CLI'],failed_unused_reservation_retained=1,new_DSP_calls=132,completed_batches_not_repeated=True,source_and_block_calls_counted=True,denial_probe=proof,candidate_HMM_denied=True,final_non_neural=True,quality_certified=False),j)
        b.save(HERE/'isolation-repair-cost-note-v2.json',dict(actual_total_render=1274,charged_total_render=1275,DSP=420,ASR=128,source_and_wave_parameters_unchanged=True,failed_reservation_not_refunded=True,normal_and_isolated_batches_reused=True,quality_goal_completed=False),j)
    print(dict(isolation_completed=True,batch_waves_reused=128,CLI=4,prohibited_reads_and_network_denied=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','finish']);a=p.parse_args();globals()[a.stage]()
