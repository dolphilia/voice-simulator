# 短音の実時間歌唱で先行PCMだけを0にする対照

前回はChromiumで短音 `Pop Dee` を再生し、先行信号なしの8試行で開始待ちのフレームが飛び、先行信号を流した8試行では飛びが0だった。今回は先行枝を両条件で動かし、枝に流すPCMだけを既知信号と全サンプル0で比較する。歌唱側は全体の乱流係数1、声門・狭窄のゲイン倍率0、歯の低域通過周波数の下限1,200 Hzを維持する。[前回の実測](worklet-live-song-fast-context-lead.md#実測)・[事前登録](../cases/worklet-live-song-fast-zero-lead-pcm.json)

## 呼び出し経路と入力の測り方

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の歌唱画面は `playTune()` で音節をスコアにし、`AudioEngine.schedule()` からWorkletに送る。`ChimeraProcessor.handle()` が線形メモリにジェスチャーを書き、`engine_schedule()` から `Engine::schedule()` で待ち時間をEngineの時計（秒）に加える。`process()` は要求されたフレーム数で `engine_render()` を呼び、得られたPCMを出力チャンネルにコピーする。`engine` の `output_does_not_depend_on_the_host_block_size()` は同じ状態列を128フレームと複数の分割で比較し、`sing_fast` は240 BPMを含む短音の母音の拍位置を照合する。固定上流との波形比較は前回の保存済みレンダーを基準にする。[上流の歌唱画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts)・[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)

再実装は実時間歌唱ボタンから `renderRealtimeSongVoice()` と `withRealtimeContext()` を通じて歌唱用のWorkletを接続する。`WorkletStartup.ready()` が `currentFrame` を前の量子の末尾と照合し、連続8量子が揃った時点で `RealtimeSpeechCapture.ready()` が2,048フレーム先を予約する。先行枝は計測ページの `installSharedContextMarker()` が用意する。48 kHzの同じモノラルAudioBufferSourceNode、同じ512量子のループバッファ、同じ読取Workletと接続先を使う。先行枝で32量子を記録してから歌唱ノードを接続する。[実時間歌唱](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[開始時計](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[開始予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[先行枝の準備](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)

先行PCMは `((multiplier × i + offset) mod 65521 − 32760) / 524288` を `f32` に丸めた値。`i` はContextの絶対フレームと先行枝の開始フレームの差を、ループの長さで折り返した値。既知信号は乗数421とオフセット173を使い、全サンプル0の対照は乗数0とオフセット32760を使う。先行枝のWorkletで `inputs[0]?.[0]` のフレーム数を量子ごとに記録し、512量子で入力が届いた長さと、出力PCMが式どおりかを照合する。歌唱枝は別の並列Workletで採り、予約位置の前後の連番、無音、最終量子の80フレームの補完を検査する。[読取Worklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)・[歌唱枝の観測](../../../../web/prototypes/chimera-research/tools/song-output-probe-worklet.js)・[測定と独立計算](../tools/measure_worklet_live_song_zero_lead_pcm.py)・[共通のPCM照合](../tools/measure_worklet_live_song_context_lead.py)

## 実測

同じ順序の4組を別の作業ディレクトリから再実行し、計8組を比較した。どちらの先行PCMでも、歌唱ノードの最初の呼び出しから予約まで、欠けたContextフレームは0。開始は最初の呼び出しから3,072フレーム（64 ms）後で、両条件の全試行で同じだった。先行枝の32〜33量子が歌唱の初回呼び出しより前に観測され、全試行とも先行枝の512量子すべてに128フレームの入力チャンネルが届いた。各記録の先行PCMは式とビット一致し、ピークは既知信号で0.0624847、全サンプル0の条件で0だった。[初回の結果](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-repeat/summary.json)・[先行PCMが0の入力長](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-repeat/artifacts/1-zero/marker.json)

歌唱の49,200フレームと769行の状態観測は全16試行でオフラインと一致した。別のWorkletから読んだ歌唱枝も予約した絶対フレームで一致し、直前256フレームと、最終量子の補完80フレームを含む末尾側の無音を確認した。固定上流との差は前回と同じで、最大PCM絶対差は `2.7573 × 10⁻³`。標準ライブラリでWAVの `data` チャンクと生の先行PCMを独立に読み、予約したフレームでの波形一致と開始待ちの連番を再確認した。[歌唱枝の時刻](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-repeat/artifacts/1-zero/output-probe.json)・[判定の内訳](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-repeat/summary.json)

今回のChromiumでは、先行PCMがすべて0でも、動作中の先行枝を使うと既知信号と同じ開始結果を再現できた。比較した時間は歌唱Workletの最初の呼び出しから予約まで。コンテキスト生成からの総所要時間、必要な先行時間の下限、音声機器での出力は未測定。次は全サンプル0のまま先行枝の待ちを8量子と32量子で比較し、歌唱の開始時刻と連続性を照合する。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_zero_lead_pcm.py <実行ID>
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各146判定と2件の予測を満たした。入力544件、出力184件のサイズ・SHA-256を照合し、20.39 MBをRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-zero-lead-pcm-20261121-repeat/manifest.json)
