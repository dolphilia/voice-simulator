# 長期包括予算の承認適用・検証結果

2026-10-08のユーザー明示承認を `long-horizon-approval-20261008-v1.json` に適用前台帳・文書hash・Git先端とともに保存した。同じ arc-20261004-v1 の全消費と旧28契約を継承した。
累計192時間・有限の総回数/取得/書込上限を適用し、campaign件数による停止を撤廃した。最後12時間と両媒体各2GBは終了専用。保存容量は増やしていない。

科学入口は `long_horizon_budget.LongHorizonBudget`。旧budget.py/storage_budget.pyと旧temporary_storage.pyは変更していない。新科学契約を開始する前に比較一式の時間・回数・書込・容量を予約し、個別上限と拡張理由、技術再試行を強制する。旧封印ソースの入口を再実行しない。

管理campaignは29件目、科学campaignの進展には数えない。未承認拒否・旧消費・各有限資源の予約超過・終了12時間・個別上限・失敗attempt・一時回収・外部位置/hashの検証が通過した。初回fixture検証は索引登録漏れと試験リンクの親回収で失敗し、そのattemptと失敗版を保持した。別版v2で試験の登録と所有リンク回収を修正して通過した。

旧28封印の参照と前回の包括integrity-manifestを照合し、102,794実体のSHA-256が一致した。既存外部24,387位置も一致。新一時領域2件は成功・失敗とも削除/物理不存在を確認した。初回読取の自己所有bytecode 7,379 bytesも記録・削除し、費用を戻していない。P5はhash照合だけで本文を読まず、未開封を保持した。

音声品質は未達。今回の処理は予算管理・保存同一性の確認で、生成改善や知覚資格の証拠ではない。31方式、992波形、固定支持31,601区間、欠測249区間（HTS音響曖昧94、WORLD未確認155）、旧二ASR33群と不採択は維持する。

次はHTS224件のLPF後と声道filter後の周期寄与を旧波形完全一致の下で観測する。WORLDは同じobserverのフラグ反復をせず原実装の演算/環境差を別契約で分離する。短窓/動的/境界の測定資格と日本語非ニューラル知覚資格も進める。資格不足だけで有効な音響・制御作業を停止しない。

最新消費はcontrol/state.jsonを正本とし、管理/Git費を含める。24稼働時間または科学6件終了のレビュー基準はlong_horizon.last_reviewを引き継ぐ。承認済み枠内の次案/レビュー/P5条件付き移行に逐次承認を求めない。

詳細はcampaigns/nas-long-horizon-management-20261008-v1のregistration、validation、preservation-audit、implementation-repair、resultを参照。適用用入口はapply_long_horizon_20261008_v2.py。保存後のHEAD/origin実照合を正本とし、自己参照記録だけのcommit連鎖を作らない。
