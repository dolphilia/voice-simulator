# 原HTSとLPF前の固定LF声門流微分の比較

新16文×2条件×2方式64波形。元有声impulseだけを固定LFへ置換し、MCP/LF0/LPF/duration、元clock/noise/phase、MLSA/gain.25を保持した。候補は比較用native観測を内部で一度生成し、その費用も数える。全64通常/隔離・CLI4・実読取/通信拒否を照合した。

|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|31/32|0/720|0/33|0/33|
|lf|29/32|27/32|3/720|26/33|16/33|

保存全20055frameの三stream/durationと全32対の源clock/原励振/noise/phase/固定支持を確認した。周期関数の面積0・clock一致を処理後のpitchや自然さへ読み替えない。

Tp=.4/Te=.6/Ta=.05/Ee=1と連続周期RMS尺度を固定。有限/時間変動の面積0、aliasing、日本語知覚の資格は未確認。出力後の係数/phase/LPF/gain探索なし。

旧31方式・支持31,601/欠測249・二ASR33群と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達・最終採択なし。

一次資料: [Fant, Liljencrants & Lin (1985), LF model](https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf)。独自LF式と変更したHTS-BSD励振を明示する。

元隔離は内部登録資料の読取拒否に不通過。空の実体一覧を無条件許可にしないv2を出力前固定し、隔離64+CLI2を追加99生成/66DSPで再検証した。元波形/失敗/消費を保持し、元normal64+CLI2はhash照合で再利用。
全件研究保護: {'native': False, 'lf': False}
LFの工学/固定支持/二ASRを全分母で保持。不通過を同コホートの係数/phase/LPF/gainで救済しない。第5回分岐に従い独立な調音source-tract制御か異なる共有文脈/韻律表現へ進む。
