# Context再開とWorklet登録を重ねる歌唱の対照

## 上流の開始順と候補の依存関係

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start` は既存のContextを再開し、初回は `build` に入る。`build` はクリックの処理中に `ctx.resume()` を要求してPromiseを保持し、その完了を待たず `audioWorklet.addModule` を呼ぶ。登録が成功すると、事前にコンパイル済みのWASMを `AudioWorkletNode` に渡し、ゲインなどを経由して出力先につなぐ。登録に失敗したContextは閉じる。歌唱のスコアは `playTune` が `engine.schedule` に送り、`Engine::schedule` が発声時計上の開始位置を加える。検証に使う上流試験は、短音符での母音核の拍、語尾の開大と呼気、128フレーム以外のホスト分割でも音声が一致する条件を確かめる。[上流の開始と登録](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱の予定](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[発声時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[拍](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[語尾](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[ホスト分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の現行順は、`withRealtimeContext` が48 kHzのContextを作ってWASMの準備と再開を待ち、辞書と歌唱計画を進めてから `captureWorklet` で登録を始める。対照では `resume()` 要求直後に同じ登録関数を呼び、ノードを作る前にそのPromiseを待つ。停止時は `AbortSignal` が呼び出しを終了させ、`finally` がContextを閉じる。登録のPromiseが先に失敗しても監視を付け、その失敗はノード生成前に伝える。停止後に失敗した場合も未処理の拒否を残さないようにした。計画、WASM、ノードの入力、持続時間、音声出力は同じ歌唱の経路を使う。ブラウザの歌唱画面には研究用クエリ `songParallelRegistration=1` で対照を指定できる。[候補の再開と登録](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L146)・[歌唱画面](../../../../web/prototypes/chimera-research/src/main.tsx#L584)

Workletは準備したWASMを使って合成状態を初期化する。最初の8連続量子を確認した次の位置を `armedContextFrame`、そこから2,048フレーム先を歌唱開始とする。歌唱の拍は `最初の拍 + 先の音符の拍数の和 × 60 / BPM` 秒で独立計算する。120 BPMの `Pop Dee` では開始から24,000・48,000フレームになる。全713量子のうち末尾は64フレームを採取する。Context作成からノード接続までの経過はメインスレッドの `performance.now` で測る。登録の区間 `[a,b]` と別区間 `[c,d]` の重なりは `max(0, min(b,d) − max(a,c))` msで求める。各区間は同時に重なり得るので、個別の重なりを加算して総時間にはしない。[Workletの開始予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L26)・[区間と拍の比較コード](../tools/measure_worklet_song_parallel_registration.py)

## 事前登録と停止の対照

各試行は新しいブラウザとページで行う。両条件とも最初に現行順で音節のない `...` を試し、警告後に同じ `Pop Dee` を開始する。これで初回描画前に展開済み辞書を読み込む順序を揃える。並行条件は警告後にだけクエリを有効にする。FirefoxとChromiumで4対ずつ試し、試行順は交互に変える。各対の `現行順の接続までの時間 − 並行条件の時間` の中央値でFirefoxの20 ms短縮、Chromiumの10 ms以内の遅延増を評価する。PCMと状態はCLI・オフラインと一致した既存実行をハッシュで確認して照合する。[事前登録](../cases/worklet-song-parallel-registration.json)・[歌唱とCLIの参照](../runs/worklet-live-song-cross-browser-20261121-a/manifest.json)・[前回の区間観測](../runs/worklet-song-startup-phases-20261121-repeat/summary.json)

通常のタイミング比較とは別に、各ブラウザで1回、`addModule` のPromiseを保留した状態から停止する。計測器は一つのContextの登録を保留し、停止ボタンがそのContextを接続前に閉じたことを確かめる。閉鎖後に計測器からPromiseを失敗させ、未処理の拒否や画面エラーを調べる。同じ操作で完成した再開後のWAVと観測を保存した後、接続後0.7秒からの停止と再開も確認する。実ブラウザでの登録時間は別の通常試行で採る。[画面操作と停止の実装](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L953)

## 初回結果

Firefoxで並行条件の登録は再開と中央値25.5 ms、歌唱計画と23.5 ms重なった。登録開始から完了までは151.5から193.5 msに延び、計画後の登録待ちは151.5から147.5 msに減った。接続までの対ごとの差は−1、−18、+11、+6 msで、短縮の中央値2.5 msは20 msの目安に届かなかった。Chromiumの中央値は0.5 ms短縮で、10 msを超える遅延増はなかった。[初回の各対と区間](../runs/worklet-song-parallel-registration-20261121-a/summary.json)

通常16試行と停止の2試行で、48 kHz・91,200フレームのPCM、1,425観測行、予定拍、調音スコアがハッシュを確認した従来の歌唱と一致した。固定上流との差はフレーム4,114で最初に現れ、最大2.33×10⁻¹⁰だった。固定上流の関係する17試験も通過した。登録を保留したContextはどちらも接続前に閉じ、遅れて拒否したPromiseの未処理通知は0件だった。次の歌唱が完了し、接続後の停止と再開も通過した。[初回の判定](../runs/worklet-song-parallel-registration-20261121-a/manifest.json)・[上流試験ログ](../runs/worklet-song-parallel-registration-20261121-a/artifacts/upstream-tests.log)

## 再実行と判断

`/tmp` からの再実行も機能95判定すべてを通過した。Firefoxの接続までの対ごとの差は0、−5、−5、−7 msで、中央値は5.0 ms延びた。Chromiumは中央値1.8 ms延び、登録した10 ms以内に収まった。Firefoxの20 ms短縮は両方の実行で未達だったので、並行登録は研究用条件として残した。[再実行の各対と機能判定](../runs/worklet-song-parallel-registration-20261121-repeat/summary.json)

| Firefoxの中央値（ms） | 現行順 初回 / 再実行 | 並行条件 初回 / 再実行 |
| --- | ---: | ---: |
| 登録開始から完了まで | 151.5 / 148.0 | 193.5 / 198.0 |
| 登録と再開の重なり | 0 / 0 | 25.5 / 25.0 |
| 登録と歌唱計画の重なり | 0 / 0 | 23.5 / 23.0 |
| 歌唱計画後の登録待ち | 151.5 / 148.0 | 147.5 / 148.5 |

Firefoxは並行条件の全8試行で計画後に登録を待った。測っている境界はJSの `addModule` 呼び出しとPromiseを待つ処理が戻った時点である。登録のPromiseの区間が延びた分を、モジュール取込、Worklet内での評価、メインスレッドへの通知にまだ分けていない。次は `fixed-processor.ts` の評価と `registerProcessor` をWorklet側で計時し、メイン側の登録開始・解決と照合する。[再実行の区間データ](../runs/worklet-song-parallel-registration-20261121-repeat/summary.json)・[Workletの登録入口](../../../../web/prototypes/chimera-research/src/fixed-processor-entry.ts#L6)・[後続の区間別の計時](worklet-song-module-evaluation.md)

Chromiumでは最初のWorkletコールバックが、両実行の全対でContext上の2,048から768フレームに早まった。予約した歌唱開始の中央値は初回で同じ、再実行では並行条件が128フレーム後だった。両条件に起動時のフレーム不連続1件を観測し、連続量子を確認した後に同じ2,048フレームを待った。歌唱の間の量子列に欠落は0件。最初のコールバック位置の変化と、接続までの経過時間や歌唱開始位置の変化は個別に照合する必要がある。[初回のContext時計](../runs/worklet-song-parallel-registration-20261121-a/summary.json)・[再実行のContext時計](../runs/worklet-song-parallel-registration-20261121-repeat/summary.json)

## 再現と保存

研究ワークスペースから新しい実行IDで再現できる。macOS 15.6.1 arm64、Firefox 157.0、Chromium 156.0.8078.4、Rust 1.94.1、Node 24.19.0、Bun 1.4.4を使った。二回分の各119成果をサイズとSHA-256で照合し、可逆圧縮した約25.58 MBの実体をRTL9210B-CGに保存した。展開したブラウザWAV40本はバイト一致した。従来のIPA `/ɑpɑ/` の停止・復帰と、保存済みPCM・調音観測も比較した。物理出力での時間は未計測である。[初回マニフェスト](../runs/worklet-song-parallel-registration-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-song-parallel-registration-20261121-repeat/manifest.json)・[IPA比較の基準](../runs/worklet-live-ipa-cross-browser-20261121-repeat/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=140000000 \
  ../../.venv/bin/python tools/measure_worklet_song_parallel_registration.py worklet-song-parallel-registration-next
```
