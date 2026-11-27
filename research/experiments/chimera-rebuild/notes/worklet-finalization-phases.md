# 実時間発声の末尾量子を区間ごとに測る

## 固定上流と採取終了の経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor.process()` は、出力チャンネルの長さだけ `engine_render` に描画を求め、32ビットPCMを出力チャンネルへコピーする。処理予算を `1000 × 出力フレーム数 / sampleRate` msとし、処理時間を `Date.now` で測って平滑化する。テレメトリの送信はこの時間の計測より後にある。固定上流は連続するノードを基本とする。Rustの `engine_free` は生存中のハンドルをBoxに戻して解放する入口で、描画とは分かれている。同じ絶対フレームで操作を適用するとホストのブロック長を変えてもPCMが一致することを上流のテストが検査する。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[上流のWASM ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L159)・[上流のブロック分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の固定発声は、各量子で `FixedVoiceEngine.renderInto` がRustを呼んで出力へPCMをコピーし、`LiveProcessor` が採取用PCMと観測配列へ保存する。観測列の `process_ms` は、コールバック冒頭からPCM・観測を書いた直後まで。絶対時刻にはContextの `currentFrame`、採取内の位置には `frames` と観測行を進める `row` を持つ。停止位置と減衰区間の合計に達すると、観測時刻を書いた後に完了メッセージを組み立て、バッファとともに送る。その後に `engine.close()` が `vocal_free` を呼び、ポートを閉じて `process()` が `false` を返す。メインスレッドで観測行を変換し、WAV・JSONを保存する処理はこの末尾量子の計測より後にある。[候補のWorklet](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[候補のWASMホスト](../crates/vocal-wasm/host/fixed-voice.ts#L462)・[メインスレッドの受信](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts#L58)

## 事前登録と観測

