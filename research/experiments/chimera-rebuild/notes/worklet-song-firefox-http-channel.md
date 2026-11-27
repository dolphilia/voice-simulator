# Firefoxの親子プロセス間で歌唱WorkletのHTTPチャネルを追う

## 固定上流の入口とFirefoxでの観測点

固定上流の `AudioEngine.start` は既存Contextを再開し、初回は `build` でContextの再開要求、WorkletのURL登録、WASMを渡すノードの作成の順で準備する。歌唱側の `playTune` は辞書を待って現在の歌詞と再生トークンを読み直し、MIDI番号・拍数・テンポを調音計画へ変換する。拍秒は `t₀ + 先行音符の拍数の合計 × 60 / BPM` で独立に求める。上流試験は拍での母音核、句末の声帯開大と呼気、ホストのブロック分割を変えたPCMを照合する。[エンジンの起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L97)・[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[歌唱の拍](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[句末](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[ブロック分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Firefoxの公開ソースでは、`HttpChannelChild::AsyncOpenInternal` が子のチャネル開設を記録する。 `ContinueAsyncOpen` はURLやチャネルIDを含む引数を組み立てて `SendPHttpChannelConstructor` に渡し、親は `HttpChannelParent::DoAsyncOpen` で同じURLとIDを記録する。親の `nsHttpChannel` は接続準備後にキャッシュを照会し、非同期処理中なら結果を待つ。 `OnCacheEntryAvailable` はエントリ、新規フラグと状態コードを受け取り、ネットワーク取得が必要ならトランザクションを開始する。 `nsHttpConnectionMgr::ProcessNewTransaction` と `DispatchTransaction` はURLとチャネルIDを持つ。ソケットスレッドで計時し、プロファイルの表示先を親のメインスレッドに指定する。後者の区間は保留開始から接続への割当までを表す。[子の開設と送信](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/HttpChannelChild.cpp)・[親の受信](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/HttpChannelParent.cpp)・[キャッシュ照会](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/nsHttpChannel.cpp#L1518)・[トランザクション](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/nsHttpConnectionMgr.cpp)

応答完了後は親の `nsHttpChannel::OnStopRequest` が同じチャネルのフローIDで処理される。親のリスナーは `HttpBackgroundChannelParent` から子のソケットスレッドへ完了を知らせる。子では `ProcessOnStopRequest` が処理を `ChannelEventQueue` に渡し、メインで `OnStopRequest` を実行する。両端のHTTP完了マーカーの差には、各スレッドの処理や通知も含まれる。チャネルIDを持つ境界と、実行した関数を示すフローIDを組み合わせて読む。[親の完了通知](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/HttpChannelParent.cpp#L1417)・[子の受信](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/HttpBackgroundChannelChild.cpp#L225)・[チャネルのキュー](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/ipc/ChannelEventQueue.cpp)

## 同じ時計への変換と事前登録

直前の3実行の全18試行を読む。チャネルとウィンドウのID、URLで親子を結び、`requestStart`、`responseStart`、`responseEnd` の親時刻から子時刻を引いた3値の中央値を原点差 `δ` とする。子の時刻 `c` は親のミリ秒で `c + δ` になる。3値の残差を0.1 ms以内、独立にプロファイルのプロセス開始時刻から引いた原点差との差を1 ms以内とした。親の `AsyncOpenFinal` がチャネル開設時刻と0.1 ms以内で一致する一つのフローを採り、同じフローにある停止やキャッシュの関数を対応づける。送信前の長い待ちは親側に寄り、親が要求を受けるまでと親から子への完了は各10 ms以内と予測した。[事前登録](../cases/worklet-song-firefox-http-channel.json)・[元の計測](worklet-song-firefox-registration-native.md)・[解析CLI](../tools/measure_worklet_song_firefox_http_channel.py)

保存プロファイルのIPCマーカーは無効だったため、通常画面から同じ歌唱を現行順と並行登録で追加採取する。 `ipcmessages` と `nsHttp:4` を指定し、チャネルIDを出す子の `ContinueAsyncOpen` の直後に始まるコンストラクタの一つを照合する。親子のPID、メッセージ名、相互のシーケンス番号を確かめ、キューへの投入や実行と結べる区間のみ測る。[IPCのマーカー形式](https://github.com/mozilla-firefox/firefox/blob/437dd728/ipc/glue/MessageChannel.h#L771)・[Firefoxのログの記録方法](https://github.com/mozilla-firefox/firefox/blob/437dd728/xpcom/base/Logging.cpp#L709)

## 保存済み18試行の再解析

現行順の全9試行は、コンテンツのチャネル開設から親の `Receive AsyncOpen` まで128.0〜135.6 ms。親が受け取ってからのキャッシュ待ちには長い区間がなく、親側に待ちが集中するという事前予測はこの条件で外れた。保存プロファイルにIPCマーカーがないため、子の送信処理が始まる前と送信後のどちらかは確定できない。[保存済み試行の比較](../runs/worklet-song-firefox-http-channel-20261121-ipc/summary.json)

並行登録で要求前に待った8試行は、親がチャネル開設を0.4〜1.8 msで受け取り、親の `BeginConnect` 終了からキャッシュコールバック開始まで173.4〜186.1 msを要した。キャッシュコールバック後とHTTPトランザクションの割当は短かった。キャッシュの作業とメインスレッド上のコールバック待ちの内訳は採取されていない。[保存済み試行の比較](../runs/worklet-song-firefox-http-channel-20261121-ipc/summary.json)

応答を受信した後に173.9 msを要した並行登録の1試行では、親の `OnStopRequest` の開始まで173.686 msかかった。親の関数の開始から親の完了マーカーまで0.026 ms、親から子の完了マーカーまで0.195 msだった。長い区間は親のHTTP完了処理が始まる前にあった。同フローの `OnStartRequest` も受信完了の約173.3 ms後に始まった。[該当試行の生プロファイル](../runs/worklet-song-firefox-registration-native-20261121-a/artifacts/2-parallel/firefox-profile.json.gz)・[同じチャネルの計時](../runs/worklet-song-firefox-http-channel-20261121-ipc/summary.json)

## IPCを採れた8試行

現行順と並行登録を各4回追加し、全8回で同じチャネルを開くIPCの送信、親のI/Oスレッドへの到達、親のメインスレッドによる処理を照合した。送信から親のI/Oスレッドへの到達は0.008〜0.071 msだった。現行順の長い待ちが再現した2回では、メッセージ到達からメインスレッド上の処理まで131.357 msと134.828 msかかった。残る現行順2回と並行登録4回の同区間は0.011〜1.336 msだった。[再計測の各マーカー](../runs/worklet-song-firefox-http-channel-20261121-verified/summary.json)

追加の並行登録4回では、最長区間の位置が分かれた。親が受け付けてからチャネル開設まで182.838 msが1回、開設から `BeginConnect` 開始まで174.221 msと178.336 msが2回、`BeginConnect` 終了からキャッシュコールバックまで173.980 msが1回だった。[再計測の各マーカー](../runs/worklet-song-firefox-http-channel-20261121-verified/summary.json)

追加の1回では、親子の完了マーカー間に26.421 msを観測した。同じ子チャネルのログをオブジェクト識別子で結び、停止IPCは親の完了マーカーから0.098 msで子のソケットスレッドに届いて処理が始まったことを確かめた。ソケットスレッド上の `ProcessOnStopRequest` から子のメインスレッドの完了マーカーまでが26.317 msだった。ほかの7回の同区間は0.093〜3.623 ms。最初の停止ログ照合は、採取したFirefoxがオブジェクト識別子の後ろに出すコンマと追加フィールドで取りこぼした。照合を修正して同じプロファイルを読み直し、全8回の開始と停止のIPCを対応づけた。停止イベントのキュー投入から個別イベントが実行されるまでの内訳は欠測である。[初回の追加採取](../runs/worklet-song-firefox-http-channel-20261121-ipc/manifest.json)・[修正前の再実行](../runs/worklet-song-firefox-http-channel-20261121-repeat/manifest.json)・[修正後の再解析](../runs/worklet-song-firefox-http-channel-20261121-verified/summary.json)

## 再現と保存

macOS 15.6.1 arm64、Firefox 157.0（Playwrightのビルド20261002115412）、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4を使用した。上流の関連試験はブラウザを採取した2実行で各17件を通過した。最終再解析は182判定を通過し、保存済み18試行の計時・比較結果は3実行で一致した。追加8試行も含めた全26試行で、PCM各91,200点、音響観測1,425行、歌唱の予定拍が基準と一致した。固定上流との差は最大2.33×10⁻¹⁰で、最初の差はフレーム4,114だった。新規プロファイルと周辺成果約30.04 MBをRTL9210B-CGに保存した。[初回](../runs/worklet-song-firefox-http-channel-20261121-ipc/manifest.json)・[別ディレクトリからの追加採取](../runs/worklet-song-firefox-http-channel-20261121-repeat/manifest.json)・[全26試行の再解析](../runs/worklet-song-firefox-http-channel-20261121-verified/manifest.json)

研究ワークスペースから、同じ26試行を次のコマンドで再解析できる。新しい収録を追加するときは、Firefoxのパスを `CHIMERA_FIREFOX` に設定し、`--fresh-ipc` を付ける。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 \
  ../../.venv/bin/python tools/measure_worklet_song_firefox_http_channel.py worklet-song-firefox-http-channel-next \
  --include-ipc-run worklet-song-firefox-http-channel-20261121-ipc \
  --include-ipc-run worklet-song-firefox-http-channel-20261121-repeat
```
