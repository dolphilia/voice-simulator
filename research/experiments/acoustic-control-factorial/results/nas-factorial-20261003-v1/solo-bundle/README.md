# 単独軸の非ニューラル研究版

固定20係数回帰とHMMで、任意入力文の解析・校正・初回生成・一回補正を実行する。教師波形、ニューラル重み、発話別設定は同梱しない。

`runtime.py --text TEXT --variant direct_f0_only --pitch-reference 180 --speed 0.85 --output output.wav`。速度単独は`direct_duration_only`。1〜120音素、F0参照140〜320、速度0.75〜1.3。参照F0は相対指定であり絶対F0を保証しない。1実行3生成。Python・NumPy・SciPy・pyopenjtalkと辞書が必要。Mei音源の出典・CC BY 3.0は同梱文書参照。

内容・自然さの資格を得た製品版ではない。
