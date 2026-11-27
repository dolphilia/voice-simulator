# 短音の実時間歌唱に先行する信号と開始待ち

48 kHzのChromiumで、通常画面の短音 `Pop Dee` を同じ設定で再生する。乱流係数1、声門・狭窄のゲイン倍率0、歯の低域通過周波数の下限1,200 Hzを固定した。無音から始める条件と、既知のPCMを同じAudioContextで32量子以上流してから歌唱をつなぐ条件を、両方とも並列観測を付けて比較する。[事前登録](../cases/worklet-live-song-fast-context-lead.json)・[前回の開始待ち](worklet-live-song-fast-teeth-lowpass-floor.md#初回の判定と計測の改訂)

## 呼び出し経路と観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` は `AudioEngine` がWorkletを出力グラフに接続する。`ChimeraProcessor.handle()` は歌唱のジェスチャーの開始時刻をEngineの時計（秒）に写し、`process()` は出力要求の長さだけ `engine_render()` で描画する。`Engine::render()` は内部境界の位相を保つ。`engine` の `output_does_not_depend_on_the_host_block_size()` が128フレームを基準に1、77、4,096、48,000フレーム分割のPCMを照合する。ChromeのContext開始待ちの機構は候補側の実装で、固定上流への波形照合には前回検証した保存済みのPCMを使う。[上流AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[上流Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

候補の通常画面は `renderRealtimeSongVoice()` から `withRealtimeContext()` を通り、`AudioContext.resume()` の後にWASMと歌唱ノードを準備する。`RealtimeSpeechCapture.ready()` は `WorkletStartup.ready()` が連続8量子を確認した時刻から2,048フレームを待って開始する。先頭から飛びがあれば連続数を初期化し、最後に成立した連続区間の始点から3,072フレームで歌唱が始まる。歌唱ノードの出力と同じContextで別ノードが読み取ったPCMを絶対フレームで照合し、先頭の観測から予約までの飛びの数と欠けたフレーム数を測る。[実時間歌唱とノード接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[開始時計](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[開始予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[並列観測](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs)

## 比較方法

計測ブラウザは試験時にだけ、歌唱ノードと同じContextに既知の信号を流す。歌唱枝の観測ノードを先に準備し、先行信号の観測ノードを出力へ接続してから32量子を待つ。観測は先行信号と歌唱をそれぞれ混合前の枝で読み取る。先行信号のサンプル番号 `i` はContextフレームから起点を引いた値をバッファ長で折り返す。各サンプルは `((421i + 173) mod 65521 − 32760) / 524288` を `f32` に変換した値で、記録順に依存せずフレーム番号から照合できる。先行信号のあり・なしを交互に実行し、どちらも実時間歌唱ボタンを使う。歌唱のPCMと状態はオフラインWorkletを参照する。[先行信号の設定](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[先行信号の観測](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)・[取得と判定](../tools/measure_worklet_live_song_context_lead.py)

## 初回の欠測と改訂

初回の先行信号あり4試行では、歌唱枝の観測ノードが接続前から呼ばれたため、448量子の採取範囲が歌唱の最終量子より9〜11量子手前で終わった。歌唱ノード自身が保存したWAVはオフライン版と4試行ともビット一致し、先行信号も4試行とも独立計算と一致していた。この初回は、歌唱枝の全区間を並列に観測する取得判定を満たさなかった。改訂2では歌唱枝から入力が届くまで並列ノードが記録枠を消費しないようにし、接続からの448量子を採る。条件の順序、比較区間、判定基準は同じで、改訂前のマニフェストと判定を保存した。[初回の判定](../runs/worklet-live-song-fast-context-lead-20261121-a/summary.json)・[初回マニフェスト](../runs/worklet-live-song-fast-context-lead-20261121-a/manifest.json)・[入力起点の採取](../../../../web/prototypes/chimera-research/tools/song-output-probe-worklet.js)

## 実測

改訂後の初回と `/private/tmp` からの再実行で、各4組・計8組を比較した。無音から始めた条件では8試行すべてで、歌唱ノードの最初の呼び出しとその次の呼び出しの間に256〜1,024フレームの飛びがあった。既知の信号を先に32〜33量子流した条件は8試行とも飛びが0。先行信号ありでは歌唱ノードの最初の呼び出しから予約まで3,072フレーム（64 ms）、無音からの開始では3,456〜4,224フレーム（72〜88 ms）だった。両条件とも最後の連続8量子の始点から3,072フレームで歌唱を始め、予約したフレームに揃った。時刻の起点は歌唱ノードの最初の呼び出しで、先行信号を準備する時間も含めたユーザー操作からの所要時間は未比較。[改訂後の結果](../runs/worklet-live-song-fast-context-lead-20261121-b/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-context-lead-20261121-repeat/summary.json)

全16試行で歌唱の49,200フレームはオフラインとビット一致し、保存した観測・計画・入力も一致した。並列観測でも同じ開始位置で全波形を読み取れ、歌唱前と最終量子の補完80フレームおよび歌唱後に無音を確認した。先行信号は歌唱枝の最初の呼び出しの前8量子から末尾の後2量子までフレーム番号が連続し、記録した512量子のPCMは8試行とも独立計算とバイト一致した。別途、標準ライブラリでWAVの `data` と生の先行信号を読み、歌唱区間と先行信号を照合した。固定上流とのPCM最大差は両条件とも前回と同じ `2.7573 × 10⁻³` だった。[歌唱枝の再実行時刻](../runs/worklet-live-song-fast-context-lead-20261121-repeat/artifacts/1-lead/output-probe.json)・[先行信号の再実行時刻](../runs/worklet-live-song-fast-context-lead-20261121-repeat/artifacts/1-lead/marker.json)・[固定上流との比較](../runs/worklet-live-song-fast-context-lead-20261121-repeat/summary.json)

先行信号は同じContextで稼働する追加の枝を持つので、信号の振幅とグラフを先に動かした効果の寄与は未分離。次は先行枝を同じ形と長さで動かし、PCMだけを全サンプル0にした条件を既知信号と比べる。機器から出た波形と聴感は未計測。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_context_lead.py <実行ID>
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。改訂後の各実行で130判定と事前の予測が成立した。欠測を含めた3実行の入力814件・出力252件のサイズとSHA-256を照合し、27.34 MBをRTL9210B-CGに保存した。[改訂後の初回マニフェスト](../runs/worklet-live-song-fast-context-lead-20261121-b/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-context-lead-20261121-repeat/manifest.json)
