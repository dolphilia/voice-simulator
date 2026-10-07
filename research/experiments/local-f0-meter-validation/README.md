# 局所F0・有声区間計測の自己回復

承認済み `nas-f0-meter-20261003-v1`。24種の既知F0手続き的信号でDIO＋StoneMask／Harvestを測定し、開発側だけで選択、確認側で固定条件を検証する。封印済み93日本語波形の局所支持域と境界感度も診断する。32件の既存Harvest結果を再利用、残61だけ新規測定。旧係数・合否・ASR結果を変更しない。

30分・50MB、生成32、AI0・共有モデルfit0・追加教師0・取得0。失敗・判定器負例・出典・正解・費用を保存し、1 campaignで停止・封印する。信号の工学診断資格は日本語の発音・自然さの資格ではない。

実行順: campaign.py → prepare.py → generate.py → evaluate.py → regression.py → summarize.py → closeout.py → seal.py。既存評価Python・NumPy・SciPy・pyworldを使用。matplotlib・ASR・ニューラル重み・教師音声の新規実行を必要としない。
