# アフリカゾウの固定発声と口・鼻の放射経路

上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `render creature elephant` は `CreatureVoice::new` を呼び、既定値で1.2秒の持続音と0.4秒の停止を描画する。その後にコールを順に再生する。鼻の経路を検証する今回の範囲では先頭76,800フレームを使う。上流は `creature_realtime` で割り当て、`golden_creatures` で既定の動物音声とテレメトリ、ホスト分割を検査する。低レートの回帰では `engine::the_creatures_hold_at_the_lighter_rate` がゾウの最初のコールを32 kHzと48 kHzで比較する。[CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[回帰試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[低レート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L133)

`elephant::create` は `mammal_airway` に気管45 cm、咽頭32 cm、口腔28 cm、鼻の基部14 cmを渡す。口は咽頭と直結する。咽頭から鼻の基部へは軟口蓋ポートがある。基部の終点から185 cmの鼻へは長さ0.6 cmの弁ポートを介して接続し、鼻先に放射負荷を付ける。鼻の断面は各セル中心 `u=(i+0.5)/N` で `4.2−3u` cm²。鼻の基部には放射負荷を付けず、咽頭と口腔の壁には放射割合0.6を与える。各管のセル数は `floor(L/(35000/(0.93 fs) × coarse))` を上下限に収めた値で、鼻は粗さ係数2.3、最大110セルを使う。[ゾウの構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L31)・[共有の気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L51)・[セル分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L7)

`Elephant::control` は肺圧を `980.665 × 呼気圧 × ゲート` dyn/cm² に設定する。固定発声の `mode=0` では、声門音源の振幅は1.6 cm²、開大0.05 cm²、粗さは演奏値の0.6倍、発声閾値は1.5 cmH₂O。音高と圧力の初期値は14 Hzと16 cmH₂O。平滑化した `trunk` の値を `t` とすると軟口蓋の目標断面は `0.1+6t`、口側の末尾15%に属するセルの目標断面は `0.05+10(1−t)` cm²である。初期値は断面に即時反映し、演奏中は64出力フレームごとに目標を更新して次の制御まで線形に移行する。[制御値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)・[制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[断面の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L682)

`Elephant::sample` は声門上下の前サンプルの圧力差から開口を求め、鼻の入口の弁を4.5 cm²に設定してから `AirwayNetwork::step` を呼ぶ。枝流量・節点圧・壁面と端の放射状態を進めた後、総放射流量の時間差分を出力段へ渡す。固定上流のゾウは内部レートと出力レートが等しく、12 HzのDC除去、リミッター、単精度化を使う。[サンプル処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L94)・[出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)

## 事前登録

48 kHzの公式冒頭と44.1 kHzの手動切り替え、96 kHzの口側固定、48 kHzの無呼気を比べる。切り替え要求の出力22,051で目標値を変更し、次の制御境界22,080から口端と軟口蓋の断面が反対方向に変わると予測した。基部の流量と鼻先の放射の順序を測り、44.1 kHzの登録区間では切り替え後に口端のRMSが下がり、鼻先のRMSが上がるかを調べる。[登録した入力・観測点・許容差](../cases/elephant-fixed-voice.json)

## 実装と実測

オフラインCLIの `elephant_voice` は、既存の哺乳類の肺圧・声門・口鼻腔に追加の管と弁を組み合わせる。鼻の基部には圧力の観測点を置き、放射は鼻先の終端で取る。ゲートと形状の平滑化は64フレームごと、断面の補間と音響状態の更新はサンプルごとに行う。内部レートは出力レートと等しいため、出力段の間引きは倍率1で通過する。独立計算は制御点から求めた断面、前サンプルの声門差圧、流量の時間差分、DC除去後の出力を照合した。[共有気道](../crates/vocal-core/src/airway/mammal.rs)・[固定発声](../crates/vocal-core/src/airway/elephant.rs)・[計測器](../tools/measure_elephant_fixed_voice.py)

| 出力レートと条件 | 鼻のセル数 | 基部圧力の開始 | 弁の流量の開始 | 鼻先の放射の開始 |
| --- | ---: | ---: | ---: | ---: |
| 48 kHz、公式冒頭 | 102 | 82 | 83 | 231 |
| 44.1 kHz、口から鼻への手動切り替え | 94 | 139 | 140 | 253 |
| 96 kHz、口側固定 | 110 | 172 | 173 | 430 |

開始は系列の最初の非ゼロ出力フレームで数えた。公式冒頭では、気管端圧は34、声門流量は35、壁面放射は36、口端放射は97フレームから現れた。基部から鼻先までの立ち上がりは、実測の閾値、セル分割、制御境界での微小値の消去に影響されうる。無呼気の1,024フレームでは肺圧、弁の流量と放射、PCMがゼロだった。[全条件の到達時刻](../runs/elephant-fixed-voice-20261120-b/summary.json)

切り替え要求の出力22,051から29フレーム後の22,080で、口先断面が10.05から10.04443 cm²へ下がり、軟口蓋が0.1から0.10334 cm²へ上がった。この制御区間の最終フレームではそれぞれ9.69369、0.31379 cm²に達した。口端と軟口蓋の面積を独立した平滑化・線形補間で求めた値との差は最大 `5.68×10⁻¹⁴ cm²` だった。入口の弁の面積は切り替え中も4.5 cm²を保った。[形状の時系列と独立計算](../runs/elephant-fixed-voice-20261120-b/summary.json)

| 44.1 kHzの観測点 | 切り替え前の0.32〜0.48秒 | 切り替え後の0.85〜1.05秒 |
| --- | ---: | ---: |
| 口端の放射流量 RMS | 2,969.04 cm³/s | 159.83 cm³/s |
| 鼻先の放射流量 RMS | 51.26 cm³/s | 1,031.45 cm³/s |
| 鼻の入口弁の流量 RMS | 55.50 cm³/s | 1,039.72 cm³/s |
| 鼻の基部の圧力 RMS | 435.53 dyn/cm² | 6,342.76 dyn/cm² |
| 鼻先の圧力 RMS | 3.18 dyn/cm² | 19.00 dyn/cm² |

流量は同じレートの切り替え前後で評価した。口側固定でも軟口蓋は0.1 cm²で開いており、鼻先の放射が残る。公式冒頭の持続区間0.75〜1.10秒のPCMはRMS 0.08167で、最後の100 msでは `5.96×10⁻⁵` だった。[各区間のRMS](../runs/elephant-fixed-voice-20261120-b/summary.json)

## 残る差と再現

48 kHzの公式CLIとの比較は先頭76,800フレームで、差は13フレーム、最大絶対差は `4.66×10⁻¹⁰`。44.1 kHzの切り替えでは4フレームで最大 `1.82×10⁻¹²`、96 kHzの口側固定では12フレームで最大 `3.73×10⁻⁹` だった。公式冒頭で最初の差は、フレーム1の肺ポートの流量に現れ、気管端圧は34、声門流量は35、壁面放射は36、PCMは12,783で初めて異なった。3レートとも肺の固定圧力、声門位相、瞬時F0は一致した。最初の計測ではCSVに書き出したPCMの十進表記を比較していた。最終の計測では、WAVと上流の単精度値をそろえてから差を求めた。登録条件と合否は同じだった。[初回結果](../runs/elephant-fixed-voice-20261120-a/summary.json)・[最終結果](../runs/elephant-fixed-voice-20261120-b/summary.json)

研究ディレクトリからと `/tmp` からの最終実行は各188項目を通過し、要約とWAV・CSV・JSONの観測ファイル33件が一致した。実行コマンド、ツールチェーン、入力と出力のSHA-256はマニフェストに記録した。[最終実行](../runs/elephant-fixed-voice-20261120-b/manifest.json)・[再実行](../runs/elephant-fixed-voice-20261120-repeat/manifest.json)
