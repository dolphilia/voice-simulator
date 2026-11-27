# Safariでの予備描画付き歌唱の構築と途中停止

## 構築時間と描画時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のWorkletは、`engine_schedule()` に音素ジェスチャーと先行時間を渡し、`process()` が `engine_render()` のPCMを出力する。研究版の「上流音源の比較」プリセットは、既存の歌唱入口から音源設定とスコアをWorkletへ送り、`vocal_start_score_prepared()` で予約前の描画を実行する。各出力フレームで声門、気道、出力段を進め、予備描画後の音源時計にスコアを置く。今回の48 kHzでは128フレームの出力量子は約2.667 ms。内部は96 kHzで、声門位相と面積を出力サンプル1点につき2ステップ進める。元の構築経路の数値照合はChromiumで実施済み。[上流の予約と出力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[研究版の予備描画](../crates/vocal-wasm/src/lib.rs#L270)・[ChromiumとCLIの照合](worklet-song-prepared-source.md)

歌唱の起動観測を有効にしたとき、Worklet内で `FixedVoiceEngine` の構築直前と直後のエポック時刻を `Date.now()` で採取する。その区間にはWASMインスタンス、合成器、バッファの準備と指定した予備描画が入る。主スレッドの `new AudioWorkletNode()` を挟む時間と、クリックから最初に出力するまでの時間も記録する。量子ごとの描画では、歌唱の保存フレーム数、Contextの絶対フレーム、壁時計での経過時間をすでに採取している。Context停止完了時のフレームを `P` として、これらの量子の `P−128` と `P` を照合する。[Worklet内部の構築計測](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[準備通知と主スレッドの記録](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L455)・[既存の量子採取](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)

## 事前登録

Pop Deeの2音、通常乱流、ドリフト5セント・周期ジッター0.00455・振幅シマー0.042を固定した。予備描画16,384・16,512フレームに連続と途中停止を組み合わせ、直接出力で比較する。予備描画0の直接出力を前後に置き、構築時間の対照とした。16,384フレーム条件は並列の観測ノードでも、連続と停止を各1回ずつ採る。停止要求の目標は保存開始から22,784フレームで、停止完了後に約120 ms待って再開する。二回目は試行順を反転する。[事前登録](../cases/worklet-safari-song-prepared-pause.json)

Safariの通常歌唱ボタンをWebDriverで押し、試行ごとにページとContextを初期化した。予備描画のある条件はChromiumの保存済みオフラインPCMと観測系列を比較し、0フレーム条件のPCMは同じ設定のCLIから生成する。並列ノードは既存の接続と併用し、サンプルの並びを絶対フレームで照合する。ログに使う停止操作と出力の並列観測は以前のSafari実験と同じ入口を使う。[既存の途中停止の実験](worklet-live-song-fast-safari-mid-song-pause.md)・[Safari採取器](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)・[判定器](../tools/measure_worklet_safari_song_prepared_pause.py)

## 初回の解析不合格

初回は、Chromiumのオフライン観測の先頭列 `context_frame` を実時間用の `output_frame` として読み、予備描画付きの6試行の判定が途中で止まった。Safari側の実時間列とオフライン基準列をそれぞれの書式で読み、両方の出力サンプル位置に対応させるように修正した。保存済みの初回データを修正後の読出しに通し、全8試行のPCM・停止境界と、並列2試行の出力位置を再確認してから正式に再採取した。[初回の不合格とログ](../runs/worklet-safari-song-prepared-pause-20261122-a/manifest.json)・[修正後の読出し](../tools/measure_worklet_safari_song_prepared_pause.py#L80)

## 実測

Safari 18.6の比較2回で、全16試行のPCMは各31,200サンプルが比較基準とビット一致した。予備描画0の4試行は同じ設定のCLIに、予備描画付きの12試行はChromiumに一致した。予備描画付きでは、各488点の声門位相・面積・流量・F0・放射など11系列と、歌唱計画も一致した。並列観測4試行で、歌唱開始の絶対フレームから読み出したPCMは同じ基準とビット一致した。[初回の合格結果](../runs/worklet-safari-song-prepared-pause-20261122-b/summary.json)・[順序を反転した再実行](../runs/worklet-safari-song-prepared-pause-20261122-repeat/summary.json)

停止した6試行の停止位置は出力22,784〜23,040フレーム。停止完了から再開要求までの121〜123 msでContextのフレームは同じ位置にとどまった。停止前と再開後の隣接した描画はすべて `P−128` と `P` で、壁時計上の間隔は141〜150 msだった。停止の前後を含む出力全域で、PCM・観測系列は同じ予備描画量の連続条件と一致した。[停止位置と境界のログ例](../runs/worklet-safari-song-prepared-pause-20261122-b/artifacts/direct-16384-paused/startup.json)・[並列観測のフレーム列](../runs/worklet-safari-song-prepared-pause-20261122-repeat/artifacts/observed-16384-paused/output-probe.json)

| Safariの直接出力 | 予備描画0の4試行 | 予備描画ありの8試行 |
| --- | ---: | ---: |
| Worklet内の合成器構築時間 | 3〜4 ms | 135〜142 ms |
| クリックから先頭PCMまで | 154〜177 ms | 204〜233 ms |

Worklet内の構築時間の中央値の差は最初の合格実行で135.5 ms、順序を逆にした実行で133.5 ms。主スレッドのノード生成呼び出しは全試行で0〜5 msだった。経過時間は比較対象ごとに区間が異なり、クリック後の一部の処理は構築と並行する。予備描画を含む起動コストを測るときはWorklet内の区間も記録する。[2実行の構築時刻](../runs/worklet-safari-song-prepared-pause-20261122-b/summary.json)・[反転順の時刻](../runs/worklet-safari-song-prepared-pause-20261122-repeat/summary.json)

## 再現手順

研究ワークスペースから以下の一つ目を実行した。二つ目は `/private/tmp` からPythonとスクリプトを絶対パスにして実行した。各実行はWASMを含むフロントエンドをビルドし、既存のSafari WebDriverで採取する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_prepared_pause.py worklet-safari-song-prepared-pause-20261122-b
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_prepared_pause.py worklet-safari-song-prepared-pause-20261122-repeat --reverse
```

macOS 15.6.1 arm64、Safari 18.6、Rust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4。修正後の2回は各63判定を通過し、各271入力・74出力のサイズとSHA-256を確認した。再実行ケース、PCMとWASMの18件は両実行でバイト一致した。従来の短音プリセットの直接出力を同じ採取器で再取得し、49,200サンプルの保存WAVとのバイト一致も確認した。外部ディスクRTL9210B-CGへの保存は合格2回で計8,626,556バイト、初回の解析不合格を含めて12,939,485バイト。[初回の合格記録](../runs/worklet-safari-song-prepared-pause-20261122-b/manifest.json)・[反転順の記録](../runs/worklet-safari-song-prepared-pause-20261122-repeat/manifest.json)・[従来の短音の基準](../runs/worklet-live-song-fast-safari-mid-song-pause-20261121-repeat/artifacts/direct-1-continuous/browser.wav)

次は、既知の信号を同じContextで先に鳴らした状態で、今回の予備描画を含む合成器構築を入れる。歌唱の予約と波形を固定しながら、先行信号の描画時刻とPCMの連続性への影響を確認する。
