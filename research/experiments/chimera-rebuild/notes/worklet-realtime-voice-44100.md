# 44.1 kHzの固定母音を実時間で検証

## 上流の経路と時計

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build` は、指定レートでAudioContextを作り、実際の `ctx.sampleRate` を保存する。Workletのコンストラクタはグローバルの `sampleRate` をWASMの `engine_new` に渡す。`Engine::make_voice` は `oversample_for` で内部倍率を選ぶ。内部レートを60 kHzより高くする式は `floor(60000 / 出力Hz) + 1` で、44,100 Hzでは倍速の88,200 Hzとなる。上流の `engine` テストは44,100 Hzで倍率2を明示し、低レート条件では定常区間の有限性と48 kHz基準に対するRMSを検査する。ホストのブロック分割に依存しないことは別のテストで確認している。[Contextの生成](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L108)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L52)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L138)・[倍率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L212)・[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L77)

`HumanVoice::new` は声道と声門を内部レートで構築し、制御間隔を `64 × 倍率` 内部サンプルにする。`render` は必要な制御更新、肺圧補間、声門面積、気道の圧力・流量、放射の順に進み、間引きで完成したPCMを返す。64出力フレームは44.1 kHzで約1.451 ms、128フレームの描画量子は約2.902 ms。呼気の制御ゲートは無次元で、目標に向けて `g += (目標−g) × (1−exp(−dt/τ))` を更新する。固定発声では立ち上がりが25 ms、解放が70 ms。圧力差は dyn/cm²、声門流量は cm³/s、放射差分は cm³/s² の系列で観測する。[内部初期化と制御周期](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L222)・[描画と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[呼気の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L508)

間引きは倍率2で49タップのKaiser窓付きsincを使う。遮断位置は内部ナイキストで正規化すると0.46、実周波数では20,286 Hz。係数和を1にそろえ、2内部サンプルごとに出力する。そのあとゲイン、25 HzのDC除去、リミッターを通す。出力フレーム `j` と同時に採る最後の内部サンプルの番号は `2(j+1)−1`。候補の `OutputStage` は整数倍を明示した設定をCLIとWASMで共有する。[上流の間引き](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L50)・[候補の出力段](../crates/vocal-core/src/output.rs#L27)・[WASMのレート入力](../crates/vocal-wasm/src/lib.rs#L71)

## 事前登録

48 kHz基準の成人男性 /i/ の姿勢、肺圧7.2 cmH₂O、基準F0 110 Hz、ゲインを維持し、出力44,100 Hz、内部88,200 Hzを指定する。開始は無音で、出力フレーム3,840でゲートを1、47,872で0にする。最後の35,200フレームを減衰として取り、計83,072フレームを比較する。開始と停止は128フレームの境界に置き、発声中の観測窓を開始後11,025〜18,375フレーム、末尾の無音窓を2,205フレームとする。[登録条件](../cases/worklet-realtime-voice-44100.json)・[姿勢の基準](../cases/vowel-voice-i.json)

まずCLIと固定上流を同じゲートで進め、出力、状態、異なるホスト分割、独立した呼気の指数式とFIR係数を確認する。ブラウザでは固定発声パネルから同じ条件を選び、実際のContextとWorkletのレート、開始から減衰末尾までの量子の連続、CLIとのPCMビット一致を確認する。定常F0は109.9〜110.1 Hz、末尾のPCMピークは `10⁻⁵` 以下を予測する。初期化を除いたネイティブの割り当てとWASMメモリ成長は0件、冒頭32量子を除いた発声中のp99は量子の時間予算以内を判定条件とする。

## 再実装と先行CLI検証

実時間の固定発声パネルで44,100 Hzを選べる。元の固定母音の姿勢を読み、レートと観測時間をケースの値で設定する。Workletは実際の `sampleRate` とケースのレートを照合し、描画後に両レート、内部レート、WASMの制御フレーム数とメモリ成長を報告する。比較器は設定に従って自動停止を待ち、採取したゲートフレームをCLIと上流プローブに渡す。[画面の設定](../../../../web/prototypes/chimera-research/src/main.tsx#L145)・[Worklet](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[計測器](../tools/measure_worklet_realtime.py)

先行したネイティブ実行は10項目を通過した。CLIの77・128フレーム分割はWAVと出力段CSVがバイト一致。間引き2と制御間隔128内部サンプルを確認し、49タップの独立計算との差は最大 `1.51×10⁻¹⁵`。呼気ゲートの指数式との差は最大 `8.88×10⁻¹⁶`。649量子をネイティブのWASM用ABIで再現して、描画中の割り当て・再割り当てを0件と確認した。[先行実行](../runs/worklet-rate-44100-20261120-native/summary.json)・[ネイティブの計数](../crates/vocal-wasm/src/lib.rs)

固定上流とのPCMの最初のビット差は出力フレーム53,995で、最大差は `1.14×10⁻¹³`。圧力の密な系列ではゲート開始後6フレームにあたる3,846で声門上圧に `8.08×10⁻²⁸ dyn/cm²`、次の3,847で放射差分に `1.29×10⁻²⁶ cm³/s²` の差が現れた。ゲート、声門位相、F0の系列は全フレームで一致した。[上流と候補の出力ハッシュと時系列](../runs/worklet-rate-44100-20261120-native/manifest.json)

## ブラウザ検証

最初のブラウザ実行はレート欄の名前を完全一致で探す段階で終了した。選択肢を含むラベルを、選択欄に明示的に結び付けるラベルに変更した。登録済みの設定と判定条件は同じケースを読み込んで再実行した。[初回の失敗](../runs/worklet-rate-44100-20261120-a/manifest.json)

修正後は研究ワークスペースと `/tmp` から各13項目を通過した。ChromiumのAudioContext、Worklet、WAVはいずれも44,100 Hz。649量子の描画フレームは連続し、加工前の83,072フレームはCLIとビット一致した。64フレームごとの制御更新に対応する声門と呼気などのWorkletの観測は、128出力フレームごとの649観測点でCLIと一致した。再実行のWAV、ネイティブと上流の出力、フレームに対応する音響観測も同一。無音からの立ち上がりはゲートから27フレーム後で、定常のF0は109.99959 Hz、最後の50 msのPCMピークは `3.39×10⁻¹⁰` だった。[修正後の実行](../runs/worklet-rate-44100-20261120-b/summary.json)・[再実行](../runs/worklet-rate-44100-20261120-c/summary.json)

量子予算は約2.902 ms。冒頭32量子を除く発声中のp99は両回2 msで、全649量子の予算超過とWASM線形メモリの増加は両回0件だった。コールバック開始時刻の間隔は両回最大10 msで、同じ量子の計算時間やContext上のフレームの連続性とは違う量を測っている。今後のレート比較でも、実時間の間隔とPCM上の欠落を別々に記録する。[初回の実時間観測](../runs/worklet-rate-44100-20261120-b/manifest.json)・[再実行の実時間観測](../runs/worklet-rate-44100-20261120-c/manifest.json)

計測器の実行記録を整理し、ネイティブ計測はブラウザ用ツールの情報を取得せずに実行できるようにした。再実行ではネイティブの要約が先行実行と一致し、ブラウザ側も13項目を通過した。この回は減衰中の出力フレーム53,248からの量子が4 msで、全区間で1件の予算超過を観測した。発声中のp99は2 msで、フレームに対応する音響観測とWAVは修正後の初回と一致した。[ネイティブの再実行](../runs/worklet-rate-44100-20261120-native-repeat/summary.json)・[ブラウザの最終実行](../runs/worklet-rate-44100-20261120-d/summary.json)

48 kHzの固定発声と、舌・唇の操作およびケース書き出しの回帰も通過した。[48 kHzの固定発声](../runs/worklet-rate-44100-20261120-fixed-regression/manifest.json)・[手動調音の回帰](../runs/worklet-rate-44100-20261120-manual-regression/manifest.json)
