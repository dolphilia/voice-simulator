# 原HTSと固定句アクセント指令応答の日本語比較

新16文×2条件×2方式64波形。LF0輪郭をラベル指令から計算し、MCP/LPF/duration/MSD/state/variance・原pulse/noise/MLSA・共通gain.25を保持した。係数/時刻規則の出力後探索なし。全64通常/隔離・CLI4・9論理/物理資料と通信の実拒否を照合した。

|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|32/32|0/696|0/33|0/33|
|fujisaki|32/32|28/32|4/696|18/33|20/33|

保存全20599frameの保持列/mask/sentinelと候補LF0の固定独立scalar式を照合した。LF0/源時計の方式間一致を主張しない。

alpha3/beta20/gamma.9/Ap.15秒/Aa.25/句先行.2秒は出力前固定。元LF0値の輪郭/教師/録音/lookupを使わない。全有声median校正はstreaming因果でなく、F2末尾核/無アクセント同値化は未知を保持する。

旧31方式・支持31,601/欠測249・二ASR33群と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達・最終採択なし。

一次資料: [Fujisaki and Hirose (1984)](https://www.jstage.jst.go.jp/article/ast1980/5/4/5_4_233/_pdf)。式とラベル規則の独自実装。

全件研究保護: {'native': True, 'fujisaki': False}
固定Fujisaki文脈韻律の全分母結果を保持。不改善時は同応答係数/指令時刻/median/gainを同コホートで救済せず、独立な調音source-tract機構または異なる生成表現へ進む。
