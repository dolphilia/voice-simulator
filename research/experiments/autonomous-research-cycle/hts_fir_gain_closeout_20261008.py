"""64波形の全分母と全MCP frameを照合し、FIR経路の内容保護を封印する。"""
import ast
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from budget import read,digest,encode
from hts_fir_gain_comparison_20261008 import ROOT,HERE,NAME,REPO,Budget,job,BASE,PYTHON,MECHANISM

ALL_FRAMES=r'''"""保存した全native/candidate列を検査し、全MCPの有限grid応答を診断する。"""
import sys,json
from pathlib import Path
here=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from fft_fir import kernel
p=json.loads((here/'protocol.json').read_text());N=16384
q=np.exp(-2j*np.pi*np.arange(N//2+1)/N);a=(q-.55)/(1.-.55*q);rows=[]
for row in p['rows']:
 for condition in p['conditions']:
    base=here/'render'/row['id']/condition
    with np.load(base/'native.npz',allow_pickle=False) as z:native={k:z[k].copy() for k in ('mcp','lf0','lpf','duration')}
    for method in ('fft_fir','fft_loggain'):
        with np.load(base/(method+'.npz'),allow_pickle=False) as z:
            assert all(np.array_equal(z[k],v) for k,v in native.items())
    relative=[];tail=[]
    for c in native['mcp']:
        h=kernel(c);target=np.exp(np.polynomial.polynomial.polyval(a,c));reference=np.fft.irfft(target,n=N)
        error=float(np.max(np.abs(np.fft.rfft(h,n=N)-target)/np.maximum(np.abs(target),1e-12)))
        energy=float(np.sum(reference[2048:]**2)/np.sum(reference**2))
        assert np.isfinite(error) and np.isfinite(energy)
        relative.append(error);tail.append(energy)
    assert len(relative)==len(native['mcp'])
    bad=[i for i,(r,t) in enumerate(zip(relative,tail)) if r>1e-3 or t>1e-6]
    rows.append(dict(id=row['id']+'/'+condition,all_saved_parameters_exact=True,frames_checked=len(relative),excluded_frames=0,
        maximum_complex_relative_error=max(relative),maximum_grid_IR_tail_energy=max(tail),
        worst_response_frame=int(np.argmax(relative)),worst_tail_frame=int(np.argmax(tail)),failed_frames=bad,passed=not bad))
assert len(rows)==32
print(json.dumps(dict(rows=rows,passed=all(v['passed'] for v in rows),all_frames_checked=sum(v['frames_checked'] for v in rows),
    FFT_grid=N,IR_length=2048,scope='保存した全実MCPの有限16384grid応答と参考IR tail。連続全域/短窓F0/知覚資格へ拡張しない。',
    saved_arrays_only=True,no_speech_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))
'''

