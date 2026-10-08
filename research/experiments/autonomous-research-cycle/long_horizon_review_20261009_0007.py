"""科学42件のレビュー。独立声道の内容不保護と放射結合の限定資格を保持する。"""
import hashlib,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261009-v7';NAME='long-horizon-review-v7'
SCIENCE=['nas-waveguide-vowel-mechanism-20261008-v1','nas-waveguide-sequence-runtime-20261008-v1','nas-waveguide-vowel-comparison-20261008-v1','nas-radiation-boundary-mechanism-20261008-v1','nas-radiation-passive-state-20261008-v1','nas-radiated-waveguide-mechanism-20261009-v1']
def main():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==42
    previous=state['long_horizon']['last_review'];assert previous['scientific_completed']==36 and digest(ROOT/previous['path'])==previous['sha256']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(review_number=7,trigger='前レビュー後の科学6件終了',scientific_completed=42,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','六封印・内容/全分母・旧契約・一時不存在・二駆動の限定内容配分',reserve_bytes=10000000) as j:
        b.save(HERE/'registration.json',reg,j);checked={};seals={}
        for name in SCIENCE:
            p=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(p);seals[str(p.relative_to(REPO))]=digest(p)
            assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened']
            for n,h in seal['files'].items():
                f=REPO/n;assert not any(v in f.parts for v in ('protected','holdout','splits'))
                if n in checked:assert checked[n]==h
                else:assert digest(f)==h,n;checked[n]=h
        a=state['long_horizon'];assert digest(ROOT/a['preservation_path'])==a['preservation_sha256'];b._authorization(b.snapshot());b._science_ready(b.snapshot())
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in b.snapshot()['temporary_work'].values())
        b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,new_references_hashed=len(checked),new_references_sha256=hashlib.sha256(encode(checked)).hexdigest(),old_preservation_audit_sha256=a['preservation_sha256'],old_28_contracts_exact=True,validated_management_sources_exact=True,old_102794_physical_files_full_rehash_this_review=False,all_owned_temporary_absent=True,protected_confirmation_text_read=False),j)
        results=[read(ROOT/'campaigns'/n/'aggregate-summary.json') for n in SCIENCE];vowel,seq,comp,fixed,port,coupled=results
        assert vowel['engineering_all_required_pass'] and seq['engineering_all_required_pass'] and not comp['adopted'] and not comp['research_protection_gates']['waveguide']
        assert fixed['passed'] and port['passed'] and coupled['mechanism_passed'] and not coupled['engineering_all_required_pass']
        comparison=dict(total=64,research_gates=comp['research_protection_gates'],methods={m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],support=e['fixed_support_intervals'],ASR={n:len(v['worsening_groups']) for n,v in comp['content'][m].items()}) for m,e in comp['engineering'].items()})
        failures=[dict(id=r['id'],source=r['source'],dio_error_semitones=r['pitch']['dio_error_semitones'],acf_error_semitones=r['pitch']['acf_error_semitones'],acf_confidence=r['pitch']['acf_confidence'],missing=r['pitch']['missing']) for r in coupled['rows'] if not r['pitch']['passed']]
        sequence_subset={s:dict(total=8,E0=sum(r['E0']['E0_pass'] for r in coupled['rows'] if r['source']==s and r['kind']=='sequence'),pitch=sum(r['pitch']['passed'] for r in coupled['rows'] if r['source']==s and r['kind']=='sequence')) for s in ('derivative','flow')}
        assert len(failures)==12 and all(x['E0']==x['pitch']==8 for x in sequence_subset.values())
        decision=dict(review_number=7,scientific_completed=42,previous_review=previous,finite_vowel_comparison=comparison,
          coarse_vowels=dict(static_total=15,transition_total=20,E0_and_pitch_all_pass=True,missing=0,support=105,not_modern_MRI_truth=True),
          sequence=dict(total=8,longest_ms=6000,E0_and_pitch_all_pass=True,missing=0,support=77,normal_isolated_CLI_exact=True,initial_isolation_failure_and_extra_cost_kept=True),
          radiation=dict(fixed_conditions=16,passive_state_grid=516,passive_state_signals=56,fixed_and_dynamic_math_passed=True,loss_port_not_far_field=True,moving_wall_work_not_qualified=True),
          coupled=dict(total=86,mechanism_passed=True,engineering_all_required_pass=False,sources=coupled['summary'],sequence_subset=sequence_subset,pitch_failures=failures,actual_render_calls=coupled['actual_render_calls'],output_source_coefficients_not_optimized=True),
          causes=['粗い一次16径と連続stateは工学を通過したが、新64語句の二ASR内容を保持せず不採択。',
            '固定円管反射と共通正規化放射stateは独立数値/受動/因果/区切りを通過。人体壁仕事や実micに資格を広げない。',
            '声道結合の両駆動はE0 43/43、pitch 37/43、欠測0/182。主に/e/220Hzとその遷移で倍音測定に不通過。積分形でDIOが近づいてもACF不通過を除外/緩和しない。',
            '両駆動の有限連続列8/8はE0/pitchを通過している。この限定域の新語句内容診断は未実施。両方を同時に比較し、全機構43件の失敗を採択前に忘れない。'],
          actual_generated_speech_quality_improvement_verified=False,generalization_quality_certified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
          frozen_routes=['全前レビューまでの凍結を維持','第70失敗コホートの径/gain/終端/時刻/LF係数の救済をしない','第73の/e/失敗条件を径/反射/駆動係数/phase/gain/測定基準で救済しない','どちらかの駆動を第73出力を見て選別しない','12知覚資料は新しい対応資料なしに同条件再探索しない'],
          old_support_intervals=31601,old_missing=dict(total=249,HTS=94,WORLD=155),old_31_methods_and_each_ASR33_groups_kept=True,
          two_review_rule='第6/7回も最終品質改善資格なし。旧HMM/フィルタ/励振の救済へ戻らない。独立声道の源/放射という新機構の内容効果を、新入力の一回の限定診断で確かめる。全工学不通過を先に保持し、内容改善があっても最終資格にはしない。次の反復は同係数探索ではなく、一次の新形状/分布損失/閉鎖/鼻腔/子音の独立機構へ移る。',
          next_question='両放射結合駆動は、新しい有限母音語句において原nativeに対して二ASR33群の内容を保持できるか。全第73工学失敗を保持した診断であり、一般日本語または採択の資格ではない。',
          next_estimate=dict(seconds=28800,bytes=1800000000,write_bytes=2800000000,render=6000,dsp=3000,ai=384,teacher=0,train=0,inverse=0,download=0,expected_DSP=678,expected_AI=192,expected_render_at_most=5200,expansion_reason='新16語句×2条件×原native/二事前固定駆動の96波形、全192通常/隔離とCLI6を源/内部block込みで比較するため、通常3000renderを超える。開始前理由付き上限6000を使用し、旧消費と残枠を保持する。'),
          next_input='新しい8短/8長。短は4..6母音、長は8..24母音。第70の固定支持数不足を旧基準変更で救わず、新しい入力の最小長を事前設計する。未使用本文とfull-context履歴を照合し、初出力後に語句を変更/除外しない。候補は共通の250/215ms、native支持indexを一度固定、最低3支持・欠測全分母を維持。',
          next_after_failure='同新コホートの係数/gain/時刻/径/終端を探索しない。新一次MRI形状や分布した壁/粘熱損失等を別登録する。源はpower-wave注入という限界と補完loss portの位相の非物理性を保持する。',
          perceptual_status='既存12資料は現日本語非ニューラル刺激/個別評点の実校正資格なし。新声道域へ資格を自動移転しない。P5未開封。',resource_status=b.review_due(),review_does_not_require_user_approval=True,all_caps_and_closing_reserve_kept=True)
        b.save(HERE/'decision.json',decision,j)
        lines=['# 長期包括承認後の第7回定期レビュー','','科学6件、累計42件終了。最終品質未達・日本語知覚資格なし・P5未開封。旧31方式、支持31,601/欠測249、全契約・封印・費用を保持する。','', '|有限語句比較|E0|pitch|支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in comparison['methods'].items():lines.append(f'|{m}|{e["E0"]}/32|{e["pitch"]}/32|{e["missing"]}/{e["support"]}|{e["ASR"]["whisper"]}/33|{e["ASR"]["reazon"]}/33|')
        lines += ['', '原の独立声道は二ASR内容不保護で不採択。同コホートの径/gain/終端/時刻/源係数の救済を凍結する。固定放射16条件と共通stateの516行列/56信号は数値・受動・因果・区切りを通過。数学的loss portを実mic音圧へ読み替えない。','', '|結合駆動|E0|pitch|固定支持欠測|連続列E0/pitch|','|---|---:|---:|---:|---:|']
        for m,e in coupled['summary'].items():lines.append(f'|{m}|{e["E0_pass"]}/43|{e["pitch_pass"]}/43|{e["missing_support"]}/{e["fixed_support_intervals"]}|8/8|')
        lines += ['', '第73の全工学は不通過。/e/220Hz周辺の倍音測定での不通過を残し、基準・係数を変更しない。両駆動の連続列8件の限定工学は通過した。新しい有限語句で両駆動を同時に比較し、内容の効果だけを診断する。内容が改善してもこの工学失敗と知覚資格不足を消さず、最終採択としない。','',decision['two_review_rule'],'',decision['next_question'],'',decision['next_input'],'',decision['next_estimate']['expansion_reason'],'',
          '新六封印の全参照・旧28契約・管理ガード・指定媒体/索引・全所有一時の不存在を照合。旧102,794実体の全再hashはしていない。192時間/終了専用12時間/0円/全資源上限を同じ台帳で維持し、自律的に継続する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=42,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0007-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0131.json',dict(latest_completed=NAME,scientific_completed=42,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()));print(dict(review_completed=True,scientific_completed=42,quality_goal_completed=False),flush=True)
if __name__=='__main__':main()
