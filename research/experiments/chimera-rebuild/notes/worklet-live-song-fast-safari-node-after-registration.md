# Safariで登録完了から歌唱Workletノードを作るまでの間隔を比べる

前回はSafari 18.6で、Context再開後に登録すると8試行中7試行で先頭のフレーム番号が飛んだ。停止中に登録した8試行は連続した。今回はContextを操作中に再開してから登録する順にそろえ、最後のモジュール登録が済んだ時点のContextフレームから、128フレーム以上進むまで待つ条件を加えた。[前回の実験](worklet-live-song-fast-safari-resume-order.md#実測)・[事前登録](../cases/worklet-live-song-fast-safari-node-after-registration.json)

## 読解

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では `AudioEngine.start()` が初回に `build()` を呼び、操作中に `resume()` を要求する。`addModule()` が完了すると、コンパイル済みWASMを渡してノードを作る。`playTune()` は音高、拍数、音節からジェスチャーを作り、`60 / bpm` 秒を1拍として時刻を組む。`AudioEngine.schedule()` が計画をWorkletへ送ると、`processor.ts` はレコードをWASMに書く。`engine_schedule()` が読み戻し、Rustの `Engine::schedule()` は `voice.clock + lead` 秒を足してエンジン上に予約する。Workletの `process()` は出力チャネルのフレーム数を `engine_render()` へ渡し、返るfloat32 PCMをコピーする。Rustの `Engine::render()` は累積フレーム `pos` を持ち、`pos % 128` によって呼び出しをまたいで内部更新の境界を保つ。上流の短音テストは母音開始を拍と照合し、ホストブロック長のテストは異なる長さでもPCMがビット一致することを確かめる。[上流の起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[譜面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[ブロック長のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版では `captureWorklet()` が登録Promiseを待ってから `AudioWorkletNode` を作り、出力先につなぐ。`FixedProcessor.process()` はWorkletの `currentFrame` を `RealtimeSpeechCapture.ready()` に渡す。`WorkletStartup.ready()` は128フレーム刻みが崩れると連続回数を数え直す。連続8量子の次の位置に待ち2,048フレームを足した値が歌唱予約になり、連続区間の先頭から `8 × 128 + 2,048 = 3,072` フレームとなる。起動トレースを有効にした試行では、歌唱ノードが受けた第2量子の番号も直接記録するようにした。[ノードの生成と接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L417)・[量子の入口](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L137)・[先頭の記録と予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)・[連続性の検査](../../../../web/prototypes/chimera-research/src/worklet-clock.ts#L1)

公開WebKitの `a0b5d79d7218` は、Workletのグローバルな `m_currentFrame` の初期値を0からContextの現在のサンプル位置へ変更している。更新処理は固定して読んだ公開版 `0eef7560baac` の `AudioDestinationNode::render()` で、グラフを描画した後に累積サンプル位置を進め、`AudioWorkletGlobalScope::handlePostRenderTasks()` に渡す。公開の回帰テストは、先にオシレーターで時計を進めてContextを停止し、Workletノードのコンストラクター側で読んだ番号を、停止時のContext時刻から計算した番号と照合する。今回のSafari 18.6で観測した先頭0と、描画後に現在位置へ追いつく挙動は、公開の修正前の実装と整合する。実験したSafariのバイナリの内部状態は直接採取していない。[WebKitの変更](https://github.com/WebKit/WebKit/commit/a0b5d79d7218)・[描画後の時計の更新](https://github.com/WebKit/WebKit/blob/0eef7560baac704b60f3f118665f47a7711cd335/Source/WebCore/Modules/webaudio/AudioDestinationNode.cpp#L104)・[回帰テスト](https://github.com/WebKit/WebKit/blob/a0b5d79d7218/LayoutTests/imported/w3c/web-platform-tests/webaudio/the-audio-api/the-audioworklet-interface/audioworkletglobalscope-creation-time.https.html)

## 比較と結果

Safariで通常の歌唱ボタンを押し、短音「Pop Dee」、240 BPM、出力48 kHz・内部96 kHz、歯フィルタ下限1,200 Hzを生成した。直接出力の最後の登録は合成用モジュール、並列観測では観測用モジュール。比較用の取得スクリプトで、最後のネイティブ `addModule()` の解決後に `round(currentTime × sampleRate)` が128フレーム以上進むまで待ってから、登録完了をアプリに返す。タイマーの間隔により、その時点で128フレームを超えて進む場合も実測値を保存する。通常条件では元の登録Promiseを返す。[Safariの取得スクリプト](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)・[比較器](../tools/measure_worklet_safari_song_resume_order.py)

2回の実行で計16試行を取得した。追加待機なしの8試行中7試行で、最後の登録完了とノード生成のContextフレームが同じだった。この7試行では、Workletの最初の番号が0、次が1,664〜1,920だった。追加待機なしでも1試行は生成までに128フレーム進み、最初から128刻みになった。待機を指定した8試行ではContextが128フレーム進んだものが5件、256フレーム進んだものが3件で、全件で最初の2量子の差は128だった。並列観測8試行の最初の2値は歌唱Worklet側と一致した。登録完了とノード生成の間に少なくとも1量子分の進行が記録された全9試行で、番号の飛びは0だった。[初回の結果](../runs/worklet-live-song-fast-safari-node-after-registration-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-safari-node-after-registration-20261121-repeat/summary.json)

待機自体の実測は10〜27 ms。クリックから歌唱先頭までの組内差は待機ありから通常を引いて、直接出力4組で −5〜+9 ms、並列観測4組で −6〜+2 ms。両方の中央値は −2.5 msで、直接出力の実行別中央値は初回 +3 ms、再実行 −3.5 msだった。直接出力では最後の登録解決から待機の終了までの中央値が17.5 ms、そこから歌唱先頭までは66 msだった。追加待機なしでは最後の登録解決から歌唱先頭までの中央値が83 msだった。今回の少数試行ではクリックからの短縮を再現条件に含めていない。[組内差とタイムライン](../runs/worklet-live-song-fast-safari-node-after-registration-20261121-repeat/summary.json)

全試行で連続区間の先頭から3,072フレーム後に歌唱を始め、PCM49,200フレームと状態769点、計画はオフライン基準と一致した。並列観測8試行では生PCMを予約位置から独立に切り出し、歌唱前後の無音と末尾80フレームの補完を照合した。固定上流との差は最大 `2.757307142019272 × 10⁻³`、`10⁻⁶` を超えた最初の箇所は27,939フレームで、従来の歯フィルタ下限1,200 Hzの基準と一致した。Safari内部の物理的なコールバック数、iOS・修正後のWebKitでの挙動、機器出力と聴感は未検証。[並列観測の例](../runs/worklet-live-song-fast-safari-node-after-registration-20261121-repeat/artifacts/observed-2-immediate/output-probe.json)・[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)

## 再現と保存先

`safaridriver` が利用可能なmacOSで研究ワークスペースから実行する。`<実行ID>` は未使用の名前。再実行は `/private/tmp` からPython、スクリプト、ケースを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 ../../.venv/bin/python \
  tools/measure_worklet_safari_song_resume_order.py <実行ID> \
  --case cases/worklet-live-song-fast-safari-node-after-registration.json
```

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各回取得判定186件が通過し、失敗と欠測は0だった。待機で飛びが消えること、通常経路で飛びを再現すること、PCM・状態の一致に関する6件の予測を支持し、両条件が初回番号から連続するという2件には反例を保存した。各回の入力274件・出力76件のサイズとSHA-256を照合し、大容量成果2回分12,447,622バイトをRTL9210B-CGに保存した。上流の短音とホストブロック長の試験は各1件通過した。従来の停止中登録の並列観測も1試行再確認し、保存WAVの一致と448量子の取得を確認した。[初回マニフェスト](../runs/worklet-live-song-fast-safari-node-after-registration-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-safari-node-after-registration-20261121-repeat/manifest.json)
