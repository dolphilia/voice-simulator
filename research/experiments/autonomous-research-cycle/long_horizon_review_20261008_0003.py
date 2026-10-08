"""科学18件で第3回レビューし、FIRから別測定資格へ配分を変更する。"""
import hashlib
import os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261008-v3';NAME='long-horizon-review-v3'
SCIENCE=['nas-hts-minphase-comparison-20261008-v1','nas-hts-fir-cutoff-qualification-20261008-v1','nas-hts-fft-fir-mechanism-20261008-v1','nas-hts-fft-fir-comparison-20261008-v1','nas-hts-fir-gain-mechanism-20261008-v1','nas-hts-fir-gain-comparison-20261008-v1']

def main():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==18
    previous=state['long_horizon']['last_review'];assert previous['scientific_completed']==12 and digest(ROOT/previous['path'])==previous['sha256']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(review_number=3,trigger='前回レビュー後に科学6件終了',scientific_completed=18,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),quality_goal_completed=False,scientific_outputs=0)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','新六封印・全FIR失敗・旧保護・測定資格への配分を照合',reserve_bytes=10000000) as j:
        b.save(HERE/'registration.json',reg,j);checked={};seals={}
        for name in SCIENCE:
            p=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(p);seals[str(p.relative_to(REPO))]=digest(p)
            assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened']
            for n,h in seal['files'].items():
                f=REPO/n;assert not any(x in f.parts for x in ('protected','holdout','splits'))
                if n in checked:assert checked[n]==h
                else:assert digest(f)==h,n;checked[n]=h
        a=state['long_horizon'];assert digest(ROOT/a['preservation_path'])==a['preservation_sha256'];b._authorization(b.snapshot());b._science_ready(b.snapshot())
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in b.snapshot()['temporary_work'].values())
        b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,new_references_hashed=len(checked),new_references_sha256=hashlib.sha256(encode(checked)).hexdigest(),old_preservation_audit_sha256=a['preservation_sha256'],old_28_contracts_exact=True,validated_management_sources_exact=True,old_102794_physical_files_full_rehash_this_review=False,all_owned_temporary_absent=True,protected_confirmation_text_read=False),j)
        results={name:read(ROOT/'campaigns'/name/'aggregate-summary.json') for name in SCIENCE}
        last=results[SCIENCE[-1]];assert last['total']==96 and results[SCIENCE[3]]['total']==64
        fir_pass=any(last['research_protection_gates'][m] for m in ('fft_fir','fft_loggain'))
        compact={}
        for name in (SCIENCE[0],SCIENCE[3],SCIENCE[-1]):
            r=results[name];compact[name]=dict(total=r['total'],all_MCP_frames=r['real_MCP_grid_audit']['all_frames_checked'],MCP_grid_passed=r['real_MCP_grid_audit']['passed'],research_gates=r['research_protection_gates'],methods={m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],support=e['fixed_support_intervals'],ASR={n:len(v['worsening_groups']) for n,v in r['content'][m].items()}) for m,e in r['engineering'].items()})
        decision=dict(review_number=3,scientific_completed=18,previous_review=previous,comparisons=compact,
            causes=['人工MCPの資格は実日本語の全frame応答を保証しなかった。FIR1024は306frameで有限応答/tailの基準を外れた。',
                '既コホートで2048点を最小適格長として固定し、新コホートでも全frameの有限gridを通過した。静的応答と音声の保護は別だった。',
                '原HTSのb0対数利得とIR全体の算術補間は異なる。純利得と形状を分離する別表現は人工式・原HTS・因果性を検証できた。',
                '全MCP/LF0/LPF/duration/状態/励振/時計と通常・隔離出力の一致は、フィルタ後のピッチ・内容・自然さの一致を保証しない。'],
            actual_generation_improvement=fir_pass,generalization_quality_certified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            measurement_scope='有限16384gridの静的応答/参考IR tailと人工時間表現のみ。固定DIO/全体ACFを短窓・動的・瞬時F0・知覚へ拡張しない。',
            frozen_routes=['前レビューまでの全凍結を維持']+([] if fir_pass else ['FIR1024→FFT2048→利得分離の三比較で全件保護不通過。同じFIR補間・係数・利得のコホート別救済を封印']),
            old_support_intervals=31601,old_missing=dict(total=249,HTS=94,WORLD=155),old_31_methods_and_each_ASR33_groups_kept=True,
            two_review_rule='第2回・第3回でも音声品質目標への資格は得ていない。機構/有限長/時間利得の原因を区別したが、同フィルタ経路の係数探索を続けず、測定資格と別の共有生成制御へ配分を変える。',
            next_question='YIN型の累積平均正規化差分・固定閾値・放物線補間は、既知音響周期の人工信号で20/40/80ms・動的・境界のどの範囲を検証できるか。旧測定/欠測/判定は不変。',
            next_estimate=dict(seconds=7200,bytes=300000000,write_bytes=800000000,render=2000,dsp=8000,ai=0,teacher=0,train=0,inverse=0,download=0,comparison='新規に式で生成した周期/変動/境界・無周期fixtureを出力前固定。音響周期truthのみ、知覚truth・保存HTS救済ではない。'),
            next_gates_unchanged=True,review_does_not_require_user_approval=True,resource_status=b.review_due(),
            perceptual_status='現HTS域の日本語刺激/個別評点対応・適用範囲・利用条件を満たす資格は引き続きない。新公開対応がない同じ8資料は繰り返さない。',
            remaining_independent_work='新しい短窓/動的/境界の測定資格、別の共有源制御/調音表現、新公開音声-評点対応が成立する場合の知覚資格研究。')
        b.save(HERE/'decision.json',decision,j)
        lines=['# 長期包括承認後の第3回定期レビュー','','科学6件、累計18件の区切りでレビューした。品質未達・日本語知覚資格なし・P5未開封。旧消費・旧28契約・旧31方式・支持31,601・欠測249・二ASR各33群を引き継ぐ。','',
            'FIRの人工資格、実MCP全frame、有限長、対数利得の時間表現を区別した。2048点で静的応答を守れても音声の保護は別であり、源時計一致をピッチや自然さのtruthにしない。','',
            '|比較|方式|pitch通過|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---|---:|---:|---:|---:|']
        for name,r in compact.items():
            for m,e in r['methods'].items():lines.append(f'|{name}|{m}|{e["pitch"]}/32|{e["missing"]}/{e["support"]}|{e["ASR"]["whisper"]}/33|{e["ASR"]["reazon"]}/33|')
        lines+=['','三回目のFIR全件保護通過: '+str(fir_pass)+'。不通過の同補間・係数救済は封印する。第2回・第3回でも最終品質への資格は得ておらず、別の測定資格と共有生成制御へ配分を変更する。','',decision['next_question'],'',
            '新六封印の全参照をhash照合した。旧28契約・検証済み管理ソース・指定媒体・位置索引・所有一時領域全件の不存在を確認した。旧102,794実体の全再hashは今回は行っていない。','',
            '192時間・最後12時間終了専用・0円・全資源上限は維持する。レビューは新予算・品質達成・初期化ではなく、枠内で次の有効処理へ継続する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=18,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0003-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0078.json',dict(latest_completed=NAME,scientific_completed=18,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()))
    print(dict(review_completed=True,scientific_completed=18,FIR_passed=fir_pass,quality_goal_completed=False),flush=True)

if __name__=='__main__':main()
