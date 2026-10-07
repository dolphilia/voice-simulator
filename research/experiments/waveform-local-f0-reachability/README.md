# 実波形での局所F0到達性

承認済み1 campaign `nas-waveform-f0-20261003-v1`。保存済みdevelopment4文と教師、固定HMM、状態別入口、中心化先行射影を使う。4係数・局所±3半音の制御を状態目標／実波形目標へ逆推定して比較する。発話別逆推定は参照が必要な研究用であり、最終共有モデルとして配布しない。

1時間・100MB、生成128・AI32、共有モデルfit0・追加教師0・取得0。純粋関数の負例、出典、損失、支持域、受理条件を生成前に固定。実波形探索は最大3反復、中央差分0.25、更新各係数0.5、正則化0.1。欠損区間を落として改善させず、失敗と棄却も保存する。ASRは探索後1回ずつ、同一波形・同一文章は保存結果を参照。

実行順: campaign.py → prepare.py → render.py → evaluate.py --engine whisper → evaluate.py --engine reazon → summarize.py → closeout.py → seal.py。既存 `.venv-eval/bin/python` とローカル資産を使用。旧11封印を開始・終了に検証する。合否にかかわらず1 campaignで封印して停止し、残余枠で自動延長しない。
