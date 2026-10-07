# 保存実波形目標から学習した非ニューラル研究版

文章の辞書・アクセント規則、固定16係数共有回帰、HMM＋手続き的合成で音を作る。直接方式と蒸留方式を同じ入口で比較する。発話別係数・録音・教師・ニューラル重みは同梱しない。

`runtime.py --text TEXT --model direct_non_neural --pitch-reference 220 --speed 1 --output output.wav`。学生は`distilled_non_neural`。macOS arm64、固定pyopenjtalk0.4.1・辞書、NumPy、SciPyが必要。1実行1生成。範囲はF0参照140〜320、速度0.75〜1.3、1〜120音素。対応版HTSヘッダのBSD通知とMeiモデルのCC BY3.0通知を同梱。自然さ・広い日本語の品質は未認定。
