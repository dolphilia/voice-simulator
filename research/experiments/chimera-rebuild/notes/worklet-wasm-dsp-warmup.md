# 使い捨ての発声状態でWASM関数本体を準備する

## 発声状態とコンパイル済みコード

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`ChimeraProcessor` がWASMをインスタンス化してから `engine_new(sampleRate)` でエンジンと出力領域を確保する。最初の `process()` で `engine_render(h, n)` に先頭出力チャンネルのフレーム数を渡し、戻った32ビットPCMをチャンネルへコピーする。Rustの `Engine::render` は出力位置 `pos` を持ち、128フレームの境界でビートの予約を更新する。発声の制御は `HumanVoice` が64出力フレームごとに更新する。ホストブロック長を1・77・128・4,096・48,000に変えても、同じ絶対フレームの操作を与えたPCMがビット一致することを上流がテストしている。[固定上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L138)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補は `vocal_new` が設定・PCM・観測の領域を確保し、`vocal_start` が23値の入力から固定声道、呼気と声帯、出力段を新規に組み立てる。状態には制御更新までの内部サンプル数、呼気のゲートと圧力、声帯の位相、気道の圧力・流量、出力段の履歴、累計の出力フレーム数がある。96 kHzでは内部倍率1で、64サンプルごとに呼気の制御を更新する。各サンプルは呼気・肺圧境界、声門圧差と開口面積、気道の伝搬と放射、出力段の順を通る。描画ごとにPCMと最後の観測を更新し、`vocal_free` がハンドルと所有する状態を破棄する。V8の `Runtime_WasmCompileLazy` は同じインスタンスから `NativeModule` を取得して関数をコンパイルする。ハンドルを破棄しても同じWASMインスタンスを使う限り、準備した関数コードが再利用されると予測した。[候補のWASM ABI](../crates/vocal-wasm/src/lib.rs)・[呼気から放射までの順序](../crates/vocal-core/src/voice.rs#L214)・[V8の遅延コンパイル](https://chromium.googlesource.com/v8/v8/%2B/main/src/runtime/runtime-wasm.cc#373)

## 事前登録と観測

前回の共有Contextでラッパーを準備した6試行の生トレースを読み直した。発声の先頭量子に出た `wasm.CompileLazy` の関数番号は6回とも同じ10件だった。番号は今回のWASMバイナリのSHA-256にひも付けた。通常のラッパー準備、使い捨て状態の作成と解放、使い捨て状態での128フレーム描画を比較する。後二者は同じ1,000回の0フレーム呼び出しを行い、通常の発声ハンドルを作る前に使い捨て状態を解放する。後二者の差は、ゲート0の状態で描画を1ブロック実行するかどうかとした。[前回の共有Context再実行](../runs/worklet-wasm-wrapper-shared-context-20261121-repeat/manifest.json)・[今回の事前登録](../cases/worklet-wasm-dsp-warmup.json)・[準備と本番ハンドルの実装](../crates/vocal-wasm/host/fixed-voice.ts)

通常画面と同じ96 kHz Workletで、先行音が鳴るContextを使う。選んだ条件は実験用のオプションで渡し、事前描画の開始・終了をトレースに記す。同じオーディオスレッドのコンパイルイベントをµs単位で照合する。両対照は登録した10件が本番の先頭、128フレーム条件は事前描画区間に現れると予測した。本番の累計128フレーム、先行音の時刻・独立PCM、発声音と全音響観測、固定上流とCLIを前回と同じ基準で照合する。構築と先頭量子の処理時間は診断量として保存する。[Workletの入口](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[共有Contextの観測](worklet-wasm-wrapper-shared-context.md)・[計測コマンド](../tools/measure_worklet_dsp_warmup.py)

## 結果

初回と `/tmp` からの再実行で各292判定を通過した。18試行すべてでラッパーの同期コンパイルをコンストラクター内に観測した。登録した10関数は両対照の計12試行で本番の先頭量子に、128フレーム事前描画の6試行では全件が事前描画区間に現れた。後者の本番の先頭量子には遅延コンパイルを1件も観測しなかった。事前描画全体は0.768〜0.964 msで、そのうち10関数のコンパイルイベントの期間の和は0.260〜0.332 msだった。[初回の判定と関数番号](../runs/worklet-wasm-dsp-warmup-20261121-a/summary.json)・[再実行の判定](../runs/worklet-wasm-dsp-warmup-20261121-repeat/summary.json)

| 各6試行 | 本番の先頭量子の範囲・中央値（ms） | コンストラクター全体の範囲・中央値（ms） | 構築をまたぐ先行音のコールバック間隔（ms） |
| --- | ---: | ---: | ---: |
| ラッパー準備 | 1.027〜1.372、1.124 | 3.613〜6.475、5.045 | 5.381〜7.954 |
| 使い捨て状態を作成、描画0フレーム | 1.104〜1.479、1.207 | 4.088〜6.283、4.930 | 5.300〜6.842 |
| 使い捨て状態を作成、描画128フレーム | 0.419〜0.520、0.450 | 4.699〜6.680、5.513 | 5.337〜7.201 |

使い捨て状態同士の比較で、先頭量子の中央値は0.757 ms短く、構築時間の中央値は0.583 ms長かった。128フレーム事前描画の6試行は全量子が1.333 ms以内だった。両対照では先頭量子で各1回、ラッパー準備のみの1試行では末尾でも1回予算を超えた。本番の先頭の累計は全試行で128フレーム、発話のPCMと全観測は単独・共有Contextの基準とビット一致した。先行音は各196,608サンプル、計3,538,944サンプルが独立計算とビット一致し、フレームは連続した。固定上流との最大PCM差は2.92×10⁻¹¹未満、呼気ゲートの独立計算との差は最大2.11×10⁻¹⁵だった。コンストラクターは引き続き先行音と同じスレッドで動くため、構築側への移動を研究用のオプションとして使う。物理出力と別ブラウザでの効果は未計測。[初回の波形と時刻](../runs/worklet-wasm-dsp-warmup-20261121-a/manifest.json)・[再実行の波形と時刻](../runs/worklet-wasm-dsp-warmup-20261121-repeat/manifest.json)

初回9試行の生トレースを、先行音のコールバックを除いて再確認した。起動待ちを除いた0始まりの66量子目、ゲートを開く位置には全条件で関数60・891の遅延コンパイルが残り、2件の合計は0.038〜0.058 msだった。末尾の1,727量子目では関数46が全試行にあり、ラッパー準備のみでは48・41も現れた。使い捨て状態を解放する両条件では48・41は末尾に出なかった。末尾の処理には最後のPCM、完了通知とバッファの転送、ハンドルとポートの解放があり、各区間の時間を次の対照で分けて測る。[初回の生トレース](../runs/worklet-wasm-dsp-warmup-20261121-a/manifest.json)・[Workletの終了処理](../../../../web/prototypes/chimera-research/src/live-processor.ts)

## 再現と保存

研究ワークスペースから以下のコマンドで実行する。実行IDは新しく指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=440000000 \
  ../../.venv/bin/python tools/measure_worklet_dsp_warmup.py worklet-wasm-dsp-warmup-next
```

macOS 15.6.1 arm64、Headless Chromium 156.0.8078.4、V8 15.6.75、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で実行した。計測の先行音PCM、音声WAV、観測JSON、生トレースは実行後に可逆圧縮し、主比較2実行の約33.62 MBをRTL9210B-CGに保存した。内蔵にはケース、ソースのスナップショット、結果要約、マニフェストを置いた。事前描画を指定しない従来の共有Contextも166判定を通過し、3実行の189出力をマニフェストのSHA-256と照合した。[初回の実行条件](../runs/worklet-wasm-dsp-warmup-20261121-a/manifest.json)・[再実行の実行条件](../runs/worklet-wasm-dsp-warmup-20261121-repeat/manifest.json)・[従来経路の回帰確認](../runs/worklet-wasm-wrapper-shared-context-20261121-dsp-regression/summary.json)

後続の計測では末尾で観測した関数番号をWASMの名前と照合し、メッセージ作成とハンドル解放の区間に対応づけた。[末尾量子の区間計測](worklet-finalization-phases.md)
