# 原HTSと最小位相因果FIRの比較

新16日本語文×2条件×2方式の64波形。全32対のMCP/LF0/LPF・有声mask・duration・実励振/周期時計と固定支持を保護した。FIRは1024点の因果IRと出力時刻のIR補間を使い、原MLSAのb補間とは異なる。原nativeとの全64通常/隔離・CLI4の波形hashを照合し、候補内部の原MLSA補助生成も別計数した。

|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|31/32|0/761|0/33|0/33|
|fir1024|32/32|26/32|6/761|9/33|0/33|

実MCP全21333frameを除外なしで有限8192grid応答/tail検査した。所定機構判定: False。この検査は連続全域・知覚pitch・自然さの資格ではない。

知覚資格がないため最終候補を採択しない。旧31方式・支持31,601・欠測249・二ASR各33群の旧結果を保持し、総CERや波形別gainによる救済は行わない。P5未開封・品質未達。

一次資料: [SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)と[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。源の時計と原励振の一致は、フィルタ後の音響/知覚pitch一致を保証しない。

原nativeへの全研究保護: {'native': False, 'fir1024': False}
FIRの全実MCP応答と音声の工学/二ASR保護を区別し、不通過は全件で保持する。有効な範囲から時間表現または共有生成制御の別要因へ進む。
