# 全実MCPによる有限IRの切分け

前の64波形比較から保存済みの全32native・21,333MCP frameを再利用し、除外0でC1024係数/解析prefix、8192→16384grid、IR長1024/2048/4096を照合した。新しい音声・ASR・P5処理は0。

|IR長|最大複素応答相対誤差|最大参考tail energy|不通過frame|全条件通過|
|---|---:|---:|---:|---|
|1024|28.79043|0.00015200321|306|False|
|2048|1.090143e-05|1.473499e-17|0|True|
|4096|1.5328854e-11|2.7967546e-28|0|True|

登録規則による最短長: 2048。C prefix相対誤差最大5.0738398e-15、grid refinement最大4.6184816e-15。

この結果は選択に用いた既コホートの有限gridに限る。未知MCP・連続全周波数・瞬時F0・知覚の資格ではない。旧FIR1024の内容悪化/欠測/不通過と旧249欠測を変更しない。
有効な固定長のFFT/因果畳み込みを別fixtureで検証し、新日本語比較を登録する。

一次資料: [SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)、[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。P5未開封・品質未達。
