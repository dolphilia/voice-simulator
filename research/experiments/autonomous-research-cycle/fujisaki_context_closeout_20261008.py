"""64波形の全分母と全MCP frameを照合し、固定文脈韻律の内容保護を封印する。"""
import ast
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from budget import read,digest,encode
from fujisaki_context_comparison_20261008 import ROOT,HERE,NAME,REPO,Budget,job,BASE,PYTHON,MECHANISM

ALL_FRAMES='"""保存全32対の保持因子と候補LF0の独立scalar式を全frame照合。波形再生成なし。"""\nimport sys,json,math\nfrom pathlib import Path\nhere=Path(sys.argv[1]);p=json.loads((here/\'protocol.json\').read_text())\nimport numpy as np\nrows=[]\nfor row in p[\'rows\']:\n for condition,q in p[\'conditions\'].items():\n  base=here/\'render\'/row[\'id\']/condition\n  with np.load(base/\'native.npz\',allow_pickle=False) as z:n={k:z[k].copy() for k in (\'mcp\',\'lf0\',\'lpf\',\'duration\')}\n  with np.load(base/\'fujisaki.npz\',allow_pickle=False) as z:c={k:z[k].copy() for k in n}\n  assert all(np.array_equal(n[k],c[k]) for k in (\'mcp\',\'lpf\',\'duration\'));mask=n[\'lf0\'][:,0]>0\n  assert np.array_equal(mask,c[\'lf0\'][:,0]>0) and n[\'lf0\'][~mask].tobytes()==c[\'lf0\'][~mask].tobytes()\n  nm=json.loads((base/\'native.json\').read_text());cm=json.loads((base/\'fujisaki.json\').read_text());detail=cm[\'meta\'][\'control\'];cmd=detail[\'commands\']\n  assert detail[\'parameters\']==dict(alpha=3.,beta=20.,gamma=.9,Ap_seconds=.15,Aa=.25,phrase_lead_seconds=.2)\n  def gp(t):return 9.*t*math.exp(-3.*t) if t>=0 else 0.\n  def ga(t):return min(1.-(1.+20.*t)*math.exp(-20.*t),.9) if t>=0 else 0.\n  shape=np.array([sum(.15*gp(i*.005-u) for u in cmd[\'phrase_times\'])+sum(.25*(ga(i*.005-u)-ga(i*.005-v)) for u,v in cmd[\'accent_times\']) for i in range(len(n[\'lf0\']))])\n  expected=shape[mask]+detail[\'log_offset\'];error=float(np.max(np.abs(expected-c[\'lf0\'][mask,0])))\n  assert error<=1e-12 and abs(np.median(c[\'lf0\'][mask,0])-math.log(q[\'requested_f0\']))<=2e-15\n  assert not np.array_equal(n[\'lf0\'][mask],c[\'lf0\'][mask]) and not detail[\'native_LF0_values_used_for_shape\']\n  assert nm[\'measurement\'][\'support\']==cm[\'measurement\'][\'support\']\n  for key in (\'duration\',\'msd\',\'settings\',\'state_sha256\',\'variance_sha256\',\'native_parameter_hashes\'):assert nm[\'meta\'][key]==cm[\'meta\'][key]\n  rows.append(dict(id=row[\'id\']+\'/\'+condition,all_saved_retained_parameters_exact=True,LF0_intentionally_changed=True,independent_scalar_LF0_max_error=error,\n                   frames_checked=len(n[\'mcp\']),excluded_frames=0,voiced_mask_and_sentinel_exact=True,fixed_support_exact=True,passed=True))\nassert len(rows)==32\nprint(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v[\'frames_checked\'] for v in rows),saved_arrays_and_metadata_only=True,no_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))\n'

