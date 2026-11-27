# 固定発声Wasmから放射を観測する

固定上流の `engine_render` はハンドルが持つPCM領域を `Engine::render` に渡す。 `Engine` は絶対フレーム位置を128で割った余りで制御境界を決め、境界間を `HumanVoice::render` に渡す。上流のブロック分割試験は同じ位置に操作を並べ、ホストの分割長を1、77、128、4096、48000に変えてPCMを比較する。 [上流のWasm入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[ブロック処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

上流の内部標本では肺圧と声門開口を更新してから気道を進める。枝流量、壁速度と変位、放射負荷と接続した端の圧力を順に更新する。壁の体積流量に口端と鼻端の体積流量を加える。合算の単位は cm³/s。前標本との差に内部レートを掛けた cm³/s² の値を間引き器に送り、直流除去と振幅制御の後のPCMを返す。上流の一様管試験は壁の有無ごとにインパルス応答と線形周波数応答のピークを照合する。 [固定上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[壁速度](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[放射の差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1135)・[一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

研究版の `FixedVoiceEngine.renderInto` は `vocal_render` を呼ぶ。 `OutputStage::render_frame` は出力が出るまで内部標本を取り、最後に渡した `VoiceSample` をPCMと一緒に返す。固定 /i/ では96 kHzから48 kHzへ間引くため、出力フレーム `k` の観測は内部標本 `2k+1` になる。従来のWasm観測は描画ブロック末尾の23値で、固定発声のTypeScriptホストはその先頭8値を使う。全フレームの放射観測には準備時に専用領域を確保し、ブロック内の各フレームの `VoiceSample` を順に写す。 [研究版のWasmレンダー](../crates/vocal-wasm/src/lib.rs#L981)・[出力フレームの生成](../crates/vocal-core/src/output.rs#L76)・[ホスト](../crates/vocal-wasm/host/fixed-voice.ts)・[事前登録したケース](../cases/fixed-vowel-i-wasm-radiation.json)

通常の `renderFixedVoice` はケースを `OfflineAudioContext` の固定発声Workletに渡す。ケースで `fixed_voice_probe.radiation_components` が有効なら、Workletが全フレーム用の配列を確保し、出力を写すたびに放射の5値を同じ位置へ写す。完了時にバッファを転送し、報告の `radiation.columns` と `radiation.values` で取得できる。Wasmハンドルは最大4,096フレーム分の160 KiBを確保する。Workletは今回の32,768フレーム分として1.25 MiBを確保する。 [Workletの描画](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[ブラウザの報告](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)

## 実測

Wasmの128・77・4,096フレーム分割とChromiumのWorkletで、通常CLIの全32,768出力フレームの放射5値とPCMにビット一致した。Workletは128フレームの連続した256量子を処理し、既存の77フレーム間隔の観測点もCLIと一致した。未指定と明示無効時には放射列を作らず、両条件のPCMと既存の観測は有効時と一致した。ネイティブの放射観測付き描画中の割り当ては0件だった。 [再実行の全判定](../runs/fixed-vowel-i-wasm-radiation-20261124-repeat/summary.json)

CLIの全内部標本を使って流量の和と差分を求め、FIR・直流除去・振幅制御からPCMを再計算して全てビット照合した。上流との比較で最初に観測した差はフレーム7（内部標本15）の壁の体積流量で、同じフレームの合算と微分にも差が現れた。口端の最初の差はフレーム24で、鼻端は全点一致した。上流に対する流量と微分のピーク正規化誤差は最大3.12×10⁻¹³。PCMはフレーム3,901からビット差があり、絶対差は最大2.33×10⁻¹⁰だった。 [CLIの内部標本を検証した記録](fixed-vowel-i-cli-radiation.md#実測)・[今回の上流との差](../runs/fixed-vowel-i-wasm-radiation-20261124-repeat/summary.json)

## 実行記録

macOS 15.6.1 arm64、Rust 1.94.1、Node.js 24.19.0、Chromium 156.0.8078.4、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースから、次のコマンドの実行IDを毎回変えて実行する。再実行は `/tmp` からPythonとスクリプトを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_wasm_radiation.py fixed-vowel-i-wasm-radiation-20261124-repeat
```

初回はNode.jsの型除去だけで既存ホストのTypeScriptパラメータプロパティを読み込もうとして終了した。型変換を有効にした試行では放射とPCMを含む20判定が通り、配信バイナリの判定が落ちた。ブラウザの記録を実際の `fetch` 応答に絞り、整形後のWasmで再実行した2回は21判定が通過した。固定上流の気道・ブロック分割試験9件も通過した。 [型読み込みの初回ログ](../runs/fixed-vowel-i-wasm-radiation-20261124-registered/artifacts/cargo.log)・[配信判定の初回結果](../runs/fixed-vowel-i-wasm-radiation-20261124-typescript-transform/summary.json)・[修正後のマニフェスト](../runs/fixed-vowel-i-wasm-radiation-20261124-fetch-filtered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-wasm-radiation-20261124-repeat/manifest.json)

整形後の同じWasmで、44.1 kHzの英語発話の停止・再開をChromiumとFirefoxで照合した30判定と、48 kHzの従来の固定発声Workletを照合した13判定が通過した。48 kHzの固定発声で線形メモリの拡張は0回だった。整形前の該当2実行も保存した。 [英語発話の回帰](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261124-radiation-final/summary.json)・[48 kHzの回帰](../runs/worklet-rate-48000-radiation-memory-20261124-final/summary.json)

第33版の全体監査は195実行・3,204成果・406判定に通過した。通常Webビルドが出力したWasmと3つの現行ブラウザ計測で配信されたWasmのSHA-256は一致し、研究版Rustテスト53件と固定上流17件が通過した。今回の9実行の3,287入力・149出力をSHA-256で照合した。RTL9210B-CG上の141出力は同一内容を共有し、65ファイル分の131,706,805バイトを使用する。 [全体監査](../runs/plan-completion-v33-fixed-vowel-i-wasm-radiation-20261124/summary.json)・[監査マニフェスト](../runs/plan-completion-v33-fixed-vowel-i-wasm-radiation-20261124/manifest.json)
