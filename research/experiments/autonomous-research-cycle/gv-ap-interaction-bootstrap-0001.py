"""第21回：既存GV制御と既存AP半減の相互作用を生成前に固定する。"""
from pathlib import Path
import sys,json,ast,hashlib,shutil
ROOT=Path(__file__).resolve().parent
OLD=ROOT/'campaigns/nas-gv-ablation-20261008-v1'
AP=ROOT/'campaigns/nas-voicing-ap-20261008-v1/runtime-bundle-v2'
sys.path[:0]=[str(ROOT),str(OLD)]
from temporary_storage import ManagedStorageBudget as Budget
from budget import read,digest,encode
HERE=ROOT/'campaigns/nas-gv-ap-interaction-20261008-v1'
NAME='gv-ap-interaction-v1'
sources={}
def construct():
    originals={'paths.py':'paths.py','temporary_storage.py':'temporary_storage.py',
        'runtime.py':'runtime.py','runtime_batch.py':'runtime_batch.py','controls_v2.py':'controls_v2.py',
        'gv.c':'gv.c','gv_control.py':'gv_control.py','measurement.py':'measurement.py',
        'period_measurement.py':'period_measurement.py','asr_worker.py':'asr_worker.py',
        'controller.py':'controller_v2.py','prepare.py':'prepare_v2.py',
        'preflight.py':'preflight_v2.py','summarize.py':'summarize_v2.py','closeout.py':'closeout_v4.py',
        'test_controls.py':'test_controls.py'}
    for name,old in originals.items():
        s=(OLD/old).read_text().replace('controller_v2','controller').replace('execution-contract-v2.json','execution-contract.json')
        s=s.replace('gv-ablation-v1',NAME).replace('nas-mcp-postfilter-20261008-v1','nas-gv-ablation-20261008-v1')
        s=s.replace('gv-ablation-candidate-pool','gv-ap-interaction-candidate-pool').replace('gv-fresh-','gvap-fresh-')
        s=s.replace('gv-ablation-','gv-ap-interaction-')
        for a,z in [('256音声','160音声'),('256件','160件'),('隔離256組','隔離160組'),('ASR256','ASR160')]:s=s.replace(a,z)
        s=s.replace('prepare_v2.py','prepare.py').replace('preflight_v2.py','preflight.py')
        sources[name]=s
    assert digest(AP/'controls_v2.py')==digest(OLD/'runtime-bundle/controls_v2.py')
    sources['voicing_world.py']=(AP/'voicing_world.py').read_text()
    t=sources['runtime.py'].replace('from world_renderer2 import synthesize','from voicing_world import synthesize')
    a=t.index('METHODS=');z=t.index('VOICES=',a)
    t=t[:a]+"""METHODS=['native','voicing_no_lf0_gv','voicing_no_lf0_gv_ap_half','voicing_no_gv','voicing_no_gv_ap_half']
DISABLED={'native':[],'voicing_no_lf0_gv':['LF0'],'voicing_no_lf0_gv_ap_half':['LF0'],
          'voicing_no_gv':['MCP','LF0'],'voicing_no_gv_ap_half':['MCP','LF0']}
"""+t[z:]
    t=t.replace("lf0_method='native' if method=='native' else 'voicing'","lf0_method='native' if method=='native' else ('combined' if method.endswith('_ap_half') else 'voicing')")
    t=t.replace("raw,conversion=synthesize(params,settings);conversion.update(renderer='WORLD',AP_noise_power_factor=1.,input_streams_unchanged=True)",
        "raw,conversion=synthesize(params,settings,control['AP_noise_power_factor']);conversion.update(renderer='WORLD',AP_noise_power_factor=control['AP_noise_power_factor'],input_streams_unchanged=True)")
    sources['runtime.py']=t
    t=sources['controller.py']
    marker="                by_method[method]=meta\n                save_exact"
    checks="""                if method.endswith('_ap_half'):
                    paired=by_method[method.removesuffix('_ap_half')]
                    assert meta['output_parameter_hashes']==paired['output_parameter_hashes']
                    assert meta['GV_parameter_hashes']==paired['GV_parameter_hashes']
                    assert meta['generated_lf0_median_hz']==paired['generated_lf0_median_hz']
                    assert meta['conversion']['AP_before_sha256']==paired['conversion']['AP_sha256']
                    for key in ['f0_sha256','power_sha256']:
                        assert meta['conversion'][key]==paired['conversion'][key]
                    assert meta['conversion']['unvoiced_AP_unchanged'] and meta['conversion']['power_f0_unchanged']
                if method.startswith('voicing_no_gv'):
                    paired=by_method['voicing_no_lf0_gv'+('_ap_half' if method.endswith('_ap_half') else '')]
                    assert meta['GV_parameter_hashes'][1:]==paired['GV_parameter_hashes'][1:]
                    assert meta['output_parameter_hashes'][1:]==paired['output_parameter_hashes'][1:]
                assert meta['control']['AP_noise_power_factor']==(.5 if method.endswith('_ap_half') else 1.)
                by_method[method]=meta
                save_exact"""
    assert t.count(marker)==1;t=t.replace(marker,checks)
    sources['controller.py']=t
    t=sources['prepare.py']
    a=t.index("    with b.job(NAME,'setup','共有資産");z=t.index('    # 初期化前',a)
    t=t[:a]+"""    with b.job(NAME,'setup','封印済み共有資産と既存GV模型のhash照合コピー',reserve_bytes=20_000_000) as job:
        bundle=HERE/'runtime-bundle'
        mapping={n:PREVIOUS/'runtime-bundle'/n for n in read(PREVIOUS/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:HERE/n for n in ['runtime.py','runtime_batch.py','gv.c','gv_control.py','controls_v2.py','voicing_world.py']})
        for name,source in mapping.items():
            b.write(bundle/name,source.read_bytes(),job)
        original=(bundle/'mei_normal.htsvoice').read_bytes();split=original.index(b'[DATA]')+6
        proofs=read(PREVIOUS/'model-header-audit.json')
        assert digest(bundle/'mei_normal.htsvoice')==proofs['native_sha256']
        for item in proofs['variants']:
            model=(bundle/item['model']).read_bytes()
            assert digest(bundle/item['model'])==digest(PREVIOUS/'runtime-bundle'/item['model'])
            assert len(model)==len(original) and model[split:]==original[split:]
            assert [i for i,(a,z) in enumerate(zip(original,model)) if a!=z]==item['changed_offsets']
            assert hashlib.sha256(model[split:]).hexdigest()==item['body_sha256']
        proofs=dict(proofs,previous_proof_sha256=digest(PREVIOUS/'model-header-audit.json'),
            all_models_byte_exact_reuse=True,new_model_fit=0)
        b.save(HERE/'model-header-audit.json',proofs,job)
        b.save(HERE/'build-audit.json',dict(new_compile=0,previous_binary_sha256=digest(PREVIOUS/'runtime-bundle/gv.dylib'),
            binary_sha256=digest(bundle/'gv.dylib'),source_sha256=digest(HERE/'gv.c'),existing_binary_byte_exact=True),job)
        b.save(bundle/'manifest.json',dict(files={p.name:digest(p) for p in bundle.iterdir() if p.is_file()},shared_assets=True,
            final_non_neural=True,utterance_tables=0,waveform_lookup=0,neural_model=0,quality_certified=False),job)
"""+t[z:]
    t=t.replace("AP_noise_power_factor=1.,","AP_noise_power_factor=[1.,.5],")
    t=t.replace("GV_disabled_streams=[[],['MCP'],['LF0'],['MCP','LF0']]","GV_disabled_streams=[[],['LF0'],['MCP','LF0']]")
    sources['prepare.py']=t
    t=sources['preflight.py'].replace('旧2波形','旧3波形とAP半減2対')
    t=t.replace("verify();a2=read(HERE/'preflight-recovery-v2.json');assert all(digest(HERE/n)==h for n,h in a2['source_hashes'].items());b=Budget();b.recover()","verify();b=Budget();b.recover()")
    # 実waveなしに全依存をimportし、人工AP境界検査を実行する。
    marker="    verify();assert not _fn(None,None,0)"
    t=t.replace(marker,marker+"""
    import measurement,period_measurement,asr_worker,voicing_world
    from controls_v2 import ap_noise_power
    import runpy
    with contextlib.redirect_stdout(io.StringIO()):
        fixture=runpy.run_path(str(HERE/'test_controls.py'))
    assert callable(measurement.secondary) and callable(period_measurement.frame_acf)
""")
    a=t.index('    for m in [',t.index('def compat_worker'));z=t.index('def main():',a)
    t=t[:a]+"""    for m in ['native','voicing_no_lf0_gv','voicing_no_gv']:
        data,meta=generate(row['text'],m,q['speed'],q['requested_f0'])
        old=read(PREVIOUS/'render'/row['id']/'neutral'/(m+'.json'));assert meta['sha256']==old['wav_sha256']
        items.append(dict(name=m,sha256=meta['sha256'],bit_match=True,wav_base64=base64.b64encode(data).decode()))
    import numpy as np
    from scipy.io import wavfile
    from voicing_world import synthesize
    from acoustics import evaluate
    for m in ['voicing_no_lf0_gv_ap_half','voicing_no_gv_ap_half']:
        data,meta,params,analyzed=generate(row['text'],m,q['speed'],q['requested_f0'],full=True)
        raw,conversion=synthesize(params,meta['settings'],.5)
        audio=(raw*.25).astype(np.float32);assert evaluate(audio,{},24000)['E0_pass']
        out=io.BytesIO();wavfile.write(out,24000,audio);reference=out.getvalue();assert reference==data
        items.append(dict(name=m,sha256=meta['sha256'],bit_match=True,wav_base64=base64.b64encode(data).decode()))
        items.append(dict(name=m+'_existing_reference',sha256=hashlib.sha256(reference).hexdigest(),
            bit_match=True,wav_base64=base64.b64encode(reference).decode()))
    return dict(results=items,actual_render_calls=7,fixture_not_quality_evidence=True,
        baseline_old3_byte_exact=True,AP_existing_reference_pairs=2,quality_certified=False)
"""+t[z:]
    t=t.replace("else 2,reserve_bytes","else 7,reserve_bytes").replace("'2互換波形のE0/hash',count=2","'7互換波形のE0/hash',count=7")
    t=t.replace("parameter_engine_checks=pairs,","parameter_engine_checks=pairs,all_dependency_imports_pass=True,AP_boundary_fixture_pass=True,")
    sources['preflight.py']=t
    t=sources['summarize.py']
    a=t.index('            contrasts=');z=t.index('        secondary={}',a)
    t=t[:a]+"""            contrasts={key:values[candidate]-values[baseline] for key,baseline,candidate in [
                ('MCP_GV_on','voicing_no_lf0_gv','voicing_no_lf0_gv_ap_half'),
                ('MCP_GV_off','voicing_no_gv','voicing_no_gv_ap_half')]} if complete else {}
            factorial[metric]=dict(values=values,complete=complete,lower_is_better=True,
                AP_half_delta_at_each_MCP_GV=contrasts,
                interaction_off_minus_on=(contrasts['MCP_GV_off']-contrasts['MCP_GV_on']) if complete else None,
                descriptive_only=True)
"""+t[z:]
    t=t.replace('GV_ablation','GV_AP_interaction')
    sources['summarize.py']=t
    t=sources['closeout.py'].replace("verify();a2=read(HERE/'preflight-recovery-v2.json');assert all(digest(HERE/n)==h for n,h in a2['source_hashes'].items());b=Budget();b.recover();","verify();b=Budget();b.recover();")
    t=t.replace('actual_render=487','actual_render=491').replace('comparison=161','comparison=160').replace('compatibility=2','compatibility=7').replace('technical_retries=3','technical_retries=0')
    t=t.replace('GV_ablation','GV_AP_interaction').replace('MCP/LF0のGV補正を除く比較','既存MCP GVとAP半減の相互作用比較')
    t=t.replace('実波形487生成','実波形491生成').replace('WORLD/AP=1。','WORLD/AP係数1または0.5。')
    t=t.replace('progress-0024','progress-0026').replace('GV比較の全外部','GV/AP比較の全外部')
    t=t.replace("USE_GVの該当フラグだけを1→0とし、共有模型のデータ本体・位置・その他ヘッダを保持。GV重み0を無効化の代用には使わない。",
        "既存20のGV模型をbyte一致で再利用。native以外のLF0 GV除去を固定し、MCP GV有無×既存AP係数1/0.5を比較。模型本体・位置・GV重みを保持。")
    t=t.replace("次へ進む。","既存HTS励振周期の観測監査へ進む。")
    sources['closeout.py']=t
    for name,s in sources.items():
        if name.endswith('.py'):ast.parse(s,filename=name)
        assert 'sha160' not in s and 'sha321' not in s,name
        assert 'preflight-recovery' not in s,name
    assert 'period_measurement.py' in sources and 'voicing_world.py' in sources
    assert all('256件' not in s and '256音声' not in s for s in sources.values())
