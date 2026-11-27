# Firefoxのネイティブプロファイルで実時間歌唱の登録を測る

## 固定上流と観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start` は、既存Contextがあれば再開し、初回は `build` にサンプルレートを渡す。 `build` はContextの再開を要求してからモジュールURLを `addModule` に渡す。Promiseが解決したらコンパイル済みWASMを持つノードを作り、既存エンジンの状態と入れ替える。登録に失敗したContextは閉じる。歌唱側の `playTune` は辞書待ちの後に最新版の歌詞と再生トークンを確認し、MIDI番号と拍数を持つ音符から秒単位の計画を作ってエンジンへ渡す。上流試験は母音核の拍、句末の開大と呼気、ホストブロック長でPCMが変化しないことを確かめる。[エンジンの起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L97)・[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[拍](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[句末](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[ブロック長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Mozillaの公開ソースでは、`AudioWorkletImpl` がメインスレッドで登録呼び出しとPromise解決の境界を記録する。 `WorkletFetchHandler` はURLごとの取得状態とPromiseを持ち、初回に `StartModuleLoadRunnable` をグラフ側へ送る。そこでモジュールの読込要求を作り、`StartFetchRunnable` がメイン側でHTTP取得を開始する。 `OnStreamComplete` は取得バイト列を `FetchCompleteRunnable` に渡し、グラフ側でUTF-8を復号してモジュールロードを進める。制御メッセージは `AudioNodeTrack::SendRunnable` 内で実行される。この区間のマーカーから実行スレッドと時間は読める。対象Runnableの名前は別の計測が必要になる。[登録境界](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/media/webaudio/AudioWorkletImpl.cpp)・[Workletの取得と完了通知](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/worklet/WorkletFetchHandler.cpp)・[制御メッセージの実行](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/media/webaudio/AudioNodeTrack.cpp)

