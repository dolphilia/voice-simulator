# 短い有声イベントの測定資格

承認済み `docs/plans/short-voiced-event-meter-proposal-2026-10-03.md` の24条件を各一回生成し、DIO＋StoneMaskを各一回測定する。生成器は位相積分・調波・固定雑音のみ。学習・ニューラル推論・音声モデル・外部取得は使わない。既知駆動ゲートは音響的有声化や日本語の正解ではない。

既存の Python 3.11 環境で `-B` を使用する。`campaign.py`、`prepare.py`、`generate.py`、`measure_events.py`、`regression.py`、`summarize.py`、`closeout.py`、`seal.py` の順。一度実施・終了したcampaignは再実行しない。`prepare.py` が生成前に全ソースと正解・既定MSD領域を凍結する。測定では固定した既知有声域の境界フレームを除かず、音素全体50%判定と区別する。

全数を各一回計数し、失敗は欠損として記録して再試行しない。参照54波形は保存DIOを読み取るだけ。旧支持域・採択条件は変更しない。新枠の上限は30分・50MB・24生成・24非学習測定、AI/fit/逆推定/教師/取得0。排他・符号化後容量予約・外部変更検出・終了封印を継続する。

`offline.sb` をmacOS sandbox-execに渡して通信を禁止する。結果は新しい `results/nas-short-event-meter-20261003-v1/` に保存し、封印後の追記・生成を拒否する。資格は既知手続き的信号群に限り、日本語自然さや研究全体の完了を認定しない。
