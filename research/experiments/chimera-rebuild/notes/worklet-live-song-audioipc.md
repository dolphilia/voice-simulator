# FirefoxのAudioIPCで出力要求が遅れる位置を調べる

前回のクライアント側のプロファイルでは、192フレームの事前描画後に次の出力要求が5.31〜7.43 ms遅れた。256フレームの要求とグラフが描画した256フレームは全要求で一致した。今回はAudioIPCの他端を時刻で照合し、広がった間隔をサーバー側でも観測できるかを確かめる。[出力要求とグラフ前進の前回の比較](worklet-live-song-output-callback.md)

## 読解と事前登録

固定上流の `AudioEngine.build` はAudioContextとWorkletノードを作り、`ChimeraProcessor.process` は出力チャンネルのフレーム数をエンジンに渡す。上流の `output_does_not_depend_on_the_host_block_size` は同じ絶対フレームに操作を置き、ホストの要求長を変えたときの出力を照合する。候補でもAudioWorkletの量子と64フレームの観測区間を分けており、48 kHzでは前者が128フレームで約2.667 msに当たる。Geckoの出力要求はこの構成で256フレーム、約5.333 msだった。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[分割長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

AudioIPCのサーバー側ではcubebの音声スレッドが `ServerStreamCallbacks::data_callback` を呼び、`nframes` を `CallbackReq::Data` に載せる。`Proxy::call` は要求をキューへ積み、イベントループを起こして応答を待つ。受け手の `CallbackServer::process` は入力・出力の1フレームのバイト幅と共有メモリからバッファを用意し、Geckoの `DataCallback` を呼び、返ったフレーム数を応答に載せる。サーバーは応答で示された分の出力を共有メモリからcubeb側のバッファへコピーする。この順序に沿って、サーバーの音声コールバック開始、RPCスレッドの送受信、クライアントの `DataCallback` を観測点にする。[サーバーの音声コールバック](https://github.com/mozilla/audioipc/blob/75dd7e16020eeeee4281239726df6e8090c3813b/server/src/server.rs#L208)・[要求を積んで応答を待つ処理](https://github.com/mozilla/audioipc/blob/75dd7e16020eeeee4281239726df6e8090c3813b/audioipc/src/rpccore.rs#L162)・[クライアントでの処理](https://github.com/mozilla/audioipc/blob/75dd7e16020eeeee4281239726df6e8090c3813b/client/src/stream.rs#L56)

Firefoxはモジュール名に `::` を含む `MOZ_LOG` 設定をRust側へ渡す。タイムスタンプ付きログでAudioIPCの開始と接続内の送受信を調べ、クライアントのプロファイルを時間軸に加える。予備の1組で取得できる端点を確認し、本比較では固定した条件で4組を採取する。直後に増えた間隔がサーバーのコールバック開始にも現れ、両端の開始間隔の差は0.5 ms以内と予測する。[FirefoxからRustのログへの設定](https://searchfox.org/firefox-main/source/xpcom/base/Logging.cpp#2507)・[事前登録](../cases/worklet-live-song-audioipc.json)

## 取得経路の確認

最初の1組は共有Contextの34判定を通過した。`MOZ_LOG` でAudioIPCのモジュールを有効にしたが、生成されたログは空だった。Rustの `RUST_LOG` とcubebの詳細ログで採り直すと、親プロセスのcubebログに256フレーム、2チャンネル、2,048バイトの出力バッファが現れた。AudioIPCの要求と応答の行は追加されなかった。cubebの `ALOGV` は実時間スレッドで整形した文字列をキューへ入れ、別の `cubeb_log` スレッドが取り出す。この出力の時刻から、元のコールバック時刻を求めることはできない。[最初の予備採取](../runs/worklet-live-song-audioipc-20261121-pilot/manifest.json)・[別のログ設定での採取](../runs/worklet-live-song-audioipc-20261121-cubeb-pilot/manifest.json)・[診断ケース](../cases/worklet-live-song-audioipc-diagnostic.json)・[cubebの非同期ログ実装](https://github.com/mozilla/cubeb/blob/master/src/cubeb_log.cpp)

macOSの `xctrace` では `Audio System Trace` に `syscall` と `audio-hal-client-io-cycle` の表がある。短いテストプロセスで採取・エクスポートを確認し、Firefoxを使う追加の1組を登録した。最初は `xctrace` の起動対象を `env` と書いたため、実ファイルの位置を解決できず収録前に停止した。`/usr/bin/env` を明示して採り直した。[システムトレースの条件](../cases/worklet-live-song-audioipc-system-trace.json)・[起動に失敗した実行](../runs/worklet-live-song-audioipc-20261121-system-pilot/manifest.json)

### 採取範囲と欠測

`/usr/bin/env` から起動した `Audio System Trace` は、事前描画条件で約0.181秒ぶんだった。Firefoxの親プロセスはトレース開始の約1.81秒後、歌唱を処理した子プロセスは約4.52秒後に起動していた。書き出した `syscall` と `audio-hal-client-io-cycle` の表はともに0行だった。親子のプロファイルと歌唱の34判定は残った。続けてNodeを絶対パスで直接起動した `System Trace` では、未準備条件で10秒間を収録し、Firefoxのプロファイルを取得した。対象限定の `syscall` 表は0行であり、独立プロセスで動くFirefoxの送受信の観測には使えなかった。[envによる再採取](../runs/worklet-live-song-audioipc-20261121-system-pilot-b/manifest.json)・[Node直接起動の条件](../cases/worklet-live-song-audioipc-system-direct.json)・[直接起動の実行](../runs/worklet-live-song-audioipc-20261121-system-direct/manifest.json)

`System Trace` の全プロセス収録を12秒の条件で1組試した。2件で合計約5.6 GiBの途中ファイルと、Firefox側の歌唱WAV・プロファイルが残った。当時の処理はブラウザの終了時にxctraceへ割り込みを送り、保存を最大60秒待って終了する。保存完了の行はなく、エクスポートは `Document Missing Template Error` を返した。この2件ではクライアント側だけでも未準備・事前描画の構築区間が11.18・17.19 msと長く、次の要求は各12.44・16.02 ms遅れた。通常の予備ログ採取での構築は1.79・7.50 ms、次の要求の遅れは−0.02・5.36 msだった。全プロセス収録下の値は本比較から除外した。[全プロセス収録の条件](../cases/worklet-live-song-audioipc-system-pair.json)・[失敗時のマニフェスト](../runs/worklet-live-song-audioipc-20261121-system-pair/manifest.json)

### ローカルソケットによる対照

Pythonの `socket.socketpair()` で7バイトの既知データを送受信した。Pythonを直接起動する `System Trace` の約2.36秒には、2,322行のシステムコールのうち `sendmsg` と `recvmsg` が各406件あり、すべて同じスレッドの送信fd 3と受信fd 4で7バイトが一致した。表の時刻はナノ秒で、XML中の `id` と `ref` を解決してPID・TID・fd・戻り値とともに抽出できる。全プロセス収録から対象PID・TIDだけを抜き出すPythonツールを用意した。[抽出ツール](../tools/filter_worklet_audioipc_syscalls.py)

収録後の保存を自然に終えるように変更し、全プロセスの `Audio System Trace` でもう一度ソケット対照を走らせた。指定は4秒で、書き出した913,671行の範囲は開始から約0.190秒までだった。対照プロセスがPIDを書いたのはトレースに記録された開始より0.688秒前で、送受信は収録前に終わった。トレース約99 MiBに対し、書き出した表は約344 MiBだった。2秒の `System Trace` でも実データの範囲は約0.232秒、対照のPIDの書き出しは開始の0.877秒前だった。両方の `RunIssues.storedata` に `Data stream: Time Mapping` が1件あり、短い有効範囲との因果関係は未確認。表は作業用ディスクの一時領域に置き、抽出後の比較データと区別する。

送受信を20 ms間隔で175回繰り返す対照では、全プロセスの `Audio System Trace` に約0.301秒、1,207,954行のシステムコールが残った。指定PID・TIDの `sendmsg` と `recvmsg` は各12件で、12組すべてで送信7バイト、受信7バイトと実行順が一致した。試した環境では「収録開始」の表示に従って起動するだけでは必要な時間帯を確保できないため、次回は先行音のマーカーとトレースの実時刻で構築前後17要求を含むことを確かめる。

反復対照の結果は作業ディスクの `/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-audioipc-audio-repeat.iXr8XH/fixture-io.json` にある。SHA-256は `e167c0e60242958eacfdb3ac45f8952c63dc4182d10797d60ab96eea6e3e9bc6`。単発売信2件と反復1件の比較に使った抽出JSON、トレース、目次を残し、再生成できる3件の全プロセスXML計1,297,459,336バイトを一時領域から取り除いた。

## 再現と保存

macOS 15.6.1 arm64、Xcode 26.2（17C52）、PlaywrightのFirefox Nightly 157.0（ビルドID `20261002115412`）、Node 24.19.0、Bun 1.4.4、Python 3.14.4で実行した。以下は `research/experiments/chimera-rebuild` から実行する。

```bash
PLAYWRIGHT_BROWSERS_PATH=/Volumes/RTL9210B-CG/voice-simulator/build/playwright \
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_shared_context.py \
  worklet-live-song-audioipc-local-1 --audioipc-log pilot
```

予備採取の合否は歌唱のPCM・観測・スコアと共有Contextの採取を検証する。AudioIPCの端点時刻の判定状態は `audioipc_acquisition.endpoint_timing_evaluated` で確認する。本比較の定義は未準備と事前描画の4組で、準備後に出力要求の間隔が広がる位置を両側で照合する条件は未判定。[本比較の事前登録](../cases/worklet-live-song-audioipc.json)

この手順の最終確認では、最初に `PLAYWRIGHT_BROWSERS_PATH` を省略して既定キャッシュ上のFirefoxを開けなかった。作業ディスク上の既存Firefoxを指定した再実行は34判定を通過し、成果39件のサイズとSHA-256を照合した。AudioIPCの圧縮ログ16件を展開するとすべて空だった。[起動できなかった実行](../runs/worklet-live-song-audioipc-20261121-pilot-verified/manifest.json)・[最終確認](../runs/worklet-live-song-audioipc-20261121-pilot-verified-b/manifest.json)

ソケット対照の収録・書き出しは下記で再実行できる。実データの開始・終了は `toc.xml` の日時と `syscall.xml` の範囲で確かめる。 `--tid` を指定するとさらにスレッドを限定できる。

```bash
out=$(mktemp -d /Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-audioipc-local.XXXXXX)
../../.venv/bin/python tools/capture_worklet_system_pair.py "$out" \
  --template 'Audio System Trace' --time-limit 2s -- ../../.venv/bin/python -c '
from pathlib import Path
import os, socket, sys, time
Path(sys.argv[1]).write_text(str(os.getpid()))
a, b = socket.socketpair()
for seq in range(175):
    payload = f"{seq:07d}".encode()
    a.sendmsg([payload])
    assert b.recvmsg(32)[0] == payload
    time.sleep(0.02)
' "$out/socket-fixture.pid"
xcrun xctrace export --input "$out/audio-system.trace" --toc --output "$out/toc.xml"
xcrun xctrace export --input "$out/audio-system.trace" \
  --xpath '/trace-toc/run/data/table[@schema="syscall"]' --output "$out/syscall.xml"
../../.venv/bin/python tools/filter_worklet_audioipc_syscalls.py "$out/syscall.xml" \
  --pid "$(cat "$out/socket-fixture.pid")" > "$out/fixture-io.json"
```

## 先行音を鳴らした状態で収録する

固定上流の `AudioEngine.build` はContextを再開し、モジュールを登録して `AudioWorkletNode` を作る。 `ChimeraProcessor.process` は出力チャンネル長を `engine_render` に渡し、WASMメモリ上のPCMを各チャンネルへ複製する。歌唱のPCMはWorkletが要求されたフレーム数だけ描画した出力で、今回追うのはその手前にあるFirefoxの音声機器向け256フレームの要求である。実験の待ち合わせは候補の研究用Playwrightに置いた。先行音のWorkletが192量子を処理したと通知すると、歌唱ノードを作る直前のモジュール登録を保留する。その間も先行音は流れ、各128フレームの処理をGraphRunnerで観測できる。Pythonは準備通知後にxctraceを起動し、構築を解放した時刻を記録する。[上流でWorkletを作る箇所](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流のフレーム分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[待ち合わせを置いた先行音](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)

音声のRPCはmacOSではUnixストリーム上の送受信を使う。受信は `recvmsg` で得たバイトを接続バッファへ入れてからメッセージを復号する。応答はバッファを経由して `sendmsg` で送る。クライアントの受信終了～応答送信開始にGeckoの `DataCallback` を合わせ、その両端の時刻差を通じて時計のずれを調べる。サーバー側は同一接続の送信・応答受信の列を探し、各方向で戻り値のバイト数と前後関係が揃う候補を採用する。ソケットが分割・結合した系列や候補が複数の系列は、この1メッセージずつの対応条件を満たさない。[Unixの接続](https://github.com/mozilla/audioipc/blob/75dd7e16020eeeee4281239726df6e8090c3813b/audioipc/src/sys/unix/mod.rs#L33)・[受信バッファと復号](https://github.com/mozilla/audioipc/blob/75dd7e16020eeeee4281239726df6e8090c3813b/audioipc/src/ipccore.rs#L473)・[時刻の照合ツール](../tools/measure_worklet_live_song_audioipc.py)

### 構築を入れる位置の予備比較

通知の980 ms後に解放した最初の1組は、先行音1,536量子と歌唱の34判定が通った。収録の実データは未準備で254.868 ms、事前描画で310.289 ms。構築開始は収録開始から260.198 ms、317.866 msだった。どちらも構築直前の7要求が時刻上の範囲に入り、構築とその後の要求は外れた。同じ歌唱のログだけの比較に対し、構築時間は未準備で0.414 ms、事前描画で5.607 ms増えた。原条件の判定には数えず、解放を150 ms早める次の予備条件を登録した。[980 msの登録ケース](../cases/worklet-live-song-audioipc-system-gated.json)・[980 msの採取](../runs/worklet-live-song-audioipc-20261121-gated-a/manifest.json)・[830 msの登録ケース](../cases/worklet-live-song-audioipc-system-centered.json)

解放を830 msへ早めた事前描画試行では、収録開始から48.864〜139.708 msに17要求が入った。構築時間は7.322 msで、ログだけの比較より0.433 ms長かった。次の要求間隔は10.683 msで、比較との差は−0.017 msだった。syscall表1,082,495行の中で、親子のPIDは目次に載っていた。Geckoで特定した両AudioIPCスレッドに該当する行は0件だった。未準備試行では端末の通知が実際の収録開始に1,056.982 ms先行し、17要求が収録より早く終わった。先行音と歌唱のフレーム番号の対応も2判定で不合格になった。PCM・観測・スコアの照合は通過した。[830 msの採取と判定](../runs/worklet-live-song-audioipc-20261121-gated-centered/manifest.json)

端末の表示から収録までの間隔が4試行で674〜1,057 msに変わったため、Xcode 26.2の `xctrace record --notify-tracing-started <name>` を使う条件を登録した。Darwin通知を各試行固有の名前で受け取り、通知から80 ms後に構築を解放する。受信待ちに使うファイル記述子はmacOS SDKの `notify_register_file_descriptor` で取得し、 `notify_cancel` で解放する。通知を送って受信し、解放後に記述子が無効になることをローカルの対照で確かめた。[Darwin通知を使うケース](../cases/worklet-live-song-audioipc-system-notified.json)・[収録の起動と解放](../tools/capture_worklet_system_pair.py)

実際の `Audio System Trace` では、Darwin通知は目次の開始から1,116.421 ms、823.170 ms後に到着した。一方、書き出し可能な長さは177.450 ms、198.893 msだった。通知時点で対象になるデータはすでに終わっていた。2,304量子へ延長した先行音はAudioContextが閉じるまでに記録が終わらず、通常の歌唱採取もタイムアウトになった。構築を含むFirefoxプロファイルは両方で残った。[Darwin通知の採取結果](../runs/worklet-live-song-audioipc-20261121-gated-notified/manifest.json)

`xctrace record --instrument 'System Call Trace'` だけで起動すると、xctraceはBlankテンプレートにシステムコールの計測器だけを載せる。既知の `sleep` プロセスを起動する1秒の対照で1.487秒の目次と `syscall` 表の定義を得た。Firefoxの比較は先行音を1,536量子に戻し、システムコールだけを2秒収録する条件にした。[システムコールのみのケース](../cases/worklet-live-song-audioipc-system-calls.json)

### システムコールだけを採った1組

未準備と事前描画の実データの長さは2,322.346 msと2,319.093 msだった。Darwin通知の到着は目次の開始より314.995 ms、310.955 ms後だった。収録開始から構築前後17要求が占める範囲は、未準備で366.660〜452.130 ms、事前描画で369.040〜459.821 ms。先行音、歌唱PCM、観測、スコアの34判定を通過した。さらにFirefoxの予算マーカー、グラフ前進のマーカー、先行音のフレーム印を独立に照合した。34要求すべてで要求とグラフ前進が256フレーム、先行音は連続2量子だった。以前の予備採取に対するノード構築時間の差は−0.105 msと+0.346 ms、次の要求間隔の差は−0.013 msと−0.030 msで、登録した2 msの範囲内だった。[システムコールのみの採取](../runs/worklet-live-song-audioipc-20261121-gated-syscalls/manifest.json)・[出力要求とフレームの照合器](../tools/measure_worklet_live_song_output_callback.py)

未準備1,448,879行、事前描画1,578,913行のsyscall表から、Firefoxの対象PIDとTIDのソケット操作を抽出した。クライアントの `recvmsg` 終了と `sendmsg` 開始に `DataCallback` の両端を揃えると、時計の定数補正は+0.135 msと−0.176 ms、照合に残った最大残差は0.004 msと0.008 msだった。34要求のすべてで、サーバーの送信 → クライアントの受信 → クライアントの応答送信 → サーバーの応答受信を順序どおりに一意に対応づけた。両条件ともローカルのfdはサーバー76、クライアント16で、4点の戻り値は各16バイトだった。

| 条件 | 構築を含む要求の往復 | 応答受信からサーバーの次の送信 | サーバーの送信間隔 | クライアントの処理開始間隔 |
| --- | ---: | ---: | ---: | ---: |
| 未準備 | 2.425 ms | 2.894 ms | 5.319 ms | 5.317 ms |
| 192フレーム事前描画 | 7.694 ms | 2.979 ms | 10.672 ms | 10.670 ms |

送信から相手の受信を完了するまでは8.75〜21.75 µsだった。構築直後の間隔はサーバー送信時点で既に5.339 msほど予算を超え、クライアント側との差は約2.3 µsだった。未準備から事前描画へのサーバー間隔の増加5.353 msを分けると、構築を含む要求の往復時間が5.269 ms増え、応答から次の送信までは0.085 ms増えた。この1組のソケット時刻はサーバー側まで遡れた。音声機器による実時間コールバックの入口時刻、応答後に機器へ渡すPCMと、4組での再現性は引き続き調べる。

出力の詳細は、作業ディスクの `/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-audioipc-only-calls.XBJtVw/comparison.json` に保存した。SHA-256は `68c82790b1da32ca51647daa64176522df0b9c27763c793c2bfb2e5e365a1010`。今回の4実行では生トレースとトレース目次、抽出した比較JSONを残し、再生成可能な8件の一時XML計3,951,322,961バイトを作業領域から取り除いた。

### 1組を再現する

```bash
PLAYWRIGHT_BROWSERS_PATH=/Volumes/RTL9210B-CG/voice-simulator/build/playwright \
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=6000000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_shared_context.py \
  worklet-live-song-audioipc-local-2 --audioipc-log system-calls

capture=runs/worklet-live-song-audioipc-local-2
physical=/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/worklet-live-song-audioipc-local-2/artifacts
out=$(mktemp -d /Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-audioipc-local.XXXXXX)
for trial in 1-control 1-draw192; do
  mkdir "$out/$trial"
  xcrun xctrace export --input "$physical/$trial/audio-system.trace" --toc --output "$out/$trial/toc.xml"
  xcrun xctrace export --input "$physical/$trial/audio-system.trace" \
    --xpath '/trace-toc/run/data/table[@schema="syscall"]' --output "$out/$trial/syscall.xml"
done
../../.venv/bin/python tools/measure_worklet_live_song_audioipc.py \
  "$capture" "$out" > "$out/comparison.json"
```

## 4組のソケット送受信の比較

固定したCHIMERAでは、`AudioEngine.build` がAudioWorkletを接続し、`ChimeraProcessor.process` が出力チャンネルの長さを `engine_render` に渡す。ホストが異なるブロック長で呼んでも、発声操作を絶対フレームでそろえたエンジンテストではPCMが一致する。今回の比較は、このサンプル列を出力する時刻を扱う。Firefoxで回収した予算マーカーの時間に48 kHzを掛けて、要求のフレーム数を求める。グラフの前進には別のマーカーを使い、先行音の128フレームの印が各要求に2件入ることを確認する。サーバーの送信開始から同じ要求の応答受信までと、応答受信から次の送信までをそれぞれ整数ナノ秒の差で測り、その和を送信から次の送信までの差に戻して確認する。[固定上流の呼び出し元](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[固定上流の描画処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

予備採取の手順を、既存の共有Contextケースと同じく未準備・192フレームの事前描画、事前描画・未準備の順を交互に2回ずつ実行した。4試行中3試行以上の事前描画で、サーバー送信の間隔が256フレームの予算より2 ms以上長く、クライアントの処理開始間隔との差が0.5 ms以内になると予測した。各試行の合否と欠測を保存し、計測を加えない予備採取より構築時間または次の要求間隔が2 msを超えて増えた試行は有効数に含めない。生トレース、Firefoxプロファイル、フレーム印、解放時刻のサイズとハッシュは採取記録に照合する。解析はトレースと時刻の対応表を保存し、一時XMLを読み終えたら解放する。[4組の登録条件](../cases/worklet-live-song-audioipc-system-calls-series.json)・[4組の解析ツール](../tools/measure_worklet_live_song_audioipc_series.py)

最初の未準備では、歌唱成果とトレースを書き出した後にブラウザ計測の終了待ちが45秒でタイムアウトした。保存された8試行の歌唱WAVは予備採取とバイト単位で一致し、観測と計画の署名も基準と一致した。この未準備試行の元の不合格は採取記録に残し、残ったプロファイルとトレースは欠測の位置を確認するために分析した。4組目では採取ヘルパーの `--instrument` を繰り返せるようにした版が起動した。新旧の引数解釈を同じ一計測器の入力で実行し、構築の解放時刻、計測器の一覧、対象コマンドが一致することを確かめた。以降の採取では開始時のソーススナップショットからこのヘルパーを起動する。[採取のマニフェスト](../runs/worklet-live-song-audioipc-20261121-series-a/manifest.json)

事前描画の4試行すべてが登録した予測を満たした。サーバー送信間隔は未準備の有効3試行では5.312〜5.323 ms、事前描画4試行では10.662〜10.681 msだった。事前描画では各試行で予算の5.333 msを5.328〜5.348 ms超え、クライアントの処理開始間隔との差は2.042〜5.418 µsだった。構築時間の増加は最大0.891 msだった。エンジンの固定上流テスト17件を通過し、8試行の136要求で予算、グラフ前進、先行音のフレーム印を照合した。ソケットの16バイトの往復は133要求で一致した。最初の未準備は構築後6〜8番目の3要求がトレースの実データ範囲を外れた。[4組の結果要約](../runs/worklet-live-song-audioipc-20261121-series-analysis/summary.json)

| 組 | 未準備の送信間隔 | 事前描画の送信間隔 | 構築を含む要求の往復時間の差 | 応答から次の送信までの時間の差 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 5.316 ms（診断値） | 10.674 ms | 欠測 | 欠測 |
| 2 | 5.313 ms | 10.681 ms | +5.383 ms | −0.015 ms |
| 3 | 5.323 ms | 10.674 ms | +6.117 ms | −0.766 ms |
| 4 | 5.312 ms | 10.662 ms | +5.475 ms | −0.126 ms |

有効な3組では、応答受信後から次の送信まではわずかに短くなった。送信間隔が広がった約5.35 msは、構築を含む要求の往復時間の増加に対応した。保存した整数ナノ秒から両時間の和と次の送信間隔を再計算し、独立に一致を確かめた。[時刻照合のマニフェストと試行別の成果](../runs/worklet-live-song-audioipc-20261121-series-analysis/manifest.json)

研究ワークスペースで次の順に再実行する。採取とトレースの書き出しは別々に実行する。採取コマンドが不合格でも、保存されたマニフェストと結果要約から試行ごとの記録を解析できる。

```bash
PLAYWRIGHT_BROWSERS_PATH=/Volumes/RTL9210B-CG/voice-simulator/build/playwright \
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=6400000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_shared_context.py \
  worklet-live-song-audioipc-local-series --audioipc-log system-calls-series

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=5000000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_audioipc_series.py \
  worklet-live-song-audioipc-local-analysis worklet-live-song-audioipc-local-series
```

## 音声機器のI/O区間を追加した1組

AppleのAudio Clientは、アプリのI/Oプロセスが実行された区間を観測する。AudioIPCのソケットを操作するスレッドと音声I/Oを処理するスレッドの関係を確認するため、System Call TraceにAudio Clientだけを追加した。音声機器からのコールバックで始まる処理は、その要求がAudioIPCを通って返るまで待つ。採取したI/O区間については、Firefoxのサーバーを持つプロセスIDを使い、各要求の送信開始から応答受信末尾までを同じスレッドの一意なI/O区間が包む場合に、開始時刻を比較する。[AppleのAudio Clientの説明](https://developer.apple.com/documentation/audiotoolbox/analyzing-audio-performance-with-instruments)・[AudioIPCのサーバー側コールバック](https://github.com/mozilla/audioipc/blob/75dd7e16020eeeee4281239726df6e8090c3813b/server/src/server.rs#L208)・[この1組の条件](../cases/worklet-live-song-audioipc-audio-client.json)

最初の1組では、未準備と事前描画の各17要求で、256フレームの要求、グラフ前進、先行音2量子、16バイトの送受信とAudio ClientのI/O区間を照合した。I/O区間を記録したスレッドは、どちらもFirefoxの親プロセスにあり、ソケットを送信するスレッドとは別だった。構築を含む要求の送信開始は、I/O区間の開始から未準備22.167 µs、事前描画20.375 µs後だった。次のI/O開始までの間隔は5.320 msから10.656 msへ広がり、次の送信までの間隔は5.317 msから10.707 msへ広がった。事前描画の構築時間はトレースなしで取得した基準から2.312 ms増え、計測による増分の2 ms条件を超えた。時刻の対応は保存し、同じ設定で比較をやり直す。[初回のAudio Client採取](../runs/worklet-live-song-audioipc-20261121-audio-client-a/manifest.json)

初回の照合結果は作業ディスクの `/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-audioipc-audio-client.1IwOLc/comparison.json` にある。SHA-256は `80d7b855301d99aab9f962b21d0a228091f6aeb2a11e6beb79d93e4d9b9a3d1b`。生トレース、目次、I/O区間と照合結果を残し、再生成できるシステムコールXML 2件、1,183,155,100バイトを整理した。

同じ設定で採り直すと、構築時間の増加は未準備1.263 ms、事前描画0.669 msで、双方とも2 msの範囲内だった。通常の歌唱と先行音の34判定に合格し、双方の各17要求をソケットとI/O区間に対応づけた。予備採取と同じ観測・計画の署名を確認した。ゲートを待つ間も流した先行音のフレーム印から、対応した各要求は256フレームであることを独立に確認した。[再採取のマニフェスト](../runs/worklet-live-song-audioipc-20261121-audio-client-repeat/manifest.json)

| 条件 | I/O開始から構築を含む要求の送信まで | 構築を含むI/O区間 | 次のI/O開始まで | 次のサーバー送信まで |
| --- | ---: | ---: | ---: | ---: |
| 未準備 | 18.000 µs | 4.599 ms | 5.319 ms | 5.314 ms |
| 192フレーム事前描画 | 25.625 µs | 8.388 ms | 10.658 ms | 10.661 ms |

事前描画のI/O区間は5.333 msを超え、次のI/O開始は約2要求分後だった。I/O開始間隔とソケット送信間隔との差は未準備5.084 µs、事前描画3.959 µsだった。この採取ではサーバー送信より前の、Core Audioがアプリの出力処理を始める時点で間隔が広がっていた。I/O区間の長さは3.789 ms、区間末尾から次のI/O開始までの時間は1.549 ms伸びた。2値の和は開始間隔の増分5.338 msと一致する。音声機器が受け取ったPCMや実際の欠落の有無は、別の位置でサンプルを採る必要がある。

再採取の抽出結果は作業ディスクの `/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-audioipc-audio-repeat.m6g0Gp/comparison.json` にある。SHA-256は `3d04d16ef4f2ac8369ace4357bc329adb5be19d10ad7cc5834a87e571d1a2e2b`。生トレース、目次、I/O区間のXML、照合結果を残し、システムコールの一時XML 2件、814,789,974バイトを整理した。

再実行には「1組を再現する」の `--audioipc-log system-calls` を `--audioipc-log audio-client` に変更し、2試行のトレースから以下の表も書き出す。ソケットとI/O区間の照合は同じ `measure_worklet_live_song_audioipc.py` で行う。

```bash
for trial in 1-control 1-draw192; do
  xcrun xctrace export --input "$physical/$trial/audio-system.trace" \
    --xpath '/trace-toc/run/data/table[@schema="audio-hal-client-io-cycle"]' \
    --output "$out/$trial/audio-client.xml"
done
```
