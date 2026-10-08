# 原HTSと二つのFIR利得補間の比較

新16日本語文×2条件×3方式の96波形。全64対のMCP/LF0/LPF・有声mask・duration・実励振/周期時計と固定支持を保護した。FIRは2048点の因果IRで全体利得込み算術補間と対数利得分離補間を比較し、原MLSAのb補間とは異なる。原nativeとの全96通常/隔離・CLI4の波形hashを照合し、候補内部の原MLSA補助生成も別計数した。

|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|32/32|0/820|0/33|0/33|
|fft_fir|32/32|28/32|4/820|16/33|0/33|
|fft_loggain|32/32|28/32|4/820|9/33|0/33|

実MCP全22905frameを除外なしで有限16384grid応答/tail検査した。所定機構判定: True。この検査は連続全域・知覚pitch・自然さの資格ではない。

知覚資格がないため最終候補を採択しない。旧31方式・支持31,601・欠測249・二ASR各33群の旧結果を保持し、総CERや波形別gainによる救済は行わない。P5未開封・品質未達。

一次資料: [SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)と[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。対数利得分離は波形からの利得推定ではなくMCPのb0式を使う。源の時計と原励振の一致は、フィルタ後の音響/知覚pitch一致を保証しない。

原nativeへの全研究保護: {'native': True, 'fft_fir': False, 'fft_loggain': False}
FIR三回目の全件保護不通過を保持し同補間/係数救済を封印。6件レビュー後、YIN型の短窓/動的/境界測定を別契約で資格検証する。
