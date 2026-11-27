# cubebとプロセスタップで同じ歌唱開始を観測する

試験用Firefoxでは、192フレームの事前描画後に機器の要求時刻が256フレーム分進み、cubebがCore Audioへ渡した先行音の連番は続いた。次の比較では、同じ試行のcubebとプロセスタップで先行音の両端を対応づけ、タップ側の欠落、繰り返し、無音と要求時刻の飛びを別々に読む。[cubebの実測](worklet-live-song-cubeb-output.md#試験用firefoxの実測)・[同時採取のケース](../cases/worklet-live-song-paired-output.json)

## 読解と採取順序

`AudioHardwareCreateProcessTap` は指定した試験プロセスの出力をタップに割り当てる。タップは非公開の集約デバイスの入力に接続する。`AudioDeviceCreateIOProcIDWithBlock` のコールバックが受け取る `inInputTime` はブロックの先頭に対応する。`chimera_process_tap.swift` は `AudioBufferList` の左右Float32を予約済み領域に書き、`mSampleTime` と `mHostTime` をブロック単位で記録する。cubebの計測点ではAudioUnitへ渡す先頭フレームの予定ホスト時刻を記録している。タップの音は集約デバイスの入力として採取するため、機器から出た音と聴感は別の観測になる。[Appleのタップの説明](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)・[Core Audioのコールバック登録](https://developer.apple.com/documentation/coreaudio/audiodevicecreateioprocidwithblock%28_%3A_%3A_%3A_%3A%29)・[Swiftの採取処理](../tools/chimera_process_tap.swift)・[cubebの計測位置](worklet-live-song-cubeb-output.md#読解と比較位置)

既存の `SharedContextMarker.process` は各128フレームの先行音とフレーム番号を保持し、192量子を処理すると構築用の準備通知を出す。同時採取では64量子の時点で先にタップ起動を依頼する。48 kHzでは64量子と192量子の間に341.333 msあり、この時間を起動に使う。ブラウザ側は192量子の完了とタップ側の準備通知の両方を待つ。タップが0.65秒以内に準備できなかった試行ではブラウザの出力を保存し、同時観測を欠測にする。cubebの上限256ブロックの中に前後の窓が収まることは、実際の連番照合で確認する。[先行音の通知](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)・[ブラウザ側の待機](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[タップへの接続](../tools/measure_worklet_live_song_process_tap.py)・[計測入口](../tools/measure_worklet_live_song_shared_context.py)

## 連番と時刻の照合

前後8要求で合計17要求のグラフ進行を既存のマーカーで読んで、左右の差分に埋め込んだ先行音の番号で両方のPCMを切り出す。窓の両端には256フレームずつの連続したアンカーを要求する。cubebのファイル名に含むPIDとタップが記録したPID、記録したホスト時刻の換算比も照合する。各アンカーの時刻差は、ブロック先頭の整数ホスト時刻の差を `mach_timebase_info` でミリ秒へ直し、ブロック内の位置の差に `1000 / 48000` を掛けた値を加える。終端の時刻差から始端の時刻差を引くと、その区間で両地点の対応がどれだけ変化したかを得られる。タップの入力時刻が進む限り、フレーム単位の飛びもデータとして保存する。[照合処理](../tools/inspect_firefox_cubeb_output.py)・[既知PCMの校正条件](../cases/worklet-live-song-process-tap-probe.json)

同時採取コマンドには、48 kHz・連続する既知PCM・有効なブロック時刻を確認した校正実行が必要になる。指示されたアプリの実行ファイルのSHA-256と、校正時のPCM・メタデータを照合する。今回の校正の再試行は35秒でタイムアウトした。アプリのPIDは保存されたが `tap-ready`、録音PCM、時刻のファイルは得られなかった。macOSのログには同じPIDに対する `kTCCServiceAudioCapture` の事前照会があり、許可の成立を示す採取結果は得られていない。校正に不合格だった実行を指定する同時採取は、Firefoxやタップの起動前に拒否した。[校正の再試行](../runs/worklet-live-song-process-tap-20261121-calibration-recheck/manifest.json)

## 対照の結果

タップ準備だけを模擬した試行では、試験用Firefoxから先行音8,192フレームで起動通知が来て、構築を含むcubeb要求は24,576フレームの位置に入った。先行音前後4,352フレームがcubebのPCMと一致し、歌唱の91,200フレーム、拍、観測値は既存の実測と一致した。初回判定はWAVのgzipストリームを直接SciPyに渡したため歌唱PCMと観測の2判定が失敗した。保存成果をメモリ上へ展開して再判定すると、WAV全体がバイト一致して17判定に合格した。元の判定と生データは残した。この対照でプロセスタップは起動していない。[元の対照](../runs/worklet-live-song-paired-output-20261121-gate-control/manifest.json)・[保存データの再判定](../runs/worklet-live-song-paired-output-20261121-gate-reanalysis/summary.json)

保存済みの実測cubebデータに模擬タップを合わせる対照では、連続、256フレームの削除、256フレームの繰り返し、256フレームの無音、入力サンプル時刻だけの256フレームの飛びを区別した。PID違い、ホスト時刻の換算比違い、ホスト時刻の逆行は棄却し、8判定を通過した。たとえばタップのPCMと時刻が連続する模擬例では窓の両端で時刻差が約−5.333 ms変わり、タップの時刻にも同じ飛びを入れると変化はほぼ0 msとなった。[模擬タップによる照合](../runs/worklet-live-song-paired-output-20261121-clock-control/summary.json)

従来の `--cubeb-output` で4試行を取り直し、71判定に合格した。校正の再試行と今回の対照・回帰の全5実行で、入力458件と出力106件のサイズおよびSHA-256を照合した。採取成果約24.37 MBの実体はRTL9210B-CGに置いた。[cubeb単独採取の回帰](../runs/worklet-live-song-paired-output-20261121-cubeb-regression/manifest.json)

## 滑らかな先行音での同時採取

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine` が接続するWorkletでは、`ChimeraProcessor.process()` がフレーム数を `engine_render()` に渡し、Rust側が内部の絶対フレームを進めてPCMを返す。上流のホスト幅試験は入力操作のフレームをそろえてPCMをビット照合する。研究版の通常の歌唱画面ではその加工前PCMに加え、歌唱とは別枝の先行音を観測する。Firefoxの `AudioCallbackDriver::Init()` は出力フレーム数の単位でcubebの遅延を設定する。計測パッチは `audiounit_output_callback()` で再標本化とチャンネル変換を終えた出力バッファを返す直前に、ステレオFloat32とCore Audioが指定したサンプル時刻・ホスト時刻を採る。Swift側は同じPIDのタップを集約デバイスの入力として開き、実際に呼ばれた採取ブロック先頭の入力時刻とPCMを保存する。予定出力時刻と採取入力時刻の両方を、同一の先行音の位置で対応づける。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[上流のホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[Geckoの出力設定](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/dom/media/GraphDriver.cpp#L495)・[cubebの採取位置](../tools/chimera-cubeb-output-snapshot.patch#L161)・[タップの入力](../tools/chimera_process_tap.swift#L121)

従来の段差のある逆相信号を `afplay` で校正し直すと、48 kHzで95,232フレームを時刻の飛びなしで採れた。16,384フレームの連続照合が必要なところ、最長は71フレームだった。校正済みの滑らかな逆相信号をFirefoxへ渡し、同じ採取器の実行ファイルと設定を照合した。グラフの生成値では参照がゼロの場合だけ誤差1×10⁻¹⁴を認め、他の値はビット照合する。[従来信号の失敗記録](../runs/worklet-live-song-process-tap-20261122-paired-calibration/summary.json)・[滑らかな信号の校正](../runs/safari-process-tap-smooth-marker-20261122-repeat/summary.json)・[同時採取の条件](../cases/worklet-live-song-paired-output-smooth.json)

新しい照合では、4,352フレームのグラフ窓の先頭と末尾の1,024フレームを相関で探す。±32フレームの外の競合ピークと比較し、校正と同じ相関、ピーク差、相対RMS残差を要求する。個々の端点の位相を±1フレームで補正し、物理時刻に換算するときは記録したホスト時刻差に `(タップのブロック内フレーム位置 − cubeb側の位置 − タップの分数位相 ＋ cubeb側の分数位相) × 1000 / 48000` msを足す。窓の中は単一の時間差とゲインで説明できるかを算出し、1,024フレーム窓の位相とPCMの完全ゼロを別に保存する。SciPyの `CubicHermiteSpline` で独立生成した0.25フレーム位相の対照4件で、連続、256フレームの欠落、繰り返し、ゼロ挿入を識別した。欠落・繰り返しは位相差の符号が逆で、ゼロ挿入は端点の位相差が増えなくても連続判定を外れた。[波形の照合](../tools/smooth_tap_marker.py)・[二地点の時計](../tools/inspect_firefox_cubeb_output.py)

同時採取の初回は、cubeb側の窓が両条件で得られた。タップの右端から連続だと仮定して逆算した左端は651〜721フレーム、最初に先行音が閾値を超えたのは1,657〜1,727フレームだった。独立に見たタップ時刻は連続しても、構築解放が早いため比較窓の左端は採取の立ち上がりにかかっていた。歌唱の基準WASMも前日の版で、SHA-256の同一性が不合格だった。初回の判定を保存し、両条件に準備通知から100 msの待機を加えた。歌唱は現行WASMと同じ入力で通常のオフライン入口から再取得し、従来の固定上流との差の許容幅を保った。照合の閾値と前後8要求の窓は初回と同じである。[初回の三つの不合格](../runs/worklet-live-song-paired-output-smooth-20261122-a/summary.json)・[現行WASMでの歌唱基準](../runs/worklet-song-voice-20261122-paired-reference/manifest.json)

### 実測

macOS 15.6.1の試験用Nightly 157.0で、研究ワークスペースと `/private/tmp` から1ペアずつ採った。未準備の2試行では、cubebとタップのどちらも同じ4,352フレームで、完全な無音はなかった。192フレーム事前描画では、cubebが連続する4,352フレームを返す一方で、その次の予定要求時刻は両試行で256フレーム飛んだ。同じ両端に対応するタップのPCMは4,608フレームで、うち161フレームが連続して左右とも完全にゼロだった。全試行でタップの入力時計は連続し、対応する両端の `タップ − cubeb` のホスト時刻差は26.106〜26.113 ms、同じ試行の両端での変化は0.13 µs未満だった。[初回の有効な同時採取](../runs/worklet-live-song-paired-output-smooth-20261122-b/summary.json)・[別ディレクトリからの再実行](../runs/worklet-live-song-paired-output-smooth-20261122-repeat/summary.json)

| 比較位置 | 未準備の2試行 | 192フレーム事前描画の2試行 |
| --- | ---: | ---: |
| 構築を含むcubebコールバック | 1.29〜1.88 ms | 6.69〜7.12 ms |
| cubebの予定サンプル時刻の飛び | 0 | 256フレーム |
| cubebで照合した先行音の区間長 | 4,352フレーム | 4,352フレーム |
| タップで照合した同じ区間長 | 4,352フレーム | 4,608フレーム |
| タップで左右とも完全ゼロ | 0 | 161フレーム |

生PCMを読み直すと、両事前描画試行の完全ゼロはタップ窓を0起算とした区間 `[2095, 2256)` だった。別計算では、4,352フレームの参照のどこに256点のゼロを挿入するとタップと最も近づくかを1フレームずつ動かした。両試行とも、構築を含む要求の先頭に相当する位置2,048が最小で、全区間の相対RMS残差は0.470〜0.471%だった。位置2,304での残差は32.7〜35.7%だった。256点の挿入モデルに対して完全ゼロは47フレーム後に始まり、48フレーム前に終わった。Safariと自作AudioUnitでも完全ゼロの区間が期待区間より95フレーム短い例を観測している。境界を変える処理段と機器端子の波形は未観測である。[同じ95フレーム差の自作対照](coreaudio-output-buffer-entry.md#実測)

再取得したオフライン基準は15判定、同時採取の2実行は各40判定と固定上流の各17試験を通過した。同時採取の4試行で歌唱WAVは同じSHA-256で、91,200サンプル・1,425観測点・譜面が現行WASMで取得した基準に一致した。従来の段差のある先行音で保存したcubeb単独の2試行も再解析し、保存時の全項目と一致した。失敗した校正と同時採取の初回を含む5実行の1,180入力・183出力をサイズとSHA-256で照合した。採取物・基準の実体205,004,932バイトはRTL9210B-CGに保存した。[有効な実行の記録](../runs/worklet-live-song-paired-output-smooth-20261122-b/manifest.json)・[再実行の記録](../runs/worklet-live-song-paired-output-smooth-20261122-repeat/manifest.json)

## 再現

既知PCMの校正には [専用アプリの実行手順](worklet-live-song-output-pcm.md#再現) を使う。校正が有効になったら `research/experiments/chimera-rebuild` から次を実行する。

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build
firefox="$build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox"
app="$build/chimera-process-tap/CHIMERA-PCM-Probe.app"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py worklet-live-song-paired-output-local \
  --cubeb-output "$firefox" --paired-process-tap "$app" "$calibration_run"
```

滑らかな試験音の場合は、ケースに記載した現行WASMのオフライン基準を使う。同じ版で基準から取り直す場合は、新しい基準実行IDをケースに反映し、通常のChromeを明示する。別ディレクトリではPython、スクリプト、ケースを絶対パスにする。

```bash
CHIMERA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 ../../.venv/bin/python \
  tools/measure_worklet_song.py worklet-song-voice-paired-reference-example

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py worklet-live-song-paired-output-smooth-example \
  --cubeb-output "$firefox" --paired-process-tap "$app" safari-process-tap-smooth-marker-20261122-repeat \
  --paired-case cases/worklet-live-song-paired-output-smooth.json
```
