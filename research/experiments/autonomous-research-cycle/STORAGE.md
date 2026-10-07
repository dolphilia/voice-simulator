# 外部保存の運用

2026-10-06の明示承認は `docs/plans/autonomous-research-external-storage-amendment-2026-10-06.md` に記録する。
旧 `budget.py` と台帳の初期承認hash、科学的契約、消費済み分は保持する。

2026-10-08の現在の再開判断・一時領域・Git保存は、[改訂研究計画](../../../docs/plans/neural-assisted-non-neural-speech-plan-2026-10-08.md)と[継続プロンプト](../../../docs/plans/autonomous-research-continuation-prompt-2026-10-08.md)を参照する。以下の保存APIの手順を使い、最新台帳の未実施部分から再開する。

今後の新しい実験・再開入口は、次の保存バックエンドを明示的に使用する。

```python
from storage_budget import StorageBudget
b = StorageBudget()
b.resume()  # 既存セッションがある場合もリセットしない。
with b.job(campaign, 'render', label, reserve_bytes=maximum) as token:
    b.write(logical_wav, encoded_wav, token)
    b.save(local_metadata, metadata, token)
```

WAV・NPZなどは外部の実体へ保存し、論理ファイルのリンクとメタデータは内蔵に残る。
それ以外の大容量データは `write_data` を使う。ディレクトリ全体はリンクにしない。
実行環境・小さい最終モデルを外部へ送らない。既存データの検証済み外部移動には[2026-10-08追補](../../../docs/plans/repository-data-storage-amendment-2026-10-08.md)を適用し、内容・論理パス・封印を保持する。保存済みの比較は再生成しない。

`external_output` で子プロセスの最大出力を予約する場合、その処理中は他のサイクルファイルを保存しない。
子プロセスにも `storage_output.open_output` 相当のマウント確認とディレクトリFDによる出力を使用する。
親が予約した外部のリンクに対して、子が独自に親ディレクトリを作る処理は禁止する。
隔離プロファイルは外部の音声実体も読取禁止にする。保存用ディレクトリと識別markerに限って必要な読取を許す。

`b.reconcile()` は論理ファイル・外部参照・サイズ/時刻・外部専用領域の予約外ファイルを検査する。
`b.audit_data_hashes()` は登録した外部データのhashを検査する。
媒体が外れた、UUIDが違う、識別marker不一致、読取専用、容量不足なら停止する。
内蔵へ自動フォールバックしない。壊れたリンクや未完了保存を自動削除しない。

2026-10-08確認時には `campaigns/nas-post-mlpg-timing-20261005-v1` の比較896件、
未知文の通常/隔離160組、二ASRの1,792記録と終了監査が完了し、封印済みである。
旧生成・隔離・評価・終了入口を再実行しない。次の未開始候補は絶対F0校正で、
`control/state.json` のcheckpointと終了集計を確認し、新契約を生成前に固定する。

`/private/tmp/` 等のシステム一時領域は極力使わない。必要な作業ファイルは外部専用領域で
所有manifest・予算予約・照合・不要時削除を行う。現行APIは任意の一時ディレクトリを
自動管理しないため、その用途が必要な入口には改訂計画の管理手順を先に実装・検証する。
システム一時領域を使った場合も、自分が作成した不要なファイルを必ず削除し、残存を確認する。

隔離controllerは自分でsandbox-execを起動するため、controllerに外側のsandboxを重ねない。
二ASRの評価入口にはネットワーク禁止の `offline.sb` を使い、固定済みモデルだけを読む。
外部メディアへの書込とdiskutilの読取はホスト側sandboxで許可された実行経路を使う。
逐次の科学的承認は包括予算内では不要。新しい金銭支出や上限超過は自動で認めない。

最後は未終了ジョブがないことを確認し、照合後に `b.suspend()` で無稼働区間の時間加算を止める。
これは研究目標の達成・放棄・目標の一時停止とは区別する。再開時は `StorageBudget().resume()` で既存消費を引き継ぐ。
