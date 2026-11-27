# SafariとCore Audioの出力PCM採取を較正する

## 観測点と試験信号

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.build()` が `AudioContext` を作ってWorkletを接続し、`ChimeraProcessor.process()` は `engine_render()` から受け取ったfloat32のPCMを各出力チャンネルにコピーする。上流のブロック長試験は、同じ絶対フレームで操作したときのPCMを照合する。研究版で確認済みの先行PCMと同じ方式を使い、今回は歌唱を外した専用ページで出力経路を較正する。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流のブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[前回のグラフ内での比較](worklet-safari-song-score-preparation-switch.md)

SafariのAudioContextを48 kHzで開き、左チャンネルへ `((421 × i + 173) mod 65521 − 32760) / 8388608`、右へその符号を反転した値を出す。`i` は試験音の先頭から数えたサンプル番号。ステレオの差 `(L − R) / 2` から振幅とフレーム位相を復元する。出力の一周期は65,521フレーム、タップの採取は1秒なので、採取区間は一周期を超えない。SafariのWorkletでは160量子、計20,480点を再生元の連番と照合する。[事前登録](../cases/safari-process-tap-calibration.json)・[逆相のWorklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)・[位相の復元](../tools/measure_worklet_live_song_process_tap.py)

Core Audioの `kAudioHardwarePropertyProcessObjectList` から、SafariとWebKitに属する候補のPID、オブジェクトID、出力状態を取得する。試験音の開始で出力が有効になり、停止で無効になり、再開で同じPIDが有効になる場合にそのプロセスを選ぶ。既存のSwift採取器はステレオの `CATapDescription` と非公開の集約デバイスを作成し、その入力コールバックのPCM・ホスト時刻・サンプル時刻を保存する。Appleの手順では、採取アプリの `NSAudioCaptureUsageDescription` と、OSのシステムオーディオ録音許可が必要になる。この計測点で得られるのはプロセスの出力PCMで、物理端子やスピーカー側は別の観測点となる。[Core Audioの出力状態](https://developer.apple.com/documentation/coreaudio/audiohardwareprocess/isrunningoutput)・[Appleのプロセスタップ手順](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)・[PIDを照合するコード](../tools/chimera_coreaudio_output_processes.swift)・[収録コード](../tools/chimera_process_tap.swift)

## 実測

最初の試行では、Safariの試験音の開始前、再生、停止、再開に対応して、同じ `com.apple.WebKit.GPU` プロセスの出力状態が無効・有効・無効・有効と切り替わった。最初の再生と再開後の各20,480サンプルが独立計算とビット一致し、グラフのフレーム番号も128ずつ進んだ。このPCMで作った対照は、連続、128サンプルの欠落、128サンプルの重複、128サンプルの無音置換を正しく識別した。欠落・重複の最初の変化位置は10,240、無音置換の直後は10,368だった。試験中の17判定のうち16件が成立した。[試行要約と欠落対照](../runs/safari-process-tap-calibration-20261122-a/summary.json)・[プロセス状態の時系列](../runs/safari-process-tap-calibration-20261122-a/artifacts/capture.json)

残る1件はタップの開始・完了判定だった。採取アプリの起動とPIDの書き出しは確認したが、8秒で `tap-ready` は届かず、採取側のPCMと入力時刻は未取得。対象を採取アプリの記録済みPIDとbundle IDに絞ってOSログを読み直し、`kTCCServiceAudioCapture` の許可要求1件を確認した。許可の付与または拒否を示す記録は今回の照合には含まれない。採取側での連続16,384点・サンプル時刻・逆相の合格条件は保留した。[タップの欠測](../runs/safari-process-tap-calibration-20261122-a/manifest.json)・[許可要求の照合](../runs/safari-process-tap-calibration-20261122-permission/summary.json)

`/private/tmp` からの再試行と、採取アプリを起動しないグラフ対照ではSafariのWebDriverセッションは作られたものの、再生ボタンを操作した後もページ状態が `idle` に留まった。両試行では採取アプリを起動する手前で止まった。最初の試行では採取待機が切れた後、Safariの停止通知も時間切れとなった。待機の終了時に今回の一時採取アプリのPIDと実行パスを照合してから終了させる処理を追加し、先の試行のブラウザ状態と区別して保存した。[再試行](../runs/safari-process-tap-calibration-20261122-repeat/summary.json)・[グラフ対照](../runs/safari-process-tap-calibration-20261122-graph-control/summary.json)

グラフ対照の再試行では、WebDriverのクリック後にページ状態が変わらないとき、同じボタンへWebDriverでSpaceキーを送った。最初は再生だけ復旧し、停止にも同じ方法を適用して再開と最後の停止まで完了した。採取アプリを起動しない条件で、研究ワークスペースと `/private/tmp` から各17判定が通り、両再生のグラフPCMは最初の試行と同じハッシュになった。開始・停止・再開・最終停止に対応するプロセスの出力状態も再現した。[再生のみ復旧した試行](../runs/safari-process-tap-calibration-20261122-graph-input-retry/summary.json)・[最後の停止までの操作と出力状態](../runs/safari-process-tap-calibration-20261122-graph-release/artifacts/capture.json)・[別ディレクトリでの再現](../runs/safari-process-tap-calibration-20261122-graph-repeat/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6と同梱WebDriver、Node.js 24.19.0、Swift 6.2.3、Python 3.14.4とNumPy 2.4.4を使用した。署名済みの既存採取アプリを一時ディレクトリへ複製して起動し、試験に関係するプロセス一覧だけを保存した。7実行の全91入力・50出力をサイズとSHA-256で照合した。結果JSONとマニフェストはローカル、グラフのPCMと時刻、コマンドのログなど計1,214,559バイトの採取物はRTL9210B-CGに配置した。[初回のマニフェスト](../runs/safari-process-tap-calibration-20261122-a/manifest.json)・[許可要求の照合記録](../runs/safari-process-tap-calibration-20261122-permission/manifest.json)・[別ディレクトリでの対照のマニフェスト](../runs/safari-process-tap-calibration-20261122-graph-repeat/manifest.json)

```bash
# 研究ワークスペースで実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py \
  safari-process-tap-calibration-20261122-a \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=10000000 \
  ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py \
  safari-process-tap-calibration-20261122-permission \
  --inspect-permission safari-process-tap-calibration-20261122-a

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py \
  safari-process-tap-calibration-20261122-graph-release --graph-control
```

既知信号では、採取アプリへの許可が利用できる状態でタップを再実行し、実際に採れた信号と採取側のサンプル時刻を判定する。その較正を経て、歌唱の予備描画の切り替えを含む区間でサンプルの欠落・重複・無音が現れるか比較する。

後続の再試行では48 kHzのステレオPCMを取得できた。段差のある試験音では連番の照合が途切れたため、二値を滑らかにつないだ試験音で連続区間と採取時刻を較正した。[後続の較正](safari-process-tap-smooth-marker.md#実測)
