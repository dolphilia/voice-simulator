# 外部保存の運用

2026-10-06の明示承認は `docs/plans/autonomous-research-external-storage-amendment-2026-10-06.md` に記録する。
旧 `budget.py` と台帳の初期承認hash、科学的契約、消費済み分は保持する。

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
実行環境・小さい最終モデルを外部へ送らない。既存の成果は移動・再生成しない。

`external_output` で子プロセスの最大出力を予約する場合、その処理中は他のサイクルファイルを保存しない。
子プロセスにも `storage_output.open_output` 相当のマウント確認とディレクトリFDによる出力を使用する。
親が予約した外部のリンクに対して、子が独自に親ディレクトリを作る処理は禁止する。
隔離プロファイルは外部の音声実体も読取禁止にする。保存用ディレクトリと識別markerに限って必要な読取を許す。

`b.reconcile()` は論理ファイル・外部参照・サイズ/時刻・外部専用領域の予約外ファイルを検査する。
`b.audit_data_hashes()` は登録した外部データのhashを検査する。
媒体が外れた、UUIDが違う、識別marker不一致、読取専用、容量不足なら停止する。
内蔵へ自動フォールバックしない。壊れたリンクや未完了保存を自動削除しない。

現在の実験 `campaigns/nas-post-mlpg-timing-20261005-v1` は比較896件がそろい、
`runtime-preflight-storage-02.json` に既知の通常/隔離波形一致と物理データ読取拒否を保存した。
次の入口は `isolate-storage-02.py`。実行後に `evaluate-storage.py --engine whisper` と
`evaluate-storage.py --engine reazon`、固定済み `summarize.py` の保存backendラッパー、
`closeout-storage.py` を順に使う。旧 `run.py` を最初から再実行しない。

隔離controllerは自分でsandbox-execを起動するため、controllerに外側のsandboxを重ねない。
二ASRの評価入口にはネットワーク禁止の `offline.sb` を使い、固定済みモデルだけを読む。
外部メディアへの書込とdiskutilの読取はホスト側sandboxで許可された実行経路を使う。
逐次の科学的承認は包括予算内では不要。新しい金銭支出や上限超過は自動で認めない。

最後は未終了ジョブがないことを確認し、照合後に `b.suspend()` で無稼働区間の時間加算を止める。
これは研究目標の達成・放棄・目標の一時停止とは区別する。再開時は `StorageBudget().resume()` で既存消費を引き継ぐ。
