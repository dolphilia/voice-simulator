# 実時間AudioWorkletでのアフリカゾウの固定発声と口・鼻の放射

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryで選んだ種と演奏値は `AudioEngine` を経てWorkletの `creature`・`cparams` に届く。WASMの `engine_set_creature`・`engine_creature_param` が設定を反映し、`CreatureVoice::render` が同じ状態を持ち続ける。公式CLIは出力48 kHzで1.2秒の持続と0.4秒の停止を描画してから各コールを再生する。今回は固定発声の先頭76,800フレームを比較する。固定試験はPCM・区間RMS・テレメトリを照合し、実時間試験は割り当て、低レート試験は32 kHzと48 kHzで最初のコールのRMSを検査する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Workletの制御](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[低レート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L133)

`elephant::create` は気管45 cm、咽頭32 cm、口腔28 cm、鼻の基部14 cmを共有の気道で作る。咽頭と鼻の基部を軟口蓋ポートで結び、基部から長さ0.6 cmの入口弁を介して185 cmの鼻へ進む。鼻の断面はセル中心 `u` を使って `4.2−3u` cm²、放射負荷は口端と鼻先。弁の実断面は固定発声中4.5 cm²。`Elephant::control` は64出力フレームごとに演奏目標を平滑化し、肺圧を `980.665×呼気圧×ゲート` dyn/cm²に設定する。平滑化された経路 `t` は口先目標 `0.05+10(1−t)` cm²、軟口蓋の目標 `0.1+6t` cm²に入る。平滑化の時定数は40 msで、その結果から次の制御境界まで断面をさらに線形補間する。[気道の構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L31)・[ゾウの制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)・[制御周期](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

各サンプルでは気管端と咽頭入口の前サンプルの圧力差で声門を進め、入口弁の実断面を入れてから枝流量・節点圧・各端の放射を更新する。声門と弁の流量は cm³/s、鼻の基部・入口・先端の圧力は dyn/cm²。壁面・口端・鼻先の放射体積速度の和を時間差分に取り、ゲイン、12 HzのDC除去、振幅制限、単精度化を施して加工前PCMを出す。ゾウは内部と出力のレートが同じ。[各サンプルの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L94)・[総放射と差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1073)・[出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[CLIの読解と測定](elephant-fixed-voice.md)

## 事前登録

48 kHzの公式冒頭と無呼気、44.1 kHzの発声中の経路変更、96 kHzの口側固定を再生する。48・96 kHzの有声条件は立ち上がりを連続で観測し、44.1 kHzの経路変更は全52,000サンプルを観測する。基部圧・弁流量・鼻先圧と放射の最初の非ゼロを出力フレームで比較する。加工前PCMはCLIとビット一致、内部状態も最大差0を要求し、固定上流と独立計算には既登録の許容差を使う。44.1 kHzの経路変更では独立に計算した断面補間と肺圧を照合し、0.32〜0.48秒から0.85〜1.05秒にかけて口端流量RMSは下がり、鼻先流量RMSは上がると予測する。

44.1 kHzでは同じ初期状態と呼気を用い、22,051の経路変更だけを省いたCLI対照も測る。目標の差は指示時点、実断面の差は22,080の制御更新から現れる。鼻の基部・入口弁・鼻先の順で非ゼロの差が現れると予測し、圧力は `1e-6 dyn/cm²`、流量は `1e-5 cm³/s` の閾値通過も記録する。固定弁面積、音高、肺圧は対照と一致すると予測する。[ブラウザの登録条件](../cases/worklet-elephant-fixed-voice.json)・[CLIと独立計算の登録条件](../cases/elephant-fixed-voice.json)

## ブラウザへの接続

CLIと同じ `ElephantVoice` をWASMの固定発声で使い、呼気と演奏目標をイベントの出力フレームに渡した。一つのインスタンスで発声を始め、経路変更後も声門・気道・フィルタを維持した。29列の観測は、CLIと共通の音響・制御状態と、制御更新前に記録できる経路目標を含む。書き出したケースをCLIへ渡し、PCMをビット単位、状態を同一フレームで比較した。独立計算では経路の平滑化と断面補間をブラウザの観測へ、声門の駆動差圧と放射差分・DC除去を全フレームの系列へ照合する。[WASMの操作と観測](../crates/vocal-wasm/src/elephant.rs)・[観測列とWorkletの受け渡し](../crates/vocal-wasm/host/elephant.ts)・[計測手順](../tools/measure_worklet_elephant_fixed_voice.py)

## 実測

Chromium 156.0.8078.4のAudioWorkletは、3レートの全187,424フレームで加工前PCMがCLIとビット一致し、54,939観測点で内部の制御・音響状態も最大差0だった。固定上流に対する最初の内部差とPCMの最大差は次の表のとおりで、すべて登録した許容差内だった。無呼気では肺圧、弁流量、壁面・口端・鼻先の放射とPCMは0だった。[ブラウザ・CLI・固定上流の比較](../runs/worklet-elephant-fixed-20261120-a/summary.json)

| 条件 | 出力フレーム | 観測点 | 固定上流との差が最初に出た位置 | PCM最大絶対差 |
| --- | ---: | ---: | --- | ---: |
| 公式冒頭 48 kHz | 76,800 | 1,517 | 肺流量 1 | `4.66×10⁻¹⁰` |
| 経路変更 44.1 kHz | 52,000 | 52,000 | 肺流量 65 | `1.82×10⁻¹²` |
| 口側固定 96 kHz | 57,600 | 1,405 | 肺流量 5 | `3.73×10⁻⁹` |
| 無呼気 48 kHz | 1,024 | 17 | 全系列が一致 | 0 |

最初のPCM差は上から出力12,783、5,981、66に現れた。連続観測した立ち上がりでは、基部圧・入口弁流量・鼻先の圧力と放射が48 kHzで82・83・231、44.1 kHzで139・140・253、96 kHzで172・173・430フレームに現れた。固定発声の入口弁は全系列で4.5 cm²だった。[放射までの到達と差の発生箇所](../runs/worklet-elephant-fixed-20261120-a/summary.json)

### 口から鼻へ切り替わるときの伝搬

44.1 kHzでは経路目標が22,051で0→1に変わった。29フレーム後の22,080で口先断面は10.05から10.04443 cm²、軟口蓋は0.1から0.10334 cm²へ動いた。同ブロック末尾22,143の断面は9.69369・0.31379 cm²だった。独立の40 ms平滑化と64フレームの補間は各観測点で許容差内だった。0.32〜0.48秒と0.85〜1.05秒の流量RMSを比べると、口端は2,969.04→159.83 cm³/s、鼻先は51.26→1,031.45 cm³/sと変わった。[断面の補間と区間RMS](../runs/worklet-elephant-fixed-20261120-a/summary.json)

経路変更だけを省いた対照では、最初の音響差が22,080の口端・壁面の放射とPCMに出た。鼻の基部圧は22,092、入口圧と弁流量は22,093、鼻先圧は22,274、鼻先放射は22,275で初めて異なった。鼻先放射の差が `1e-5 cm³/s` を超えた22,311は、実断面が動いてから約5.24 ms後だった。音高・肺圧・弁面積は対照と一致した。[経路変更を省いた入力](../runs/worklet-elephant-fixed-20261120-a/artifacts/fixed-oral-control-case.json)・[対照との差の時系列](../runs/worklet-elephant-fixed-20261120-a/summary.json)

### 実時間と再実行

固定上流とのCLI基準は188項目、ブラウザ比較は研究ディレクトリと `/tmp` で各80項目を通過した。54,939観測行、WASM、CLIとブラウザのWAVと再生ケース・CLIのCSV、固定経路の対照を含む計20ファイルが一致した。CLIのWAV・CSV計8ファイルは接続前の基準実行とも一致した。128フレームの描画時間p95は2回の計測で48・44.1 kHzの発声が1〜2 ms、96 kHzと無呼気が1 msで、各条件の予算内だった。Workletは `Date.now` の1 ms刻みで計時した。ネイティブでは44.1 kHzの経路変更と96 kHzの口側固定の描画で割り当ては0回だった。[CLI基準](../runs/elephant-fixed-before-worklet-1/manifest.json)・[ブラウザ再実行](../runs/worklet-elephant-fixed-20261120-repeat/manifest.json)

共有するWorkletへの接続後も、アリゲーターの固定発声86項目は通過し、4,666観測行と20計測ファイルが変更前と一致した。Rustの整形、Clippy、ワークスペースの試験36件が通過した。固定上流との基準取得では `creature_realtime`・`golden_creatures`・`engine` の13件が通過した。[アリゲーターの回帰](../runs/worklet-alligator-fixed-elephant-regression-20261120/manifest.json)・[上流試験のログ](../runs/elephant-fixed-before-worklet-1/artifacts/upstream-tests.log)
