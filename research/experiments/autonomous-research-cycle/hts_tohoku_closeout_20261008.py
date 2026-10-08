"""64波形の全分母と全MCP frameを照合し、全共有HMM比較の内容保護を封印する。"""
import ast
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from budget import read,digest,encode
from hts_tohoku_comparison_20261008 import ROOT,HERE,NAME,REPO,Budget,job,BASE,PYTHON,MECHANISM

ALL_FRAMES='"""全32対で各モデル固有の状態長・列・校正と固定音素支持を確認する。"""\nimport sys,json,hashlib\nfrom pathlib import Path\nhere=Path(sys.argv[1]);p=json.loads((here/\'protocol.json\').read_text())\nimport numpy as np\ndef ah(v):return hashlib.sha256(np.asarray(v,dtype=\'<f8\').tobytes()).hexdigest()\nrows=[]\nfor row in p[\'rows\']:\n for condition,cfg in p[\'conditions\'].items():\n  base=here/\'render\'/row[\'id\']/condition;items={}\n  for method in (\'native\',\'tohoku\'):\n   with np.load(base/(method+\'.npz\'),allow_pickle=False) as z:a={k:z[k].copy() for k in (\'mcp\',\'lf0\',\'lpf\',\'duration\')}\n   r=json.loads((base/(method+\'.json\')).read_text());meta=r[\'meta\'];n=len(a[\'mcp\'])\n   assert a[\'mcp\'].shape==(n,35) and a[\'lf0\'].shape==(n,1) and a[\'lpf\'].shape==(n,31)\n   assert all(np.isfinite(a[k]).all() for k in a) and a[\'duration\'].shape==(len(row[\'full_context_labels\'])*5,)\n   assert np.all(a[\'duration\']>=1) and np.all(a[\'duration\']==np.floor(a[\'duration\'])) and int(a[\'duration\'].sum())==n\n   assert a[\'duration\'].tolist()==meta[\'duration\'] and [ah(a[k]) for k in (\'mcp\',\'lf0\',\'lpf\')]==meta[\'output_parameter_hashes\']\n   voiced=a[\'lf0\'][:,0]>0;assert voiced.any() and np.all(a[\'lf0\'][~voiced,0]==-1e10)\n   median=float(np.exp(np.median(a[\'lf0\'][voiced,0])));assert abs(median-cfg[\'requested_f0\'])<=1e-9\n   assert meta[\'native_parameter_hashes\'][0]==meta[\'output_parameter_hashes\'][0] and meta[\'native_parameter_hashes\'][2]==meta[\'output_parameter_hashes\'][2]\n   assert meta[\'model_original_states_and_parameters_preserved_except_uniform_LF0\'] and meta[\'invariants_pass\']\n   assert meta[\'conversion\'][\'original_excitation_sha256\']==meta[\'conversion\'][\'processed_excitation_sha256\']\n   items[method]=(a,r)\n  a,ra=items[\'native\'];z,rz=items[\'tohoku\'];assert ra[\'measurement\'][\'support\']==rz[\'measurement\'][\'support\']\n  assert all(0<=index<len(row[\'full_context_labels\']) for index in ra[\'measurement\'][\'support\'])\n  assert ra[\'meta\'][\'voice_sha256\']!=rz[\'meta\'][\'voice_sha256\'] and not np.array_equal(a[\'mcp\'],z[\'mcp\'])\n  rows.append(dict(id=row[\'id\']+\'/\'+condition,frames_checked_native=len(a[\'mcp\']),frames_checked_candidate=len(z[\'mcp\']),frames_checked=len(a[\'mcp\'])+len(z[\'mcp\']),excluded_frames=0,\n   each_model_duration_and_parameter_hashes_exact=True,each_model_MCP_LPF_and_voicing_control_preserved=True,fixed_phoneme_index_support_exact=True,\n   model_specific_time_and_acoustics_are_intended_factor=True,source_clock_equality_between_models_claimed=False,passed=True))\nassert len(rows)==32\nprint(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v[\'frames_checked\'] for v in rows),saved_arrays_only=True,no_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))\n'

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
    for name,h in read(MECHANISM/'runtime-bundle/manifest.json')['files'].items():assert digest(HERE/'runtime-bundle'/name)==h,name
    with job(b,'dsp','保存全32対の各モデル状態長・全列・校正・音素支持の物理照合',96,20000000,600) as j:
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
                key=row['id']+'/'+condition+'/';a=records[key+'native'];z=records[key+'tohoku']
                assert a['measurement']['support']==z['measurement']['support']
                assert a['meta']['settings']==z['meta']['settings'] and a['meta']['output_gain']==z['meta']['output_gain']==.25
                assert a['meta']['shared_acoustic_model']=='mei' and z['meta']['shared_acoustic_model']=='tohoku'
                assert a['meta']['voice_sha256']!=z['meta']['voice_sha256']
                for r in (a,z):
                    assert r['meta']['model_original_states_and_parameters_preserved_except_uniform_LF0'] and r['meta']['conversion']['source_method']=='native'
                    assert r['meta']['conversion']['original_excitation_sha256']==r['meta']['conversion']['processed_excitation_sha256']
                    assert r['meta']['conversion']['render_calls_including_internal_MLSA']==1
                pairs.append(dict(id=key+'tohoku',each_model_internal_controls_preserved=True,model_specific_time_and_streams_intentionally_changed=True,fixed_phoneme_index_support_exact=True,
                    native_duration_frames=sum(a['meta']['duration']),candidate_duration_frames=sum(z['meta']['duration']),source_clock_equality_between_models_claimed=False,output_changed=a['wav_sha256']!=z['wav_sha256']))
        assert len(pairs)==32 and len(physical['rows'])==32
        fixture=read(HERE/'fixture-audit.json');assert fixture['passed'] and fixture['inherited']
        research_gates={method:engineering[method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[method].values()) and (method=='native' or physical['passed']) for method in protocol['variants']}
        summary=dict(total=64,engineering=engineering,content=content,full_model_factor_pairs=pairs,paired_generation_complete=True,
            inherited_mechanism_fixture_passed=True,physical_parameter_audit=physical,mechanical_fixture_is_not_speech_quality=True,research_protection_gates=research_gates,
            independent_new_input_noncollision=True,final_non_neural_runtime_verified=True,full_runtime_hash_match=True,
            methodological_limits='旧DIO/全体ACFの操作的条件。全HMM対比でモデル固有の時間/有声/源が違う。native音素index支持を候補の時間軸に適用する。自然さ/動的pitch/境界のtruthではない。',
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,adopted=False,
            old_31_methods_and_249_missing_and_two_ASR33_groups_unchanged=True,
            next='全モデルの工学/二ASR結果を全分母で保持。全件保護と改善が確認できれば独立新入力へ別登録し、未通過を同コホートのstyle/補間/係数/gainで救済しない。資格不足の知覚を採択根拠にしない。')
        b.write_data(HERE/'summary.json',encode(summary),j)
        compact=dict(summary);compact['content']={m:{n:{k:v for k,v in value.items() if k!='pairs'} for n,value in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json');b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 原Meiと公開Tohoku共有HMM全モデルの比較','','新16文×2条件×2モデル64波形。全HMMを交換するため、MCP/LF0/LPF/duration/MSD/GVはモデル固有。辞書・labels・速度/指定中央値・MLPG/HTS・resample/fade/gain.25を共通化した。nativeの音素index支持を固定し、candidate固有の時間軸へ適用。通常/隔離64組・CLI4・実拒否を確認した。','','|モデル|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'二モデルの保存全{physical["all_frames_checked"]}frameで各モデル固有の状態長合計・列/hash・有限性・指定LF0中央値と固定音素支持を照合した。二モデル間の源時計/列一致や同標本の対比は主張しない。','',
            'HTS voice tohoku-f01、Copyright 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University。[公式配布](https://github.com/icn-lab/htsvoice-tohoku-f01)・[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。モデルは不改変、生成時の一様LF0制御と共通resample/fade/gainを変更として表示。Meiの元CC BY 3.0表示もbundleに保持する。提供者の推奨を主張しない。','',
            '旧31方式・支持31,601・欠測249・二ASR33群と凍結経路を保持。日本語知覚資格なし・P5未開封・品質未達。最終採択なし。','',
            '全件研究保護: '+str(research_gates),summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,internal_MLSA_helpers_counted=True,failures_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-tohoku-comparison-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0101.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)
    print(dict(parameter_pairs=physical['pairs_checked'],research_protection_gates=research_gates),flush=True)

if __name__=='__main__':close()