def main():
    construct()
    b=Budget();b.recover();v=b.snapshot()
    assert not v['jobs'] and len(v['campaigns'])==20 and all(c['closed'] for c in v['campaigns'].values())
    summary=read(OLD/'aggregate-summary.json');assert not any(summary['qualifications'].values())
    draft=read(ROOT/'next-gv-ap-interaction-draft-0001.json');old=read(OLD/'registration.json')
    pool=read(ROOT/'gv-ap-interaction-candidate-pool-0001.json')
    reg=dict(question=draft['question'],reason=draft['reason'],variants=draft['variants'],
        conditions=old['conditions'],new_short=8,new_long=8,input_pool_sha256=digest(ROOT/'gv-ap-interaction-candidate-pool-0001.json'),
        previous_seal_sha256=digest(OLD/'artifact-seal.json'),previous_summary_sha256=digest(OLD/'aggregate-summary.json'),
        direct_non_neural_only=True,neural_pathway_used=False,fill_rule=old['fill_rule'],
        factor_rules='native基準無改変。他はLF0 GVオフと既存LF0補完/中央値校正を固定、MCP GV有無×既存AP係数1/0.5、β0・WORLD・gain.25。出力後調整なし。',
        causal_guards=draft['causal_guards'],existing_routes_only=True,
        gates=dict(engineering='全E0・状態/MSD/音響状態分布/LPF/設定/利得保持。AP対の全パラメータ/F0/power一致、無声AP保持。GV C実内部照合。全160通常/隔離組・CLI4byte一致。',
            pitch=old['gates']['pitch'],content=old['gates']['content'],quality=old['gates']['quality']),
        limits=draft['limits'],cost_estimate=draft['estimates'],compatibility_render=7,
        AP_source_sha256=digest(AP/'voicing_world.py'),control_source_sha256=digest(OLD/'runtime-bundle/controls_v2.py'),
        baseline_models_byte_exact=True,new_model_fit=0,no_optimization_after_first_audio=True,
        protected_confirmation_opened=False,quality_goal_completed=False,
        technical_retry_per_job=2,technical_retry_campaign=10,
        budget_review='21/24（87.5%）。新しい経路は追加せず、既存GVとAPの未検証相互作用比較。以後は既存経路の観測監査と終了を優先。')
    assert reg['cost_estimate']['peak_total']<reg['limits']['bytes']
    assert v['limits']['seconds']-v['seconds']-14400>=reg['limits']['seconds']
    assert all(reg['limits'][k]<=v['limits'][k]-v['counts'].get(k,0) for k in ['render','dsp','ai','teacher','train','inverse','download'])
    assert shutil.disk_usage(ROOT).free>=20000000000 and shutil.disk_usage(b.guard.root).free>=3500000000
    b.reconcile();b.start_campaign(NAME,str(HERE.relative_to(ROOT)),reg['limits'],hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','既存GV/AP相互作用の生成前登録・全依存ソース',reserve_bytes=400000) as j:
        b.save(HERE/'registration.json',reg,j)
        for name,s in sources.items():b.write(HERE/name,s.encode(),j)
        for p in (OLD/'vendor').iterdir():
            if p.is_file():b.write(HERE/'vendor'/p.name,p.read_bytes(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(OLD/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'implementation-audit.json',dict(Python_AST_pass=True,all_dependencies_included=True,
            source_hashes={n:hashlib.sha256(s.encode()).hexdigest() for n,s in sources.items()},
            actual_render=0,protected_confirmation_opened=False,prior_seal_sha256=digest(OLD/'artifact-seal.json')),j)
    with b.locked():
        t=b._load();t.setdefault('continuation_checkpoint_history',[]).append(t['continuation_checkpoint'])
        t['continuation_checkpoint']=dict(id='gv-ap-interaction-registered-20261008-0001',active_campaign=NAME,
            campaign_closed=False,next='prepare → preflight static/compat7 → commit/push → comparison/isolate/二ASR → summarize/closeout',
            quality_goal_completed=False,protected_confirmation_opened=False,git_save_pending=True);b._write_state(t)
    b.save(ROOT/'progress-0025.json',dict(active_campaign=NAME,prior_completed='gv-ablation-v1',
        quality_goal_completed=False,protected_confirmation_opened=False,
        next='prepare.py → preflight.py static/compat → commit/push → controller.py comparison/isolate/asr → summarize.py → closeout.py',
        budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
