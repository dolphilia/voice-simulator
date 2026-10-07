# 実行した入口と再現上の注意

初版READMEのprepare.py/run.pyは、旧pilotの同名rendererのimport衝突を保存した版。有効な入口はprepare-v2.py/run-v2.pyで、counter_renderer.py/counter_diagnostics.pyを使う。成功したcounter.dylibは1度だけビルドし、prepare-v2.pyでhash照合して再利用した。

固定Python: /Users/dolphilia/github/voice-simulator/research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python -B

実行順: campaign.py → prepare.py（接続失敗を保存）→ prepare-v2.py → /usr/bin/sandbox-exec -f results/nas-source-filter-20261003-v1/profile.sb <固定Python> run-v2.py → summarize.py → results/nas-source-filter-20261003-v1/timing-audit.py → closeout.py → 終了資料 → seal.py。

このcampaignは終了・封印済み。既存成果を上書きする再実行を禁止する。生成を再現する場合は新しい承認枠・ディレクトリ・IDを使い、生成前に封印・protocol・18入力のhashと環境を照合する。現在の結果の検証は、封印と保存WAV/配列のhash照合で生成なしに行える。新しい工程では初版の接続失敗を繰り返さず、有効入口だけを準備する。

最初の18 WAV・LF0・DIO/時刻の一致を必須にし、残36生成は一致後にだけ実行した。全対照で元MLPG表・c0・LF0の保持、LPFを外す方式では第3ストリームだけの除去、C側のPSS復元を検査した。源とフィルタの対照は研究用であり、最終品質を認定する配布bundleではない。
