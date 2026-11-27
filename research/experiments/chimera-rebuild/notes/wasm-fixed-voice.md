# 固定姿勢の発声をWASMから実行する

## 固定上流の読解

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `AudioEngine.build` はWeb AudioのサンプルレートでContextを開き、コンパイル済みモジュールをWorkletに渡す。WorkletのコンストラクタがWASMをインスタンス化し、`engine_new(sampleRate)` で音源とバッファを確保する。`process()` は出力チャンネルの長さだけ `engine_render` を進め、線形メモリのf32をチャンネルにコピーする。テレメトリは間隔を空けて取得し、次回の観測が上書きする前にJavaScriptの値にする。線形メモリが伸びると既存のTypedArrayを作り直す必要がある。上流の `api.rs` のUTF-8 JSON呼び出しは別の準備経路で、実時間のレンダーは数値とアドレスを使う。[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[C ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L118)・[JSON入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs)

`Engine::render` は出力済みの総フレーム数を持つ。128フレームの相対位置は `pos % 128`、次の更新境界までの長さは `128 - pos % 128`。ホストの残り長との小さい方を実際に処理し、境界を越えたらシーケンサを進める。ホストはイベント時刻でブロックを分ける。人間の内部制御は別周期で、48 kHz出力では64出力フレームごとに更新される。96 kHzの内部計算では呼気の圧力境界、声門の開口と流量、気道の圧力・速度の順で進め、放射流量の時間差分を間引き、DC除去、リミッターへ渡す。出力フレーム `n` を観測する内部サンプルはゼロ始まりで `2(n + 1) - 1`。音響量はCGS、声門位相は0〜1、PCMは加工前のモノラルf32。[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[人間の声のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[出力段の読解](pcm-output.md)

上流のRustテストはイベント時刻を固定して1・77・4096などの分割を検査し、TypeScriptのテストはWASMのインポートとネイティブに対するPCM各サンプルの一致を検査する。C ABIの実時間テストは準備後のヒープ割り当ても数える。[ブロックテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[WASM比較](../../../../docs/reference/chimera-vocal-synth/upstream/tests/wasm-engine.test.ts#L69)・[割り当てテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/tests/realtime.rs#L42)

## 実装前の予測と登録

以前の[固定母音 /i/](../cases/vowel-voice-i.json)を同じまま使う。成人男性、肺圧7.2 cmH₂O、ゲート1、基準F0 110 Hz、出力32,768フレーム。既存の[固定上流との照合](../runs/vowel-voice-i-20261119-e/summary.json)ではPCMがバイト一致した。今回も各PCMフレームのビット一致を予測する。ホストのブロックを1・77・128・4096に変えても、最終フレームの観測は同じになる。共通観測点は257フレーム間隔と、発音開始39および制御更新64の前後等。位相の周回を補間して定常区間のF0を独立に測る。呼気・声門・放射の系列の許容差、オンセット閾値、ヒープ割り当ての判定は実装前に登録した。[WASM比較ケース](../cases/wasm-fixed-voice.json)

## 実装

Rustでは `vocal_new` で固定長のPCM領域と観測領域を確保し、`vocal_start` で調音軸17個と音源・ゲイン6個から成人男性の固定声道を作る。型付き配列を作るのは準備後に行う。出力領域には最大4096フレームのf32、観測領域には累積出力フレーム数と状態7項目のf64を置く。ホストは同じPCM領域を読み、観測値を保持する場合は次のレンダー前にコピーする。固定姿勢と音源の計算は既存の `SagittalModel` と `FixedVoice` を使う。PCMの入口はCLIとWASMで共有し、`OutputStage::render_frame` が間引きの成立した内部サンプルの観測をPCMと一緒に返す。初期化の対象はインパルスなしの成人男性固定声道。過大な声道・フィルタの確保を避けるため、レートを出力8 kHz以上、内部384 kHz以下の整数倍関係に制限した。[C ABI](../crates/vocal-wasm/src/lib.rs)・[TypeScriptホスト](../crates/vocal-wasm/host/fixed-voice.ts)・[共通の出力段](../crates/vocal-core/src/output.rs)

Nodeの計測ホストは、ホストのブロック境界に加えて登録済み観測点で出力バッファを分ける。例えば出力フレーム64を観測するときは累積出力65で止め、ネイティブの内部サンプル129を参照する。位相の周回を含む2点 `(n₀, φ₀)` と `(n₁, φ₁)` の間では、交差位置を `n₀ + (n₁ − n₀)(1 − φ₀)/(1 − φ₀ + φ₁)` で求め、周回数と交差間隔からF0を計算する。位相の観測間隔は最大257フレームで、110 Hzの1周期より短い。[計測ホスト](../tools/render_wasm_fixed.ts)・[比較器](../tools/measure_wasm_fixed.py)

## 検証結果

| 観測 | 結果 |
| --- | --- |
| 加工前のPCM | 1・77・128・4096フレームの4条件すべてで、32,768フレームがCLIとWASM、固定上流のネイティブ版でビット一致 |
| 声門、呼気と放射 | 各分割で135時点・7系列を照合。WASMとCLIの差は0、固定上流との差は各系列のピーク比で最大1.58×10⁻¹³ |
| オンセットとF0 | 0始まりのフレーム39でPCMが閾値を超えた。定常部は位相から110.0000 Hz、PCMのYINから110.0016 Hz |
| バッファと割り当て | WASMに外部インポートなし。線形メモリと2つのバッファのアドレスは安定。ネイティブのABIテストで初期化後の割り当ては0回 |

初回は全条件を通過した。再実行ではバッファのアドレスと線形メモリを観測点ごとに検査し、体型などのWASM入力チェックも追加した。ケースと合否基準は初回と同じ。固定母音のPCMと、上流・候補の時系列のハッシュは再実行でも一致した。歌唱の回帰、Rustワークスペースの9件、Clippy、TypeScriptホストの型検査、固定上流のブロック処理6件とABI割り当て1件が通過した。[初回](../runs/wasm-fixed-voice-20261119-a/manifest.json)・[再実行](../runs/wasm-fixed-voice-20261119-c/manifest.json)・[歌唱回帰](../runs/song-voice-long-20261119-wasm-regression/summary.json)

再実行にはRustの `wasm32-unknown-unknown` ターゲットと、TypeScriptの型消去を備えるNodeを使う。今回の比較計測はNode 24.19.0で実施した。ブラウザのWorkletでのPCMと実時間の処理予算、発話・歌唱、調音操作は第6段階の残りで確認する。

```bash
cargo build --locked --release -p vocal-wasm --target wasm32-unknown-unknown
python3 tools/measure_wasm_fixed.py wasm-fixed-voice-local-1
```
