# 先行PCMが0の実時間歌唱で待ち時間8量子と32量子を比較する

前回はChromiumで全サンプル0の先行PCMを32量子以上流すと、短音 `Pop Dee` の開始待ちに飛びがなかった。今回は同じ先行PCMと接続を使い、先行枝が準備完了を通知するまでの量子数だけを32から8に変える。48 kHzの128フレーム量子では24量子が3,072フレーム、64 msに当たる。[前回の実測](worklet-live-song-fast-zero-lead-pcm.md#実測)・[事前登録](../cases/worklet-live-song-fast-zero-lead-wait.json)

## 上流から開始待ちまで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `playTune()` は音節と音符を計画し、AudioEngineからWorkletへジェスチャーを送る。Workletは `engine_schedule()` を呼び、`Engine::schedule()` が各ジェスチャーの時刻に現在の声の時計と指定の待ち時間を加える。`process()` は `engine_render()` の出力をチャンネルへコピーし、Engineは呼び出しをまたいで内部のブロック位相を保つ。`sing_fast` の `fast_runs_land_on_the_beat()` は短い音でも母音の計画時刻が拍に揃うことを、`engine` の `output_does_not_depend_on_the_host_block_size()` は分割を変えたPCMが揃うことを検査する。今回のPCM比較には同じ固定上流の保存済みレンダーを使う。[上流の歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

候補では `renderRealtimeSongVoice()` が歌唱用Contextを生成し、計測ページは `installSharedContextMarker()` で同じContextに全サンプル0の先行枝を接続する。先行枝の開始予定はContextの現在時刻を量子境界に切り上げ、16量子を加えたフレーム。読取Workletはその時刻以降の量子を数え、`index === readyQuanta` で準備完了を通知する。通知をメインスレッドが受けてから歌唱ノードを接続するため、歌唱ノードの最初の呼び出しまでに観測される先行量子数は設定値より多くなる場合がある。[実時間歌唱](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[先行枝の作成](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[先行枝の量子計数](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)

歌唱ノード自身の開始待ちは両条件で揃えた。`WorkletStartup.ready()` が最初の連続8量子を確認し、`RealtimeSpeechCapture.ready()` がその後に2,048フレームを待つ。歌唱ノードの初回呼び出しから始まる連続区間に飛びがなければ、歌唱は初回から3,072フレーム後に始まる。先行枝の最初の観測フレームを `M`、歌唱ノードの最初の呼び出しを `V`、歌唱開始を `S` とし、`V − M` と `S − V` の和 `S − M` を組ごとに比較する。独立計算は、128フレームずつ連続する量子から `V − M` を再構成し、8量子と2,048フレームから `S − V` を求める。前者は先行枝の通知後に接続が行われるまでの時間も含む。[歌唱の開始時計](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[予約とPCMの採取](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[比較コード](../tools/measure_worklet_live_song_zero_lead_pcm.py)

## 実測

2回の実行で計8組を比較した。8量子・32量子とも、各8試行で歌唱ノードの開始待ちの飛びは0。歌唱ノードの最初の呼び出しから予約までの間隔 `S − V` は、全試行で3,072フレームだった。先行枝の最初の観測から歌唱開始までの `S − M` は、8量子条件で4,096〜4,224フレーム、32量子条件で7,168〜7,296フレーム。同じ組で短くなった幅は2,944〜3,200フレーム（61.33〜66.67 ms）、中央値は3,136フレーム（65.33 ms）だった。[初回の結果](../runs/worklet-live-song-fast-zero-lead-wait-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-zero-lead-wait-20261121-repeat/summary.json)

各組の短縮幅のばらつきは1量子以内だった。保存時刻から準備完了を通知した量子の末尾を求めると、歌唱Workletの最初の呼び出しはそのフレームか、次の128フレーム境界にあった。歌唱枝の49,200フレームと769行の状態は、両条件の全試行でオフラインと一致した。先行枝の512量子には各128フレームの入力チャンネルが届き、値はすべて0。標準ライブラリで先行枝、歌唱枝、保存WAVを別途読み、絶対フレームでの連番と予約位置、歌唱の前後の無音を再確認した。固定上流との最大PCM差は、1,200 Hzの設定を加えた前回と同じ `2.7573 × 10⁻³` だった。[先行枝の観測](../runs/worklet-live-song-fast-zero-lead-wait-20261121-repeat/artifacts/1-short/marker.json)・[歌唱枝の観測](../runs/worklet-live-song-fast-zero-lead-wait-20261121-repeat/artifacts/1-short/output-probe.json)・[固定上流との照合](../runs/worklet-live-song-fast-zero-lead-wait-20261121-repeat/summary.json)

短縮幅には先行枝を流し始める前のContext生成やWASMの準備を含めていない。次は計測用の先行枝から得た8量子条件を歌唱画面の試験用設定として構成し、通常の開始経路との比較で、操作からの時間と開始前後のPCMを確認する。機器から出た波形と聴感、8量子より短い条件は未計測。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_zero_lead_pcm.py <実行ID> \
  --case cases/worklet-live-song-fast-zero-lead-wait.json
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各146判定・3予測を満たした。入力550件と出力184件のサイズ・SHA-256を照合し、20.39 MBをRTL9210B-CGに保存した。[初回マニフェスト](../runs/worklet-live-song-fast-zero-lead-wait-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-zero-lead-wait-20261121-repeat/manifest.json)
