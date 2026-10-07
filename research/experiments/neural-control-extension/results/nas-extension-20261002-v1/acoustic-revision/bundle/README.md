# 音響量制御の研究版

固定回帰とHMMのみで生成する。教師音声、ニューラル重み、発話ごとの軌跡は含めない。

`runtime.py --text TEXT --model direct_non_neural --output output.wav`で生成する。`--pitch-reference`は学習した既定F0に対する220基準の相対指定で、指定値そのものの絶対F0は保証しない。`--speed`は相対速度。1〜120音素、F0参照140〜320、速度0.75〜1.3の研究用範囲。校正・初回生成・一回補正の3生成を実行する。

内容と自然さは未検証。品質認定版として使用しない。Python、NumPy、SciPy、pyopenjtalkと辞書が必要。Mei音源の出典とCC BY 3.0は同梱文書参照。