def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    registration=read(HERE/'registration.json');assert digest(Path(__file__))==registration['closeout_source_sha256']
    spec=importlib.util.spec_from_file_location('_minphase_controller',HERE/'controller.py')
    import sys
    sys.path.insert(0,str(HERE));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.verify()
    old=(BASE/'summarize.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='grouped')
    scope={};exec(ast.get_source_segment(old,node),scope);grouped=scope['grouped']
    protocol=read(HERE/'protocol.json');manifest=read(HERE/'render-manifest.json');runtime=read(HERE/'runtime-audit.json')
    assert len(manifest['rows'])==64 and len(runtime['pairs'])==64 and len(runtime['CLI'])==4 and runtime['passed']
    assert manifest['new_render_calls']==64 and runtime['new_render_calls']==132
    records={}
    for x in manifest['rows']:
        assert digest(REPO/x['record'])==x['sha256'];r=read(REPO/x['record']);assert digest(REPO/r['wav'])==r['wav_sha256'];records[r['id']]=r
    for n,h in read(HERE/'measurement-package-contract.json')['files'].items():assert digest(REPO/n)==h
    assert digest(HERE/'runtime-bundle/fujisaki_context.py')==digest(MECHANISM/'runtime-bundle/fujisaki_context.py')
    assert digest(HERE/'runtime-bundle/hts_arrays.dylib')==digest(MECHANISM/'runtime-bundle/hts_arrays.dylib')
    with job(b,'dsp','保存全32対の保持列と独立LF0式の全frame物理照合',96,20000000,600) as j:
        with b.workspace(j,'全保存パラメータ対の科学ライブラリ初期化') as (_,env):
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
                asr_manifest=read(HERE/('asr-manifest-'+engine+'.json'));assert len(asr_manifest['rows'])==asr_manifest['new_ai']==64
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
                key=row['id']+'/'+condition+'/';a=records[key+'native'];z=records[key+'fujisaki']
                assert a['meta']['output_parameter_hashes'][0]==z['meta']['output_parameter_hashes'][0] and a['meta']['output_parameter_hashes'][2]==z['meta']['output_parameter_hashes'][2]
                assert a['meta']['output_parameter_hashes'][1]!=z['meta']['output_parameter_hashes'][1] and a['measurement']['support']==z['measurement']['support']
                assert z['meta']['control']['MCP_LPF_duration_and_MSD_unchanged'] and not z['meta']['control']['native_LF0_values_used_for_shape']
                assert z['meta']['conversion']['alpha']==.55 and z['meta']['conversion']['source_method']=='native-pulse-noise'
                assert a['meta']['conversion']['render_calls_including_internal_MLSA']==z['meta']['conversion']['render_calls_including_internal_MLSA']==1
                pairs.append(dict(id=key+'fujisaki',MCP_LPF_duration_mask_exact=True,LF0_is_intended_factor=True,between_method_source_clock_identity_claimed=False,fixed_support_exact=True,output_changed=a['wav_sha256']!=z['wav_sha256']))
        assert len(pairs)==32 and len(physical['rows'])==32
        fixture=read(HERE/'fixture-audit.json');assert fixture['passed'] and fixture['inherited']
        research_gates={method:engineering[method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[method].values()) and (method=='native' or physical['passed']) for method in protocol['variants']}
        summary=dict(total=64,engineering=engineering,content=content,source_factor_pairs=pairs,paired_generation_complete=True,
            inherited_mechanism_fixture_passed=True,physical_parameter_audit=physical,mechanical_fixture_is_not_speech_quality=True,research_protection_gates=research_gates,
            independent_new_input_noncollision=True,final_non_neural_runtime_verified=True,full_runtime_hash_match=True,
            methodological_limits='旧工学DIO/全体ACFの操作的条件だけ。句/アクセント機構資格を音韻正解・自然さ・動的/境界truthへ拡張しない。全発話中央値はstreaming因果でない。',
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,adopted=False,
            old_31_methods_and_249_missing_and_two_ASR33_groups_unchanged=True,
            next='固定Fujisaki文脈韻律の全分母結果を保持。不改善時は同応答係数/指令時刻/median/gainを同コホートで救済せず、独立な調音source-tract機構または異なる生成表現へ進む。')
        b.write_data(HERE/'summary.json',encode(summary),j)
        compact=dict(summary);compact['content']={m:{n:{k:v for k,v in value.items() if k!='pairs'} for n,value in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json');b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 原HTSと固定句アクセント指令応答の日本語比較','','新16文×2条件×2方式64波形。LF0輪郭をラベル指令から計算し、MCP/LPF/duration/MSD/state/variance・原pulse/noise/MLSA・共通gain.25を保持した。係数/時刻規則の出力後探索なし。全64通常/隔離・CLI4・9論理/物理資料と通信の実拒否を照合した。','','|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'保存全{physical["all_frames_checked"]}frameの保持列/mask/sentinelと候補LF0の固定独立scalar式を照合した。LF0/源時計の方式間一致を主張しない。','',
            'alpha3/beta20/gamma.9/Ap.15秒/Aa.25/句先行.2秒は出力前固定。元LF0値の輪郭/教師/録音/lookupを使わない。全有声median校正はstreaming因果でなく、F2末尾核/無アクセント同値化は未知を保持する。','',
            '旧31方式・支持31,601/欠測249・二ASR33群と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達・最終採択なし。','',
            '一次資料: [Fujisaki and Hirose (1984)](https://www.jstage.jst.go.jp/article/ast1980/5/4/5_4_233/_pdf)。式とラベル規則の独自実装。','', '全件研究保護: '+str(research_gates),summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,internal_MLSA_helpers_counted=True,failures_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='fujisaki-context-comparison-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0114.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)
    print(dict(parameter_pairs=physical['pairs_checked'],research_protection_gates=research_gates),flush=True)

if __name__=='__main__':close()
