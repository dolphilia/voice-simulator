# Firefoxの親メインスレッドのスタックでWorklet取得の待ちを調べる

## 固定上流と調査対象

固定上流の `AudioEngine.start` は最初の起動で `build` に進み、Contextの再開を要求してから `audioWorklet.addModule` でモジュールを登録し、ノードにWASMを渡す。 `playTune` は辞書取得後に現在の歌詞と再生トークンを確認する。各音符の開始秒は開始オフセットに `先行音符の拍数の合計 × 60 / BPM` を加えた値で、合成へは音符から組み立てた調音計画を渡す。上流の歌唱試験は拍と母音核、句末の開大と呼気を確認し、エンジンの試験はホストのブロック分割を変えてもPCMが一致することを確認する。[起動の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L97)・[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[拍の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[句末の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[PCM比較の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

WorkletのURL取得で子が送ったHTTPチャネルのコンストラクタを、親のI/Oスレッドで受信し、メインのキューに投入する。前回は同じIPCのフローIDを使って投入と `DispatchMessage` の受信マーカーを対応づけた。今回はこの2点の間に親の `GeckoMain` で採られたスタックを読む。IPCの関連づけには従来どおりPID、メッセージ名、シーケンス番号を使い、フローの文字列は各スレッドの表から復元する。[前回の投入とCPU時間](worklet-song-firefox-ipc-queue.md)・[Firefoxの受信処理](https://github.com/mozilla-firefox/firefox/blob/437dd728/ipc/glue/MessageChannel.cpp#L1686)

## 事前登録と計時

通常画面から48 kHzの `Pop Dee` を歌わせ、現行順と並行登録を交互に採る。前回のIPC・フロー・CPUの計測に `js` と `stackwalk` を加え、`nostacksampling` を外す。スタック採取対象は `GeckoMain` とし、その他のスレッドのマーカーも保存する。100 ms以上で採取区間が90%以上ある現行順では、レイアウト・描画またはFirefoxのJavaScriptを含むスタックがCPU重みの50%以上と予測した。[事前登録](../cases/worklet-song-firefox-ipc-stack.json)・[Firefoxのプロファイラーの機能](https://github.com/mozilla-firefox/firefox/blob/437dd728/tools/profiler/public/ProfilerState.h)

`samples` のスタック番号を `stackTable` の前のフレームへ再帰的にたどり、`frameTable` のカテゴリと `stringTable` の位置を親から葉の順に復元する。各窓にサンプルの前後が収まるとき、現在のスタックに `threadCPUDelta` をミリ秒へ直した重みを付ける。CPU重みの総和は前回のスタックを使わないCPU集計と照合する。アドレスの所属はプロファイル内のライブラリ範囲で確認し、対応するライブラリの先頭からの相対位置を保存する。重みはサンプリングによる近似で、1回の関数呼び出しの継続時間は表さない。[Geckoのプロファイル形式](https://github.com/firefox-devtools/profiler/blob/main/docs-developer/gecko-profile-format.md)・[計測CLI](../tools/measure_worklet_song_firefox_ipc_stack.py)

## 初回のスタックと読み取りの修正

現行順の長い3試行では、投入からIPC受信処理まで137.535〜182.982 msかかった。FirefoxのJavaScriptまたはレイアウト・描画を含むスタックは、CPU重みの98.6〜99.7%だった。さらに、`chrome://juggler/content/NetworkObserver.js` を含むスタックだけで94.6〜95.9%を占めた。深い位置には `getBase64EncodedResponse`、`convertString`、`onStreamComplete` と、その中の `Array.from` に対応する自己ホストのイテレータが現れた。[初回の保存プロファイル](../runs/worklet-song-firefox-ipc-stack-20261121-a/manifest.json)・[初回を読み直したスタック](../runs/worklet-song-firefox-ipc-stack-20261121-deferred/summary.json)

初回の現行順1件は、同じHTTP応答に `nsHttpChannel::OnDataAvailable` が2件あり、1件に限定した集計が落とした。生ログと初回の68/69判定を保存し、同じチャネルの本文到達マーカーをリストとして扱うように修正した。再解析でこの試行の待ちとスタックも対応した。[初回の不合格](../runs/worklet-song-firefox-ipc-stack-20261121-a/summary.json)・[修正したHTTPマーカーの集計](../tools/measure_worklet_song_firefox_http_channel.py)

## Playwrightの応答本文を読む時刻の対照

Playwright 1.64.1のFirefoxに同梱された `omni.ja` の `chrome/juggler/content/NetworkObserver.js` は、公開v1.64.1とSHA-256が一致した。 `getBase64EncodedResponse` はHTTPのエンコーディングが付いた本文を `convertString` で展開してからBase64にする。展開の完了時には `Array.from(data)` と分割した文字列への変換を行う。英語辞書は868,793バイトのgzipで取得され、Playwright側で検証した本文の3,330,130バイトは一次資料の展開済みハッシュと一致した。これまでの採取は再生ボタンを押した直後にWASMと辞書の `response.body()` を呼び出していた。[Playwright v1.64.1の応答本文](https://github.com/microsoft/playwright/blob/v1.64.1/browser_patches/firefox/juggler/NetworkObserver.js#L956)・[同版の展開ループ](https://github.com/microsoft/playwright/blob/v1.64.1/browser_patches/firefox/juggler/NetworkObserver.js#L1041)・[歌唱試験の資産確認](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L1080)

スタックの観測後に対照を登録し、ブラウザが歌唱のために行う取得と、Playwrightが確認用に本文を読む操作のうち、後者だけを歌唱完了後に移した。Playwright側の本文の読込開始・終了をエポックミリ秒で記録し、親プロファイルの開始時刻からの差に換算した。まず6試行を実行し、通常の実時間歌唱採取にも変更を取り入れた。従来の読込位置は実験ケースの `defer_asset_evidence: false` で再現できる。[追試条件](../cases/worklet-song-firefox-ipc-stack.json)・[本文の読込を移した実行](../runs/worklet-song-firefox-ipc-stack-20261121-deferred/manifest.json)

| 観測値 | 従来の本文読込 | 完了後の本文読込 | 既定化後に `/tmp` から再実行 |
| --- | ---: | ---: | ---: |
| 現行順の親メインのIPC待ちの中央値 | 148.654 ms | 0.013 ms | 0.015 ms |
| 現行順のContext作成開始から接続までの中央値 | 227 ms | 63 ms | 59 ms |
| 並行登録のContext作成開始から接続までの中央値 | 223 ms | 59 ms | 55 ms |

延期後の全12試行で投入後のIPC待ちは1.115 ms以下だった。 `NetworkObserver.js` に対応するCPU重み169.383〜200.572 msを、歌唱後に本文を読む区間で確認した。処理を始める時刻を移すと、登録中の長い待ちが解消した。全18試行でPCM全91,200点、音響観測1,425行、予定拍と計画は基準と一致し、固定上流との差は最大2.33×10⁻¹⁰だった。[初回の再解析と対照](../runs/worklet-song-firefox-ipc-stack-20261121-deferred/summary.json)・[既定化後の再実行](../runs/worklet-song-firefox-ipc-stack-20261121-repeat/summary.json)

## 標準の歌唱採取

通常画面のFirefoxとChromiumで、実時間とオフラインのWAV・観測、歌詞エラーからの復帰、接続後の停止と再開、辞書とWASMのハッシュを照合した。標準の採取と `/tmp` からの再実行は各177/179判定を通過した。Firefoxの通常時計では、各実行2試行のp99が冒頭32量子を除いた681量子で3.00 msとなり、2.667 msの基準を超えた。[標準の歌唱採取](../runs/worklet-live-song-cross-browser-20261121-deferred-default/summary.json)・[別ディレクトリからの標準採取](../runs/worklet-live-song-cross-browser-20261121-deferred-default-repeat/summary.json)

別のネイティブ診断4試行では、同じ窓のp99は1.713〜1.800 msで、超過量子は0件だった。同じ診断の通常時計では、ネイティブ計時の基準内に収まった13量子が超過として記録された。ネイティブ計時で超過したのは、最初の実行の各試行で先頭2量子、再実行の各試行で先頭1量子だった。最初の量子は3.43〜4.08 ms。次はこの区間のWASM呼び出しと観測処理を分けて採る。[初回のネイティブ診断](../runs/worklet-live-song-cross-browser-20261121-deferred-default/summary.json)・[再実行のネイティブ診断](../runs/worklet-live-song-cross-browser-20261121-deferred-default-repeat/summary.json)

## 再現と保存

計測にはmacOS 15.6.1 arm64、Playwright 1.64.1のFirefox 157.0（ビルド20261002115412）、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4を使用した。同梱 `NetworkObserver.js` のSHA-256は `1fed9a9e239ca804524fe8492e8522bcd90961bad4e4b8c4325b856adda87209`。XULの公開シンボルを同じ識別子で取得できなかったため、一部のネイティブフレームはライブラリと相対アドレスで保存した。延期した2実行は各121判定を通過し、固定上流の試験は3実行それぞれ17件を通過した。未対応の1件を含む初回の生ログと追試の成果約130.48 MBをRTL9210B-CGに置いた。[初回](../runs/worklet-song-firefox-ipc-stack-20261121-a/manifest.json)・[延期試行](../runs/worklet-song-firefox-ipc-stack-20261121-deferred/manifest.json)・[既定化後の再実行](../runs/worklet-song-firefox-ipc-stack-20261121-repeat/manifest.json)

標準の採取には同じFirefoxと、ChromiumとしてChrome 157.0.8103.79を使用した。各85成果、合計約125.68 MBをRTL9210B-CGに保存した。再実行時は `CHIMERA_CHROMIUM` に `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` を指定して `tools/measure_worklet_live_song_cross_browser.py` を実行する。[標準採取のマニフェスト](../runs/worklet-live-song-cross-browser-20261121-deferred-default/manifest.json)・[標準採取の再実行マニフェスト](../runs/worklet-live-song-cross-browser-20261121-deferred-default-repeat/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 \
  ../../.venv/bin/python tools/measure_worklet_song_firefox_ipc_stack.py worklet-song-firefox-ipc-stack-next --defer-asset-evidence
```
