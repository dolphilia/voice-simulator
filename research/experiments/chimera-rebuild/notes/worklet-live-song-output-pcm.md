# Firefoxの出力PCMとCore Audioの要求間隔

前回のFirefoxでは、48 kHzで256フレームの出力要求を調べた。事前描画を含む回の直後に、Core AudioのI/O開始間隔が5.319 msから10.658 msに広がった。今回は、構築前後に出力サンプルの欠落・繰り返し・無音があるかを調べるため、プロセス出力の採取とフレーム印の照合を用意した。[前回のI/O区間の計測](worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)

## 出力までの経路と観測点

固定上流の `AudioEngine.build` は `AudioContext` を作って `ChimeraProcessor` を接続する。Workletの `process` は出力チャンネルの要素数を `engine_render` に渡し、WASMメモリから `Float32` のPCMを取り出して各チャンネルに書く。エンジン側のブロック長の試験は、操作の絶対フレームをそろえたときに、分割方法によってPCM列が変わらないことを検証する。研究用の共有Contextでは、歌唱の前から先行音を同時に流す。先行音を左右 `+x` と `−x` で書き、モノラル歌唱 `s` はFirefoxのチャンネル変換で左右に同じ値で加える。出力の `(L−R)/2` は、左右に共通の歌唱を相殺して先行音を取り出す。[固定上流のWorklet接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[固定上流のPCM出力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[先行音のWorklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)

先行音は `((421 × i + 173) mod 65521 − 32760) / 524288` で、`i` は先行音の開始からのサンプル番号である。48 kHzでの1周期は約1.365秒。採取PCMからゲインを推定した後、値を整数に戻し、421の剰余逆数を掛けて周期内の番号を復元する。構築の前後8要求を含む区間は、Firefoxの予算マーカーとグラフ前進のマーカーから決める。区間の両端で連続256フレームを合わせ、両端を一意に選べる場合に、その間で番号が先へ飛ぶ、戻る、読めないという事象を数える。左右PCMが同時にゼロである場合は無音の別の計数に載せる。音声ブロックに付くCore Audioのサンプル時刻も確認し、採取側の時刻が連続する区間を使う。[ケースの採用条件](../cases/worklet-live-song-process-tap.json)・[フレームを照合する処理](../tools/measure_worklet_live_song_process_tap.py)

## 実行した採取と対照

macOS 15.6.1の組み込み出力は48 kHz・2チャンネルだった。Core Audioのプロセスタップは、指定したFirefoxの親プロセスの出力を採る。非公開のタップと非公開の集約デバイスを作り、既定の出力や音量には手を加えない。Nativeのコールバックは予約メモリへステレオFloat32、ホスト時刻、サンプル時刻を書き、停止後に保存する。公式の手順に従い、専用アプリの `Info.plist` にシステムオーディオの使用目的を入れた。[Appleのプロセスタップの資料](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)・[採取するSwiftコード](../tools/chimera_process_tap.swift)

既知のPCMを `afplay` で流す採取を試した。最初のCLIではmacOSがCodexに対してシステムオーディオの許可を要求し、12秒で待機を打ち切った。外部ディスク上の専用アプリをLaunchServicesで起動した試行は `posix_spawn` の `Operation not permitted` で停止した。アプリと受け渡し先を内蔵の一時領域へ置くと専用アプリとして起動できた。手動の起動確認では採取可能状態に進むまでに `afplay` が終了し、48 kHz・0フレームだった。専用アプリを使う再試行は35秒で待機を打ち切った。許可が利用できることと、既知のPCMを採れたことは未確認。[CLIの失敗記録](../runs/worklet-live-song-process-tap-20261121-probe/manifest.json)・[外部上の起動結果](../runs/worklet-live-song-process-tap-20261121-app-probe/manifest.json)・[一時領域での採取結果](../runs/worklet-live-song-process-tap-20261121-staged-probe/manifest.json)

待機中に、逆相の先行音を使ったFirefox内の1組を実行した。先行音と歌唱の34判定を通過し、両試行の構築前後17要求は各256フレームで、先行音の番号が合った。左右の波形を合成した対照では、連続したPCMを合格とし、256フレーム削除・256フレーム重複・左右をゼロにした256フレーム・歌唱成分だけを残した256フレームを区別した。さらに実際のFirefoxプロファイルから選んだ4,352フレームの窓を使い、模擬ステレオ波形へ入れた256フレームの欠落位置を両試行で復元した。これらの対照は出力PCMを判定する処理の検証に使った。[Firefox内部の対照](../runs/worklet-live-song-process-tap-20261121-graph-control/manifest.json)

Firefoxとタップを接続する入口では、試験で起動したFirefoxの親プロセスを特定して、先行音を流しながらタップの準備を待つ。未準備、事前描画の両方で2.5秒待ってもタップの準備通知が来なかったため、構築を解放して保存できるブラウザ成果を残した。歌唱と先行音の34判定は通り、タップの有無を確認する2判定が不合格になった。別の出力解析は両試行を `tap_not_recorded` として保存した。[Firefoxを接続した採取](../runs/worklet-live-song-process-tap-20261121-bridge-a/manifest.json)・[PCMの欠測結果](../runs/worklet-live-song-process-tap-20261121-bridge-analysis/summary.json)

配布版Firefoxの代わりに使える計測位置も調べた。Geckoの `MOZ_DUMP_AUDIO` は `AudioStream` の経路にあり、今回観測している `GraphDriver` に同じ記録処理は見つからなかった。macOS版cubebのRustバックエンドにはビルド時の `audio-dump` 機能がある。手元のFirefoxのXULには `MOZ_DUMP_AUDIO` の文字列がある一方、この出力ダンプ用の識別文字列とAPI名は確認できなかった。アプリが出力へ渡すPCMを追加で測る場合は、計測を有効にした実験用Firefoxを別に用意する経路がある。[GeckoのAudioStream](https://github.com/mozilla/gecko-dev/blob/master/dom/media/AudioStream.cpp)・[GeckoのGraphDriver](https://github.com/mozilla/gecko-dev/blob/master/dom/media/GraphDriver.cpp)・[cubebの出力ダンプの条件](https://github.com/mozilla/cubeb-coreaudio-rs/blob/master/src/backend/mod.rs)

## AudioUnitの要求時刻を観測する別の対照

自作の48 kHz再生AudioUnitのコールバックで、与えられたサンプル時刻とホスト時刻を記録する。コールバックが受け取った `frames` を回ごとの出力長とし、そのフレーム数だけ番号付きPCMを作って、次に書く番号を進める。65回目だけ時間を使い、次のコールバックの `sampleTime − (前回のsampleTime + frames)` をデバイス側の要求の飛びとする。実際の待機時間は入退時のホストクロックから求め、Core Audioから渡されたホスト時刻の差を別に読む。[対照の実装](../tools/chimera_output_deadline_probe.swift)・[初回の条件](../cases/coreaudio-output-deadline-probe.json)

このAudioUnitの要求は512フレームで、1回の予算は10.667 msだった。8.401 msかかった回では次のホスト時刻まで10.667 msで、サンプル時刻は連続した。待機だけ14 msにした別ケースを登録して2組測ると、待機した出力回は両方とも14.002 msだった。次のホスト時刻までの間隔は21.333 msになり、デバイス側のサンプル時刻は512フレーム分飛んだ。待機なしの対照では飛びはなかった。アプリが書き込んだ番号列は全試行で連続していた。生の2要求の時刻を引き算して再検証した結果も、計測スクリプトと一致した。[8.4 msの結果](../runs/worklet-live-song-output-deadline-20261121-native/summary.json)・[14 msの登録ケース](../cases/coreaudio-output-deadline-probe-512.json)・[比較](../runs/worklet-live-song-output-deadline-20261121-native512/summary.json)・[再実行](../runs/worklet-live-song-output-deadline-20261121-native512-repeat/summary.json)

この測定から、Core Audioが次に渡すサンプル時刻は、処理予算を超えると要求1回分だけ飛び得ると確認した。Firefoxでは1要求が256フレームで、今回の自作AudioUnitは512フレームだった。Firefoxのプロセス出力では、同じような時刻の飛びに対して、音声が欠けるか、繰り返されるか、ゼロで埋まるかを別に調べる。

## 再現

`research/experiments/chimera-rebuild` から実行する。Nativeの対照はマイクやシステムオーディオの録音を要求しない。

```bash
out=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap
mkdir -p "$out"
xcrun swiftc -O -framework AudioToolbox tools/chimera_output_deadline_probe.swift \
  -o "$out/chimera-output-deadline"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python \
  tools/measure_coreaudio_output_deadline.py worklet-live-song-output-deadline-local \
  "$out/chimera-output-deadline" --case cases/coreaudio-output-deadline-probe-512.json
```

プロセスタップの使用を許可した環境では、既知PCMの採取が合格した後、同じアプリでFirefoxの対象プロセスを採取する。生成された `tap.json` はブロックごとの入力時刻と実際のフレーム数、`tap.f32le` は対応するPCMを持つ。

```bash
app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
```

アプリを再作成する場合はこのパスへビルドする。

```bash
mkdir -p "$app/Contents/MacOS"
cp tools/chimera_process_tap_info.plist "$app/Contents/Info.plist"
xcrun swiftc -O -framework CoreAudio tools/chimera_process_tap.swift \
  -o "$app/Contents/MacOS/chimera-process-tap"
/usr/bin/codesign --force --sign - "$app"
```

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_process_tap.py worklet-live-song-process-tap-local-probe "$app"
PLAYWRIGHT_BROWSERS_PATH=/Volumes/RTL9210B-CG/voice-simulator/build/playwright \
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py worklet-live-song-process-tap-local --process-tap "$app"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_process_tap.py --playback-analysis \
  worklet-live-song-process-tap-local-analysis worklet-live-song-process-tap-local
```
