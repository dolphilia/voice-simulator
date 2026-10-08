"""追加承認の28回を終了し、品質未達・再開条件を追記版へ保存する。"""
from paths import *
def main():
    from audit import verify
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    with b.job(NAME,'audit','追加4枠の結果と包括監査を封印',reserve_bytes=5000000) as j:
        integrity=read(HERE/'aggregate-summary.json');integrated=read(HERE/'integration-summary.json')
        assert integrity['campaigns_used']==28 and not integrated['quality_goal_completed']
        c=b.snapshot()['campaigns'][NAME]
        b.save(HERE/'cost-audit.json',dict(campaign=c,render=0,DSP=0,AI=0,download=0,new_temp_files=0,
            all_temporary_removed=True,quality_goal_completed=False),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,
            quality_goal_completed=False,protected_confirmation_opened=False),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),
            all_temporary_removed=True,quality_goal_completed=False),j)
    b.close_campaign(NAME);s=b.snapshot();assert len(s['campaigns'])==s['limits']['campaigns']==28
    assert all(c['closed'] for c in s['campaigns'].values()) and not s['jobs']
    remaining=dict(seconds=s['limits']['seconds']-s['seconds'],counts={k:s['limits'][k]-s['counts'].get(k,0) for k in ['render','teacher','ai','dsp','train','inverse','download']},
        campaigns=0,write_bytes=s['limits']['write_bytes']-s['write_bytes'])
    result=dict(cycle=s['cycle'],quality_goal_completed=False,protected_confirmation_opened=False,all28campaignsclosed=True,
        stop_reason='campaigns_limit_reached',campaigns_used=28,campaigns_limit=28,remaining=remaining,
        known_HTS_source_cases=224,unknown_WORLD_source_cases=768,
        fixed_support_intervals=integrated['total_fixed_support_intervals'],missing_fixed_support_intervals=integrated['missing_fixed_support_intervals'],
        missing_source_states=integrated['missing_fixed_support_source_states'],
        next_control_comparison_valid_now=False,integration=str((HERE/'integration-summary.json').relative_to(REPO)),
        comprehensive_audit=str((HERE/'aggregate-summary.json').relative_to(REPO)),audit_seal_sha256=digest(HERE/'artifact-seal.json'),
        final_quality_unmet=['新文全件の指定F0/固定有声支持','二ASR33群の内容保護','日本語非ニューラル音声に有効な知覚資格','独立P5最終確認'],
        no_new_human_answers_required_for_measurement_or_control_research=True,
        new_allocation_request='next-campaign-allocation-request-20261008-0002.md',
        budget=b.reconcile(),git_save_pending=True)
    b.save(ROOT/'progress-0041.json',result);b.save(ROOT/'cycle-closeout-result-20261008-0002.json',result)
    report=['# 追加4枠の終了結果（品質未達）','',
        '承認されたcampaign上限28回に到達したため、新しい科学campaignを停止する。時間・回数の残額をcampaign追加へ読み替えない。品質未達、P5未開封。',
        '第25回はHTS128件の短窓/動的測定を検証。中心ACFの安定60msは128/128、動的60msは25/128、20msは全件不通過。資格の対象範囲を保持した。',
        '第26回はWORLD768件を登録したが、観測Cの旧WAV完全一致が初回と技術再試行2回で不通過。最初の例のfloat32差は1サンプルの2.7756e-17だったが条件を緩和せず、全件観測を実行しなかった。旧PyWORLD再構成4例は完全一致。未確認768件を保持した。',
        '第27回はHTS追加96件を旧WAV完全一致で観測し、既存128件と合わせ224件の源周期/パルスを確認。全992件の固定支持・旧DIO・欠測件数は一致した。']
    report+=[f"固定支持は{result['fixed_support_intervals']:,}区間、欠測{result['missing_fixed_support_intervals']:,}区間。源区分: {result['missing_source_states']}。",
        '第28回は二ASR33群の旧不採択/悪化群と測定結果を統合。次の係数比較を旧測定だけで採否判断する根拠は不足。周期成分・短窓/動的測定・WORLD再現差の検証を先に行う必要がある。',
        f"包括監査では終了済み27封印の{integrity['prior_sealed_references']:,}参照、外部登録{integrity['current_external_files_verified']:,}ファイル、移動52,390ファイルを照合。重複を除く{integrity['distinct_physical_files_hashed']:,}実体のSHA-256が一致。所有一時領域{integrity['temporary_owned_workspaces']}件は全件削除/物理不存在が一致した。",
        '新しいASR・教師・学習・逆推定・制御比較は追加4枠で0。旧科学契約/封印/採否は上書きしていない。Gitは生データ/位置索引のバックアップを代替しない。','',
        '|項目|消費|上限|','|---|---:|---:|']
    for k in ['render','teacher','ai','dsp','train','inverse','download']:report.append(f"|{k}|{s['counts'].get(k,0):,}|{s['limits'][k]:,}|")
    report+=['',f"監査時の稼働{s['seconds']/3600:.3f}時間、残り{remaining['seconds']/3600:.3f}時間（終了専用4時間を含む）。この後のGit/終端管理費を含む最新control/state.jsonを正本とする。",
        '再開には追加配分案の承認が必要。旧24→28承認は保持し、新しい28→32案は未承認として保存した。次の制御比較やP5の開封はその案に含めない。',
        '終端Git保存では結果commitを記録し、自己参照commit記録の連鎖を避ける。終端commitのHEADとorigin/mainの実照合を行う。','']
    b.write(ROOT/'cycle-closeout-report-20261008-0002.md','\n'.join(report).encode())
    proposal='''# 次の測定検証4枠の追加配分案（未承認）

28回の承認枠が終了した。品質未達、WORLD768件の実励振は未確認、HTSの源パルス存在だけでは周期音響成分・短窓/動的測定・知覚pitchを保証できない。新しい係数比較へ進む根拠はまだ不足している。

同じarc-20261004-v1でcampaign上限だけ28→32（最大4回）へ追補する案を提案する。既消費・48h・生成20,000・AI50,000・DSP100,000・teacher1,000・fit60・inverse300・取得5GB・金銭0・保存/書込上限を維持する。旧承認と封印は上書きしない。これは未承認で、承認されるまで開始しない。

1. HTS224既存波形のLPF後の周期成分を純観測し、波形全件bytehash不変を条件に、源パルスと音響成分の関係を分離する。残響・雑音・動的区間を保持し、知覚資格へ広げない。
2. WORLDはobserver条件の単純な再反復をしない。観測を入れない原実装の再ビルドを旧PyWORLDと比べ、差の発生段階を演算単位へ分離する。旧波形不変を得る前に実励振truthを使わない。係数や許容差の調整はしない。
3. 既存波形・有効な実励振を使い、短い有声/動的区間の測定可否を検証する。新しい測定法や境界処理は出力前に登録し、不足対象・欠測を全分母に残す。旧DIO/ACFゲートや採否は変更しない。
4. 上記と二ASRの悪化群を統合し、制御比較へ進むための対象範囲・必要証拠を判断する。包括保存/会計/終了監査を行う。

各回は通常4h・2GB以内、4回計最大16hを開始前に残時間と照合し、最後4hと両媒体2GBは保持する。事前の配分目安は生成計4,000、DSP24,000、依存取得最大1MB、AI/teacher/fit/inverse0。未使用回は使うことを目的に開始しない。各回の実入力・具体的処理・再試行・後始末を開始前に登録し、開始後に上限を増やさない。技術再試行は1ジョブ2回・campaign10回。RAM8GB、計算同時最大2を維持する。

新しい合成経路、制御比較、P5開封、知覚ゲート緩和はこの案に含めない。新しい人の回答を測定・制御研究の必須条件にしない。品質達成は有効な知覚資格と独立P5を別途満たすまで認定しない。

承認後は最新terminal-state、台帳、全封印、Git先端、指定媒体UUID/marker/空き、所有一時物不存在を照合して追補を新しい記録で適用する。第29回は結果に即した具体的契約の登録から始める。
'''
    b.write(ROOT/'next-campaign-allocation-request-20261008-0002.md',proposal.encode())
    with b.locked():
        s=b._load();s.setdefault('continuation_checkpoint_history',[]).append(s['continuation_checkpoint'])
        s['continuation_checkpoint']=dict(id='campaign-limit-stop-20261008-0002',active_campaign=None,all_campaigns_closed=True,
            stop_reason='campaigns_limit_reached',campaigns_used=28,campaigns_limit=28,quality_goal_completed=False,
            protected_confirmation_opened=False,all_temporary_removed=True,jobs={},approval_required_for_additional_campaigns=True,
            next='commit/push終了結果→終端台帳suspend/commit/push→28→32案の承認待ち',git_save_pending=True);b._write_state(s)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
