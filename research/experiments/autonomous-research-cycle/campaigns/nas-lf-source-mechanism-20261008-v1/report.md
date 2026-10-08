# LF声門流微分の固定周期関数

Tp=.4/Te=.6/Ta=.05/Ee=1を出力前固定し、有限帰還のepsilonとゼロ面積のalphaを数式から解いた。連続解析二乗積分で源のRMS尺度を一つに固定し、波形からgain/係数をfitしない。LF0列の縮小/平坦化やRosenberg有限差分の救済ではない。

独立quadによる面積0・power1、閉相/周期端の連続、flow非負の17点、基本波Fourier係数非ゼロ、密phase gridと20人工条件のC/Python数値一致・前半一致・不正入力拒否を確認した。42生成/128DSP。周期関数の固定入力に限り、時間変動の源・声道、HTS/LPFへの結合、aliasing、日本語自然さ/知覚pitchを資格付けしない。

一次資料: [Fant, Liljencrants & Lin (1985), A four-parameter model of glottal flow](https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf)。式に基づく独自C/Python実装。Pink TromboneやGPL派生コードは取得/コピーしていない。

次は科学30件のレビュー後、限定LFを原HTS励振へ結合する機構を別登録する。旧欠測と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達。
