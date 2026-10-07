# 局所F0の非ニューラル研究版

固定16係数回帰、辞書・アクセント規則、HMMと非ニューラル合成器で入力文から局所F0を計算する。教師音声・ニューラル重み・発話別軌跡を同梱しない。

`runtime.py --text TEXT --model direct_non_neural --pitch-reference 220 --speed 1 --output output.wav`。蒸留回帰は`distilled_non_neural`。1〜120音素、F0参照140〜320、速度0.75〜1.3。局所補正は±3半音、対象音素単純平均の発話内中心化。1実行1生成。

現在はmacOS arm64、固定版pyopenjtalk 0.4.1・既存辞書・NumPy・SciPyで検証。対応版HTSヘッダとBSD通知、Mei音源のCC BY 3.0通知を同梱。Python依存とHTS共有ライブラリは別途必要。品質未認定。内容・自然さの一般保証はない。
