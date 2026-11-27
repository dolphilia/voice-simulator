# Safariで歌唱Workletの登録とAudioContext再開の順序を比べる

ChromiumとFirefoxでは、合成Workletを停止中に登録した場合に無音先行を省いても、歌唱開始が連続し、PCMがオフライン基準に一致した。今回のmacOS Safariでは先行枝を両条件で省き、クリックから直接 `resume()` を要求する経路と、停止中にWorkletを登録してから `resume()` を要求する経路を比べる。[事前登録](../cases/worklet-live-song-fast-safari-resume-order.json)・[Firefoxの計測](worklet-live-song-fast-app-silent-lead-preregister-firefox.md)

## 上流の起動と歌唱の時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` はContextが既にあれば再開し、初回は `build()` でContextを作る。`build()` は操作中に `resume()` を要求し、音声Workletを `addModule()` で登録して、コンパイル済みWASMをノードへ渡す。上流のコメントは、iOS Safariで非同期の待ちの後に `resume()` を呼ぶ場合に停止状態が続く挙動を記している。今回はmacOSに搭載されたSafari 18.6を対象にする。[固定上流の起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)

`playTune()` は準備が済んでから音節、音高（MIDI番号）、長さ（拍数）を歌唱ジェスチャーへ変換する。拍の長さは `60 / bpm` 秒。`AudioEngine.schedule()` は歌唱計画、置換フラグと識別子をWorkletへ送る。WorkletはWASMの領域へジェスチャーを書き、WASMの `engine_schedule()` を呼ぶ。Rustの `Engine::schedule()` は `voice.clock + lead` 秒を相対の開始・終了時刻に足して、エンジン上に予約する。`process()` はホストから求められたサンプル数を `engine_render()` に渡し、得たfloat32 PCMをチャネルにコピーする。`Engine::render()` は累積フレーム `pos` の剰余 `pos % 128` を使い、呼び出しをまたいで内部の刻みを維持する。上流テストは短音でも母音の開始を拍にそろえられることと、別のブロック長で同じビット列が出ることを検査する。[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジンの予約と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[ブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## macOSでの観測方法

`safaridriver` のローカルWebDriverセッションを使い、Safari本体で「実時間で歌唱」を要素クリックする。クリックの `isTrusted`、`navigator.userActivation.isActive`、Contextの状態、`suspend()`・`addModule()`・`resume()` の要求とPromiseの決着を記録する。観測は元のPromiseをそのまま返す。通常の歌唱経路は `withRealtimeContext()` がクリック中に再開を要求し、譜面の準備後にWorkletを登録する。試験経路の `songRegisterBeforeResume=1` は停止完了、合成用Workletの登録完了、再開の順で進む。観測用Workletがある場合は、合成用モジュールを登録した直後に同じContextへ登録する。歌唱後に画面の保存リンクと同じBlobからWAV・観測JSON・再実行ケースを読み出す。[AppleのWebDriver手順](https://developer.apple.com/documentation/webkit/testing-with-webdriver-in-safari)・[画面の起動経路](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L167)・[Safariの取得スクリプト](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)

短音「Pop Dee」は240 BPM、48 kHz出力・96 kHz内部、歯フィルタ下限1,200 Hzとした。128フレームのコールバックが途切れずに8量子進み、さらに2,048フレーム待つと、歌唱開始は最初から3,072フレーム後になる。歌唱中は絶対フレームと累積描画量を比べ、並列観測で開始位置とPCMを取り出す。今回の許容差・基準は以前の歯フィルタ条件と共通とし、録音49,200フレームと観測769点をオフライン基準に照合する。[研究版の開始判定](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)・[並列観測](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs#L1)・[比較用のオフライン実行](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)

## 取得時の失敗と修正

初回8試行はページ遷移直後に入力欄を探し、Reactが歌唱パネルを表示する前に失敗した。歌唱ボタンの存在をWebDriverで待つように変更し、単発の通常順で保存リンクのWAVがオフライン基準と一致することを確認した。取得の失敗と入力は初回マニフェストに残した。[初回のログ](../runs/worklet-live-song-fast-safari-resume-order-20261121-a/artifacts/cargo.log)・[通常順の予備試行](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-safari-song-pilot-Io963e/startup.json)

修正後の8試行はすべて歌唱を完了した。再開後登録の並列観測1試行では計測用モジュールの `addModule()` 要求が無く、Contextは歌唱終了の54,400フレームで閉じた。歌唱ノードのWAVと起動の記録は保存できていた。観測スクリプトは `AudioWorklet` のJavaScriptラッパーに `addModule()` を置くため、ラッパーへの参照をContext側に持たせ、観測用の差し替えを維持するようにした。ラッパーが回収された瞬間は計測していない。並列観測に失敗した試行でも歌唱WAVと観測JSONの判定を残せるようにした。歌唱の入力、予約式、合否基準は事前登録と同じものを使った。[欠測した試行](../runs/worklet-live-song-fast-safari-resume-order-20261121-b/artifacts/observed-1-running/startup.json)・[取得のログ](../runs/worklet-live-song-fast-safari-resume-order-20261121-b/artifacts/cargo.log)・[並列観測のラッパー](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs)

## 実測

修正後は2回、各8試行で、両方の登録順とも `addModule()` と `resume()` が完了した。停止中に登録する場合も、クリック時と再開要求時の `navigator.userActivation.isActive` は全試行で `true` だった。両経路で初回から番号が連続するという予測には反例が出た。再開後登録は直接出力4/4試行と並列観測3/4試行で、歌唱Workletの最初の番号が0、次の番号が1,664〜2,176になった。1量子分の128フレームを引くと、初回の番号から連続区間までの間に1,536〜2,048フレーム分の番号が現れなかった。並列観測の3試行では観測ノードの番号列も同じ位置で飛んだ。停止中の登録は直接出力と並列観測の計8試行で、すべて最初の番号から128フレーム刻みで進んだ。[修正後の結果](../runs/worklet-live-song-fast-safari-resume-order-20261121-c/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-safari-resume-order-20261121-repeat/summary.json)

| クリックから歌唱先頭の描画まで | 停止中の登録から再開後登録を引いた組内差の中央値 | 4組の範囲 |
| --- | ---: | ---: |
| 直接出力 | −25.5 ms | −31〜−18 ms |
| 並列観測 | −18 ms | −19〜−16 ms |

全16試行で、歌唱は連続区間の先頭から3,072フレーム後に始まった。保存された49,200フレームのPCMはビット一致し、観測769点と歌唱計画もオフライン基準と一致した。並列観測の8試行では、歌唱位置の生PCM、前後の無音、最終量子の補完80フレームを標準ライブラリで再照合した。固定上流PCMとの最大絶対差は `2.757307142019272 × 10⁻³` で、差が `10⁻⁶` を超える最初の位置は27,939フレーム。歯フィルタ下限1,200 Hzの基準と同じだった。Safari内部の描画呼び出しの回数や機器出力は計測していない。番号の飛びが実描画の欠落を伴うかと、iOS Safariで同じ順序が成立するかは未検証。[並列観測の番号列の例](../runs/worklet-live-song-fast-safari-resume-order-20261121-c/artifacts/observed-1-running/output-probe.json)・[固定上流の保存基準](../runs/song-voice-fast-constriction-source-20261121-repeat/manifest.json)

## 再現と保存先

`safaridriver` の利用が許可済みのmacOSで、研究ワークスペースから実行する。`<実行ID>` は未使用のIDを指定する。2回目は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。[macOSのWebDriver設定](https://developer.apple.com/documentation/safari-developer-tools/macos-enabling-webdriver)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 ../../.venv/bin/python \
  tools/measure_worklet_safari_song_resume_order.py <実行ID>
```

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。修正後の各回で取得判定166件が通過した。予測6件のうち登録順の完了とPCM・状態の4件を支持し、初回番号からの連続性の2件には反例が出た。失敗を含む4実行で各回の入力271件と出力28・73・76・76件のサイズとSHA-256を照合した。4実行の大容量成果19,933,954バイトをRTL9210B-CGに保存した。固定上流の短音とホストブロック長のテストは各1件が通過。変更した観測スクリプトをChromiumとFirefoxでも各1試行し、448量子の採取とWAVの一致を確認した。[修正後マニフェスト](../runs/worklet-live-song-fast-safari-resume-order-20261121-c/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-safari-resume-order-20261121-repeat/manifest.json)