def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    registration=read(HERE/'registration.json');assert digest(Path(__file__))==registration['closeout_source_sha256']
    spec=importlib.util.spec_from_file_location('_minphase_controller',HERE/'controller.py')
    import sys
    sys.path.insert(0,str(HERE));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.verify()
    old=(BASE/'summarize.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='grouped')
    scope={};exec(ast.get_source_segment(old,node),scope);grouped=scope['grouped']
    protocol=read(HERE/'protocol.json');manifest=read(HERE/'render-manifest.json');runtime=read(HERE/'runtime-audit.json')
    assert len(manifest['rows'])==96 and len(runtime['pairs'])==96 and len(runtime['CLI'])==4 and runtime['passed']
    assert manifest['new_render_calls']==160 and runtime['new_render_calls']==326
    records={}
    for x in manifest['rows']:
        assert digest(REPO/x['record'])==x['sha256'];r=read(REPO/x['record']);assert digest(REPO/r['wav'])==r['wav_sha256'];records[r['id']]=r
    for n,h in read(HERE/'measurement-package-contract.json')['files'].items():assert digest(REPO/n)==h
    assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib') and digest(HERE/'shape.c')==digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/shape.c')
    with job(b,'dsp','全実MCP frameの解析応答・finite IR tailと保存列照合',96,20000000,600) as j:
        with b.workspace(j,'全frame FIR検証の科学ライブラリ初期化') as (_,env):
            env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
            out=subprocess.run([str(PYTHON),'-B','-c',ALL_FRAMES,str(HERE)],env=env,check=True,capture_output=True,text=True,timeout=540)
        physical=json.loads(out.stdout);b.save(HERE/'all-frame-fir-audit.json',physical,j)
    engineering={};content={};pairs=[]
    with job(b,'audit','全件・固定33群・因子差・保存hash・一時回収の終了監査',size=10000000,seconds=300) as j:
        for method in protocol['variants']:
            selected=[r for r in records.values() if r['variant']==method];assert len(selected)==32
            engineering[method]=dict(expected=32,missing_records=0,E0_pass_count=sum(r['E0_pass'] for r in selected),pitch_pass_count=sum(r['pitch_gate']['passed'] for r in selected),
                fixed_support_intervals=sum(len(r['measurement']['support']) for r in selected),missing_support=sum(len(r['measurement']['missing_support']) for r in selected),
                all_required_pass=all(r['E0_pass'] and r['pitch_gate']['passed'] and r['invariants_pass'] for r in selected),
                failures=[dict(id=r['id'],E0=r['meta']['E0'],pitch_gate=r['pitch_gate'],missing_support=r['measurement']['missing_support']) for r in selected if not(r['E0_pass'] and r['pitch_gate']['passed'])])
            content[method]={}
            for engine in ('whisper','reazon'):
                asr_manifest=read(HERE/('asr-manifest-'+engine+'.json'));assert len(asr_manifest['rows'])==asr_manifest['new_ai']==96
                for x in asr_manifest['rows']:assert digest(REPO/x['path'])==x['sha256']
                comparisons=[]
                for row in protocol['rows']:
                    for condition in protocol['conditions']:
                        path=HERE/'asr'/engine/row['id']/condition/(method+'.json');x=read(path);y=read(path.with_name('native.json'))
                        assert x['status']==y['status']=='completed' and x['reference_kana']==y['reference_kana'] and x['characters']==y['characters']
                        for value in (x,y):
                            assert value['protocol_sha256']==digest(HERE/'protocol.json') and value['engine_contract_sha256']==digest(HERE/'engine-contract.json')
                            assert digest(REPO/value['wav'])==value['wav_sha256']
                        comparisons.append(dict(text_id=row['id'],condition=condition,length=row['length'],challenge_group=row['challenge_group'],status='completed',errors=x['errors'],native_errors=y['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],native_hypothesis=y['hypothesis']))
                groups=grouped(comparisons)
                content[method][engine]=dict(pairs=comparisons,groups=groups,worsening_groups=[n for n,v in groups.items() if not v['non_worsening']],all_groups_non_worsening=all(v['non_worsening'] for v in groups.values()))
        for row in protocol['rows']:
            for condition in protocol['conditions']:
                key=row['id']+'/'+condition+'/';a=records[key+'native']
                for method in ('fft_fir','fft_loggain'):
                    z=records[key+method]
                    assert a['meta']['output_parameter_hashes']==z['meta']['output_parameter_hashes']
                    assert a['meta']['conversion']['source_clock_hashes']==z['meta']['conversion']['source_clock_hashes'] and a['measurement']['support']==z['measurement']['support']
                    assert z['meta']['conversion']['effective_filter_alpha']==.55 and z['meta']['conversion']['periodic_source_delay_samples']==0
                    assert a['meta']['conversion']['render_calls_including_internal_MLSA']==1 and z['meta']['conversion']['render_calls_including_internal_MLSA']==2
                    pairs.append(dict(id=key+method,all_parameters_exact=True,excitation_and_cycle_clock_exact=True,fixed_support_exact=True,output_changed=a['wav_sha256']!=z['wav_sha256']))
        assert len(pairs)==64 and len(physical['rows'])==32
        fixture=read(HERE/'fixture-audit.json');assert fixture['passed'] and fixture['inherited']
        research_gates={method:engineering[method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[method].values()) and (method=='native' or physical['passed']) for method in protocol['variants']}
        summary=dict(total=96,engineering=engineering,content=content,filter_factor_pairs=pairs,paired_generation_complete=True,
            inherited_mechanism_fixture_passed=True,real_MCP_grid_audit=physical,mechanical_fixture_is_not_speech_quality=True,research_protection_gates=research_gates,
            independent_new_input_noncollision=True,final_non_neural_runtime_verified=True,full_runtime_hash_match=True,
            methodological_limits='固定DIO/全体ACF診断と有限grid応答。短窓/動的/瞬時F0/知覚/連続全周波数への資格ではない。',
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,adopted=False,
            old_31_methods_and_249_missing_and_two_ASR33_groups_unchanged=True,
            next='FIR三回目の全件保護不通過を保持し同補間/係数救済を封印。6件レビュー後、YIN型の短窓/動的/境界測定を別契約で資格検証する。' if not any(research_gates[m] for m in ('fft_fir','fft_loggain')) else '全件保護を満たす範囲から独立した知覚資格の取得へ進む。')
        b.write_data(HERE/'summary.json',encode(summary),j)
        compact=dict(summary);compact['content']={m:{n:{k:v for k,v in value.items() if k!='pairs'} for n,value in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json');b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 原HTSと二つのFIR利得補間の比較','',
            '新16日本語文×2条件×3方式の96波形。全64対のMCP/LF0/LPF・有声mask・duration・実励振/周期時計と固定支持を保護した。FIRは2048点の因果IRで全体利得込み算術補間と対数利得分離補間を比較し、原MLSAのb補間とは異なる。原nativeとの全96通常/隔離・CLI4の波形hashを照合し、候補内部の原MLSA補助生成も別計数した。','',
            '|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'実MCP全{physical["all_frames_checked"]}frameを除外なしで有限16384grid応答/tail検査した。所定機構判定: {physical["passed"]}。この検査は連続全域・知覚pitch・自然さの資格ではない。',
            '', '知覚資格がないため最終候補を採択しない。旧31方式・支持31,601・欠測249・二ASR各33群の旧結果を保持し、総CERや波形別gainによる救済は行わない。P5未開封・品質未達。',
            '', '一次資料: [SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)と[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。対数利得分離は波形からの利得推定ではなくMCPのb0式を使う。源の時計と原励振の一致は、フィルタ後の音響/知覚pitch一致を保証しない。',
            '', '原nativeへの全研究保護: '+str(research_gates),summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,internal_MLSA_helpers_counted=True,failures_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-fir-gain-comparison-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0077.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)
    print(dict(all_MCP_frames=physical['all_frames_checked'],grid_passed=physical['passed'],research_protection_gates=research_gates),flush=True)

if __name__=='__main__':close()