候補の通常の歌唱入口に研究用クエリ `songNativeRegistrationTrace=1` を追加した。呼び出し、解決、ノードからの `ready` 受信で、既存の `performance.now()` と同じ値を `performance.mark` の開始時刻に使う。Firefoxではその値をページの作成からのミリ秒としてプロファイルの `UserTiming` に書く。先頭の印のプロファイル時刻を `p₀`、同じ印の `Date.now()` を `e₀` とすると、HTTPとWorkletの時刻 `e` は `p₀ + (e − e₀)` でコンテンツプロセスのミリ秒に移せる。残りの2印の相対間隔を二つのJavaScript時計と照合する。別プロセスの時刻はプロファイルにある原点とともに保存する。[計時の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L36)・[Firefoxの印の実装](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/performance/Performance.cpp)・[プロファイラー](https://firefox-source-docs.mozilla.org/tools/profiler/)

## 事前登録

毎回新しくFirefoxを起動し、48 kHzの通常画面で `...` の歌詞エラーを経由して辞書を準備する。次に `Pop Dee` を120 BPM・MIDI 60と69で歌う。各実行で現行順と並行登録を交互に3回ずつ試す。3つの印、ネイティブの登録区間の境界、`registerProcessor` の直前・直後を5 ms以内に対応させる。登録区間の75%以上が最初の計測文より前になると予測した。要求前に100 ms以上待つ試行では、取得タスクの開始より前に待つという予測を置いた。音声はCLIのPCM全91,200点と観測1,425行、歌唱計画、独立計算した開始からの拍24,000・48,000フレームを照合する。[事前登録](../cases/worklet-song-firefox-registration-native.json)・[CLIと上流の基準](../runs/worklet-live-song-cross-browser-20261121-a/manifest.json)・[前回の計時](../runs/worklet-song-module-evaluation-20261121-repeat/summary.json)

## 初回の判定と照合の修正

初回は43判定中41件が通過した。歌唱は全6試行で基準と一致した。並行登録1回目と現行順3回目の `registerProcessor` は生プロファイルにあり、丸め済みのJavaScript完了印より0.291 msと0.133 ms後に始まっていた。初版の集計はこの印を上限に探し、2件を落とした。先に5 ms以内で対応を確かめたネイティブの登録区間を探索範囲に変更すると、同じ保存プロファイルで両件を含む全6件が照合できた。もとの不合格実行は生ログとともに残した。[初回判定](../runs/worklet-song-firefox-registration-native-20261121-a/summary.json)・[そのときの計測器](../runs/worklet-song-firefox-registration-native-20261121-a/artifacts/source/research/experiments/chimera-rebuild/tools/measure_worklet_song_firefox_registration_native.py)

URLとチャネルIDが一致するコンテンツ側の `Network` マーカーを追加で集計した。ソース上で `STATUS_START` の終了は `HttpChannelChild` がチャネルを開いた時点、`STATUS_STOP` の終了は同プロセスの `OnStopRequest` の観測点である。後者のペイロードにHTTPトランザクションの `requestStart` と `responseEnd` が入る。これらを使うと、送信前と応答受信後を一つのプロファイル時計で計算できる。HTTPサーバー側の要求受信・応答送出は、同じ要求を照合するために併記する。[HTTPチャネルのマーカー](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/HttpChannelChild.cpp)・[トランザクションの時計](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/nsHttpTransaction.cpp)・[集計コード](../tools/measure_worklet_song_firefox_registration_native.py)

## 再実行と待ち時間の位置

修正後の実行と `/tmp` からの再実行は、各43判定を通過した。初回の生ログを同じ手順で読み直した結果を合わせ、18試行すべてでメインの3印、`AudioWorklet.addModule`、`GraphRunner` 内の `registerProcessor` と対象URLを対応づけた。時刻境界の観測差は最大2 ms。ネイティブで測った `registerProcessor` は6.8〜34.0 µsだった。エポック時計の照合に5 msの幅を見込んでも、登録の少なくとも95.9%が最初の計測文より前にあった。[修正後](../runs/worklet-song-firefox-registration-native-20261121-b/summary.json)・[再実行](../runs/worklet-song-firefox-registration-native-20261121-repeat/summary.json)

| コンテンツプロセス内の区間 | 現行順 9試行 | 並行登録 9試行 |
| --- | --- | --- |
| `addModule` 開始からチャネル開設 | 2.0〜4.9 ms | 2.1〜2.3 ms |
| チャネル開設からHTTPトランザクションの送信開始 | 129.3〜138.8 ms | 176.2〜189.8 ms（8試行）、2.9 ms（1試行） |
| 送信開始から応答受信完了 | 1.8〜5.9 ms | 2.3〜6.7 ms |
| 応答受信完了からチャネルの完了マーカー | 3.9〜4.8 ms | 1.3〜5.8 ms（8試行）、173.9 ms（1試行） |
| チャネルの完了マーカーから登録を含む制御メッセージの開始 | 0.5〜4.9 ms | 0.2〜5.1 ms |

HTTP要求前の待ちが長かった17試行では、チャネルはすでに開いていた。取得タスクの開始より前に長く待つという予測は、この17試行の順序に合わなかった。残る並行登録1試行では、親プロセスでも同じチャネルIDの `responseEnd` から `STATUS_STOP` まで173.7 ms経過していた。受信後の待ちは親側の区間にも現れた。この比較は各プロセス内で差を取った。取得開始・完了のRunnable名はプロファイルのマーカーに現れず、送信前または受信後のどの処理が待ったかは未特定である。次は子の `ContinueAsyncOpen` と親の `OnStopRequest` を起点に、同じチャネルの親子間の通知とエンキュー・実行を対応づける。[初回の2回目の並行登録の生プロファイル](../runs/worklet-song-firefox-registration-native-20261121-a/artifacts/2-parallel/firefox-profile.json.gz)・[親HTTPチャネル](https://github.com/mozilla-firefox/firefox/blob/437dd728/netwerk/protocol/http/nsHttpChannel.cpp)

全18試行のWAV、PCM各91,200点、音響観測1,425行、計画、拍は保存済みCLI・ブラウザの基準と一致した。固定上流との最大PCM差は振幅2.33×10⁻¹⁰で、最初に差が見えるのはフレーム4,114だった。物理出力の時刻と、最初の描画量子の処理内訳はこの実験の未計測項目である。[音声の参照](../runs/worklet-live-song-cross-browser-20261121-a/manifest.json)・[再実行の音声判定](../runs/worklet-song-firefox-registration-native-20261121-repeat/summary.json)

## 再現と保存

研究ワークスペースを起点に以下を実行できる。macOS 15.6.1 arm64、Firefox 157.0のビルド20261002115412、Rust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4を使った。3実行で固定上流の歌唱・エンジン試験各17件を通過した。各48成果と各258点の入力スナップショットをSHA-256で照合し、18本の展開済みWAVが同じSHA-256となることを確認した。圧縮プロファイルを含む成果約56.85 MBとサブプロセスの一時領域はRTL9210B-CGに置いた。[初回マニフェスト](../runs/worklet-song-firefox-registration-native-20261121-a/manifest.json)・[修正後マニフェスト](../runs/worklet-song-firefox-registration-native-20261121-b/manifest.json)・[再実行マニフェスト](../runs/worklet-song-firefox-registration-native-20261121-repeat/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  ../../.venv/bin/python tools/measure_worklet_song_firefox_registration_native.py worklet-song-firefox-registration-native-next
```
