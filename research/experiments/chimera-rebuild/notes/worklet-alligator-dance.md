# 実時間AudioWorkletでのアメリカアリゲーターの `dance`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryから `AudioEngine` を経て送られる `call` は、Workletでコールの索引に変わり、WASMの `engine_play_call` から `CreatureVoice` に届く。公式CLIは同じ声門・気道・乱数・フィルタを使い続け、持続・停止・`bellow`・`growl`・`hiss` に続いて出力336,000で `dance` を再生する。48 kHzの最終出力位置は441,600フレーム。上流の単発試験 `alligator-call-dance` は89,760フレームのPCM、区間RMS、テレメトリを照合し、実時間試験はキー解決と再生・操作・停止時の割り当てを検査する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Workletの操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASMの操作](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

コールは18 Hzを基準に移調し、口の目標を0に保つ。この口の目標は断面0.05 cm²に対応する。平滑化の前の粗さは1.7秒かけて0→0.75へ直線補間し、ゲートは開始から1.6秒まで1、その後1.7秒までに0になる。古い `hiss` の所有は切り替え時に解除され、手動目標が戻る。64出力フレームごとの制御で新しいコールの目標を評価してから、平滑値、肺圧、声門、断面の指示へ進む。平滑粗さ `c` は声門位相が一周したときに `x←(2.9+1.1c)x(1−x)` を進め、周期長の倍率に `0.45c(x−0.5)`、振幅の倍率に `1.1c(x−0.5)` が入る。ジッターとシマーの基準値は粗さ0のときにも残る。位相と瞬時F0から、内部レート `fs` に対して新周期の倍率を `(F0/fs)/Δ位相` として復元する。[コールのキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L117)・[切り替えと制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[周期境界の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L181)

壁面・口端・鼻端の放射体積速度 `U`（cm³/s）を内部サンプルごとに足し、`fs·(U[n]−U[n−1])` を放射の出力（cm³/s²）とする。差分の周波数利得は `2fs·|sin(πf/fs)|` で低域ほど小さい。48・44.1 kHzでは間引きが入り、96 kHzでは内部と出力が同じレート。間引きの後にゲイン、12 HzのDC除去 `y[n]=v[n]−v[n−1]+exp(−2π·12/f_out)·y[n−1]`、振幅制限、単精度PCMへの変換が続く。各放射経路の足し合わせは位相を保って行う。[放射の加算と差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1073)・[間引きと出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L365)・[CLIの低域計測](alligator-dance.md)

## 事前登録

48 kHzの公式全体、44.1 kHzの `hiss` からの切り替え、96 kHzの単独コールを再生する。ブラウザの加工前PCMはCLIと全フレームでビット一致、内部観測は最大差0を要求し、固定上流には既登録の許容差を使う。3条件ともコール最初の制御から0.3〜0.9秒の全内部サンプルを取り、Hann窓の10〜80 Hzで声門面積、圧力、放射体積速度、PCMのピークを照合する。声門面積は18 Hz条件で15〜21 Hz、24 Hz条件で20〜28 Hzとし、PCMのピークはその上に出ると予測する。44.1 kHzは切り替え39,001で手動 `hiss=0.12`、制御境界39,040で音高24 Hzと口0の目標に移ることを確認する。

96 kHzでは0〜92,159の連続系列から、総放射体積速度を足し合わせ、差分・DC除去・PCMを独立に再構成する。25〜80 Hzと12〜25 HzのRMS比は差分後に増え、DC除去によってさらに増えると予測する。線形なDC除去段では経路ごとに計算した系列の和が同じ出力になり、観測されたPCMには登録した許容差で一致する。壁面・口端・鼻端は各経路を省いた合成も作り、ピークと帯域RMSへの寄与を測る。先に登録した粗さ0の対照と条件を合わせ、0.3〜0.9秒のブラウザ位相から求めた周期長倍率の平均が大きくなることを検査する。[ブラウザの登録条件](../cases/worklet-alligator-dance.json)・[上流との比較・スペクトル窓・粗さ対照](../cases/alligator-dance.json)

## ブラウザへの接続

画面の `dance` の再生ケースを既存のアリゲーター用WASM・AudioWorkletへ接続した。連続観測区間とイベントの境界で描画を分け、気道と声門の状態を保ったまま同じ合成器で再生する。保存したケースをCLIで再生し、ブラウザの加工前PCMと観測値を照合する。公式条件は末尾441,600フレームまでを固定上流の公式WAVとも比較する。96 kHzの各放射経路を省く対照には、保存した流量から線形な出力段を再構成した波形を使う。気道の圧力や他経路の流量は実測した値を使う。[ブラウザの再生入口](../../../../web/prototypes/chimera-research/src/main.tsx)・[共通比較処理](../tools/measure_worklet_alligator_call.py)・[低域と放射経路の計測](../tools/measure_worklet_alligator_dance.py)

## 実測

Chromium 156.0.8078.4で取得した加工前PCMは、48・44.1・96 kHzの全746,600フレームでCLIとビット一致した。声門・気道・制御の156,832観測点も最大差0だった。公式デモ全441,600フレームと固定上流の差は単精度16フレーム、最大 `9.31×10⁻¹⁰`。最初の内部差は先行する持続音の肺流量の内部1、最初のPCM差は出力73,414だった。`dance` 区間105,600フレームでは4フレームに差があり、全体の356,373が最初で最大 `2.27×10⁻¹³` だった。44.1 kHzでの最初の内部差は壁面放射の258でPCM最大差は `7.45×10⁻⁹`。96 kHzでは肺流量・気管入口圧の内部65が最初で、PCM最大差は `1.16×10⁻¹⁰`。いずれも登録した許容差内だった。[比較と差の発生箇所](../runs/worklet-alligator-dance-20261120-a/summary.json)

44.1 kHzでは出力39,001で手動 `hiss=0.12` へ目標が戻り、39,040で平滑値が下がって目標音高24 Hzと口0が入った。最初の制御から0.3〜0.9秒の10〜80 Hzを調べると、各条件で声門面積・気管端圧・咽頭入口圧と壁面・口端・鼻端の体積速度が同じ周波数ビンで最大だった。ブラウザと固定上流のピークのビンは全系列で一致した。[制御境界とブラウザのスペクトル](../runs/worklet-alligator-dance-20261120-a/summary.json)

| 条件 | 声門面積・圧力・各放射流量のピーク | 加工前PCMのピーク |
| --- | ---: | ---: |
| 公式デモ 48 kHz | 18.33 Hz | 36.67 Hz |
| 24 Hzへ移調 44.1 kHz | 23.33 Hz | 46.67 Hz |
| 単独 96 kHz | 18.33 Hz | 35.00 Hz |

### 総流量の時間差分と壁面放射

96 kHzの先頭92,160サンプルについて、壁面・口端・鼻端の流量を足して差分を取り、12 HzのDC除去と振幅制限を独立計算した。観測した総放射差分との最大差は `1.16×10⁻¹⁰ cm³/s²`、DC除去後との差は `1.87×10⁻¹⁶`。再構成した単精度PCMは観測と数値上すべて一致した。0.3〜0.9秒の窓には振幅制限が働いたフレームはなかった。[出力段の独立再構成](../runs/worklet-alligator-dance-20261120-a/summary.json)

| 96 kHzの観測位置 | スペクトルのピーク | 25〜80 Hz / 12〜25 HzのRMS比 |
| --- | ---: | ---: |
| 総放射流量 | 18.33 Hz | 0.590 |
| 時間差分後 | 35.00 Hz | 1.275 |
| DC除去後 | 35.00 Hz | 1.469 |

ピークは時間差分の段で移り、DC除去は高い側の比率をさらに上げた。各経路のDC除去後の和は総流量から得た出力と最大 `1.76×10⁻¹⁴` の差で一致した。記録した流量を固定し、壁面由来の系列だけを省くとピークは18.33 Hz、口端または鼻端だけを省くと35.00 Hzだった。[段階別と放射経路別の対照](../runs/worklet-alligator-dance-20261120-a/summary.json)

### 粗さと周期長

96 kHzの0.3〜0.9秒では、粗さ0の対照で11周期の周期長倍率が平均0.99985、軌跡を使ったブラウザでは10周期で平均1.02109だった。ゲート・肺圧・口先と軟口蓋の実断面・平滑音高・瞬時F0は対照と一致した。ブラウザの連続系列全体から復元した17周期の倍率を、独立の写像と乱数計算へ最大差 `2.22×10⁻¹⁶` で照合した。[粗さ0の対照と周期倍率](../runs/worklet-alligator-dance-20261120-a/summary.json)

### 実時間と再実行

固定上流とのCLI基準は316項目、ブラウザ比較は研究ディレクトリと `/tmp` で各288項目が通過した。156,832観測行と、3条件のブラウザWAV、書き出しケース、CLIのWAV・CSV、WASMの計13ファイルが一致した。CLIのWAV・CSV計6ファイルは事前のCLI基準とも一致した。128フレームを処理する時間のp95は48・44.1・96 kHzの順に2・2・1 msで、各予算の2.67・2.90・1.33 msを下回った。計時は `Date.now` の1 ms刻み。96 kHzではコール再生と自然終了を通じてネイティブの描画時割り当ては0回だった。[固定上流とのCLI基準](../runs/alligator-dance-before-worklet-1/manifest.json)・[ブラウザ初回](../runs/worklet-alligator-dance-20261120-a/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-alligator-dance-20261120-repeat/manifest.json)

公式デモ全体を照合できるように比較処理を更新した後、`hiss` の311項目と116,978観測行、計測ファイル13件を再確認した。Rustは `cargo fmt --all --check`、`cargo clippy --locked --workspace --all-targets -- -D warnings`、`cargo test --locked --workspace --release` を通過し、ワークスペースの試験は35件だった。固定上流はCLI基準取得時に `creature_realtime` の3件と `golden_creatures` の4件が通過した。[hissの回帰](../runs/worklet-alligator-hiss-dance-regression-20261120/manifest.json)・[上流試験のログ](../runs/alligator-dance-before-worklet-1/artifacts/upstream-tests.log)
