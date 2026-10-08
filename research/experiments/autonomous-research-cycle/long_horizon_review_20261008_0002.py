"""科学12件までの第2回レビュー。新因果経路の全比較へ継続し、旧証拠は保持する。"""
import hashlib
import os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261008-v2';NAME='long-horizon-review-v2'
SCIENCE=['nas-hts-fractional-pulse-20261008-v1','nas-hts-sinc-normalization-20261008-v1','nas-hts-filter-warp-20261008-v1','nas-japanese-perceptual-novel-resources-20261008-v1','nas-hts-lf0-contour-20261008-v1','nas-hts-minphase-mechanism-20261008-v1']

def main():
    b=Budget();b.recover();state=b.snapshot()
    assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==12
    previous=state['long_horizon']['last_review'];assert previous['scientific_completed']==6 and digest(ROOT/previous['path'])==previous['sha256']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(review_number=2,trigger='前回レビュー後に科学6件終了',scientific_completed=12,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),quality_goal_completed=False,scientific_outputs=0)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','新六封印・費用・旧保護・次の全比較を照合',reserve_bytes=10000000) as j:
        b.save(HERE/'registration.json',reg,j);checked={};seals={}
        for name in SCIENCE:
            p=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(p);seals[str(p.relative_to(REPO))]=digest(p)
            assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened']
            for n,h in seal['files'].items():
                f=REPO/n;assert not any(x in f.parts for x in ('protected','holdout','splits'))
                if n in checked:assert checked[n]==h
                else:assert digest(f)==h,n;checked[n]=h
        a=state['long_horizon'];assert digest(ROOT/a['preservation_path'])==a['preservation_sha256'];b._authorization(b.snapshot());b._science_ready(b.snapshot())
        temporary=b.snapshot()['temporary_work'];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary.values())
        b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,new_references_hashed=len(checked),new_references_sha256=hashlib.sha256(encode(checked)).hexdigest(),
            old_preservation_audit_sha256=a['preservation_sha256'],old_28_contracts_exact=True,validated_management_sources_exact=True,
            old_102794_physical_files_full_rehash_this_review=False,all_owned_temporary_absent=True,protected_confirmation_text_read=False),j)
        lf0=read(ROOT/'campaigns/nas-hts-lf0-contour-20261008-v1/aggregate-summary.json')
        mechanism=read(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/aggregate-summary.json')
        assert lf0['total']==96 and mechanism['mechanical_fixture_passed'] and not mechanism['real_Japanese_MCP_qualified']
        decision=dict(review_number=2,scientific_completed=12,previous_review=previous,
            causes=['fractional phaseの機械誤差を減らしても、原MCP下の固定支持・内容保護は保てなかった。',
                '同じ9tapでもL2とDC和の正規化は別因子で、振幅・エネルギーを同時には保てない。',
                '源時計・LPF・実励振をbyte固定してalphaだけを変えても、原native保護は全候補不通過だった。',
                'LF0輪郭の縮小・平坦化はこの新コホートで欠測とASR悪化を増やした。単調源も全体pitch診断全件合格にはならない。',
                '原HTS励振からの別FIR経路は、人工MCPの解析応答・因果性・独立畳み込みを所定範囲で検証できた。'],
            actual_generation_improvement=False,generalization_quality_certified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            measurement_scope='最小位相FIR資格は登録人工MCPのみ。既存DIO/全体ACFを短窓・動的・瞬時F0・知覚へ一般化しない。',
            perceptual_resources='新2資料PASQA/P.Sup23も現HTS刺激・個別評点・適用範囲・利用条件の一式を確認できず資格なし。旧6資料の再検索やモデル推論だけで資格を作らない。',
            frozen_routes=['前レビューで凍結した全経路を維持','原フィルタ下のfractional pulse/sinc同形状の係数救済','同じMCPのalpha係数探索','原native保護を失ったLF0輪郭縮小/平坦化の同一対象救済','音声と評点の新しい公開対応がない同じ8資料の適格性再検索'],
            old_support_intervals=31601,old_missing=dict(total=249,HTS=94,WORLD=155),old_31_methods_and_each_ASR33_groups_kept=True,
            two_review_rule='原因の区別と新しい人工FIRの有効機構範囲には進展がある。音声品質の進展はない。既失敗係数経路を凍結し、別表現の実生成比較へ配分する。',
            next_question='同じ新日本語入力から生成したMCP/LF0/LPF・原HTS励振を保ち、1024点最小位相IRの因果畳み込みは原Pade-MLSAに対して内容/固定支持/工学制御を保てるか。有限IRとIR補間を含む経路全体を比較する。',
            next_estimate=dict(seconds=14400,bytes=1800000000,write_bytes=2800000000,render=1000,dsp=4000,ai=384,teacher=0,train=0,inverse=0,download=0,
                comparison='新16文×2条件×2方式=64。候補の内部MLSA一回も計上し比較96render・通常/隔離192render・CLI6render。二ASR128。全件固定支持/各33群/封印/Git。'),
            next_gates_unchanged=True,FIR_fixture_is_not_final_quality=True,review_does_not_require_user_approval=True,
            resource_status=b.review_due(),remaining_independent_work='最小位相FIRの実MCP有限長/時間補間、別の共有制御・調音経路、日本語公開知覚対応が新たに成立する場合の資格研究。')
        b.save(HERE/'decision.json',decision,j)
        report=['# 長期包括承認後の第2回定期レビュー','',
            '前回から科学6件、累計12件が終了したためレビューした。品質未達・知覚資格なし・P5未開封。全有限資源は70%未満で、有効な次の全比較を予約できる。承認待ちには戻らない。','',
            'fractional pulse、L2/DC正規化、実alpha、LF0輪郭幅を別因子として比較した。機械誤差や源の一致は確認できたが、原nativeへの工学/固定支持/二ASR各33群保護を満たす候補は得られなかった。LF0半幅はpitch26/32・欠測6/769・Whisper13群/Reazon2群悪化、平坦化は24/32・8/769・20群/12群悪化だった。旧支持31,601と欠測249、旧31方式の判定は保持する。','',
            '人工MCPの最小位相FIRは解析応答・因果性・独立畳み込みの限定機構資格を通過した。有限IRとIR補間を含むこの新経路を、次の独立日本語コホートで実生成比較する。原HTS励振・全三stream・有声mask・durationを保護し、内部の原MLSA補助生成も費用へ計上する。人工資格を実音声・自然さ・瞬時pitchへ移さない。','',
            '新しい公開知覚2資料にも必要な対応証拠はなく、旧6資料も含む同じ資料の反復を凍結した。現時点の資格不足だけで制御研究を止めない。係数救済を続けず、原因に応じてフィルタ表現を変更する。','',
            '新六封印の全参照をhash照合した。旧28契約と管理ソースの不変・指定媒体・保存/位置索引・所有一時領域全件の不存在も確認した。旧102,794実体の全再hashは今回は行っていない。','',
            '192時間・終了専用12時間・0円・各資源累計上限は維持する。レビューは新予算の発行、品質達成、消費初期化ではない。まとまった結果と次契約をcommit/pushして継続する。','']
        b.write(HERE/'report.md','\n'.join(report).encode(),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=12,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0002-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0065.json',dict(latest_completed=NAME,scientific_completed=12,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()))
    print(dict(review_completed=True,scientific_completed=12,quality_goal_completed=False,next=decision['next_question']),flush=True)

if __name__=='__main__':main()
