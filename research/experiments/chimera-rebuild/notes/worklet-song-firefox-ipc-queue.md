# Firefoxの親メインスレッドでWorklet取得のIPCを追う

## 固定上流とFirefoxの処理順

固定上流の `AudioEngine.start` は初回に `build` を呼び、サンプルレートを指定してContextを作る。再開を要求し、モジュールURLの登録完了後にWorkletノードへWASMを渡す。 `playTune` は辞書の取得後に歌詞と再生トークンを確認し、MIDI番号・拍数・テンポから調音計画を作る。先頭からの拍秒は先行音符の拍数の合計に `60 / BPM` を掛け、開始時刻を加える。上流は拍と母音核、句末の声帯開大、ホストブロック分割での音声の一致を試験する。[上流の起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L97)・[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[拍](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[句末](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[ブロック長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Firefoxでは、子のHTTPチャネルがコンストラクタを送信し、親のI/Oスレッドで受信する。 `MessageChannel::OnMessageReceivedFromLink` は対象メッセージから `MessageTask` を作り、`mPending` に入れてから `Post` で対象スレッドへ送る。 `IPCDispatch` はこの処理を囲む。送信側と投入側のフローは同じシーケンス番号とメッセージチャネルの識別子から作られる。親の `DispatchMessage` にある受信端点は、メッセージの処理に入ったことを示す。TaskControllerの実装では投入後に優先度・管理状態・依存タスクを考慮して実行する。 `Runnable` の実行名・優先度のマーカーはビルド時の `MOZ_COLLECTING_RUNNABLE_TELEMETRY` に依存する。[IPCの受信と投入](https://github.com/mozilla-firefox/firefox/blob/437dd728/ipc/glue/MessageChannel.cpp#L992)・[IPCの処理境界](https://github.com/mozilla-firefox/firefox/blob/437dd728/ipc/glue/MessageChannel.cpp#L1686)・[イベントキュー](https://github.com/mozilla-firefox/firefox/blob/437dd728/xpcom/threads/EventQueue.cpp#L18)・[タスクの記録と実行](https://github.com/mozilla-firefox/firefox/blob/437dd728/xpcom/threads/TaskController.cpp#L77)

## 事前登録と計測式

保存済みのIPC付き8試行を使う。追加の採取は通常画面の48 kHz `Pop Dee` を現行順と並行登録で交互に行い、IPCとフローのマーカーを有効にする。親子の時刻原点は同じHTTPトランザクションの時点から合わせる。子の送信を同じ名前のフローと時刻で一意に対応させた後、同じフローIDの親 `IPCDispatch` を探す。その区間内の一つの投入マーカーから実行端点までを測る。親I/Oに到達した時刻を `R`、投入を `Q`、メインの受信処理を `H` とすると、投入までの時間は `Q − R`、投入後の割合は `(H − Q) / (H − R)` となる。100 ms以上の待ちでは5 ms以内に投入され、待ちの75%以上が投入後に生じると予測した。[事前登録](../cases/worklet-song-firefox-ipc-queue.json)・[親子の時計照合](worklet-song-firefox-http-channel.md)・[解析CLI](../tools/measure_worklet_song_firefox_ipc_queue.py)

親メインの `Awake` はプロファイラーの起床マーカーで、区間内のCPU時間は別の値を読む。連続する採取点の間隔が `R` から `H` に完全に入るものだけについて `threadCPUDelta` をミリ秒に変換して足し、標本で覆えた区間を併記する。ウィンドウをまたぐ `Awake` に付いた総CPU時間は、その区間内のCPU時間へ按分しない。集計した別タスクのマーカー数は区間の活動を記録するために使う。[起床マーカーの定義](https://github.com/mozilla-firefox/firefox/blob/437dd728/tools/profiler/core/platform.cpp#L7861)

## 保存プロファイルのCPU時間

保存済みIPC付き8試行のうち、現行順2試行で親への到達から受信処理まで131.357 msと134.828 msかかっていた。親メインのCPUを採取点で集計すると、内側の130.018 msのうち128.336 ms、133.011 msのうち131.070 msを実行していた。2試行とも、採取点で覆えた範囲の98.5%以上でCPUを使っていた。親メインにはこの間に複数のタスク、描画、GCのマーカーがあった。保存済みの8試行にフロー収集はなく、隣接する投入マーカーを対象IPCのものとして扱うには識別情報が足りない。短い試行は採取点を二つ以上含む区間がなく、CPU時間は欠測となった。[保存済み8試行の再解析](../runs/worklet-song-firefox-ipc-queue-20261121-a/summary.json)

## フローの照合

初版の集計は `flow` の数値を子と親で比較した。FirefoxのJSONでは、64ビットのフロー識別子は16進文字列として各スレッドの `stringTable` に保存される。数値はその表の添字のため、スレッドが違うと同じ添字が別のフローを指すことがある。子・親I/O・親メインそれぞれの表から値を復元して比較するよう修正した。初版の採取と未対応判定は保存した。[初版の比較](../runs/worklet-song-firefox-ipc-queue-20261121-a/summary.json)・[フローのJSON出力](https://github.com/mozilla-firefox/firefox/blob/437dd728/mozglue/baseprofiler/public/BaseProfileJSONWriter.h#L344)

通常画面で新たに採った12試行すべてで、子の送信フロー、親I/Oの `IPCDispatch`、その中の一つの `TaskController::AddTask` を対応づけた。到達から投入までは2.0〜12.8 µsだった。現行順で100 ms以上の待ちを再現した2試行では、どちらも待ちの99.99%以上が投入の後にあった。ほかの10試行の投入後から受信処理までは0.010〜1.234 msだった。[全生ログの再解析](../runs/worklet-song-firefox-ipc-queue-20261121-verified/summary.json)

| 現行順の長い待ちを再現した試行 | I/O到達から投入 | 投入から受信処理 | 親メインのCPU時間 | CPUの標本で覆った区間 |
| --- | ---: | ---: | ---: | ---: |
| 1回目 | 4.167 µs | 128.625 ms | 126.032 ms | 128.114 ms |
| 3回目 | 2.041 µs | 133.290 ms | 129.934 ms | 131.987 ms |

親メインは、長い待ちを再現した2試行で、標本で覆えた区間の約98.4%でCPUを使っていた。今回のプロファイルではタスクの投入とIPC受信処理を結べた。タスクの実行名と優先度を含む `Runnable` マーカーは欠測で、どの処理が先に実行されたかは未特定である。次は採取条件のうちスタック採取だけを変え、同じIPCフローの待ち区間の親メインで採れたスタックとCPU時間を照合する。[長い待ちを再現したプロファイル1](../runs/worklet-song-firefox-ipc-queue-20261121-repeat/artifacts/fresh/1-serial/firefox-profile.json.gz)・[長い待ちを再現したプロファイル2](../runs/worklet-song-firefox-ipc-queue-20261121-repeat/artifacts/fresh/3-serial/firefox-profile.json.gz)

## 再現と保存

macOS 15.6.1 arm64、Firefox 157.0（ビルド20261002115412）、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4を使った。追加採取は初回69件、`/tmp` からの再実行75件の判定を通過した。Firefoxの追加12試行ではPCM 91,200点、音響観測1,425行、調音計画、拍が基準と一致した。固定上流との差は最大2.33×10⁻¹⁰で最初の差はフレーム4,114。上流の歌唱・エンジン試験は各17件を通過した。圧縮プロファイルを含む新規成果約76.11 MBはRTL9210B-CGに保存した。[初回](../runs/worklet-song-firefox-ipc-queue-20261121-a/manifest.json)・[追加採取](../runs/worklet-song-firefox-ipc-queue-20261121-repeat/manifest.json)・[全生ログの再解析](../runs/worklet-song-firefox-ipc-queue-20261121-verified/manifest.json)

研究ワークスペースから、保存済みの全20試行を再解析できる。追加採取には `CHIMERA_FIREFOX` で同じFirefoxを指定して `--fresh` を付ける。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 \
  ../../.venv/bin/python tools/measure_worklet_song_firefox_ipc_queue.py worklet-song-firefox-ipc-queue-next \
  --include-queue-run worklet-song-firefox-ipc-queue-20261121-a \
  --include-queue-run worklet-song-firefox-ipc-queue-20261121-repeat
```
