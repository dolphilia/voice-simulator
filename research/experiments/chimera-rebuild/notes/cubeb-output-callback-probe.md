# cubebでCore Audioへ渡すPCMと機器の要求時刻

Firefoxの歌唱の先行音では、192フレームの事前描画を含む回の次にCore AudioのI/O開始間隔が約2周期になった。前の自作AudioUnitで試せた要求長は512フレームだった。今回はFirefoxが使うcubebの版で試験用のステレオPCMを再生し、256フレーム要求の時刻と出力バッファの内容を同時に検証する。[FirefoxのI/O計測](worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)・[512フレームの対照とプロセスタップ](worklet-live-song-output-pcm.md)・[事前登録](../cases/cubeb-output-callback-probe.json)

## 読解

Playwright 1.64.1のFirefoxはGecko `fdd757a2e09c9471cddf383e64e631e4ce178499` にPlaywrightのパッチを適用している。このGeckoの `toolkit/library/rust/shared/Cargo.toml` と `Cargo.lock` は `cubeb-coreaudio` の `840f69c1b3f95accd582555e10abcef8ee67514b` を指定している。`cubeb-backend`、`cubeb-core`、`cubeb-sys` は0.34.1。Geckoに同梱された `third_party/rust/cubeb-coreaudio/src/backend/mod.rs` のSHA-256は、cubebの固定版の同じファイルと一致した。Playwrightの `bootstrap.diff` に対象ファイルを変更する差分は見つからなかった。[Playwrightの版指定](https://github.com/microsoft/playwright/blob/v1.64.1/browser_patches/firefox/UPSTREAM_CONFIG.sh)・[Playwrightのパッチ](https://github.com/microsoft/playwright/blob/v1.64.1/browser_patches/firefox/patches/bootstrap.diff)・[Geckoの依存宣言](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/toolkit/library/rust/shared/Cargo.toml)・[Geckoのロックファイル](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/Cargo.lock)

`audiounit_rust_init` がcubebのRust実装を作る。`AudioUnitContext::stream_init` はストリームの要求をコンテキストの `LatencyController` に渡す。最初のストリームで決めたレイテンシを同じコンテキスト内で共有し、出力の初期化で `set_buffer_size_sync` が `kAudioDevicePropertyBufferFrameSize` をフレーム単位で設定する。既存試験の `test_ops_context_min_latency` はコンテキストの最小レイテンシを検査し、`test_ops_stream_latency` は出力ストリームのレイテンシ取得を試す。`test_minimum_resampling_input_frames_equal_input_output_rate` は入出力が等レートのときの必要フレーム数を調べる。今回の対照では出力専用にし、試験プログラム自身の `render` を既定の出力に接続する。[初期化の入口](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/capi.rs)・[固定版のバックエンド](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/backend/mod.rs)・[インターフェース試験](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/backend/tests/interfaces.rs)・[リサンプル用の試験](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/backend/tests/api.rs)

`audiounit_output_callback` は機器側の要求フレーム数と `AudioTimeStamp` を受ける。`frames_written` を要求数だけ進め、`resampler.fill` に出力を要求する。Firefoxの共有Contextでは、ここから先でAudioIPCがクライアントにPCMを要求する。返った `outframes` が少なければ終端を無音で埋め、必要ならチャンネルを混合する。負または過大な戻り値のときはバッファを無音にしてストリームを停止する。`frames_queued` は有効な戻りフレーム数で進む。既存の `audio-dump` は混合後のPCMを取得するが、その呼び出しには時刻とフレーム境界が渡らない。今回のパッチは同じ出力境界で、ブロックごとの時刻とPCMを対にする。[固定版の出力コールバック](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/backend/mod.rs#L782)・[FirefoxのAudioIPCの順序](worklet-live-song-audioipc.md)・[計測パッチ](../tools/chimera-cubeb-output-snapshot.patch)

`CHIMERA_CUBEB_OUTPUT_DIR` を絶対パスで渡した試験プロセスのうち、48 kHz・ステレオFloat32の出力専用ストリームを対象にする。出力バッファの実際のチャンネル数、レート、フレーム当たりバイト数、読み取れる長さを検査する。最大128ブロックと1 MiBのPCM領域を開始前に確保する。コールバック内ではデータと時刻をコピーし、`CoreStreamData` がAudioUnitを停止してからファイルに書く。`blocks.csv` はPCMファイル内のバイト位置、フレーム数、機器のサンプル時刻、予定ホスト時刻、時刻フラグ、実際の入口と返却前のホスト時刻、出力分岐を含む。`pcm.f32le` の並びは左右インターリーブ。正常、停止、ドレイン、範囲外の戻り値、出力領域不足の分岐を記録する。[計測パッチ](../tools/chimera-cubeb-output-snapshot.patch)

フレーム番号 `i` を `(((421 × i + 173) mod 65521) − 32760) / 8388608` で信号に変え、左右を逆相にする。待機の有無だけを変えて、0始まりで65番目の要求の前後8ブロックを調べる。PCMの照合はPythonで独立にバイト列を計算する。機器側のサンプル時刻の差から前回の要求フレーム数を引くと、機器が指定した時刻の飛びをフレーム単位で求められる。ホスト時刻は `mach_timebase_info` でミリ秒に直し、要求境界の予定時刻と実際のコールバック開始時刻を別々に読む。[PCMを生成するRustコード](../tools/chimera-cubeb-output-probe.rs)・[照合プログラム](../tools/measure_cubeb_output_callback.py)

## 実測

macOS 15.6.1（24G90）、arm64、組み込み出力で実施した。Rust 1.94.1、macOS SDK 26.2、CMake 4.0.1を使用した。初回と `/tmp` からの再実行は各52判定を通過した。両実行の計8試行で、各128回のPCMと時刻を保存した。中央の17要求はすべて256フレームで、各4,352フレームの左右Float32が独立計算とビット一致した。[初回](../runs/cubeb-output-callback-20261121-a/manifest.json)・[再実行](../runs/cubeb-output-callback-20261121-repeat/manifest.json)

| 条件 | 対象回の処理時間 | 次の予定ホスト時刻まで | 次の実開始まで | 機器サンプル時刻の飛び |
| --- | ---: | ---: | ---: | ---: |
| 待機なし、4試行 | 0.0007〜0.0016 ms | 5.333 ms | 5.326〜5.340 ms | 0フレーム |
| 8.4 ms待機、4試行 | 8.402〜8.403 ms | 10.667 ms | 10.669〜10.692 ms | 256フレーム |

独立確認では生CSVから65番目と次の時刻を引き、左PCMの整数値から剰余逆数で連番を復元した。8試行とも境界の前後512フレームは連続した。入力12件と出力36件のサイズおよびSHA-256を照合し、PCMと時刻の実体約2.16 MBはRTL9210B-CGに置いた。固定版cubebの等レートの試験1件も合格した。[初回の時刻と判定](../runs/cubeb-output-callback-20261121-a/summary.json)・[再実行の時刻と判定](../runs/cubeb-output-callback-20261121-repeat/summary.json)・[上流試験のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-upstream-test.log)

機器の次の要求時刻が1ブロック飛ぶ条件でも、アプリの出力コールバックが返すPCMは連続し得る。今回の待機は自作プログラムのデータコールバックで与えた。Firefoxの構築中に同じPCM列が返るか、飛んだ時刻に機器がどの信号を出すか、人が途切れを聞き取れるかは未判定。コールバックに追加したコピーの時間への影響もFirefoxの対照で測る。[FirefoxのI/O計測](worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)

## 再現

`research/experiments/chimera-rebuild` から実行する。この手順では外部ディスクに固定版の独立した作業ツリーを作成する。XcodeのmacOS SDK、Rust、CMake、Python研究環境を用意する。

```bash
experiment=$PWD
build=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output
source="$build/cubeb-coreaudio-rs"
mkdir -p "$source"
git -C "$source" init
git -C "$source" fetch --depth=1 https://github.com/mozilla/cubeb-coreaudio-rs.git \
  840f69c1b3f95accd582555e10abcef8ee67514b
git -C "$source" checkout --detach FETCH_HEAD
git -C "$source" apply "$experiment/tools/chimera-cubeb-output-snapshot.patch"
mkdir -p "$source/examples"
cp tools/chimera-cubeb-output-probe.rs "$source/examples/chimera-output-probe.rs"
printf '%s\n' 'set(USE_JACK OFF CACHE BOOL "Disable JACK for the Core Audio fixture")' \
  > "$build/coreaudio-only.cmake"
DOCS_RS=1 MACOSX_DEPLOYMENT_TARGET=15.0 CMAKE_TOOLCHAIN_FILE="$build/coreaudio-only.cmake" \
  CARGO_HOME="$build/cargo-home" CARGO_TARGET_DIR="$build/target" \
  cargo build --manifest-path "$source/Cargo.toml" --locked --release --example chimera-output-probe
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=10000000 ../../.venv/bin/python \
  tools/measure_cubeb_output_callback.py cubeb-output-callback-local \
  "$build/target/release/examples/chimera-output-probe"
```

`cubeb-sys` のCMakeは既定で同梱の別のRustバックエンドをビルドする。同じ出力先を使うCargoが相互にロックを待ったため、このビルドを停止した。`DOCS_RS=1` でC/C++の共通ライブラリを組み立て、固定したRustバックエンドを試験プログラムから明示的に初期化する。AppleClang 17.0.0でJACKの `strdup` 宣言が見つからなかったため、この試験ではCMakeの `USE_JACK` を無効にした。計測パッチの初回コンパイルでは、FFIのフォーマット型とストリームを移動する前の記録位置を修正した。[cubeb-sysのビルド処理](https://docs.rs/crate/cubeb-sys/0.34.1/source/build.rs)

## 歌唱を使わないプロセスタップの同時採取

固定CHIMERAの `AudioEngine.build()` が接続する `ChimeraProcessor.process()` は、AudioWorklet出力の長さをRustの `engine_render()` に渡し、生成したモノラルPCMを他の出力チャンネルにも複製する。固定上流のホスト幅試験は、操作の絶対フレームをそろえて描画の分割幅を変え、PCMを照合する。Firefoxで見えた違いは、そのグラフより下にある出力の時刻と波形だった。今回の最小対照では、固定版cubebの `audiounit_rust_init()` で出力専用ストリームを作り、出力コールバックが `resampler.fill()` で呼び出すデータコールバックへ既知PCMを渡す。`frames_queued` は返却フレーム数で増え、チャンネル混合後のバッファと予定時刻が計測パッチに届く。等レートで必要フレーム数が変わらないことはcubebの既存試験で確認した。[CHIMERAの接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Workletの出力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[ブロック幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[固定cubebの更新](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/backend/mod.rs#L782)・[等レートの試験](https://github.com/mozilla/cubeb-coreaudio-rs/blob/840f69c1b3f95accd582555e10abcef8ee67514b/src/backend/tests/api.rs#L141)

データコールバックは0始まり65番目だけ、0または8.4 ms待つ。内部の描画済みフレーム数で校正済みの滑らかな逆相信号の1周期を巡回し、左右Float32をすべて書いて、要求されたフレーム数を返す。試験音は開始前に読み込み、待機の合図もストリームを開始する前に受け取る。タップを同じPIDへ接続し、準備通知から100 ms後に再生を開始した。48 kHzで前後8要求を含む4,352フレームをcubeb側で検証し、その両端の1,024フレームを既知波形でタップに合わせる。ホスト時刻は `mach_timebase_info` の換算比とブロック内の位置、分数位相から照合する。遅延ありで予定サンプル時刻とタップの区間長が256フレーム進み、完全ゼロの長さもFirefoxの161フレームと一致すると予測した。[事前登録](../cases/cubeb-output-callback-process-tap.json)・[ネイティブ入口](../tools/chimera-cubeb-output-probe.rs)・[採取と照合](../tools/measure_cubeb_output_process_tap.py)・[Core Audioのタップ](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)

### 実測と残る差

順序を入れ替えた2ペアを研究ワークスペースと `/private/tmp` から各1回測った。待機なし4試行も8.4 ms待機4試行も、cubebが返した各32,768フレームの左右PCMは全サンプルで同じだった。遅延ありの4試行では次の予定サンプル時刻が256フレーム飛び、対応するタップの区間が4,352から4,608フレームに延びた。待機なしでは両方とも連続した。タップの入力時計は全試行で連続し、波形の両端での `タップ − cubeb` のホスト時刻差の変化は最大0.00386 msだった。[初回](../runs/cubeb-output-callback-process-tap-20261122-a/summary.json)・[別ディレクトリからの再実行](../runs/cubeb-output-callback-process-tap-20261122-repeat/summary.json)

| 観測値 | 待機なし、4試行 | 8.4 ms待機、4試行 |
| --- | ---: | ---: |
| 対象コールバックの処理時間 | 0.00083〜0.00158 ms | 8.40125〜8.40167 ms |
| cubebの予定サンプル時刻の飛び | 0 | 256フレーム |
| cubebの比較区間 | 4,352フレーム | 4,352フレーム |
| タップでの同じ区間 | 4,352フレーム | 4,608フレーム |
| タップで左右とも完全ゼロ | 0 | 162フレーム |

対象要求の先頭に相当する位置2,048で、参照に256点のゼロを挿入したモデルの残差が両実行の全遅延試行で最小だった。全区間の相対RMS残差は0.368〜0.369%。実際に左右とも完全ゼロだったのは0起算の `[2095, 2257)` で、挿入区間の冒頭47・末尾47フレームに値が残った。Firefoxのゼロ区間は `[2095, 2256)` だった。異なるフレーム2,256は両者とも振幅1×10⁻⁵未満で、Firefoxの値は最大2.65×10⁻¹⁰、今回の対照では0だった。161フレームという予測は4試行とも不成立として残した。cubebの直後からタップまでの間に現れる欠落相当の区間を、歌唱のない対照でも確認した。機器端子と境界の微小値を生む内部処理段は未観測である。[Firefox側の二地点比較](worklet-live-song-paired-output.md#実測)

SciPyの `CubicHermiteSpline` で別に作った試験音とcubebの全32,768フレームをビット照合した。生CSVの整数ホスト時刻と生PCMから左右の完全ゼロの境界、ホスト時刻差、挿入モデルの残差も再計算した。2実行の各68判定と、従来の段差のある信号を同じバイナリの従来入口で実行した56判定が通過した。固定CHIMERAの `output_does_not_depend_on_the_host_block_size` と固定cubebの `test_minimum_resampling_input_frames_equal_input_output_rate` も通過した。3実行の46入力・126出力をサイズとSHA-256で照合し、採取物6,934,138バイトはRTL9210B-CGに保存した。[初回記録](../runs/cubeb-output-callback-process-tap-20261122-a/manifest.json)・[再実行記録](../runs/cubeb-output-callback-process-tap-20261122-repeat/manifest.json)・[従来入口の回帰](../runs/cubeb-output-callback-20261122-paired-probe-regression/manifest.json)

### 同時採取の再現

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。固定版cubebへ計測パッチを適用した前のビルド領域から再実行する。別ディレクトリから実行する場合はPythonとスクリプトを絶対パスで指定する。

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output
source="$build/cubeb-coreaudio-rs"
cp tools/chimera-cubeb-output-probe.rs "$source/examples/chimera-paired-output-probe.rs"
DOCS_RS=1 MACOSX_DEPLOYMENT_TARGET=15.0 CMAKE_TOOLCHAIN_FILE="$build/coreaudio-only.cmake" \
  CARGO_HOME="$build/cargo-home" CARGO_TARGET_DIR="$build/target" \
  cargo build --manifest-path "$source/Cargo.toml" --offline --locked --release --example chimera-paired-output-probe
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python \
  tools/measure_cubeb_output_process_tap.py cubeb-output-callback-process-tap-local \
  "$build/target/release/examples/chimera-paired-output-probe" \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app \
  safari-process-tap-smooth-marker-20261122-repeat
```

## Firefoxに載せる次の比較

外部ディスクにPlaywrightが指定したGeckoの作業ツリーを作り、Playwrightの `bootstrap.diff` を適用する。今回の計測パッチには、Geckoが同梱する `third_party/rust/cubeb-coreaudio` の固定ファイルに対して `git apply --check` を実行し、適用できることを確認した。実際のビルドでは同梱crateの `.cargo-checksum.json` にある変更ファイルと追加ファイルのハッシュを反映する。ネイティブの実装をコンパイルするため `mach build` の通常ビルドを使う。ソース、ビルド成果、一時領域はRTL9210B-CGに置く。既存の `CHIMERA_FIREFOX` で試験ビルドを指定し、48 kHzの共有Contextで未準備・192フレーム事前描画の各1試行を行う。採取を無効にした試験も実行し、同じ先行音と構築時刻を照合する。PCMは左右差のフレーム印で対応づけ、各構築の前後8要求が128ブロックの採取範囲に入るかを先に確認する。[Gecko同梱のチェックサム](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/third_party/rust/cubeb-coreaudio/.cargo-checksum.json)・[MozillaのmacOSビルド手順](https://firefox-source-docs.mozilla.org/setup/macos_build.html)・[Firefoxの切り替え口](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L1277)
