# 研究版ブラウザ歌唱の予約前描画と音源設定

## 予約と描画の順序

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の歌唱では、Workletの `engine_schedule()` が現在のエンジン時計を基準にジェスチャーを予約する。予約時点まで進んだ声門、気道、間引き器と出力段の状態が、予約後の `engine_render()` の音に引き継がれる。ブロック長を変えても処理結果が同じになることは、上流の `output_does_not_depend_on_the_host_block_size` で検証している。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[エンジンの予約と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の歌唱画面に「上流音源の比較」プリセットを追加した。基準F0は110 Hz、ドリフト5セント、周期ジッター0.00455、振幅シマー0.042。画面で予約前の描画フレーム数と出力終了時刻を指定できる。歌詞とMIDIの既存プランナーから受け取った調音スコアを、オフライン・実時間の両方で `FixedVoiceEngine` に渡す。予約用の予備描画は音源の立ち上げ時に実行する。[歌唱画面のプリセット](../../../../web/prototypes/chimera-research/src/main.tsx#L666)・[既存の歌唱プランナーとの接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L380)・[ホストからのWASM呼び出し](../crates/vocal-wasm/host/fixed-voice.ts#L265)

`vocal_start_score_prepared()` は体型・呼気・声門変調を先に設定し、同じ声道と出力段で指定フレーム数を描画する。出力1フレームで96 kHzの内部2ステップを進める。声門の位相は内部ステップごとに `F0 / 内部レート / 周期倍率` 周期進み、周期境界で振幅倍率を更新する。声門面積（cm²）と流量（cm³/s）から得た放射差分（cm³/s²）が出力段に届く。予備描画後の内部時計をジェスチャーの開始・終了（秒）へ足してからスコアを置き、保存PCMのフレーム番号は0から数える。画面の再実行ケースは、予約前のフレーム数・出力終了・3種の音源設定を含む。[WASMの予備描画と相対時刻](../crates/vocal-wasm/src/lib.rs#L270)・[出力の観測](../crates/vocal-wasm/src/lib.rs#L876)・[CLIの予備描画](../crates/vocal-cli/src/timing_case/speech_voice.rs#L652)・[保存ケースの例](../runs/worklet-song-prepared-source-20261122-a/artifacts/frame-16384-noise-1-offline-case.json)

## 比較と実測

事前登録では、240 BPMの「Pop Dee」2音、男声、48 kHz出力を使用した。予約前に16,384または16,512フレームを描画し、乱流係数0・1の4条件を既存の「歌唱をレンダー」と「実時間で歌唱」の両方に通した。予約直後から先行区間1,440点を含む31,200点を、前回のCLI入力・PCM・声門系列と照合した。サンプルレート、整数サンプルの音素境界、128フレームのWorklet描画、線形メモリからの観測時刻を確認した。[事前登録](../cases/worklet-song-prepared-source.json)・[計測器](../tools/measure_worklet_song_prepared_source.py)・[CLI基準](song-voice-schedule-default-source.md)

Chromium 157.0.8103.79の各実行で、オフライン・実時間の計8試行がすべてCLIの31,200サンプルとビット一致した。各488観測点で、位相、面積、流量、F0、口端最小断面、放射を含む11系列はCLIと数値で一致。4条件の画面から保存したケースをCLIで再描画したWAVも以前のCLIとバイト一致した。実時間側は各244回の描画でContextのフレーム番号が連続した。[結果要約](../runs/worklet-song-prepared-source-20261122-a/summary.json)・[実時間の観測](../runs/worklet-song-prepared-source-20261122-a/artifacts/frame-16384-noise-1-realtime.json)

| 予約前描画を128フレーム増やした対照 | 固定上流ネイティブ | CLI・Chromiumのオフライン・実時間 |
| --- | ---: | ---: |
| 通常乱流でPCM差が10⁻⁶を超える位置 | 14,330 | 14,330 |
| 乱流注入量0でPCM差が10⁻⁶を超える位置 | 20,903 | 20,903 |

位置は譜面時刻0から数えた出力サンプル。各予約位置の固定上流とのPCMの最大差は、4条件を通じて2.91×10⁻¹¹だった。最初のビット差は既存CLIと同じ11,692サンプルで、条件ごとに4〜9点の差が残った。以前のCLI比較では、そのPCM差より早く11,104サンプルの放射差分に微小差が見えていた。[今回の要約](../runs/worklet-song-prepared-source-20261122-a/summary.json)・[以前の放射観測](song-voice-schedule-default-source.md#実測)

## 再現手順

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_song_prepared_source.py worklet-song-prepared-source-20261122-a
```

初回は研究ワークスペースから、再実行は `/private/tmp` から同じPythonとスクリプトを絶対パスで実行した。ローカルのBunの直接起動は見つからず、既存のnpmキャッシュからBun 1.4.4を呼び出してWASM・TypeScript・Viteをビルドした。Rust 1.94.1、Node 24.19.0、Python 3.14.4、macOS 15.6.1 arm64。各48判定が通過し、各280入力・45出力のサイズとSHA-256を照合した。両実行でWASM・PCM・CSV・再実行ケース・要約の26件が一致した。比較2回の外部出力はRTL9210B-CGに計25,915,668バイト。従来の短音歌唱の回帰15判定、WASMのRustテスト26件、上流のブロック長の試験も通過した。[初回](../runs/worklet-song-prepared-source-20261122-a/manifest.json)・[再実行](../runs/worklet-song-prepared-source-20261122-repeat/manifest.json)・[従来の短音の回帰](../runs/worklet-song-voice-fast-20261122-prepared-regression/manifest.json)

次は研究版の同じプリセットをSafariの実時間歌唱に通し、予約前描画を含む構築時間と、停止前後の描画フレーム・PCMの連続性を確認する。今回の実時間のPCMはWorklet内の採取位置を対象にしている。
