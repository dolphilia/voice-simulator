# 短音の実時間歌唱で歯の乱流フィルタの設定を照合する

オフラインで検証した短音の `Pop Dee` を、通常の歌唱画面の「実時間で歌唱」から再生する。声門・狭窄のゲイン倍率0と全体係数1を維持し、歯の低域通過周波数の下限0 Hzと1,200 Hzを比較する。開始フレームは各AudioContextの絶対フレームで照合する。[事前登録](../cases/worklet-live-song-fast-teeth-lowpass-floor.json)・[オフラインの実測](worklet-song-fast-teeth-lowpass-floor.md#実測)

## 上流から実時間歌唱まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `playTune()` は、テンポと音節を `planSong()` に渡してジェスチャーを作り、`AudioEngine` からWorkletへ予約を送る。`ChimeraProcessor.handle()` はジェスチャーをWASMの作業領域に書く。`engine_schedule()` は指定の待ち時間（秒）をEngineの時計に加えてスコアの起点を決める。Workletの `process()` は量子ごとに `engine_render()` を呼び、返された `f32` を出力チャンネルにコピーする。上流の `engine` 試験はホスト分割1・77・128・4,096などでPCMの一致を検査し、`sing_fast` は短い拍でも母音の予定時刻を検査する。保存基準の固定上流は、この試験を通した前回の計測を参照した。[上流の歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts)・[上流AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[上流のC ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)

再実装の `renderRealtimeSongVoice()` は48 kHzのAudioContextでスコアを初期化し、歌唱ノードを出力先へ接続する。`WorkletStartup.ready()` が連続8量子を確認した時刻を `RealtimeSpeechCapture.ready()` が保持し、そこから2,048フレームを待った時刻を開始として予約する。それまでは出力を0で埋める。初期待ちに飛びがなければ、最初の量子から `8 × 128 + 2048 = 3072` フレーム後に描画が始まる。歌唱の49,200フレームは128フレームの量子385回で出力し、最終量子は48フレームを生成した後、80フレームを0で補完する。`RealtimeSpeechCapture.record()` は出力したPCM、Contextの絶対フレーム、累積フレーム数、処理時間を保存する。拍の絶対フレームは `開始フレーム + round(48000 × (最初の拍の秒 + 経過拍数 × 60 / BPM))` を独立に計算した。[実時間歌唱](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[初期の連続判定](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[予約と時系列](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[出力と補完](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)

## 採取と再現

通常実行に加え、計測ページに限って歌唱ノードの出力先へ接続する操作に並列の読取ノードを追加する。読み取ったPCMを事前確保したバッファに保存し、読み取り枝自身は無音を出力する。`currentFrame` と出力を448量子採取し、歌唱が終わってノードが切断された後も、計測中だけAudioContextを保持する。開始の位置合わせには `scheduledContextFrame` と読取ノードの `currentFrame` を使う。歌唱前、歌唱区間、最終量子の補完、歌唱ノード切断後を分けて比較する。並列ノードを付けた測定では負荷が変わり得るため、処理時間は通常実行と別々に保存する。[通常画面の操作](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs)・[計測ノードの接続](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs)・[並列ノードの読み取り](../../../../web/prototypes/chimera-research/tools/song-output-probe-worklet.js)・[比較コード](../tools/measure_worklet_live_song_teeth_lowpass_floor.py)

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_teeth_lowpass_floor.py <実行ID>
```

## 初回の判定と計測の改訂

初回は通常2試行と並列観測付き2試行の歌唱PCMがすべてオフラインと一致した。初回の計測器では、最初の量子から3,072フレーム後を開始と仮定し、途中で飛びがあった3試行を開始不一致と判定した。最初の量子から実際の開始までの距離は通常0 Hzで3,712、通常1,200 Hzで3,456、観測付き1,200 Hzで3,456、観測付き0 Hzで3,072フレームだった。観測付き1,200 Hzでは並列ノードの先頭が2,048、次が2,432フレームで、間の256フレームに観測がなかった。先頭からの配列位置で切ると歌唱PCMがずれた。保存した並列列を絶対フレーム5,504から取り直すと、49,200フレームが保存済みPCMとビット一致した。[初回の判定](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-a/summary.json)・[初回の並列フレーム](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-a/artifacts/observed-floor1200/output-probe.json)

改訂2では `WorkletStartup.ready()` が連続8量子を数え始めた時刻を観測に加えた。予約の計算式は既存のまま使い、その連続区間の先頭から3,072フレームであることを別計算する。並列観測のPCMは保存した絶対フレームで切り出し、開始直前2量子から末尾補完後2量子までの連番を検査する。並列観測の初期量子からも連続8量子の成立を独立に計算する。初回の「最初の量子から3,072フレーム」という仮説は各試行の予測欄に残した。[改訂前のマニフェスト](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-a/manifest.json)・[改訂後のケース](../cases/worklet-live-song-fast-teeth-lowpass-floor.json)

## 実測

改訂後の初回と `/private/tmp` からの再実行で各50件の取得判定を通過した。8試行とも、連続8量子の始点から3,072フレーム（64 ms）後の予定値に、歌唱の最初の量子が一致した。385量子の時刻は連続し、全49,200フレームのPCM、769点の音響観測、歌唱計画、保存した設定がオフラインと一致した。改訂前を含む12試行中8試行で連続8量子を数え直したため、最初に観測した量子から常に3,072フレームで始まるという初回の予測は外れた。[改訂後の初回](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-b/summary.json)・[再実行](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-repeat/summary.json)

改訂後の並列観測4試行のうち再実行の2試行で、初期の1,536フレームから次の1,920フレームまでの間に256フレーム分の飛びがあった。2試行とも救済後の連続区間から求めた予約位置で、並列ノードの歌唱PCMはオフラインと全点一致した。別計算では、各量子の絶対フレームをキーにしてWAVの `data` チャンクと照合し、初回の並列観測も含め歌唱区間を再現できた。改訂後には歌唱前の採取3,072〜3,200フレーム、最終量子の補完80フレーム、その後の4,864〜4,992フレームがすべて無音だった。採取中は比較のためAudioContextの終了を保持している。[下限0 Hzの時刻](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-repeat/artifacts/observed-floor0/output-probe.json)・[下限1,200 Hzの時刻](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-repeat/artifacts/observed-floor1200/output-probe.json)

下限0 Hzと1,200 Hzの間で最初にPCMのビットが異なる箇所は歌唱内27,927フレーム、絶対差10⁻⁶超は27,939フレームで、通常実行と並列観測で揃った。固定上流の下限0 Hzとの最大PCM差は、下限0 Hzの実時間出力では `2.91 × 10⁻¹¹`、下限1,200 Hzでは `2.76 × 10⁻³`。最初の32量子を除いた353量子の処理時間のp99は、改訂後の8試行とも `Date.now()` の計時で2 msだった。通常・並列双方で傾向は同じ範囲だが、測定した粒度で負荷の因果は分離できない。音声機器から出た音の連続性や聴感は未確認。次は同じ短音を、連続した既知の信号が先に鳴っているAudioContextで開始し、開始待ちの飛びがどう変わるかを測る。[波形と時刻の結果](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-repeat/summary.json)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用。`WorkletStartup` の8量子と飛びの直後の数え直しはNodeでも合成したフレーム列で確認した。初回の失敗を含め、入力817件、出力108件のサイズ・SHA-256を照合し、12.89 MBをRTL9210B-CGに保存した。[改訂後の初回マニフェスト](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-b/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)
