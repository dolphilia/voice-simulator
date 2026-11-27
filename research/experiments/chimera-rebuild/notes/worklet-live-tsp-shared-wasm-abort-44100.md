# 英語発話の共有WASM取得を待つ間に片方を停止する

## 固定上流と実験対象

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `src/wasm/chimera.ts` の `initChimera` は、ページ全体で最初のコンパイル・インスタンス生成を共有し、取得失敗時に読み込み中のPromiseを消す。`src/ui/speech.ts` の `speakText` は辞書を読み、`speakPhrases` は句の調音スコアを計画して `AudioEngine.schedule` に渡す。`stopSpeaking` は `src/audio/AudioEngine.ts` の `stopSpeech` を経由してWorkletへ停止を送る。`src/worklet/processor.ts` はそのメッセージをエンジンへ渡し、`Engine::stop_speech` が音声のスコアを取り消す。語表示用には現在の計画IDを停止済みとして保存する。`tests/words.test.ts` は二重母音や句間休止を含む語の境界を、`crates/chimera/tests/engine.rs` の `output_does_not_depend_on_the_host_block_size` は予定されたコマンド下でブロック長を変えてもPCMが一致することを検証する。

再実装の `src/main.tsx` の発話パネルは実時間側の中止に `AbortController` を使う。`src/render-fixed-voice.ts` の `loadEnglishModule` はページ内の取得・コンパイルのPromiseを共有する。実時間側の `withRealtimeContext` は専用のContextを作り、共有ロードと `resume()` を待つ。その途中で信号がabortすると、呼び出しを終了して `finally` でContextを閉じる。ロード後にも信号を確認してから計画とWorklet生成へ進む。オフライン側は同じモジュールと辞書を待ってから、別の `OfflineAudioContext` を使う。画面の発話パネルは同時実行を抑止するため、この試験は画面も使う二つの公開関数を同じページで直接呼び、停止時と同じ `abort()` を渡す。

時系列はページの `performance.now()` のミリ秒で観測する。音響比較の座標は出力フレームで、確認用07は44,100 Hz出力、内部88,200 Hz、128フレーム／量子。基準と同じ開始秒・話速・体型の入力を使うと、描画フレーム数は計画の終了秒に出力レートを掛けて丸めた98,790になる。応答を保留して停止側のContextが閉じたことを観測してから解放すれば、停止時にオフライン側が取得を待ち続けるか、オフラインと再開後のPCMが対照に一致するかを分けて判定できる。[事前登録](../cases/worklet-live-tsp-shared-wasm-abort-44100.json)・[同一ページでの共有の基準](../runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/summary.json)

## 実装と実行

Playwrightでブラウザからの最初のWASM取得を捕まえ、停止後のスナップショットを撮るまで応答を保留した。ページでは公開関数 `renderRealtimeEnglishVoice` と `renderEnglishVoice` を同じ確認用07で呼ぶ。実時間だけを停止し、オフライン描画が完了してから新しい制御信号で実時間再生を始める。計画器とContext、Workletノードの生成はページ内で記録し、2回分のPCMと観測は通常のWAV・JSON形式で書き出す。停止の順序はページ内の時刻と、応答の解放前に直接読んだ `AudioContext.state` を使って確認する。[ブラウザの対照](../../../../web/prototypes/chimera-research/tools/capture-shared-english-wasm-abort.mjs)・[判定とマニフェスト生成](../tools/measure_worklet_live_tsp_shared_wasm_abort.py)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Node 24.19.0。Firefox 157.0とChromium 156.0.8078.4。現行RustからWASMをビルドし、基準と同じSHA-256のバイナリを両ブラウザの計画器がコンパイルしたことを確認した。以下は研究ワークスペースからのコマンド。2回目は `/tmp` からPythonとスクリプトを絶対パスで呼び、実行ID末尾を `-b` にした。

```bash
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_shared_wasm_abort.py worklet-live-tsp-shared-wasm-abort-44100-20261122-a "$firefox"
```

## 結果

2実行で、FirefoxとChromiumの合計30判定が各回通過した。応答を保留したまま停止側は `AbortError` で終了し、最初のContextは `closed`、AudioWorkletNodeの生成は0個だった。オフライン側はこの観測時点で待機中だった。応答を解放するとオフラインが完了し、その後に始め直した実時間再生は別のContextにノードを1個作り、完了後にContextを閉じた。WASMの取得・コンパイル・計画器生成はページ全体で各1回だった。停止要求から停止側のPromiseの拒否までの観測値は、4試行で約0.8〜9 msだった。[再実行の集約](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261122-b/summary.json)・[Firefoxの時系列](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261122-b/artifacts/firefox/abort-evidence.json)・[Chromiumの時系列](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261122-b/artifacts/chromium/abort-evidence.json)

両ブラウザ・両描画の計8出力について、全98,790フレームのPCM、句とジェスチャー、ABI・声門・声道観測が各基準に一致した。PCMの最初の非ゼロはフレーム2,247、固定上流との最大絶対差は1.1641532182693481×10⁻¹⁰。標準ライブラリの独立検算で停止と解放の順序、44.1 kHz・float32のWAVの全標本、3,088点の観測、558入力と28出力のサイズとSHA-256を照合した。2実行の成果の実体43,516,757バイトをRTL9210B-CGに保存した。今回の範囲は英語の初回WASM取得を共有する同一ページの2呼び出しと、44.1 kHzでの再開。[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-shared-wasm-abort-44100.py)・[再実行のマニフェスト](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261122-b/manifest.json)
