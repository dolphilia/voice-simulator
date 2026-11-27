# Contextの再開前にWorkletを登録して最初のフレームを照合する

前回のChromiumトレースでは、先行Workletの最初の `currentFrame` が合成Workletの登録要求時の値と揃い、同じ描画要求内の次の128フレーム処理で値が384進んだ。今回は歌唱画面の `?songSilentLead=4&songRegisterBeforeResume=1` で、Contextを停止してから最初の合成Workletを登録し、登録が済んだ時点で再開する。従来の順番は `?songSilentLead=4` で比較する。[前回のトレース](worklet-live-song-fast-app-silent-lead-native-trace.md#実測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-register-before-resume.json)

## 上流の起動と歌唱

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は既存Contextを再開し、初回の `build()` ではユーザー操作中に再開を要求してからWorkletを登録する。登録後、コンパイル済みWASMを渡してノードを作る。上流のコメントには、操作後に非同期処理を挟んだ再開ではiOS Safariで再開できない場合があると記されている。今回の変更はChromiumでの比較用の経路とした。[固定上流の起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)

`playTune()` は音節、MIDI番号、音符の拍数、テンポから歌唱の予定を作る。1拍を `60 / bpm` 秒とし、Workletの `schedule` が相対秒のジェスチャーをWASMのレコード領域へ書く。Rustの `Engine::schedule()` は `voice.clock + lead` を各時刻に足して予約する。`process()` は出力長を `engine_render()` へ渡し、得たPCMを出力にコピーする。Rustの `Engine::render()` は `pos % SUB_BLOCK` により処理の分割をまたいで内部の位相を保持する。短音試験は母音の開始が拍に合うこと、分割試験は異なる長さの描画要求でPCMが揃うことを確認する。[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Chromium `f842f52ef39fd97b449eb27cff414bf05a98ddce` は、許可条件を満たすとContextの生成時から描画を開始できる。試験経路では `context.suspend()` の完了を待ってから最初の登録を要求する。同版の `NotifyWorkletIsReady()` は、停止状態なら描画先のWorkletタスクランナーを準備し、描画中なら描画先を再起動してスレッドを切り替える。グローバルのフレーム値はWorklet用オブジェクトの作成時に読み取った位置を初期値に使い、各描画の完了後にContextの位置を反映する。[ChromiumのContext生成](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/audio_context.cc#L532)・[停止中と動作中の切替](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/base_audio_context.cc#L890)・[時計の初期値](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/audio_worklet_messaging_proxy.cc#L154)

## 試験経路と観測

従来経路はContextを再開し、WASM・辞書・譜面を準備したあとに初回の合成Workletを登録する。試験経路はContextを停止した状態で合成Workletを登録し、その完了後に `resume()` を要求する。WASM取得は登録中も進められる。両経路で先行用の2本目のWorkletは譜面準備のあとに登録し、128フレームの0入力を4量子連続して受け取ってから歌唱ノードをつなぐ。歌唱ノードは連続8量子を確認し、2,048フレーム後を開始予約とする。登録の再配置にはWASM取得との重なりも含まれるため、クリック時間は経路全体の差として集計する。[実装](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L164)・[先行枝](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts#L30)・[歌唱予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

アプリのフェーズ記録で登録要求・完了時のContext状態とフレームを確認する。CDPトレースではフレーム番号付きの先行Workletマーカーを、作者コード実行、128フレームのグラフ描画と描画要求に対応づける。停止中に登録する経路では、先行Workletの初回から連続した描画に対して番号が128ずつ進むと予測した。事前登録の合否に加え、クリックから歌唱先頭までと、再開要求・再開完了・先行枝接続間の各区間を計測する。[照合コード](../tools/measure_worklet_live_song_app_silent_lead.py)

## 実測

初回と別ディレクトリからの再実行で各16試行を取得した。再開前の16試行では、登録の要求時と完了時にContextが `suspended` で、フレームはいずれも0だった。全試行で先行Workletの初回から最後の記録まで、フレーム番号は128ずつ進んだ。従来の再開後の16試行では登録要求時のフレームが1,280〜1,792、初回のフレーム番号が次の呼び出しで384進んだ試行は13件だった。その13件で前後の作者コードは同じ描画要求に入り、対応するネイティブ描画は隣接していた。全32試行の141マーカーは、Chromiumの作者コードと描画要求に一対一に対応した。[初回の結果](../runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-repeat/summary.json)

再開後登録の全16試行では、先行Workletの最初の実行がWorklet用スレッドへの切り替え後の最初の描画に入った。再開前登録の16試行では、先行Workletが初めて走るまでに同じスレッド上ですでに8〜16回の描画が進んでいた。初回の値を設定した処理を直接測っていないが、再開前に登録すると、先行ノードを接続する時点までにWorklet側のContext時計が更新されるという解釈と整合する。[ネイティブ解析](../runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-repeat/summary.json)・[Chromiumの時計更新](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/base_audio_context.cc#L913)

| クリックから歌唱先頭の描画まで | 再開前から再開後を引いた組内差の中央値 | 範囲 |
| --- | ---: | ---: |
| 直接出力8組 | −10 ms | −32〜+3 ms |
| 並列観測8組 | −16 ms | −27〜−8 ms |

直接出力8組中7組で短縮した。Context生成から再開要求までの中央値は、再開後登録で1.0 ms、再開前登録で11.1 ms。再開完了から先行枝接続までの中央値はそれぞれ55.0 msと約43.0 msだった。これらの値はWASM取得や譜面の用意と登録を含めた経路の比較になる。

全32試行で、歌唱ノードは初回の呼び出しから3,072フレーム後に開始し、開始待ちと歌唱中の呼び出しは連続した。保存PCM49,200フレームはオフライン基準とビット一致し、状態769点と歌唱計画も一致した。並列観測16試行の絶対フレームと生PCMを標準ライブラリでも照合し、前後の無音・補完80フレームを確認した。固定上流との差は歯のフィルタ下限1,200 Hzを使った基準と同じで、最大差は `2.7573 × 10⁻³`、差が `10⁻⁶` を超えた最初の位置は27,939フレームだった。[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[並列観測の例](../runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-repeat/artifacts/observed-1-suspended/output-probe.json)

Playwrightの追加確認では、最初の `addModule()` を保留して歌唱を停止し、停止後に保留を解除した。別試行では登録を拒否した。どちらもContextは閉じ、`resume()` の呼び出しは0回だった。そのまま同じ画面から正常に再生するとWAVを保存できた。未処理の拒否とページエラーは0件だった。

次はChromiumで合成Workletを再開前に登録する順番を固定し、先行枝を接続せずに歌唱ノードを作る場合と4量子の無音先行を比較する。開始待ちの連続性、予約、PCM、クリック時間を測る。再開前登録でのSafari・Firefoxの操作と機器出力、聴感は未検証。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-register-before-resume.json
```

macOS 15.6.1 arm64、HeadlessChrome 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各434件の取得判定と8件の予測を通過した。両実行の入力580件と出力296件をサイズとSHA-256で照合し、大容量成果30.11 MBをRTL9210B-CGへ保存した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-repeat/manifest.json)
