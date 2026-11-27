# Safariの歌唱準備前後にプロセス出力を照合

## 読解と観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` がAudioContextとWorkletを準備し、`ChimeraProcessor.process()` が量子内のフレーム数を `engine_render()` に渡す。WASM側は永続ハンドル内の `Engine::render()` に出力スライスを渡す。エンジンは累計 `pos` から制御更新境界を求め、発声と出力PCMを書いた後に累計を加算する。固定上流のブロック長試験は同じ絶対フレームの操作列を使い、分割長によらずPCMが一致することを検査する。[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[WASMの描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御と描画の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流のブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `renderRealtimeSongVoice()` で歌唱する。`FixedProcessor` は一括条件で合成器の生成中に予備描画し、分割条件では永続する同じ合成器に対して `advanceScorePreparation()` を呼ぶ。各片で合成器を進め、AudioContextへは歌唱の代わりに無音を返す。別枝で流す先行信号の位相はコンテキストのフレームで決まる。WebDriverでは先行信号の準備通知の後、WebKit GPUのうち出力が有効になったプロセスへ、較正済みのCore Audioタップを付ける。タップ開始通知から0.6秒後に歌唱の準備を許可する。ブラウザとタップで出力経路を保ち、0フレーム・一括16,384フレーム・分割16,384フレームを比較する。[研究版の歌唱入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L296)・[予備描画の更新順序](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L160)・[事前登録](../cases/worklet-safari-song-process-output.json)・[プロセスタップの較正](safari-process-tap-smooth-marker.md)・[Appleの採取手順](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)

タップの左右の差の半分を1,024点ずつ照合する。各窓の整数位相と分数遅延から、歌唱準備の前後の実信号の進みを推定する。Mach時刻は記録した分子・分母とエポック時刻の基準を用いてmsに変換する。入力コールバックのフレーム位置を間のサンプルの時刻に補間する。準備前380〜20 msの連続区間で65,520フレーム周期の候補を絞り、出力時刻とグラフの時刻を照合した。準備完了後10〜220 msの採用窓と準備前の採用窓との位相差から、採取側のフレーム増分を引くと、先行信号の連番が遅れた量を求められる。準備開始20 ms前から完了160 ms後には、差チャンネルの絶対振幅が1×10⁻⁵以下の区間と、両チャンネルが完全にゼロの区間を計数した。[照合器](../tools/measure_worklet_safari_song_process_output.py)

## 実測

初回は3条件のブラウザとタップの採取を完了したが、ケースに量子長とサンプルレートの数値欄がなく、位相をコンテキストのフレームに戻す処理で止まった。事前定義にある128フレーム・48 kHzの値を数値欄に記し、初回の不合格判定と生データを保存した。同じ出力を照合し直してから、順序を反転した2組を採取した。判定の閾値は同じ値を使った。[初回の記録](../runs/worklet-safari-song-process-output-20261122-a/summary.json)

再採取の6試行はいずれも114,176フレームを採り、入力ブロックは512フレームずつ連続した。準備前の採用窓では、グラフのコールバックからタップまでの時刻差は33.2〜33.9 msだった。先行信号のグラフ内PCM各229,376点はゼロ近傍の較正を含む照合を通過した。歌唱の加工前PCM各31,200点と各488点の状態はそれぞれの予備描画量の保存基準と一致した。[研究ワークスペースからの採取](../runs/worklet-safari-song-process-output-20261122-b/summary.json)・[反転順の採取](../runs/worklet-safari-song-process-output-20261122-repeat/summary.json)

| 準備条件 | 準備時間（ms） | 準備と重なるグラフの最長間隔（ms） | 最長の低振幅区間（フレーム） | 最長の完全ゼロ区間（フレーム） | 前後の位相差（フレーム） |
| --- | ---: | ---: | ---: | ---: | ---: |
| なし | 4・18 | 6・20 | 92・603 | 33・545 | +0.02・−1,279.97 |
| 一括 | 137・137 | 141・140 | 6,364・6,364 | 6,305・6,305 | −10,367.92・−10,367.91 |
| 分割 | 182・182 | 5・7 | 91・91 | 33・33 | −255.94・−255.93 |

一括の両試行で、両チャンネルが完全にゼロの区間が6,305フレーム（約131 ms）と3,873フレーム（約81 ms）に分かれて現れた。最初の区間は準備開始の約34 ms後に始まり、二つ目は約170 ms後に始まった。各組で二つの区間の開始位置の差は6,528フレームだった。先行信号の回復後は、採取時刻が進んだフレーム数に対し、先行信号の連番が約10,368フレーム（128フレーム量子81個分）遅れた。準備なしでも構築に18 msかかった試行に短い無音が二つ現れ、分割2試行でも約256フレームの位相差が残った。分割により長い無音区間は短縮された。[同順での再採取](../runs/worklet-safari-song-process-output-20261122-b/summary.json)・[逆順での再採取](../runs/worklet-safari-song-process-output-20261122-repeat/summary.json)

最初に波形の違いを確認できたのは、連続したグラフ内の先行信号より下流のプロセスタップだった。公開WebKitのGPU側は、共有リングから要求全体を取れないと読み出し位置を進めず、直前のサンプルから減衰させる。不足したWeb側FIFOからは無音をリングに書ける。この二つの経路を分けるには、それぞれの読み出し・書き込み位置、要求ごとの成否と取得したPCMを照合する必要がある。今回はWebKitの各書き込みと機器端子の波形を直接観測していない。[公開WebKitのリングと減衰](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L186-L248)・[FIFOの無音補完](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/PushPullFIFO.cpp#L80-L125)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4を使った。研究ワークスペースで次を実行する。実行順を反転する場合は `--reverse` を追加する。別ディレクトリから起動するときはPythonとスクリプトを絶対パスで指定する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_process_output.py \
  worklet-safari-song-process-output-example \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
```

再採取は各73判定に合格し、グラフ間隔、一括時の低振幅区間、分割による短縮の事前予測が2組とも成立した。固定上流のホストブロック長試験と、信号生成を共通化した後のSafariのグラフ対照17判定も通過した。生のPCMから完全ゼロの区間を数え直し、初回を含む4実行の863入力・205出力をサイズとSHA-256で照合した。採取物25,074,936バイトはRTL9210B-CGに保存した。[初回](../runs/worklet-safari-song-process-output-20261122-a/manifest.json)・[再採取](../runs/worklet-safari-song-process-output-20261122-b/manifest.json)・[反転順](../runs/worklet-safari-song-process-output-20261122-repeat/manifest.json)・[較正の回帰](../runs/safari-process-tap-smooth-marker-20261122-song-regression/manifest.json)
