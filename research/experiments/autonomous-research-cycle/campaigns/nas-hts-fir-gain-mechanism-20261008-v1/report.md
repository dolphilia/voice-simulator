# FIR形状と対数利得の補間機構

16人工MCPの独立C prefix/係数変換式、4駆動源×2時間表現の独立直接畳み込みと因果prefix、上昇/下降の純利得×2方式、4HTS条件の原native完全一致・入力列不変を検査した。IR2048/FFT16384を保持し、波形からgainを推定しない。

原HTSのb0は線形に時間補間され、源にexp(b0)を掛ける。対数利得分離はこの因子のみを式で保護し、形状の補間やMLSA状態まで同一とは呼ばない。人工純利得の反復浮動小数点加算は許容誤差で照合した。

資格は人工機構に限る。前の日本語FIR1024/2048不通過・旧欠測を保持する。次は未使用16文の三方式比較。三回目も保護不通過ならFIRの同補間/係数救済は封印する。知覚資格なし・P5未開封・品質未達。

一次資料: [SPTK mc2b](https://sp-nitech.github.io/sptk/latest/main/mc2b.html)、[mglsadf](https://sp-nitech.github.io/sptk/latest/main/mglsadf.html)。
