# 予定ホスト時刻までの残り時間でFirefoxの時刻の飛びを判別する

512フレームの既知PCM実験では、cubebの処理時間だけで比較するより、予定ホスト時刻までの返却時の残り時間で比較した方が、飛びのある群と連続する群の重なりが小さかった。今回は48 kHz・256フレームの既知PCMで判定範囲を決め、保存済みのFirefoxで歌唱ノードを構築した要求へ適用する。[512フレームの探索](cubeb-output-callback-deadline-sweep-512.md#予定ホスト時刻と返却時刻の差)・[事前登録](../cases/worklet-live-song-cubeb-return-time.json)

## 描画と時計の読解

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` は、生成したAudioContextにモジュールを登録し、コンパイル済みWASMをWorkletへ渡す。`ChimeraProcessor.process()` は出力チャンネルのフレーム数を `engine_render()` に渡し、Rustの `Engine::render()` が共有バッファにfloat32 PCMを書き込む。Rustは累積出力位置 `pos` の128フレーム境界で拍を更新し、境界まで描いた分だけ `pos` を進める。`output_does_not_depend_on_the_host_block_size()` は操作位置を同じフレームに固定して、ブロックの分割を変えた出力をビット比較する。[AudioEngine.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASMのABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[エンジンのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

計測したGecko `fdd757a2e09c9471cddf383e64e631e4ce178499` の `AudioCallbackDriver::DataCallback()` は、出力バッファの要求長からグラフを進める先をWeb Audioのブロック境界へ丸め、`Graph()->OneIteration()` を呼ぶ。その実測区間からノード構築を含む要求を見つける。固定版cubeb `840f69c1b3f95accd582555e10abcef8ee67514b` の `audiounit_output_callback()` は機器が渡すフレーム数と `AudioTimeStamp` を受ける。パッチはコールバック入口で `entered` を採り、データ分岐でPCMをコピーした後の返却前に `returned` を採る。`host_time` は機器が渡した予定ホスト時刻、`sample_time` は機器の予定サンプル位置である。予定ホスト時刻との差は測定した返却位置を表し、機器内部で必要とされる返却期限の位置は別に検証する必要がある。[GraphDriver.cpp](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/GraphDriver.cpp)・[同版cubebの読解](cubeb-output-callback-probe.md#読解)・[計測パッチ](../tools/chimera-cubeb-output-snapshot.patch)

## 比較条件

予定時間を `H`、入口と返却前の時刻を `E` と `R`、1刻みの長さをmsで `k` とする。従来の処理時間は `(R − E) × k`、返却時の残り時間は `(H − R) × k`。時刻の飛びは、次の `sample_time` から今回の `sample_time` と256フレームを引いた値で求める。保存された前後8要求・4,352フレームを先行音の逆相の連番で照合し、グラフの構築位置を同じ出力要求に対応づける。履歴の計時換算をマニフェストで照合した要約から取得する。既知PCMの2実行の80試行だけを使って各群の端を決め、Firefoxにはその値を固定して適用する。[出力要求の照合](../tools/inspect_firefox_cubeb_output.py)・[再解析の入口](../tools/measure_firefox_cubeb_return_time.py)

## 実測

既知PCMの80試行を再計算すると、飛んだ45試行の残り時間の最大は1.826250 ms、連続した35試行の最小は1.829500 msだった。Firefoxの9実行から採取を無効にした8試行を除いた34試行を再解析した。構築の要求の次に飛んだ12試行は残り時間が−0.564125〜1.804750 ms、連続した22試行は1.959042〜5.574542 msで、基準で決めた範囲にそれぞれ入った。[初回の結果](../runs/worklet-live-song-cubeb-return-time-20261121-a/summary.json)・[別ディレクトリからの再実行](../runs/worklet-live-song-cubeb-return-time-20261121-repeat/summary.json)

| 観測区間と判定方法 | 正答 | 誤判定 | 保留 |
| --- | ---: | ---: | ---: |
| 構築を含む要求、処理時間と名目周期 | 32 | 2 | 0 |
| 構築を含む要求、返却時の残り時間 | 34 | 0 | 0 |
| 前後の510区間、処理時間と名目周期 | 510 | 0 | 0 |
| 前後の510区間、返却時の残り時間 | 510 | 0 | 0 |

名目周期だけで見落としたのは、最初の64フレームの事前描画が構築と同じ要求に入った2回だった。処理時間は5.049375 msと5.283083 ms、返却時の残りはそれぞれ1.804750 msと1.569750 msだった。どちらも次の機器予定時刻で256フレームの飛びが最初に現れ、cubebが返した先行音の連番には差がなかった。分割の開始を2量子遅らせた4回では時刻の飛びがなかった。34試行すべてで前後4,352フレームの位置を既存結果と再照合し、別計算で左右の差から連番も検査した。[分割の計測](worklet-live-song-deferred-split-preparation.md#名目予算の直前で発生した時刻の飛び)

初回と `/private/tmp` からの再実行はそれぞれ115判定を通過し、要約がバイト一致した。新規に未準備・構築中の一括処理・無音中の分割処理を各2回採った回帰確認は109判定と固定上流の17テストを通過した。追加6試行では時刻が飛んだ2回と連続した4回を両方の方法が同じように判別した。3実行で入力1,541件と出力97件のサイズとSHA-256を照合した。既存の生ファイルは参照し、新規採取の実体約25.34 MBをRTL9210B-CGに保存した。[通常の入口からの回帰確認](../runs/worklet-live-song-split-preparation-20261121-return-time-regression/manifest.json)

観測は同じ環境・48 kHz・256フレームの先行音と `Pop Dee` に対応する。機器から実際に出た音の連続性はプロセスタップの校正待ち。次は短い音符で子音が詰まる既存ケースで、歌唱開始前までの返却位置も同じ方法で確認する。[短い歌唱のケース](../cases/song-voice-fast.json)・[タップの記録](worklet-live-song-paired-output.md)

## 再現

研究ワークスペースから実行する。`<実行ID>` は未使用の名前に置き換える。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=8000000 ../../.venv/bin/python \
  tools/measure_firefox_cubeb_return_time.py <実行ID>
```
