# 保存済み共有モデルの未完評価

承認済み追加枠: 1時間、追加100MB、隔離生成32、AI320、fit・逆推定・教師・取得0。旧160波形と17文から学習済みの固定モデルを再利用し、診断群を変更しない。

`campaign.py` → `prepare.py` → `export_runtime.py` → `evaluate.py --engine whisper` → `evaluate.py --engine reazon` → `summarize.py` → `closeout.py` → 資料作成 → `seal.py`。固定の既存 `.venv-eval/bin/python -B` を使う。保存を符号化後の容量予約・排他書込・容量と外部変更の照合へ接続した。再試行・自動延長はない。完了判定は結果の `summary.json` に残す。
