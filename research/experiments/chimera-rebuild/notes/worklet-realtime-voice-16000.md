# 16 kHzの固定母音と4倍の間引き

## 上流の経路

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、ページが作ったAudioContextの実レートをWorkletが `engine_new` に渡す。`Engine::make_voice` は `oversample_for` を使い、内部レートを60 kHzより高くする最小整数倍率を選ぶ。16 kHzでは `floor(60000 / 16000) + 1 = 4` で内部64 kHzとなる。上流の低レートテストは16 kHzでの2秒間の発声を含み、後半の有限性とRMSが48 kHz基準の0.5〜2倍に収まることを検査する。テストの説明には、以前の2倍設定で内部32 kHzとなる場合の不安定化が記録されている。[Context](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L108)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L52)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L138)・[倍率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L212)・[低レートテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L90)

`HumanVoice::new` は内部64 kHzから声道のセル数と声門の時間刻みを決め、制御更新の間隔には `64 × m` 内部サンプルを設定する。出力32 kHzの倍率2では128内部サンプル・2 ms、16 kHzの倍率4では256内部サンプル・4 ms。描画は境界で呼気のゲートと肺圧の目標を更新し、各内部サンプルで肺圧を補間して声門と気道の状態、放射を処理する。呼気ゲートは無次元で、圧力は dyn/cm²、声門流量は cm³/s、放射差分は cm³/s²。32 kHzと16 kHzの制御区間末尾を4 msごとにそろえると、25 msの立ち上がりと70 msの減衰の指数式は同じ値を予測する。制御目標から肺圧を補間する区間長も変わるので、途中の圧力やPCMはレートごとに照合する。[内部初期化と制御周期](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L222)・[描画順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[呼気](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L508)

`Decimator` は対称なKaiser窓付きsincを `24 × m + 1` タップで設計し、係数の和を1に正規化する。倍率4では97タップ、遮断の設定は `0.46 × 64000 / 4 = 7360 Hz`、群遅延は `(97−1)/2 = 48` 内部サンプル、0.75 ms。放射の履歴をリングに蓄え、位相カウンタが4に達するたび畳み込み・ゲイン・DC除去・リミッターを適用して1フレームを返す。出力フレーム `j` の最後の内部サンプルは `4(j+1)−1` となる。上流のホスト分割テストでは、同じ状態と操作を異なるブロック長で進めて同じPCMになることを検査する。[上流のFIRと位相](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L50)・[ホスト分割の検査](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)・[候補の間引き](../crates/vocal-core/src/output.rs#L135)

## 事前登録

成人男性の固定 /i/、基準F0 110 Hz、肺圧7.2 cmH₂O、初期無音の姿勢を既存ケースから使う。ゲートは16 kHz出力フレーム1,408で1、17,408で0にする。32 kHz基準の時刻を正確に半分のフレーム番号で表し、開始・停止・減衰末尾の内部サンプル境界をそろえる。発声後の12,800フレームを含めて30,208フレーム、128フレームずつ236量子を保存する。定常窓は開始後4,000〜6,667フレーム、末尾の無音窓は800フレーム。[登録条件](../cases/worklet-realtime-voice-16000.json)・[固定した32 kHz参照](../runs/worklet-rate-32000-20261120-native-repeat/manifest.json)

予測は、32 kHz参照と気道幾何・クーラン数が一致し、両レートで時刻をそろえた472件の制御区間末尾のゲート差が `10⁻¹⁰` 以下となること。97タップの係数を独立計算し、0〜5 kHzのゲイン誤差と10 kHz以上の指定点の抑制を調べる。同一16 kHz条件ではCLIとWorkletのPCMおよび内部観測が一致すると予測する。描画のネイティブ割り当てとWASMメモリ成長は0件、128フレームの予算8 msに対して発声中のp99はその範囲内を判定条件とする。

## 再実装とCLI検証

固定発声パネルに出力16 kHzを追加し、既存のレート選択から同じ声道姿勢と内部64 kHzをWorkletへ渡した。ネイティブの通常の `render`・`render-pcm`、固定上流の観測プローブ、両ホストで共通のWASM用ABIと、SciPyの係数・周波数応答計算を使って比較した。32 kHz参照のマニフェストと3出力はSHA-256で照合してから読み込んだ。[画面のレート選択](../../../../web/prototypes/chimera-research/src/main.tsx)・[計測器](../tools/measure_worklet_realtime.py)・[CLIの実行記録](../runs/worklet-rate-16000-20261120-native/manifest.json)

先行CLIは19項目を通過した。咽頭・口腔は各12セル、最大クーラン数は鼻腔の0.9114583。候補の気道設定全体と上流の節点CSVは32 kHz基準と一致した。共通の制御区間末尾472件では、呼気ゲートの最大差が `3.33×10⁻¹⁶`。ゲートを開いた直後の共通観測時点（内部サンプル5,635）では、16 kHz側のゲートは0.147856、32 kHz側は0.076884だった。同時刻の肺境界圧は16.4131、17.0693 dyn/cm²。16 kHz側は算出した肺圧目標へ4 msで補間し、32 kHz側は最初の肺圧目標へ2 msで補間している。共通区間の末尾でゲートが一致しても、途中の肺圧にはこの違いが現れる。[対照の集約結果と時系列](../runs/worklet-rate-16000-20261120-native/summary.json)・[32 kHzの時系列](../runs/worklet-rate-32000-20261120-native-repeat/manifest.json)

97タップの係数は独立計算との差が最大 `7.77×10⁻¹⁶`。0〜5 kHzのゲイン誤差は最大 `4.55×10⁻⁵`、10・12・20・30 kHzの4点のゲインは最大 `3.75×10⁻⁵`。群遅延は48内部サンプル、0.75 msだった。77・128フレーム分割のCLIは出力段CSVとWAVが一致し、描画中のネイティブ割り当ては0件。固定上流の加工前PCMと全フレームがビット一致した。高精度の時系列では最初に出力フレーム1,411で声門下圧に `8.67×10⁻¹⁹ dyn/cm²`、声門上圧に `8.47×10⁻²² dyn/cm²`、声門流量に `5.29×10⁻²³ cm³/s` の差を確認し、次のフレームで放射差分にも差が現れた。定常PCMの推定F0は110.0063 Hz、末尾50 msのPCMピークは `4.16×10⁻¹⁰`。[CLIの計測要約](../runs/worklet-rate-16000-20261120-native/summary.json)・[上流との時系列](../runs/worklet-rate-16000-20261120-native/manifest.json)

## ブラウザと再実行

研究ワークスペースと `/tmp` からのブラウザ実行は、各13項目を通過した。AudioContext、Worklet、WAVのレートは16,000 Hz、内部は64,000 Hz。236量子は連続し、加工前PCM 30,208フレームはCLI・固定上流とビット一致、236件の観測はCLIと数値が一致した。両回でWAVと観測の音響値は一致。発声中のp99は両回4 msで、全区間の8 ms予算超過とWASM線形メモリ成長は0件だった。[ブラウザ初回](../runs/worklet-rate-16000-20261120-a/summary.json)・[ブラウザ再実行](../runs/worklet-rate-16000-20261120-b/summary.json)

CLIを `/tmp` から再実行し、19項目の要約、PCM、時系列、上流気道CSVが先行実行と一致した。既存32 kHzは13項目の回帰が通過し、WAVは前回の通過実行とバイト一致した。[CLI再実行](../runs/worklet-rate-16000-20261120-native-repeat/manifest.json)・[32 kHz回帰](../runs/worklet-rate-16000-20261120-32000-regression/manifest.json)
