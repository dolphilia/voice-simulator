"""64波形の全分母と全MCP frameを照合し、FIR経路の内容保護を封印する。"""
import ast
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from budget import read,digest,encode
from hts_allpass_comparison_20261008 import ROOT,HERE,NAME,REPO,Budget,job,BASE,PYTHON,MECHANISM

ALL_FRAMES='"""保存した全32対の四列を直接照合する。新波形の再生成なし。"""\nimport sys,json\nfrom pathlib import Path\nhere=Path(sys.argv[1]);p=json.loads((here/\'protocol.json\').read_text())\nimport numpy as np\nrows=[]\nfor row in p[\'rows\']:\n for condition in p[\'conditions\']:\n    base=here/\'render\'/row[\'id\']/condition\n    with np.load(base/\'native.npz\',allow_pickle=False) as z:native={k:z[k].copy() for k in (\'mcp\',\'lf0\',\'lpf\',\'duration\')}\n    with np.load(base/\'allpass.npz\',allow_pickle=False) as z:assert all(np.array_equal(z[k],v) for k,v in native.items())\n    rows.append(dict(id=row[\'id\']+\'/\'+condition,all_saved_parameters_exact=True,frames_checked=len(native[\'mcp\']),excluded_frames=0,passed=True))\nassert len(rows)==32\nprint(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v[\'frames_checked\'] for v in rows),saved_arrays_only=True,no_wave_resynthesis=True,render=0,dsp=64,quality_certified=False)))\n'

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
    assert digest(HERE/'shape.dylib')==digest(MECHANISM/'shape.dylib') and digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')
    with job(b,'dsp','保存全32対のMCP/LF0/LPF/duration物理照合',64,20000000,600) as j:
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
                key=row['id']+'/'+condition+'/';a=records[key+'native'];z=records[key+'allpass']
                assert a['meta']['output_parameter_hashes']==z['meta']['output_parameter_hashes']
                assert a['meta']['conversion']['source_clock_hashes']==z['meta']['conversion']['source_clock_hashes'] and a['measurement']['support']==z['measurement']['support']
                assert a['meta']['conversion']['original_excitation_sha256']==z['meta']['conversion']['original_excitation_sha256']
                assert z['meta']['conversion']['processed_excitation_intentionally_changed']
                assert z['meta']['conversion']['effective_filter_alpha']==.55 and z['meta']['conversion']['source_allpass_pole']==.95
                assert a['meta']['conversion']['render_calls_including_internal_MLSA']==1 and z['meta']['conversion']['render_calls_including_internal_MLSA']==1
                pairs.append(dict(id=key+'allpass',all_parameters_exact=True,original_excitation_and_cycle_clock_exact=True,processed_excitation_is_intended_factor=True,fixed_support_exact=True,output_changed=a['wav_sha256']!=z['wav_sha256']))
        assert len(pairs)==32 and len(physical['rows'])==32
        fixture=read(HERE/'fixture-audit.json');assert fixture['passed'] and fixture['inherited']
        research_gates={method:engineering[method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[method].values()) and (method=='native' or physical['passed']) for method in protocol['variants']}
        summary=dict(total=64,engineering=engineering,content=content,source_factor_pairs=pairs,paired_generation_complete=True,
            inherited_mechanism_fixture_passed=True,physical_parameter_audit=physical,mechanical_fixture_is_not_speech_quality=True,research_protection_gates=research_gates,
            independent_new_input_noncollision=True,final_non_neural_runtime_verified=True,full_runtime_hash_match=True,
            methodological_limits='原工学DIO/全体ACFと人工オールパスLTI資格。人工YIN40ms資格をHTSや知覚へ拡張しない。',
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,adopted=False,
            old_31_methods_and_249_missing_and_two_ASR33_groups_unchanged=True,
            next='源の位相因子と振幅/内容保護を全件で保持する。不通過を同コホートのpole調整で救済せず、別の共有生成制御または独立測定へ進む。')
        b.write_data(HERE/'summary.json',encode(summary),j)
        compact=dict(summary);compact['content']={m:{n:{k:v for k,v in value.items() if k!='pairs'} for n,value in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json');b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 原HTSとLPF後オールパス励振の比較','','新16文×2条件×2方式の64波形。原MCP/LF0/LPF/duration、原励振と源時計を保持し、候補の処理励振だけpole.95の周波数依存位相を変更した。全32対の保存列、全64通常/隔離、CLI4と実読取/通信拒否を照合した。','','|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'保存した全{physical["all_frames_checked"]}frameの三streamとdurationを照合した。源時計・原励振一致は処理後音響pitchや自然さのtruthではない。','',
            '振幅1は安定LTIの解析性質であり、非定常MLSA出力や有限音声のエネルギー保存を保証しない。固定poleの調整で不通過を救済しない。YINの人工40ms資格もこの未知HTSへ移さない。',
            '', '旧31方式・支持31,601・欠測249・二ASR各33群の判定、FIRなどの封印経路を保持する。日本語知覚資格なし・P5未開封・品質未達。候補は最終採択しない。',
            '', '一次資料: [Julius O. Smith, Allpass Filters](https://ccrma.stanford.edu/~jos/filters/Allpass_Filters.html)。', '', '全件研究保護: '+str(research_gates),summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,internal_MLSA_helpers_counted=True,failures_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-allpass-comparison-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0084.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)
    print(dict(parameter_pairs=physical['pairs_checked'],research_protection_gates=research_gates),flush=True)

if __name__=='__main__':close()
