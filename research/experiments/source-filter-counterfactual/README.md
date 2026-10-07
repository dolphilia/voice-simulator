# 保存パラメータの音源・フィルタ対照

承認された新1時間・追加100MB・render54・AI/fit/逆推定/教師/取得0の限定比較。保存済み18条件を同じHTSで再合成し、旧WAV・LF0・DIOとの一致後にだけ平坦化とLPFを外した対照を作る。最終音源は非ニューラル。対照の音は日本語品質の候補ではない。

固定Pythonは `research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python -B`。実行順は `campaign.py`、`prepare.py`、OSのネットワーク遮断下の `run.py`、`summarize.py`、`closeout.py`、資料作成、`seal.py`。`run.py` は `results/nas-source-filter-20261003-v1/profile.sb` を `/usr/bin/sandbox-exec -f` へ指定する。既存のOS隔離を適用できる実行環境が必要。再試行と自動延長はない。

`counter.c` は対応版HTSヘッダを使ってCの所有オブジェクトを扱う。Pythonオブジェクトから内部ポインタを推測しない。MLPGを波形の前に読み出す。平坦化はc0・LF0・LPFを保持し、単純励起はさらにVocoderへ渡す第3ストリームを外す。状態・元のMLPG表は保持／復元する。コピーしたヘッダのBSD通知、Meiの旧来歴・ライセンスを元資産で保持する。

保存は符号化後の容量予約、排他書込、予約外変更の検出を使う。大きな状態snapshotは参照形式で保持する。