前回の生トレースに現れた関数番号を、固定したWASMのエクスポート表と名前セクションに照合した。46は `vocal_control_output_frames`、48は `vocal_free`、41は `FixedVoice` の `drop_in_place` だった。完了メッセージのメタデータ取得で46が、ハンドル解放で48・41が遅延コンパイルされると予測した。使い捨てハンドルを事前に解放した条件では、48・41がコンストラクターへ移ることを検査する。[前回の末尾の観測](worklet-wasm-dsp-warmup.md#結果)・[事前登録](../cases/worklet-finalization-phases.json)

同じ96 kHz・128フレームの共有Contextで、通常の転送、同じ結果の複製、使い捨てハンドルを事前に解放した条件での転送を比較する。ラッパーの0フレーム呼び出しは全条件で1,000回。固定発声の採取は221,184サンプルの32ビットPCMと、1,728行×12列の64ビット観測値で、配列の合計は1,050,624バイト。HTML標準の `MessagePort.postMessage` は送信側でメッセージを直列化する。転送リストありでは送信側のバッファが切り離され、リストなしでは内容を複製する。どちらも受信側で全データを保存する。複製で送信側の呼び出し時間の中央値が延びるとした。[HTML標準の送信](https://html.spec.whatwg.org/multipage/web-messaging.html#dom-messageport-postmessage)・[ArrayBufferの転送](https://html.spec.whatwg.org/multipage/structured-data.html#structuredserializewithtransfer)

末尾量子にだけ実験用のトレース印を挿入し、Chromiumの `AudioWorkletProcessor::Process (author script execution)` の内側で、描画、PCM・観測の保存、メッセージ作成、送信と送信元バッファの状態、WASMハンドルとポートの解放を照合する。トレースの経過時間と取得できるスレッドCPU時間はµsで保存する。区間の和と外側の時間、絶対フレーム、WASM関数のコンパイル位置を比較する。音声と観測は前回の共有・単独Contextの記録および候補CLIと固定上流に照合する。先行音のPCMは前回と同じ区間を独立計算と照合し、そのPCM記録は末尾量子より前までである。[Chromiumの処理区間](https://chromium.googlesource.com/chromium/src/%2B/main/third_party/blink/renderer/modules/webaudio/audio_worklet_processor.cc#533)・[末尾の観測と判定](../tools/measure_worklet_finalization.py)・[先行音の独立計算](worklet-wasm-wrapper-shared-context.md#観測点と予測)

## 結果

初回と `/tmp` からの再実行で各320判定を通過した。転送では送信元のPCM・観測バッファが両方切り離され、複製では両方が残った。全18試行で受信したPCMと音響観測はビット一致した。固定上流との最大PCM差は2.92×10⁻¹¹未満。先行音の記録区間は計3,538,944サンプルが独立計算と一致した。[初回の各区間と判定](../runs/worklet-finalization-phases-20261121-a/summary.json)・[再実行](../runs/worklet-finalization-phases-20261121-repeat/summary.json)

| 各6試行 | 末尾全体の範囲（ms） | 送信の中央値（ms） | ハンドル解放の中央値（ms） |
| --- | ---: | ---: | ---: |
| 通常の転送 | 0.448〜0.572 | 0.054 | 0.081 |
| 同じデータを複製 | 0.660〜0.819 | 0.291 | 0.078 |
| 事前解放あり、転送 | 0.367〜0.430 | 0.051 | 0.013 |

通常の転送では描画の中央値が0.129 ms、メッセージ作成が0.116 ms。複製で送信の中央値が0.237 ms増えた。関数46は全18試行でメッセージ作成区間にあり、48・41は事前解放の有無でコンストラクターと末尾の解放区間に分かれた。事前解放条件と通常転送の解放時間の中央値の差は0.068 ms。全18試行の末尾が1.333 ms以内に収まり、今回のトレースには末尾の予算超過がない。標準経路は転送とし、区間計測と複製は研究用オプションとした。[関数番号を含む観測値](../runs/worklet-finalization-phases-20261121-repeat/summary.json)

## 過去の予算超過

前段階のラッパー回数、ラッパー準備、共有Context、事前描画の各2実行から、末尾が1.333 msを超えた8試行を再確認した。PCMの観測行数と起動待ち数から対象の `process()` を照合し、先行音がある実行ではそのイベントを除いた。生トレースと観測JSONはマニフェストのSHA-256に照合した。末尾全体は1.346〜3.937 ms、スレッドCPU時間は0.885〜2.205 ms。経過時間とCPU時間の差が0.5 ms以上だったのは3回で、最大は2.541 ms（経過3.937 ms、CPU 1.396 ms）。残る5回の差は0.010〜0.031 msだった。[ラッパー回数の初回](../runs/worklet-wasm-wrapper-threshold-20261121-a/summary.json)・[再実行](../runs/worklet-wasm-wrapper-threshold-20261121-repeat/summary.json)・[ラッパー準備の初回](../runs/worklet-wasm-wrapper-warmup-20261121-a/summary.json)・[再実行](../runs/worklet-wasm-wrapper-warmup-20261121-repeat/summary.json)

量子末尾に出た関数46・48・41のコンパイル時間の和は0.161〜0.423 msだった。これらより前にすでに時間を使った試行もあり、例えばCPU 2.205 msの試行で最初の関数46が始まったのはコールバック冒頭から1.283 ms後だった。従来の `process_ms` は8回とも0〜1 ms。末尾の送信・解放まで覆うトレースとは観測範囲と時計の分解能が異なる。旧トレースには今回と同じ区間印が無いため、過去の8件を転送や解放だけには帰属できない。[共有Contextの計測](../runs/worklet-wasm-wrapper-shared-context-20261121-c/summary.json)・[事前描画の計測](../runs/worklet-wasm-dsp-warmup-20261121-a/summary.json)

## 再現と保存

研究ワークスペースから以下を実行する。実行IDは新しく指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=440000000 \
  ../../.venv/bin/python tools/measure_worklet_finalization.py worklet-finalization-phases-next
```

macOS 15.6.1 arm64、Headless Chromium 156.0.8078.4、V8 15.6.75、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で実行した。音声・観測・トレースを可逆圧縮し、主比較2実行の約33.60 MBをRTL9210B-CGに保存した。末尾の実験設定を指定しない共有Contextも166判定を通過した。3実行の189出力をマニフェストのSHA-256に照合した。[初回のマニフェスト](../runs/worklet-finalization-phases-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/worklet-finalization-phases-20261121-repeat/manifest.json)・[従来経路の回帰](../runs/worklet-wasm-wrapper-shared-context-20261121-finalization-regression/summary.json)
