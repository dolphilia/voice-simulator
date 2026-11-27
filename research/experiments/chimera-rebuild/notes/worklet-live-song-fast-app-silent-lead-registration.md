# 歌唱画面の無音先行で2つのWorklet登録を重ねる

前回、8量子の無音先行は歌唱開始待ちの飛びを抑えたが、直接出力でクリックから歌唱先頭の描画までの時間は組内差の中央値で24 ms延びた。今回は前回の直列登録を基準とし、8量子と接続順を保ったまま登録要求だけを重ねた。歌唱画面で `?songSilentLead=8&songSilentLeadRegistration=parallel` を指定すると比較できる。`songStartupTrace=1` を加えると区間計時を観測JSONに保存できる。[前回の実測](worklet-live-song-fast-app-silent-lead.md#実測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-registration.json)

## 上流の起動と音声時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `boot()` はWASMを初期化してから画面を読み込む。歌唱ボタンは `SingPanel` から `playTune()` を呼び、操作中に再生の準備に入る。`AudioEngine.start()` はContextがあれば再開し、初回は `build()` でインタラクティブ設定のContextを再開しながら、合成Workletを1本登録する。登録が成功してから、既にコンパイル済みのWASMモジュールを渡してノードを生成する。新しいContextの登録に失敗した場合はそのContextを閉じる。上流の起動で登録するのは合成Workletの1本で、無音先行の枝とその登録順は候補側の比較条件に当たる。[起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/main.tsx#L10)・[歌唱ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L192)・[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)

`playTune()` は再生準備と辞書を待ち、音節・MIDI番号・拍数をジェスチャーに変換する。拍の長さは `60 / bpm` 秒。Workletの `schedule` はこの相対秒の計画をWASMへ渡し、Rustの `Engine::schedule()` が `voice.clock + lead` をジェスチャーの始点と終点に足す。Workletの `process()` は量子のフレーム数を `engine_render()` に渡す。ABIはPCMバッファを返し、`Engine::render()` は累積フレーム `pos` の剰余で内部ブロックの位置を保つ。短音の試験は母音の時刻と拍を照合し、ホストのブロック分割の試験は128フレームを基準にして異なる分割とPCMのビット列を照合する。[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASM ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 登録と先行枝の切り分け

候補の `renderRealtimeSongVoice()` は、両条件で辞書と歌唱を計画してから歌唱Workletの登録を要求する。直列では歌唱Workletの解決後に先行Workletを要求し、並行では両方の登録を要求して `Promise.all()` を待つ。いずれも2本が解決した後に `prepareSongSilentLead()` が無音のバッファを同じContextに接続する。先行Workletが128フレームの0入力を8回連続して受け取ると通知し、それから歌唱ノードを作る。歌唱ノードの予約は、歌唱Workletの連続区間の先頭に `8 × 128 + 2,048 = 3,072` フレームを加える。[歌唱の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L270)・[先行枝](../../../../web/prototypes/chimera-research/src/song-silent-lead.ts)・[先行量子の計数](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts)

登録区間は `max(歌唱の解決, 先行の解決) − 歌唱登録の要求` とする。2本の区間が重なる時間、接続直前から8量子の通知までの時間、予約で歌唱先頭を処理するまでのクリック時間もそれぞれ求める。前二者はメインスレッドの `performance.now()`、クリックと描画開始はそれぞれの `Date.now()` を使う。登録の重なりはメインスレッドで観測する。短縮の主判定は追加の観測Workletを用いない直接出力で行い、観測付きの試行では保存PCMを絶対フレームで照合する。[比較処理](../tools/measure_worklet_live_song_app_silent_lead.py)

## 初回方式と末尾の観測

初回と別ディレクトリからの再実行で、直接出力の全16試行は取得判定を通過した。登録の組内差の中央値はそれぞれ約 −1.7 msと −0.95 ms、クリックから歌唱先頭までの中央値は −5.5 msと −6.0 ms。並列観測の再実行では `observed-1-parallel` が絶対フレームの判定で失敗した。歌唱開始6,400から49,200フレームは生の並列観測PCMもオフラインも一致した。並列観測で最後の歌唱48フレームと補完80フレームを含む55,552のすぐ後に、同じ55,552を全サンプル0でもう一度報告した。次は55,808で、55,680が欠けた。歌唱Workletの末尾は55,552で、歌唱中のコールバックは連続していた。ずれが観測された箇所は歌唱終了後の最初の無音量子。原因の候補をグラフ切断に絞り、改訂では並列観測時だけ2つのWorkletの切断を採取終了まで保留した。フレームの採否は変更していない。[初回](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-a/summary.json)・[再実行の失敗](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat/summary.json)・[末尾のフレーム列](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat/artifacts/observed-1-parallel/output-probe.json)・[観測ノード](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs)

## 改訂後の計測

改訂後の全32試行は取得判定を通過した。並列観測16試行すべてで先行と歌唱の2接続が採取末尾まで保持され、前後のフレームの連続性と無音を検証できた。初回方式を含む全64試行で歌唱Workletの開始待ちの飛びは0。歌唱ノードは最初の呼び出しから3,072フレーム後に描画を開始した。歌唱PCM49,200フレームは保存済みオフライン基準とビット一致し、観測769点と歌唱計画も一致した。標準ライブラリで保存WAVのデータチャンクと並列観測の生PCMを読み直し、予約フレームで整列させて再確認した。固定上流との最大PCM差は `2.7573 × 10⁻³`、`10⁻⁶` を超える位置は27,939で、歯のフィルタ下限1,200 Hzの基準と揃った。[改訂後](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-b/summary.json)・[改訂後の再実行](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat-v2/summary.json)

直接出力で求めた組内差（並行から直列を引く）の中央値は次のとおり。

| 実行 | 2本の登録区間 | クリックから歌唱先頭 |
| --- | ---: | ---: |
| 初回方式の初回 | −1.70 ms | −5.5 ms |
| 初回方式の再実行 | −0.95 ms | −6.0 ms |
| 改訂後の初回 | −1.05 ms | +1.0 ms |
| 改訂後の再実行 | +0.35 ms | −1.5 ms |
| 直接出力の全16組 | −1.00 ms | −4.0 ms |

直接出力のクリック時間の組内差は −33〜+17 ms。改訂後の直接出力8組の中央値は +0.5 msだった。登録要求の重なりは直列の0に対して並行で4.4〜11.2 msだったが、先行Workletの要求から解決までの観測時間も直列の中央値1.1 msから並行の4.8 msに延びた。両登録を終えてから先行枝の接続直前〜8量子の通知までは25.2〜41.5 ms。組ごとの増減が登録差より大きく、操作からの短縮は4回すべてでは再現しなかった。先行Workletの評価や通信を個別には計測していないため、重なった時間をCPU上の同時実行時間としては扱わない。

停止経路は追加のChromium試験で確認した。Playwrightで同じContextの両方の `addModule()` を未解決にしてから「歌唱を停止」を押した。Contextは `closed`、Workletノードは生成0、停止後に2つのPromiseを拒否しても未処理の拒否とページエラーは0件だった。同じページから再生し直すと歌唱が完了した。

次は直列登録を基準とし、先行枝が通知するまでの量子数だけを8から4に変える。48 kHzでは4量子差が約10.67 msに相当する。歌唱側の連続8量子の判定と開始予約を固定して、通知・操作からの時間、開始待ちの飛び、PCMを照合する。他ブラウザと機器からの波形、聴感は未検証。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-registration.json
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。改訂後は初回と `/private/tmp` からの再実行で各322件の取得判定を通過。クリック時間の予測は改訂後初回、登録区間の予測は改訂後再実行で外れた。4実行の入力1,112件と出力528件をサイズとSHA-256で検証し、実行時の大容量成果51.22 MBをRTL9210B-CGに保存した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-a/manifest.json)・[初回方式の再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat/manifest.json)・[改訂後マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-b/manifest.json)・[改訂後再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat-v2/manifest.json)
