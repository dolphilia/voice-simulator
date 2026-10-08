"""全96件・64因子対・二ASR各33群を固定分母でまとめ、周波数軸変更の不通過も封印する。"""
import ast
import importlib.util
import os
from pathlib import Path
from budget import read,digest,encode
from hts_filter_warp_20261008 import ROOT,HERE,NAME,REPO,Budget,job,BASE,PAPER

def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    spec=importlib.util.spec_from_file_location('_glottal_fixed_control',HERE/'controller.py')
    import sys
    sys.path.insert(0,str(HERE));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.verify()
    # 旧33群集計関数を完全なソースで抽出。方式選別用の閾値変更をしない。
    old=(BASE/'summarize.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='grouped')
    scope={};exec(ast.get_source_segment(old,node),scope);grouped=scope['grouped']
    protocol=read(HERE/'protocol.json');manifest=read(HERE/'render-manifest.json');runtime=read(HERE/'runtime-audit.json')
    assert len(manifest['rows'])==96 and len(runtime['pairs'])==96 and len(runtime['CLI'])==4 and runtime['passed']
    records={}
    for x in manifest['rows']:
        assert digest(REPO/x['record'])==x['sha256'];r=read(REPO/x['record']);assert digest(REPO/r['wav'])==r['wav_sha256'];records[r['id']]=r
    for n,h in read(HERE/'measurement-package-contract.json')['files'].items():assert digest(REPO/n)==h
    engineering={};content={};pairs=[]
    with job(b,'audit','全件・固定33群・因子差・保存hash・一時回収の終了監査',size=10000000,seconds=300) as j:
        for method in protocol['variants']:
            selected=[r for r in records.values() if r['variant']==method]
            assert len(selected)==32
            engineering[method]=dict(expected=32,missing_records=0,E0_pass_count=sum(r['E0_pass'] for r in selected),pitch_pass_count=sum(r['pitch_gate']['passed'] for r in selected),
                fixed_support_intervals=sum(len(r['measurement']['support']) for r in selected),missing_support=sum(len(r['measurement']['missing_support']) for r in selected),
                all_required_pass=all(r['E0_pass'] and r['pitch_gate']['passed'] and r['invariants_pass'] for r in selected),
                failures=[dict(id=r['id'],E0=r['meta']['E0'],pitch_gate=r['pitch_gate'],missing_support=r['measurement']['missing_support']) for r in selected if not(r['E0_pass'] and r['pitch_gate']['passed'])])
            content[method]={}
            for engine in ('whisper','reazon'):
                asr_manifest=read(HERE/('asr-manifest-'+engine+'.json'));assert len(asr_manifest['rows'])==96 and asr_manifest['new_ai']==96
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
                for method in protocol['variants'][1:]:
                    z=records[key+method]
                    assert a['meta']['output_parameter_hashes']==z['meta']['output_parameter_hashes']
                    assert a['meta']['conversion']['source_clock_hashes']==z['meta']['conversion']['source_clock_hashes']
                    assert a['measurement']['support']==z['measurement']['support']
                    assert z['meta']['conversion']['effective_filter_alpha']==read(HERE/'registration.json')['effective_alpha'][method]
                    assert z['meta']['conversion']['model_original_alpha']==.55 and z['meta']['conversion']['periodic_source_delay_samples']==0
                    pairs.append(dict(id=key+method,all_parameters_exact=True,excitation_and_cycle_clock_exact=True,effective_alpha=z['meta']['conversion']['effective_filter_alpha'],fixed_support_exact=True,output_changed=a['wav_sha256']!=z['wav_sha256']))
        assert len(pairs)==64
        fixture=read(HERE/'fixture-audit.json');checks=fixture['filter_identity_checks']
        assert len(checks)==12 and len(fixture['checks'])==8
        assert all(x['legacy_audio_exact'] and x['excitation_and_clock_exact'] for x in fixture['checks'])
        mechanical=dict(mc2b_exact=all(x['mc2b_exact'] for x in checks),maximum_log_transfer_identity_error=max(x['allpass_log_transfer_maxerr'] for x in checks),
            excitation_and_clock_exact=True,effective_alpha_only_factor=True,frequency_warp_is_not_uniform_tract_scale=True)
        research_gates={method:engineering[method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[method].values()) for method in protocol['variants']}
        summary=dict(total=96,engineering=engineering,content=content,filter_factor_pairs=pairs,paired_generation_complete=True,
            mechanical_filter_fixture=mechanical,mechanical_fixture_is_not_speech_quality=True,research_protection_gates=research_gates,
            independent_new_input_noncollision=True,final_non_neural_runtime_verified=True,full_runtime_hash_match=True,
            methodological_limits='このコホートのDIO/全体ACF診断。短窓/瞬時F0/動的/知覚の新資格ではない。native名称は双方校正LF0の原pulse対照を指す。',
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
            adopted=False,old_31_methods_and_249_missing_and_two_ASR33_groups_unchanged=True,
            next='原励振と共有係数の一致を保った周波数軸の因果結果を全分母で保持する。原nativeの全工学/二ASR条件を守る有効範囲を次の独立因子へ引き継ぎ、同じalpha係数探索による救済をしない。')
        b.write_data(HERE/'summary.json',encode(summary),j)
        compact=dict(summary);compact['content']={m:{n:{k:v for k,v in value.items() if k!='pairs'} for n,value in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json')
        b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 原励振固定のHTSフィルタ周波数軸比較','', '新16日本語文×2条件×3方式の96波形。全方式が固定の校正LF0と原pulse/noise励振を使い、MLSAのalpha=.55/.50/.60だけを比較した。全64対で全パラメータ・全sample励振列・周期時計・固定支持が一致し、通常/隔離の全96件とCLI4件の波形hashも一致した。','', '|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['','候補を採択しない。欠測/失敗/群ごとの内容悪化を保持し、総CERによる相殺や出力後のgain/係数救済を行わない。旧31方式・支持31,601区間・欠測249区間・各ASR33群の旧判定は更新しない。','',
            f'原理の一次資料: [SPTK公式: MLSAフィルタとall-pass constant]({PAPER})、[mc2bの係数変換](https://sp-nitech.github.io/sptk/latest/main/mc2b.html)。MCP35は変更せず、mc2bとMLSAの実alphaを同時に変更する独立因子。包絡/フィルタ利得の変化も因果効果に含み、波形別の出力正規化は行わない。',
            '', '源のcycle eventは共通の駆動時計であり、新波形のパルスや知覚pitchの正解を意味しない。DIO/全体ACF診断を短窓・動的・境界へ一般化しない。知覚資格なし、P5未開封、全体品質未達。','',summary['next'],'']
        assert len(protocol['rows'])*len(protocol['conditions'])*len(protocol['variants'])==96
        lines+=['機械fixtureの係数/伝達関数恒等式: '+str(mechanical),'原nativeへの全工学/二ASR33群保護: '+str(research_gates),
            'alpha変更を周波数一様倍率、物理的声道長、知覚改善の証拠と扱わない。原励振列の一致はフィルタ後の音響pitchや知覚pitchの一致を意味しない。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,failures_counted=True,Git_closeout_fee_in_global_ledger=True),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()};b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-filter-warp-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0059.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)
    print(b.reconcile(),flush=True)

if __name__=='__main__':close()
