# 32 kHzの固定母音と気道の安定条件

## 上流の経路

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、Workletが実際の出力レートを `engine_new` に渡す。`Engine::make_voice` → `oversample_for` → `HumanVoice::new` の順に、内部レートと制御周期が決まる。倍率は `floor(60000 / 出力Hz) + 1`。32,000 Hzなら2倍で64,000 Hz、内部時間刻みは15.625 µs。制御更新は64出力フレームごとの2 ms、128フレーム量子の予算は4 ms。上流テストは32 kHzを含む低レートで、2秒のうち後半が有限で、RMSが48 kHz発声の0.5〜2倍に入ることを確認する。[Workletの初期化](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L52)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L67)・[倍率と制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L212)・[低レートの上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L90)

`HumanAirway::new` は音速35,000 cm/sと時間刻みから1刻みの伝搬距離0.546875 cmを求め、設計クーラン数0.93で割った値をセル数の算定に使う。成人男性では、咽頭と口腔の想定最短長7.1 cmと7.3 cmを設計セル長で割って切り捨て、各12セルとなる。実際の姿勢から輪郭を作って断面を再標本化し、管の音響計算用の長さを `max(解剖学的長さ, セル数 × 伝搬距離 / 0.97)` にする。断面・管長を確定してから肺圧、声門面積、流量、放射、間引きの順に進める。`check_cfl` は固定圧の節点を除き、最短セルから `音速 × 時間刻み / セル長` を返す。上流の極端姿勢テストと既存の64 kHz短口腔ケースは、この長さの下限が効く条件を扱う。[セル数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L105)・[音響計算用の管長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L308)・[クーラン数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L634)・[描画順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L370)・[短口腔の既存実行](../runs/fixed-airway-short-64k-20261119-f/manifest.json)

## 事前登録

従来と同じ成人男性の固定 /i/、肺圧7.2 cmH₂O、F0 110 Hzで、32,000 Hz出力・64,000 Hz内部を試す。ゲートは出力フレーム2,816で1、34,816で0。減衰25,600フレームを含む計60,416フレームを保存する。定常窓は開始後8,000〜13,333フレーム、最後の1,600フレームを無音窓とする。出力PCM、呼気ゲート、声門面積・位相・流量、放射を観測する。上流の設定で固定姿勢を再生し、CLIと比較する。独立計算では呼気の時定数、49タップの係数、全管のセル数と最大クーラン数を検査する。[登録条件](../cases/worklet-realtime-voice-32000.json)・[共通姿勢](../cases/vowel-voice-i.json)

鼻腔は11.4 cmを19セルに分けて1セル0.6 cmとなるので、鼻腔が全管の最大クーラン数 `0.546875 / 0.6 ≈ 0.91146` を決めると予測する。咽頭・口腔にはこの姿勢では長さの下限が発動しないと見込む。描画中のネイティブ割り当てとWASMメモリ成長は0件、ブラウザのPCMはCLIとビット一致、発声中のp99は4 ms以内を判定条件とする。

## 再実装と先行計測

先行したCLIでは、発声ケースの入力を既存の固定 /i/ から読み、レートとゲート時刻を登録値で設定した。声道には既存の `TractSampling` を使い、計測器に管ごとのセル数・セル長・クーラン数と上流の節点CSVの照合を追加した。ブラウザでは同じ登録ケースを固定発声のレート一覧から選び、既存のAudioWorkletに設定を渡す。ネイティブの割り当て計数はWASMと共通のABIで発声から減衰までの全量子を再現する。[候補のセル数と管長](../crates/vocal-core/src/airway/tract_control.rs#L18)・[計測器](../tools/measure_worklet_realtime.py)・[レート選択](../../../../web/prototypes/chimera-research/src/main.tsx)

先行CLIは13項目を通過した。咽頭と口腔は上流・候補とも各12セル。音響計算上の長さはそれぞれ約8.093 cm、8.573 cmで、登録した姿勢ではセル長の下限による延長は生じなかった。鼻腔の0.6 cmセルが最大クーラン数0.9114583を決め、CLI・上流・独立計算の値は一致。節点の長さの最大差は `1.78×10⁻¹⁵ cm`、断面の最大差は `7.99×10⁻¹⁵ cm²` だった。咽頭と口腔のクーラン数はそれぞれ0.81090と0.76549。44.1 kHzで同じ姿勢を使ったときは口腔の0.78690が最大だった。[32 kHzの気道比較](../runs/worklet-rate-32000-20261120-native/summary.json)・[44.1 kHzのCLI設定](../runs/worklet-rate-44100-20261120-d/manifest.json)

77・128フレーム分割のCLIはWAVと出力段CSVが一致し、描画中のネイティブ割り当ては0件だった。独立した呼気の指数式との差は最大 `6.66×10⁻¹⁶`。固定上流とのPCM差は減衰中の出力フレーム42,227で初めて現れ、最大 `5.68×10⁻¹⁴` だった。音響状態の密な系列では、出力フレーム2,818で肺の固定圧に `3.55×10⁻¹⁵ dyn/cm²`、2,822で声門上圧に `1.32×10⁻²³ dyn/cm²`、2,823で放射差分に `1.59×10⁻²² cm³/s²` の差が現れた。定常のPCMから推定したF0は109.99942 Hz、末尾50 msのピークは `3.35×10⁻¹⁰`。[時系列とPCMの記録](../runs/worklet-rate-32000-20261120-native/manifest.json)・[呼気から放射への更新](../crates/vocal-core/src/voice.rs#L174)

## ブラウザと再実行

研究ワークスペースと `/tmp` から、ブラウザの13項目がそれぞれ通過した。AudioContext、Worklet、WAVはいずれも32,000 Hz、内部設定は64,000 Hz。固定発声から減衰末尾までの472量子は連続し、60,416フレームのPCMはCLIとビット一致した。呼気・声門・放射など472観測点はCLIと一致し、両回のブラウザWAV、音響観測、CLIと上流の時系列も一致した。冒頭32量子を除く発声中の処理時間は両回で中央値1 ms、p95とp99が2 ms。全区間で4 msの予算を超えた量子とWASMメモリ成長はいずれも0件だった。[初回](../runs/worklet-rate-32000-20261120-a/summary.json)・[再実行](../runs/worklet-rate-32000-20261120-b/summary.json)

CLIを `/tmp` から再実行し、PCM、内部時系列、上流の節点CSVが初回とバイト一致した。44.1 kHzと48 kHzの固定発声の回帰も通過し、44.1 kHzのWAVは前回と同一だった。[CLI再実行](../runs/worklet-rate-32000-20261120-native-repeat/manifest.json)・[44.1 kHzの回帰](../runs/worklet-rate-32000-20261120-44100-regression/manifest.json)・[48 kHzの回帰](../runs/worklet-rate-32000-20261120-48000-regression/manifest.json)
