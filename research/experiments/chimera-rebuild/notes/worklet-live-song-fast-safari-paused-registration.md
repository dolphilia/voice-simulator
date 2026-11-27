# Safariで停止中に登録した歌唱Workletの開始位置を照合する

先行試験では、Safari 18.6でContextを先に4,096フレーム以上進めて停止すると、停止中に作ったWorkletは最初の `process()` まで `currentFrame` が0だった。第2量子は停止位置に128を足した番号を返し、入力の連番PCMは最初から4量子とも連続した。今回は通常の歌唱ボタンを入口に、同じ条件を作り、歌唱の予約と出力を調べた。[時計と連番PCMの先行試験](worklet-safari-clock-at-creation.md#実測)・[事前登録](../cases/worklet-live-song-fast-safari-paused-registration.json)

## 上流と研究版の開始位置

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は、初回の `build()` でクリックの処理中にContextを再開し、Workletを登録してからコンパイル済みWASMをノードへ渡す。`playTune()` は音節、MIDI音高、拍数から歌唱計画を作る。拍の長さは `60 / bpm` 秒。`AudioEngine.schedule()` が送った相対時刻を `processor.ts` の `schedule` がWASMのレコードへ書き、`engine_schedule()` がRustへ渡す。`Engine::schedule()` は声の時計 `voice.clock` と `lead` を足した秒数だけずらして予約する。描画時は `process()` がホストの出力フレーム数を `engine_render()` へ渡し、Rustは累積フレーム `pos % 128` で内部処理の境界を求める。固定上流のテストは短音の拍位置とホストのブロック分割に対するPCMの一致を確認する。[上流の起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[ブロックのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `captureWorklet()` は登録の完了を待ち、歌唱ノードを作って出力先につなぐ。`FixedProcessor.process()` は `currentFrame` と128フレームのチャネル長を `RealtimeSpeechCapture.ready()` に渡す。`WorkletStartup` は次の予想位置を現在の番号に128を足して保持し、実測が違う場合は連続数をリセットする。8量子の連続を確認した次の位置に2,048フレームを足して歌唱を予約する。連続区間の先頭を `F` とすると、予約は `F + 8 × 128 + 2,048 = F + 3,072`。停止位置を `P` として、最初のラベルが0、次が `P + 128` なら、連続区間の先頭は `P + 128` に更新され、予約は `P + 3,200` になる。[ノード生成と接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L417)・[量子の入口](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L137)・[連続性の検査](../../../../web/prototypes/chimera-research/src/worklet-clock.ts#L1)・[歌唱予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

## 停止位置をそろえる対照

WebDriverの信頼済みクリックで通常の歌唱を開始する。採取スクリプトは合成Workletの登録要求を受けた時点で、0ゲインのオシレーターをつなぎ、Contextが4,096フレーム以上になってから停止する。オシレーターを外し、停止中に最後のモジュールまで登録する。生成前再開ではContextを再開し、停止位置から128フレーム以上進むまで待ってから、登録完了を歌唱側へ返す。接続後再開では、歌唱ノードを停止中に生成・接続し、並列観測の接続を含む同期処理の完了後にContextを再開する。計測用のフックはSafariの採取入口にあり、歌唱エンジンと予約ロジックは前回の版を実行する。[Safariの採取](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)・[状態と予約の判定](../tools/measure_worklet_safari_song_resume_order.py)・[並列観測](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs)

## 実測

Safari 18.6で、短音「Pop Dee」、240 BPM、出力48 kHz・内部96 kHz、歯フィルタ下限1,200 Hz、無音先行なしを計16試行した。Contextの停止位置は4,096〜5,120フレーム。接続後に再開した8試行すべてで最初の番号が0、第2量子が `P+128` となり、そこで連続数を数え直した。生成前に再開して時計を1量子分進めた8試行では、最初の番号が `P+128` で、その後も連続した。両条件の全16試行で歌唱を `P+3,200` フレームに予約し、その位置で最初の歌唱量子を得た。[初回の結果](../runs/worklet-live-song-fast-safari-paused-registration-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-safari-paused-registration-20261121-repeat/summary.json)

停止位置が4,096フレームの並列観測2試行を並べる。並列観測の開始から歌唱までのPCMには、接続後再開で最初の無音量子128フレームが含まれる。

| 再開する時点 | 最初の2量子の番号 | 開始待ちのコールバック | 歌唱予約 | 並列観測の先頭から歌唱までの無音 |
| --- | --- | ---: | ---: | ---: |
| ノード生成前 | 4,224、4,352 | 8回 | 7,296 | 3,072フレーム |
| ノード接続後 | 0、4,224 | 9回 | 7,296 | 3,200フレーム |

歌唱PCMの49,200フレームと状態769点、計画は全16試行でオフライン基準と一致した。並列観測8試行は、最初の2量子のラベルが歌唱側と一致した。生PCMを取得順に読むと、両条件で絶対フレームの予約位置から同じ歌唱が始まり、前後の無音と最終量子の補完80フレームも確認できた。再開後に最初の番号が0でも、並列観測上のその1量子は128個の0サンプルとして存在した。固定上流との最大絶対差は `2.757307142019272 × 10⁻³`、`10⁻⁶` を超える最初の位置は27,939フレームで、従来の歯フィルタ下限1,200 Hzの基準と同じだった。[生成前再開の並列観測](../runs/worklet-live-song-fast-safari-paused-registration-20261121-a/artifacts/observed-1-resume_before_node/output-probe.json)・[接続後再開の並列観測](../runs/worklet-live-song-fast-safari-paused-registration-20261121-a/artifacts/observed-2-resume_after_connect/output-probe.json)・[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)

クリックから歌唱先頭までの組内差（接続後再開から生成前再開を引く）は、直接出力4組で −16〜0 ms、中央値 −4 ms。並列観測4組では −11〜+31 ms、中央値 −2 msだった。クリック時間の終点はSafari 18.6のWeb Audioグラフ内で歌唱PCMを描き始めた時点とした。歌唱中にContextを停止・再開した場合、機器出力と聴感は未検証。[組ごとの時間](../runs/worklet-live-song-fast-safari-paused-registration-20261121-repeat/summary.json)

## 再現と保存先

`safaridriver` が利用可能なmacOSで研究ワークスペースから実行する。`<実行ID>` は未使用の名前。再実行は `/private/tmp` からPython、スクリプト、ケースを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 ../../.venv/bin/python \
  tools/measure_worklet_safari_song_resume_order.py <実行ID> \
  --case cases/worklet-live-song-fast-safari-paused-registration.json
```

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各回の取得判定178件が通過し、失敗・欠測は0件。予測のうち生成前再開の連続性、接続後再開の先頭0と再同期、PCM・状態の一致に関する8件を支持した。比較器の「両条件とも最初の量子から連続」という2件には反例を保存した。各回の入力275件、出力76件をサイズとSHA-256で照合し、2回分12,481,728バイトをRTL9210B-CGに保存した。固定上流のブロック長と短音の試験が各1件通過。以前のSafari登録後待機の並列観測も1試行し、448量子とWAVの一致を確認した。[初回マニフェスト](../runs/worklet-live-song-fast-safari-paused-registration-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-safari-paused-registration-20261121-repeat/manifest.json)
