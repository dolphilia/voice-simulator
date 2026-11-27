# 固定上流の歌唱予約を同じエンジンフレームにそろえる

## 上流の入力と時計

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の通常の「Record video」は、`AudioEngine.quiet()` が壁時計で150 ms連続の低い出力を確認してから録画を始める。その後、`playTune()` が歌詞と譜面から作ったジェスチャーを `AudioEngine.schedule()` でWorkletのポートに送る。音声エンジンは待機中も描画するため、主スレッドから譜面が届くときには、試行ごとにそれまでの処理サンプル数が異なりうる。[歌唱録画の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L157)・[譜面作成と送信](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[quiet](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L323)

`ChimeraProcessor.handle()` はジェスチャーをWASMの共有領域へ書き、`engine_schedule()` に渡す。Rustの `Engine::schedule()` は発声機構の時計に先行時間0.03秒を足した値を譜面の時刻0とし、各ジェスチャーの秒単位の開始・終了を同じ分だけ動かす。48 kHzではこの先行時間が1,440フレームになる。描画時は、`Engine::render()` が現在位置と内部ブロック境界から区切りを決め、`HumanVoice::render()` が声道・声門の状態を進めて出力PCMを返す。停止の前後の連続性を判定する際は、エンジン時計を48,000倍して丸めたフレームと、AudioWorklet側の `currentFrame` を区別した。[Workletの予約と描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASMの受け渡し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L198)・[予約と描画のRust実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[発声機構の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

上流は6描画量子ごとに肺圧、F0、声門面積・流量、気道断面、その他の観測値を送る。取得した状態は、調音や面積などの瞬時の値と、区間内の圧力・出力のRMSを含む。RMSの集計器は状態通知を作るたびにリセットされるため、測定では既存の通知をコピーした。上流のテストはホストの描画ブロック長を変えてもPCMがビット一致することと、短音での母音開始が拍に合うことを確認する。今回も両テストを実行した。[状態通知](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L202)・[計測値と集計器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L597)・[ブロック長のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[拍のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

## 条件と予測

前回と同じ「Pop Dee」の2音、MIDI 60と64を各0.25拍、240 BPM、48 kHz出力で録画した。ブラウザ向けに配信するWorkletの観測コードで、通常画面から届いた譜面を一時保持し、最初の描画が指定エンジンフレームに達したときに元の `handle()` へ渡す。指定は16,384フレームと、その1量子後の16,512フレーム。それぞれで連続描画と歌唱途中の約120 msの停止を組にし、組によって実行順を逆にした。到着時点のフレームが指定位置より後なら、録画の取得失敗として記録する。固定上流のチェックアウトはそのまま使用した。[新しいケース](../cases/upstream-safari-song-fixed-schedule-frame.json)・[前回の通常録画](upstream-safari-song-recording-pause.md)・[観測用Workletの変換](../../../../web/prototypes/chimera-research/tools/capture-upstream-safari-recording-pause.mjs)

同じ予約フレームの組では、譜面時刻0から29,760サンプルのPCMと、譜面を予約してからそのPCM区間を描画し終えるまでの状態通知が停止の有無をまたいで一致すると予測した。128フレーム後ろにずらした場合は、譜面に相対的な拍は同じでも、停止点より前でPCM差が0.000001を超えると予測した。録画の音声と映像の時刻は前回の計測を継続した。[解析](../tools/measure_upstream_safari_recording_pause.py)

## 実測

2回の実行で8試行を取得し、各48件の取得判定と11件の予測が通過した。譜面はエンジンフレーム7,808〜8,576で届き、指定した16,384または16,512で予約された。譜面の時刻0は全試行でそこから1,440フレーム先になった。停止ありの4試行は121〜124 ms保持した。停止中はContextの番号が固定され、Workletの前後の番号は128刻みだった。[初回](../runs/upstream-safari-song-fixed-schedule-frame-20261121-a/summary.json)・[再実行](../runs/upstream-safari-song-fixed-schedule-frame-20261121-repeat/summary.json)

| 譜面を予約したフレーム | 連続・停止のPCM | 同じエンジン位置での状態通知 |
| --- | --- | --- |
| 16,384 | 4試行の全29,760サンプルがビット一致 | 40点が一致 |
| 16,512 | 4試行の全29,760サンプルがビット一致 | 41点が一致 |

予約を128フレームずらした2条件では、譜面時刻0から14,268サンプル目で最初のビット差が現れ、14,330サンプル目で差が0.000001を超えた。この位置は停止目標21,472サンプルより前だった。共通の絶対エンジンフレームで状態通知を照合した場合、最初の差は29,184フレームで、調音、口腔断面、声門流量、出力RMS、圧力RMS、流量、口腔長に見られた。譜面は絶対時計で128フレームずれているので、その時点の調音制御も異なる。譜面を受けるまでに進んだ声門の位相や乱流フィルタのどの変化が、相対時刻で見たPCMの差を最初に生んだかは、6量子ごとの通知では特定できない。[初回の録画と状態通知](../runs/upstream-safari-song-fixed-schedule-frame-20261121-a/artifacts/1-paused/browser.json)・[再実行の陽性対照](../runs/upstream-safari-song-fixed-schedule-frame-20261121-repeat/summary.json)

録画音声は停止前後の復号サンプル順のオフセット変化が0。映像の停止中のフレームはPTS幅1.67〜3.33 msに収まった。バイト比較とは別に保存PCMのSHA-256を予約位置ごとに比較し、状態通知の時刻も128フレーム刻みのうち6量子ごとの位置と一致させた。録画音声PTSは整数の時刻単位とAACのサンプル数から有理数で再計算した。エンジンフレームを固定しない通常録画を同じツールで再実行し、従来の36件の取得判定と6件の予測も通過した。[通常録画の回帰](../runs/upstream-safari-song-recording-pause-20261121-fixed-schedule-regression/manifest.json)

## 再現と保存

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1、FFmpeg 7.1。各比較実行の入力21件と出力28件をサイズとSHA-256で照合し、2回分14,600,099バイトをRTL9210B-CGに保存した。通常録画の回帰1回分は2,414,178バイト。同じスクリプトとケースを絶対パスで指定して `/private/tmp` からも再実行した。[初回マニフェスト](../runs/upstream-safari-song-fixed-schedule-frame-20261121-a/manifest.json)・[再実行マニフェスト](../runs/upstream-safari-song-fixed-schedule-frame-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python \
  tools/measure_upstream_safari_recording_pause.py <実行ID> \
  --case cases/upstream-safari-song-fixed-schedule-frame.json
```

次は短い同じ譜面に対し、初期描画128フレーム分の差を、声門・気道のどちらから生じたか追う。音素区間と比較する相対サンプル位置をそろえ、声門と乱流の系列を取得できる既存のネイティブ計測で、最初の差を調べる。
