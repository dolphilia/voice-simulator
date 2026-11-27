# SafariでWorkletの作成時と再開後の時計を分けて測る

歌唱画面の前回比較では、Safari 18.6で再開後の登録とノード生成が同じContextフレームになると、最初の `currentFrame` が0、次が1,664〜1,920になった。今回は歌唱の譜面やWASMの時間を介さず、時計を先に進めたContextを停止してからWorkletを登録し、モジュール評価、コンストラクター、最初の4回の描画を観測する。[歌唱画面の先行比較](worklet-live-song-fast-safari-node-after-registration.md#比較と結果)・[事前登録](../cases/worklet-safari-clock-at-creation.json)

## 上流の更新順と回帰テスト

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は初回に `build()` を呼び、操作中の `resume()` 要求、`addModule()` の完了、WASMを渡すノード生成の順で進む。`AudioEngine.schedule()` で送った相対時刻のジェスチャーは、WorkletでWASMのレコードに入り、Rustの `Engine::schedule()` が `voice.clock + lead` 秒を加えて予約する。`process()` は `engine_render()` に出力フレーム数を渡し、返るfloat32 PCMを出力へコピーする。`Engine::render()` の `pos` は処理したフレーム数で増え、`pos % 128` で内部更新の境界を管理する。上流のブロック長テストはホストの分割に依存せず同じPCMが得られること、短音テストは母音開始が拍に収まることを確認する。これらのエンジン内部のフレームは、今回測るWeb AudioのContextフレームと単位は同じでも、時計の起点は別になる。[起動と予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[ブロック長のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

公開WebKitの修正 `a0b5d79d7218` は、Workletグローバルの `m_currentFrame` の初期値をContextのサンプル位置から設定する。修正前は0で出発し、描画後の `handlePostRenderTasks()` で更新される。公開WebKitの `AudioDestinationNode::render()` はグラフを処理し、累積サンプル位置を描画フレーム数だけ進めてからWorklet側へ渡す。公開の回帰テストはオシレーターで時刻を進めて停止し、Workletのコンストラクターが送る `currentFrame` を、停止中の `currentTime × sampleRate` の切り捨て値と比べる。今回の計測はモジュール評価時と、再開後の入力付き `process()` を追加した。試験機はmacOS搭載のSafari 18.6で、公開修正を含むビルドとの比較は行っていない。[修正コミット](https://github.com/WebKit/WebKit/commit/a0b5d79d7218)・[描画後に時計を渡す処理](https://github.com/WebKit/WebKit/blob/0eef7560baac704b60f3f118665f47a7711cd335/Source/WebCore/Modules/webaudio/AudioDestinationNode.cpp#L104)・[公開の回帰テスト](https://github.com/WebKit/WebKit/blob/a0b5d79d7218/LayoutTests/imported/w3c/web-platform-tests/webaudio/the-audio-api/the-audioworklet-interface/audioworkletglobalscope-creation-time.https.html)

## 採取条件

SafariのWebDriverでテストページを開き、各試行で新しい48 kHzのContextを作る。準備ボタンで、未描画のまま停止する条件と、0ゲインのオシレーターで4,096フレーム以上進めて停止する条件を作る。停止時刻の `round(currentTime × sampleRate)` を `P` とする。停止中に同じモジュールを評価し、Workletを構築する。コンストラクターから番号を受信した後で、入力に `(i+1)/1024` の512サンプルを入れたAudioBufferSourceをつなぎ、再開ボタンを押す。1量子は128フレーム。Workletは最初から4回の `process()` の番号と全入力サンプルを記録し、全量子の出力を0にする。番号から計算するフレーム位置と入力PCMの連続性は別々に判定できる。[Safariの取得スクリプト](../../../../web/prototypes/chimera-research/tools/capture-safari-worklet-creation-clock.mjs)・[描画の観測点](../../../../web/prototypes/chimera-research/tools/worklet-creation-clock-processor.js)・[照合スクリプト](../tools/measure_worklet_safari_clock_at_creation.py)

## 実測

初回と再実行で8試行ずつ計16試行を取得した。時計を先に進めた8試行の停止位置 `P` は4,096フレームが5件、4,224フレームが3件。停止完了から再開要求まで `P` は一定だった。モジュール評価時とコンストラクターの `currentFrame` はどちらの条件も全試行で0だった。先に進めた条件では、停止中のContextとの不一致がモジュール評価時から観測された。[初回の結果](../runs/worklet-safari-clock-at-creation-20261121-a/summary.json)・[再実行の結果](../runs/worklet-safari-clock-at-creation-20261121-repeat/summary.json)

| 停止したContextの位置 `P` | モジュール評価時 | コンストラクター | 再開後4回の `process()` | 試行数 |
| ---: | ---: | ---: | --- | ---: |
| 0 | 0 | 0 | 0、128、256、384 | 8 |
| 4,096 | 0 | 0 | 0、4,224、4,352、4,480 | 5 |
| 4,224 | 0 | 0 | 0、4,352、4,480、4,608 | 3 |

各試行で、最初の128サンプルには `1/1024` から `128/1024`、次の128サンプルには `129/1024` から `256/1024` が届いた。第4量子の末尾は `512/1024`。独立に有理数とfloat32で計算した8,192点が全件一致した。先に進めた条件では番号に `P` フレーム分の不連続が見えたが、採取した入力の4量子はサンプルの欠落・重複を生じずに届いた。最初の `process()` まで初期値0が残り、その描画の後でContextの進行がWorkletの時計に反映される、という公開コードの更新順と整合する。歌唱時のすべてのタイミングや機器出力で同じ結論が成立するかは未検証。[先に進めた試行の生記録](../runs/worklet-safari-clock-at-creation-20261121-repeat/artifacts/1-advanced.json)・[WebKitの描画処理](https://github.com/WebKit/WebKit/blob/0eef7560baac704b60f3f118665f47a7711cd335/Source/WebCore/Modules/webaudio/AudioDestinationNode.cpp#L104)

## 再現と保存先

`safaridriver` が許可済みのmacOSで、研究ワークスペースから実行する。`<実行ID>` は未使用の名前。2回目は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1000000 ../../.venv/bin/python \
  tools/measure_worklet_safari_clock_at_creation.py <実行ID>
```

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Python 3.14.4。各回で取得64件を通過した。時計、入力連番、対照に関する7項目は一致し、公開の回帰テストと同じ「先に進めたContextのコンストラクター位置がContextと一致する」という項目だけが両回で不一致となった。失敗・欠測は0件。各回の入力10件・出力11件のサイズとSHA-256を照合し、2回分219,847バイトをRTL9210B-CGに保存した。固定CHIMERAのブロック長と短音の上流テストが各1件通過した。抽出して共通化したSafariのWebDriver処理で歌唱画面の計測も再実行し、並列観測448量子とオフライン基準に一致するWAVを確認した。[初回マニフェスト](../runs/worklet-safari-clock-at-creation-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-safari-clock-at-creation-20261121-repeat/manifest.json)
