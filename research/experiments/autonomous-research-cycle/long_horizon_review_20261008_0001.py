"""科学6件の定期レビュー。承認待ちへ戻らず、費用・根拠・凍結経路を記録する。"""
import hashlib
import os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261008-v1';NAME='long-horizon-review-v1'
SCIENCE=['nas-hts-lpf-observation-20261008-v1','nas-world-original-reproduction-20261008-v1','nas-hts-overlap-qualification-20261008-v1','nas-japanese-perceptual-resource-audit-20261008-v1','nas-hts-glottal-shape-20261008-v1','nas-hts-glottal-difference-20261008-v1']

def main():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==6
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(reason='長期承認から科学6件終了による最初の定期レビュー',scientific_completed=6,last_review=state['long_horizon']['last_review'],limits=limits,scientific_outputs=0,protected_confirmation_opened=False,quality_goal_completed=False,controller_sha256=digest(Path(__file__)))
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','六科学封印全参照と旧管理境界・費用・保存・一時回収の照合',reserve_bytes=10000000) as j:
        b.save(HERE/'registration.json',reg,j)
        checked={};seals={}
        for name in SCIENCE:
            path=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(path);seals[str(path.relative_to(REPO))]=digest(path)
            assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened']
            for n,h in seal['files'].items():
                p=REPO/n
                assert 'protected' not in p.parts and 'holdout' not in p.parts and 'splits' not in p.parts
                if n in checked:assert checked[n]==h
                else:assert digest(p)==h,n;checked[n]=h
        # 旧総監査をこのレビューの全実体再hashと混同しない。
        a=state['long_horizon'];assert digest(ROOT/a['preservation_path'])==a['preservation_sha256'];b._authorization(b.snapshot());b._science_ready(b.snapshot())
        b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,new_references_hashed=len(checked),new_references_sha256=hashlib.sha256(encode(checked)).hexdigest(),
            old_preservation_audit_sha256=a['preservation_sha256'],old_28_campaign_contracts_exact=True,validated_management_sources_exact=True,
            old_102794_physical_files_full_rehash_this_review=False,old_final_results_unchanged=True,protected_confirmation_text_read=False,
            temporary_all_absent=all(v['status']=='removed' and not os.path.lexists(v['path']) for v in b.snapshot()['temporary_work'].values())),j)
        original=ROOT/'campaigns/nas-hts-glottal-difference-20261008-v1/report.md';text=original.read_text()
        assert text.count('新16日本語文×2条件×2方式の64波形。')==1 and text.count('通常/隔離の全64件')==1
        corrected=text.replace('新16日本語文×2条件×2方式の64波形。','新16日本語文×2条件×3方式の96波形。').replace('通常/隔離の全64件','通常/隔離の全96件')
        corrected+='\n追加差分は今回の計算上の前強調であり、原論文の生理的モデルや聴取結果ではない。\n'
        b.write(HERE/'scientific-report-35-corrected.md',corrected.encode(),j)
        b.save(HERE/'report-correction-35.json',dict(original_path=str(original.relative_to(REPO)),original_sha256=digest(original),corrected_sha256=digest(HERE/'scientific-report-35-corrected.md'),
            correction='本文の方式数/生成・隔離件数を2方式64件から3方式96件へ修正。全64対というnative対比数は正しい。',
            original_seal_and_outputs_preserved=True,protocol_records=96,render_records=96,ASR_each=96,source_pairs=64,result_or_gates_changed=False),j)
        shape=read(ROOT/'campaigns/nas-hts-glottal-shape-20261008-v1/aggregate-summary.json');diff=read(ROOT/'campaigns/nas-hts-glottal-difference-20261008-v1/aggregate-summary.json')
        assert diff['total']==96 and len(diff['source_factor_pairs'])==64
        decision=dict(review_number=1,review_trigger='科学6件',scientific_completed=6,
            causes=['HTS周期源はLPF後にも存在し得るため、旧欠測94をパルス不存在と扱えない。','WORLD原実装のbuild差はhookなしでも4例中1例に残り、旧768件を観測済みにはできない。','短窓の正規化とピーク選択は別因子で、無声/動的の改善と悪化を区別できた。','源形状の周期エネルギー一致は、固定MCPフィルタ後の利得/内容/音響F0保存を保証しない。'],
            measurement_scope='旧HTS安定60msなど限定的対応。20ms・動的・境界・瞬時F0・知覚pitch・WORLDへ資格を拡張しない。',
            actual_generation_improvement=False,generalization_quality_certified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
            old_missing=dict(total=249,HTS=94,WORLD=155),old_support_intervals=31601,old_31_methods_and_each_ASR33_groups_kept=True,
            frozen_routes=['旧WORLD observerの同一環境/フラグ反復','NSDF/key係数の同一対象探索による最終品質救済','6資料だけの同じ知覚適格性検索','同じMCP/LPF下のRosenberg型流量微分と追加差分の係数探索','旧スペクトル17→96文/時間投影の3不通過経路をIDだけ変えて反復すること'],
            next_question='原パルスの整数sample丸めに由来する周期内位置誤差を、共有されたfractional phaseの線形/短い窓付きsinc源で減らせるか。流量形状/差分次数を反復せず、源時計・全パラメータ・noise乱数・固定支持を守る。',
            next_estimate=dict(seconds=14400,bytes=1800000000,render=1000,dsp=2500,ai=576,teacher=0,train=0,inverse=0,download=0,
                full_comparison='新16文×2条件×3方式=96、通常/隔離192、CLI4、人工fixture。二ASR192、全33群と失敗/回収/封印/Git。'),
            next_gates_unchanged=True,source_phase_truth_not_perceptual_truth=True,
            independent_perceptual_work='異なる公開資料で日本語非ニューラルの音声/個別評点/適用劣化/権利の実対応が成立する場合のみ別契約で資格検証。現時点の不足だけでは制御研究を停止しない。',
            resource_status=b.review_due(),review_does_not_require_user_approval=True,
            two_review_stagnation_rule='このレビューが最初。次のレビューでも原因/有効範囲/生成改善に進展がなければ当該経路を凍結し別因子へ移る。')
        b.save(HERE/'decision.json',decision,j)
        lines=['# 長期包括承認後の第1回定期レビュー','', '科学6件が終了したため、規定のレビューを実施した。音声品質は未達、知覚資格なし、P5未開封。レビューは承認待ちではなく、残予算内の次の生成比較へ継続する。','',
            'HTS224件のLPF後周期寄与と、短窓の正規化/ピーク選択の効果を因子別に調べた。WORLDは原実装の再構築でも一例の完全一致を得られず、旧768件を未確認のまま保持した。旧全支持31,601区間、欠測249区間、旧二ASR各33群の悪化を保存した。','',
            '新しい源形状64件・差分次数96件は全通常/隔離・CLIの再現と最終非ニューラル依存を検証したが、波形の工学/指定F0/内容保護は全候補不通過だった。Rosenberg型の流量微分と追加差分を同じフィルタ下で探索する経路を凍結する。一般化や自然さの進展とは扱わない。','',
            '三方式の[訂正済み終了報告](scientific-report-35-corrected.md)が本文の2方式64件という転記を直している。台帳・個票・集計・隔離は全96件で一致し、native対比64対も正しい。元本文と封印を保持し、結果や閾値は変えていない。','',
            '次は共有された周期内fractional phaseに基づくパルス生成を独立因子として、整数sample位置丸めと比べる。固定出力後のgain救済や同じ流量形状の微調整は行わず、新16文・二条件・三方式、固定支持・二ASR各33群・全件隔離/CLIを生成前登録する。機構上の位置誤差低減は、知覚pitch/自然さの資格の代用にしない。','',
            '新しい六封印の全参照hashを照合し、旧28契約と管理検証源の不変、媒体/位置/保存台帳、一時領域全件の不存在を確認した。旧102,794実体の今回の全再hashは行っておらず、長期適用時の総照合結果を保持して参照する。','',
            '全有限資源は70%未満。科学6件という履歴レビューは新上限の追加や消費初期化を行わない。最後12時間の終了枠、0円、所有一時回収、まとまった成果のcommit/pushを維持する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=6,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0001-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0053.json',dict(latest_completed=NAME,scientific_completed=6,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()))
    print(b.reconcile(),flush=True)

if __name__=='__main__':main()
