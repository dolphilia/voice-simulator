"""承認回数上限で終了し、品質達成と分けて再開条件を残す。"""
from paths import *
from audit import verify
import shutil
def main():
    verify();b=Budget();b.recover();v=b.snapshot();assert not v['jobs']
    s=read(HERE/'aggregate-summary.json')
    assert s['global_and_campaign_counts_exact'] and s['all_jobs_replay_exact']
    assert len(v['campaigns'])==v['limits']['campaigns']==24
    assert s['all_temporary_removed'] and not s['quality_goal_completed']
    with b.job(NAME,'audit','包括結果・残予算・品質未達と追加承認条件を封印',reserve_bytes=3_000_000) as job:
        v=b.snapshot();c=v['campaigns'][NAME]
        assert all(c['counts'].get(k,0)==0 for k in ['render','dsp','ai','teacher','train','inverse','download'])
        b.save(HERE/'cost-audit.json',dict(actual_render=0,actual_DSP=0,actual_AI=0,
            actual_teacher_train_inverse_download_money=0,new_temporary_files=0,
            technical_retries=0,campaign=c,quality_goal_completed=False),job)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',
            experiment_completed=True,administrative_and_evidence_audit_only=True,
            quality_goal_completed=False,protected_confirmation_opened=False),job)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),
            seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_removed=True,
            stop_reason='campaigns_limit_reached',quality_goal_completed=False),job)
    b.close_campaign(NAME)
    v=b.snapshot();assert not v['jobs'] and all(c['closed'] for c in v['campaigns'].values())
    remaining={k:v['limits'][k]-v['counts'].get(k,0) for k in ['render','teacher','ai','dsp','train','inverse','download']}
    remaining.update(seconds=v['limits']['seconds']-v['seconds'],
        research_seconds=v['limits']['seconds']-v['seconds']-14400,campaigns=0,
        write_bytes=v['limits']['write_bytes']-v['write_bytes'])
    p=dict(latest_completed=str(HERE.relative_to(ROOT)),cycle=v['cycle'],campaigns_completed=24,
        active_campaign=None,stop_reason='campaigns_limit_reached',quality_goal_completed=False,
        protected_confirmation_opened=False,perceptual_qualification=False,
        all_temporary_removed=True,jobs={},remaining=remaining,
        final_budget_ledger=str((ROOT/'control/state.json').relative_to(REPO)),
        no_budget_reset=True,next='同じ台帳を維持。campaign上限追加の明示承認があるまで新規科学campaignを開始しない。',
        git_save_pending=True,budget=b.reconcile())
    b.save(ROOT/'progress-0032.json',p)
    b.save(ROOT/'cycle-closeout-result-20261008-0001.json',dict(p,
        comprehensive_audit=str((HERE/'aggregate-summary.json').relative_to(REPO)),
        audit_seal_sha256=digest(HERE/'artifact-seal.json'),
        final_quality_unmet=['新文全件の指定F0と固定有声支持','二ASR全33群の内容保護',
            '日本語非ニューラル音声で有効な知覚資格','独立P5最終確認'],
        no_new_human_answers_required_for_control_research=True))
    report=['# 自律研究サイクル終了監査（品質未達）','',
        'arc-20261004-v1の承認済み24campaignを使い切ったため停止する。48時間や生成回数には残額があるが、別の枠へ読み替えない。品質目標は未達。P5は未開封。','',
        '第15〜21回の6コホート・全31方式・992波形記録・1,984 ASR記録を第23回で再集計し、旧33群と一致した。候補の採否を変更していない。指定F0への駆動校正後も固定支持欠測や一部内容群の悪化が残る。','',
        '第22回のHTS実励振観測128件では中心ACFが全件の限定窓ゲートを通過した。対象の安定有声60ms窓は全時計点の約12.4%。動的区間・境界・短音素・WORLD・知覚ピッチ・日本語一般への資格ではない。旧ゲートを置き換えない。','',
        f"第24回は終了済み23封印の全{s['prior_sealed_references']:,}参照、外部登録{s['current_external_files_verified']:,}ファイル、既存移動52,390ファイルと48旧封印文書を照合した。重複を除く{s['distinct_physical_files_hashed']:,}実体のSHA-256が一致した。全{s['temporary_owned_workspaces']}専用一時領域は削除記録と物理不存在が一致し、新しい一時ファイルは0。",'',
        '新しい波形・ASR・音響測定・教師・fit・逆推定・取得は第23/24回とも0。旧失敗ジョブ・不採択・容量停止の履歴は保持した。最終ランタイムの独立性は今回再実験せず、旧通常/隔離・CLI・読取禁止/ネットワーク拒否の封印証拠を保持する。','',
        '|項目|消費|上限|','|---|---:|---:|']
    for k in ['render','teacher','ai','dsp','train','inverse','download']:
        report.append(f"|{k}|{v['counts'].get(k,0):,}|{v['limits'][k]:,}|")
    report+=['',f"終了監査時の稼働は{v['seconds']/3600:.3f}時間。残り{remaining['seconds']/3600:.3f}時間（終了専用4時間を含む）。この後のGit・報告管理費は最終台帳を優先する。",'',
        '大容量成果とローカル位置索引は指定外部媒体/ローカル管理で保持し、Gitが生データのバックアップを代替したとは扱わない。外部媒体UUIDとmarker、実空き、内蔵/外部配分を確認した。実空きは監査時点の値。','',
        '再開にはcampaign上限追加の承認が必要。時間・生成・AI・DSP・容量・取得・金銭の既存上限と消費は維持する。追加案と実行順は next-campaign-allocation-request-20261008-0001.md に記載する。既存比較を再生成せず、測定資格と実波形欠測の原因を先に分離する。','',
        '最終Git同期の結果はterminal-state記録とGit先端を参照する。自分自身のcommit hashを本文に埋め込む循環を避け、終了結果commitを記録し、終端状態commitはリモート先端の実照合で確認する。','']
    b.write(ROOT/'cycle-closeout-report-20261008-0001.md','\n'.join(report).encode())
    proposal=['# 追加campaign配分の承認案','',
        '現承認の24回が上限に達した。品質未達のまま追加実行はしない。今回の終了結果を踏まえ、同じarc-20261004-v1台帳で最大4回（campaign上限24→28）の追加を提案する。これは未承認であり、時間48h・生成20,000・AI50,000・DSP100,000・teacher1,000・fit60・inverse300・取得5GB・金銭0・既存容量上限は増やさない。既消費をリセットしない。','',
        '追加分も85%以降の方針を維持し、既存HTS/WORLD経路の測定検証・欠測原因分離を優先する。新しい合成経路や知覚ゲート緩和を追加しない。各回は開始前の結果に従って登録し、最大4h・2GBと再試行/隔離/後始末まで残予算に収まることを確認する。','',
        '1. 既存HTSの実励振phase/pulseから動的区間と短有声イベントの測定可否を検証する。定常60ms資格を短区間へ流用しない。','2. 既存WORLDの実励振実装を読み、源LF0と実際の有声/パルスの対応を不変波形の観測で検証する。源LF0をtruthとしない。','3. 既存波形の固定支持欠測を、実励振の不足と音響測定の失敗に分ける。事後測定を旧採否の書換えに使わない。','4. 全結果と二ASRの悪化群を統合し、次の制御比較が有効か判定する。必要な追加制御比較や最終確認は、この結果と別の承認枠で判断する。','',
        '新しい人の回答を追加制御研究の必須条件にしない。ただし日本語非ニューラルに有効な知覚資格と独立P5証拠が揃うまでは、全体品質合格を認定しない。','',
        '承認後の最初の操作: 指定媒体UUID/marker/空き、最新台帳と封印、terminal-stateのGit同期、一時領域不存在を再照合し、上限追補を新しい承認記録として適用する。第25回は新契約の事前登録から開始する。','']
    b.write(ROOT/'next-campaign-allocation-request-20261008-0001.md','\n'.join(proposal).encode())
    with b.locked():
        st=b._load();st.setdefault('continuation_checkpoint_history',[]).append(st['continuation_checkpoint'])
        st['continuation_checkpoint']=dict(id='campaign-limit-stop-20261008-0001',active_campaign=None,
            all_campaigns_closed=True,stop_reason='campaigns_limit_reached',campaigns_used=24,campaigns_limit=24,
            quality_goal_completed=False,protected_confirmation_opened=False,all_temporary_removed=True,jobs={},
            approval_required_for_additional_campaigns=True,next='commit/push終了結果→終端台帳・suspend→終端commit/push→承認待ち',
            git_save_pending=True);b._write_state(st)
    print('closed',b.reconcile(),flush=True)
if __name__=='__main__':main()
