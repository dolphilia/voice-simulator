# Safariで歌唱中の停止・再開をPCMと描画時計で照合する

前回は、停止したContextに登録した歌唱Workletの先頭番号が飛んでも、歌唱予約に再同期できることを確かめた。今回は歌唱を始めたあとに同じContextを一度停止して再開し、連続再生と比べる。オフラインの短音「Pop Dee」で2音目の母音にあたる、歌唱出力28,672フレーム（約597.3 ms）を停止要求の目標にした。この位置の前後128フレームのRMSは予備確認で0.233だった。[前回の比較](worklet-live-song-fast-safari-paused-registration.md#実測)・[事前登録](../cases/worklet-live-song-fast-safari-mid-song-pause.json)

## 上流と研究版の描画中の状態

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.start()` はすでに作成したContextを再開する。初回の `build()` は操作中の `resume()`、Workletの登録、WASMを渡すノードの生成を行う。`playTune()` は `60 / bpm` 秒を1拍として、音節と音高から歌唱計画を作る。Workletの `schedule` がWASMへ書いたジェスチャーは、Rustの `Engine::schedule()` で `voice.clock + lead` 秒だけエンジンの時計へ移される。`process()` はチャネルのフレーム数を `engine_render()` に渡し、出力PCMをコピーする。`Engine::render()` は累積フレーム `pos` を更新し、`pos % 128` で内部の更新位置を維持する。ホストのブロック長を変える上流テストはPCMのビット一致を、短音テストは母音と拍の時刻を検査する。[起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[ブロック長のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

研究版の `FixedProcessor.process()` は予約位置で合成を開始し、Contextの `currentFrame` を次の予想位置と照合する。WASMの描画に渡す位置と観測の刻みは、同じエンジンが保持する累積出力数 `rendered` に基づく。`RealtimeSpeechCapture.record()` は量子のPCMをこの出力位置へコピーし、Contextフレーム、量子長、累積出力数、描画処理時間、最初の歌唱量子からの壁時計経過を別の系列に保存する。停止中にWASMへ新たな描画が要求されず、再開時も既存ノードと状態を引き継ぐなら、PCMと内部状態は連続再生に一致すると予測した。[研究版の描画](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L137)・[出力と時計の記録](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L48)

## 比較条件

Safari 18.6の通常歌唱ボタンをWebDriverで操作した。両条件とも240 BPM、出力48 kHz・内部96 kHz、歯フィルタ下限1,200 Hz、無音先行なし。テスト用の採取コードで両条件とも既存の `scheduled` メッセージを有効にし、歌唱予約に28,672フレームを足した位置まで待つ。停止条件だけそこで `suspend()` を要求し、完了から120 msのタイマーで `resume()` を呼ぶ。ノード、WASM、譜面、並列観測の接続は継続する。Contextの停止位置 `P`、再開要求時の位置、描画コールバックの前後の時刻を採り、出力番号 `P − 歌唱予約` の前後256フレームを生PCMと照合する。[Safariの採取](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)・[比較器](../tools/measure_worklet_safari_song_resume_order.py)・[並列観測](../../../../web/prototypes/chimera-research/tools/song-output-probe-worklet.js)

## 実測

初回と再実行の計16試行で、停止した8試行は出力28,672フレームで6件、28,800フレームで2件停止した。再開要求まで全件でContextフレームは `P` に留まった。停止前最後の描画は `P−128`、再開後の最初は `P` だった。停止・再開の間をまたぐコールバック間隔は136〜149 ms、中央値139 ms。連続再生の同じ出力位置の間隔は2〜3 msで、全区間の最大でも各試行4〜6 msだった。アプリが停止完了から再開要求まで待った時間は120〜122 msだった。[初回の結果](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-repeat/summary.json)

全16試行でPCM49,200フレーム、声門・調音などの観測769点、歌唱計画がオフライン基準と一致した。並列観測の8試行でも、歌唱開始をグラフの絶対位置から求めて全PCMをビット照合した。停止付きの並列観測4試行は `P` の前後256フレームのPCMを個別に切り出し、サンプルの連続性を確認した。28,672フレームで停止した6試行では、停止直前に最も近い観測が28,671、再開後最初の観測が28,735だった。たとえば同じ2点の声門面積は0.015084から0.095079 cm²に変化し、連続再生とオフラインも同値だった。固定上流のPCMとの最大差は `2.757307142019272 × 10⁻³`、`10⁻⁶` を超えた最初の位置は27,939フレームで、歯フィルタ下限1,200 Hzの既存基準と一致した。[停止前後を含む生PCMの番号](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-repeat/artifacts/observed-1-paused/output-probe.json)・[観測値](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-repeat/artifacts/observed-1-paused/browser.json)・[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)

最初の歌唱前のフレーム番号が両条件で連続するという共通判定には反例があった。今回の停止を適用する前に現れた番号の飛びで、歌唱途中の停止位置におけるコールバックは連続した。測定はWeb Audioグラフまで。機器から出る音、録画済みメディアの間隔、聴感は未検証。[初回の番号と予測](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-a/summary.json)

## 再現と保存場所

`safaridriver` が利用可能なmacOSで研究ワークスペースから実行する。`<実行ID>` は未使用の名前。再実行は `/private/tmp` からPython、スクリプト、ケースを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 ../../.venv/bin/python \
  tools/measure_worklet_safari_song_resume_order.py <実行ID> \
  --case cases/worklet-live-song-fast-safari-mid-song-pause.json
```

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各回の取得判定182件が通過し、失敗・欠測は0件だった。歌唱途中の停止・描画間隔と音声・状態の予測8件を支持し、歌唱前の初回番号の連続性に関する2件は反例を保存した。各回の入力275件と出力76件をサイズとSHA-256で照合し、2回分12,469,910バイトをRTL9210B-CGに保存した。固定上流のホストブロック長と短音の拍位置の試験が各1件通過。以前の停止中登録の条件も1試行し、先頭0からの再同期と並列観測448量子、WAV一致を再確認した。[初回マニフェスト](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-repeat/manifest.json)
