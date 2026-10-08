# 長期包括承認の適用後に使う継続入口 v3

2026-10-08。長期包括案v1はユーザーに明示承認され、同じarc-20261004-v1へ適用・検証済み。元の案とv2は承認対象hashと履歴として保持する。v2の研究範囲・品質条件・外部保存・一時回収・commit/push・自律継続指示を引き継ぐ。

継続時は[継続本文v2](autonomous-research-continuation-prompt-2026-10-08-v2.md)と、最新のcontrol/state.json、jobs.jsonl、progress追記、開始済み契約・結果・封印を読む。文書作成時の件数・数値より最新台帳を優先する。承認を求め直したり、旧28→32未承認案を重ねたり、台帳を初期化したりしない。

承認記録はresearch/experiments/autonomous-research-cycle/long-horizon-approval-20261008-v1.json。適用・検証・旧証拠照合はlong-horizon-application-report-20261008-v1.mdとcampaigns/nas-long-horizon-management-20261008-v1。管理29件目が終了し、旧28契約と102,794実体hashは一致した。音声品質未達・P5未開封。これを生成品質の進展と扱わない。

新しい実行入口はlong_horizon_budget.LongHorizonBudgetを使う。旧budget.py/storage_budget.py/temporary_storage.pyを改変しない。管理検証の初回失敗と修正版v2を保持し、検証の有効なソースhashをvalidation.jsonで固定する。新科学契約は全時間/回数/書込/容量の比較一式を予約し、検証前・終端12時間・個別上限超過を拒否する。

累計192時間と同案の全資源上限、campaign件数の停止撤廃、終了専用12時間を引き継ぐ。24実稼働時間または科学6件終了のレビュー基準はlong_horizon.last_review。文脈/ターンでリセットしない。指定媒体と一時所有manifest・回収・位置/hash照合を維持する。

適用時の次の科学処理はHTS224件LPF後周期寄与の純観測。最新台帳が先へ進んでいれば再実行せず、正当に未実施の部分へ進む。WORLD原実装の演算差・短窓/動的/境界の測定資格・日本語非ニューラル知覚資格へ進み、生成改善へつながる有効範囲から次の方式/制御を比較する。枠内に有効な処理が残る間は通常レビュー/個別終了だけで止まらない。
