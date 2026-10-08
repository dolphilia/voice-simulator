"""全64件と二ASR各33群を固定分母でまとめ、源差分次数の不通過も封印する。"""
import ast
import importlib.util
import os
from pathlib import Path
from budget import read,digest,encode
from hts_fractional_pulse_20261008 import ROOT,HERE,NAME,REPO,Budget,job,BASE,PAPER

def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    spec=importlib.util.spec_from_file_location('_glottal_fixed_control',HERE/'controller.py')
    import sys
    sys.path.insert(0,str(HERE));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.verify()
    # 旧33群集計関数を完全なソースで抽出。方式選別用の閾値変更をしない。
    old=(BASE/'summarize.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='grouped')
    scope={};exec(ast.get_source_segment(old,node),scope);grouped=scope['grouped']
    protocol=read(HERE/'protocol.json');manifest=read(HERE/'render-manifest.json');runtime=read(HERE/'runtime-audit.json')
    assert len(manifest['rows'])==128 and len(runtime['pairs'])==128 and len(runtime['CLI'])==4 and runtime['passed']
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
                asr_manifest=read(HERE/('asr-manifest-'+engine+'.json'));assert len(asr_manifest['rows'])==128 and asr_manifest['new_ai']==128
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
                    pairs.append(dict(id=key+method,all_parameters_exact=True,cycle_clock_exact=True,fixed_support_exact=True,output_changed=a['wav_sha256']!=z['wav_sha256']))
        assert len(pairs)==96
        relative_to_latency={}
        for method in ('linear','sinc'):
            relative_to_latency[method]={}
            for engine in ('whisper','reazon'):
                values=[]
                for x,y in zip(content[method][engine]['pairs'],content['latency'][engine]['pairs']):
                    assert (x['text_id'],x['condition'],x['characters'])==(y['text_id'],y['condition'],y['characters'])
                    v=dict(x);v['native_errors']=y['errors'];values.append(v)
                relative_to_latency[method][engine]=grouped(values)
        fixture=read(HERE/'fixture-audit.json')
        mechanical={method:dict(maximum_error_samples=max(x['phase_error_samples'][method] for x in fixture['phase_checks']),
            mean_error_samples=sum(x['phase_error_samples'][method] for x in fixture['phase_checks'])/len(fixture['phase_checks'])) for method in ('latency','linear','sinc')}
        research_gates={method:engineering[method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[method].values()) for method in protocol['variants']}
        summary=dict(total=128,engineering=engineering,content=content,source_factor_pairs=pairs,paired_generation_complete=True,
            mechanical_phase_fixture=mechanical,mechanical_fixture_is_not_speech_quality=True,research_protection_gates=research_gates,relative_to_latency=relative_to_latency,
            independent_new_input_noncollision=True,final_non_neural_runtime_verified=True,full_runtime_hash_match=True,
            methodological_limits='このコホートのDIO/全体ACF診断。短窓/瞬時F0/動的/知覚の新資格ではない。native名称は双方校正LF0の原pulse対照を指す。',
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
            adopted=False,old_31_methods_and_249_missing_and_two_ASR33_groups_unchanged=True,
            next='機械的位置誤差低減と実波形の全保護ゲートを区別し、補間の位相/利得と後続の有効な生成比較を判断する。')
        b.write_data(HERE/'summary.json',encode(summary),j)
        compact=dict(summary);compact['content']={m:{n:{k:v for k,v in value.items() if k!='pairs'} for n,value in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json')
        b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 共有HTSのpulse位置補間比較','', '新16日本語文×2条件×4方式の128波形。双方とも固定の校正LF0を使い、原pulse、4sample遅延pulse、同遅延下の線形/9tap窓付きsinc補間を比較した。全96対で全パラメータ・周期時計・固定支持が一致し、通常/隔離の全128件とCLI4件の波形hashも一致した。','', '|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['','候補を採択しない。欠測/失敗/群ごとの内容悪化を保持し、総CERによる相殺や出力後のgain/係数救済を行わない。旧31方式・支持31,601区間・欠測249区間・各ASR33群の旧判定は更新しない。','',
            f'補間原理の一次資料: [J. O. Smith: Windowed Sinc Interpolation]({PAPER})。4sample遅延、2tap線形/9tap窓付きsincの固定独自実装。最適設計や聴取結果の再現、日本語知覚資格、品質改善の証明ではない。',
            '', '源のcycle eventは共通の駆動時計であり、新波形のパルスや知覚pitchの正解を意味しない。DIO/全体ACF診断を短窓・動的・境界へ一般化しない。知覚資格なし、P5未開封、全体品質未達。','',summary['next'],'']
        assert len(protocol['rows'])*len(protocol['conditions'])*len(protocol['variants'])==128
        lines+=['機械fixtureの基本周波数での位相誤差(sample): '+str(mechanical),'原nativeへの工学/二ASR全33群保護: '+str(research_gates),
            '位置補間の固定L2正規化は周波数ごとの利得を保存しない。遅延と補間の別対照を保持し、位相だけの効果と読み替えない。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,failures_counted=True,Git_closeout_fee_in_global_ledger=True),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()};b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-fractional-pulse-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0055.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)
    print(b.reconcile(),flush=True)

if __name__=='__main__':close()
