# Firefoxの歌唱開始時にcubebが返すPCM

48 kHzの共有Contextで歌唱ノードを構築するとき、Firefox親プロセスの出力要求が約2周期空く試行があった。固定版cubebの自作対照では8.4 ms待たせると機器の指定時刻は1周期飛び、その前後の出力PCMは連続した。今回はFirefoxの同じ出力境界で両方を比較する。[Firefoxの既存計測](worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)・[固定版cubebの対照](cubeb-output-callback-probe.md)・[ケース](../cases/worklet-live-song-cubeb-output.json)

## 読解と比較位置

Playwrightの `Firefox.defaultArgs` は起動時に `-juggler-pipe` を渡す。`FFBrowser.connect` はパイプを使って `Browser.enable` と版の問い合わせを送る。Gecko側の `Juggler.observe` はプロファイル初期化後のコマンド起動でフラグを読み、パイプから受け取ったメッセージをルートセッションのハンドラへ渡す。Playwrightが公開する固定版Geckoの差分に加え、`juggler` ディレクトリもビルドに含める。`toolkit/toolkit.mozbuild` の差分は `ENABLE_WEBDRIVER` のときにこのディレクトリを追加する。[Playwrightの起動引数](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/src/server/firefox/firefox.ts#L87)・[接続処理](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/src/server/firefox/ffBrowser.ts#L44)・[Firefox側の起動処理](https://github.com/microsoft/playwright/blob/v1.64.1/browser_patches/firefox/juggler/components/Juggler.js#L69)・[Geckoへの差分](https://github.com/microsoft/playwright/blob/v1.64.1/browser_patches/firefox/patches/bootstrap.diff)

歌唱側は通常の研究画面を使う。`installSharedContextMarker` は `AudioWorklet.addModule` で先行音を接続し、192量子の完了通知まで待つ。先行音は128フレーム単位で進み、左右逆相の差からフレーム番号を復元できる。歌唱ノードの `ConstructProcessor` の時刻から `AudioCallbackDriver::DataCallback` のうち構築を含む要求を求め、同じグラフ反復の描画フレームと先行音の番号を照合する。Cubeb側で採るのは `resampler.fill` とチャンネル混合を終えたステレオFloat32のPCMと、それを返す回にCore Audioが渡した2種類の時刻。前後8要求の左端と右端を各256フレームの連続した番号で合わせ、同じ窓の機器サンプル時刻の飛び、PCMの欠落、繰り返し、印の消失、両チャンネルが無音の区間を数える。[先行音の接続](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[グラフ反復と出力要求の照合](../tools/measure_worklet_live_song_output_callback.py)・[cubeb出力の照合](../tools/inspect_firefox_cubeb_output.py)

固定版Geckoの `AudioCallbackDriver::Init` は `mSampleRate` と `mOutputChannelCount` を `CUBEB_SAMPLE_FLOAT32NE` のストリーム設定に渡す。遅延は `GetCubebMTGLatencyInFrames` でフレーム単位に取得し、Web Audioの1量子未満なら128フレームに切り上げる。`mInputChannelCount` が0なら入力ストリーム設定にはヌルを渡す。macOSでは `USE_AUDIOUNIT_RUST` のビルド時に `cubeb_init` の候補でRust版がC++版より先に試される。実際の要求長とPCMの採用は今回の計測で確認する。[Geckoのストリーム初期化](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/dom/media/GraphDriver.cpp#L495)・[cubebのバックエンド選択](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/media/libcubeb/src/cubeb.c#L247)

機器のサンプル時刻の飛びは `次のsample_time − 現在のsample_time − 現在の出力フレーム数` で求める。2回の予定ホスト時刻の差も `mach_timebase_info` でミリ秒に直して、サンプル時刻の差を48 kHzで換算した値と0.5 ms以内で一致することを確認する。第1組は同じFirefoxでコピーを無効にし、第2組で有効にする。固定上流と従来の歌唱基準の検証を全試行に適用し、採取による構築時間の増分も各条件で判定する。[比較の入口](../tools/measure_worklet_live_song_shared_context.py)・[事前登録した判定](../cases/worklet-live-song-cubeb-output.json)

## 再現

Gitを浅く取得した固定Geckoと、Playwright 1.64.1の固定ソースをRTL9210B-CGに置く。Geckoのネイティブビルド、依存ツール、一時領域も同じ外部ディスクを使う。作業ツリーに差分を適用する前にコミットとパッチの適用可否を確認し、同梱のcubebの変更ファイルと追加ファイルは `.cargo-checksum.json` に反映する。[準備のスクリプト](../tools/prepare_firefox_cubeb_source.sh)・[Mozillaのビルド手順](https://firefox-source-docs.mozilla.org/setup/macos_build.html)

```bash
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
build=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output
bash "$experiment/tools/prepare_firefox_cubeb_source.sh" "$build/gecko-source" "$build/playwright"
llvm=/opt/homebrew/opt/llvm@21/bin
wasi="$build/gecko-wasi/wasi-sdk-34.0-arm64-macos"
cd "$build/gecko-source"
PATH="$build/gecko-tools/bin:$llvm:/opt/homebrew/opt/python@3.12/libexec/bin:$PATH" \
  CC="$llvm/clang --no-default-config" CXX="$llvm/clang++ --no-default-config" \
  HOST_CC="$llvm/clang --no-default-config" HOST_CXX="$llvm/clang++ --no-default-config" \
  WASM_CC="$wasi/bin/clang" WASM_CXX="$wasi/bin/clang++" \
  MOZBUILD_STATE_PATH="$build/mozbuild-state" MOZCONFIG="$build/gecko-mozconfig-wasi" \
  TMPDIR=/Volumes/RTL9210B-CG/voice-simulator/scratch/gecko-tmp CARGO_HOME="$build/gecko-cargo-home" \
  ./mach --no-interactive build -j5
```

`gecko-mozconfig-wasi` には `MOZ_OBJDIR=@TOPSRCDIR@/../obj-gecko`、`--enable-application=browser`、展開したSDKを参照する `--with-macos-sdk` と `--with-wasi-sysroot` を指定する。`cbindgen 0.29.4` は `cargo install --locked --version 0.29.4 --root "$build/gecko-tools" cbindgen` で用意した。既存の構成状態に対してコンパイラの環境変数を変えたときは、同じ環境で `./mach --no-interactive configure` を実行してからビルドを再開する。[ビルド設定](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mozconfig-wasi)・[実行スクリプト](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/build-gecko.sh)・[SDKを指定する上流設定](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/build/moz.configure/toolchain.configure#L244)

ビルドしたMacのアプリバンドルにPlaywrightの設定を追加し、`Contents/MacOS/firefox` を渡す。既存の配布版のパッケージと同じ配置で、`playwright.cfg` は `Contents/Resources/`、`00-playwright-prefs.js` はその `defaults/pref/` に置く。アプリへの接続確認後、通常画面で4試行を行う。[Playwrightの設定ファイル](https://github.com/microsoft/playwright/tree/v1.64.1/browser_patches/firefox/preferences)

```bash
app="$build/obj-gecko/dist/Nightly.app"
prefs="$build/playwright/browser_patches/firefox/preferences"
mkdir -p "$app/Contents/Resources/defaults/pref"
cp "$prefs/playwright.cfg" "$app/Contents/Resources/"
cp "$prefs/00-playwright-prefs.js" "$app/Contents/Resources/defaults/pref/"
cd "$experiment"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py worklet-live-song-cubeb-output-local \
  --cubeb-output "$app/Contents/MacOS/firefox"
```

## 照合処理の対照

配布版Firefoxで通常の先行音の採取をやり直し、2試行の34判定に合格した。保存済みの実際のグラフプロファイル2試行では、構築を含む要求を先行音の開始から24,576フレームの位置に対応づけた。そこへ合成したcubeb出力を与え、正常、機器時刻だけ256フレームの飛び、時刻とPCMの両方に256フレームの欠落、2時計の不一致の4条件を各試行に通した。8判定に合格し、2時計が一致しない対照は棄却した。[配布版Firefoxでの回帰](../runs/worklet-live-song-cubeb-output-20261121-marker-regression/manifest.json)・[保存済みグラフでの8判定](../runs/worklet-live-song-cubeb-output-20261121-analysis-control/summary.json)

`--cubeb-output` にも配布版Firefoxを指定し、計測コードのない場合の欠測を試した。採取あり・なしの4試行で通常の歌唱と先行音を照合した。71判定中、採取ありの2試行の `cubeb_output_window` だけが想定どおり不合格となった。どちらもグラフ前後8要求の窓を復元でき、`streams` は空だった。[欠測を確認した実行](../runs/worklet-live-song-cubeb-output-20261121-missing-output-control/manifest.json)

## 試験用Firefoxの実測

Zucchiniのテスト修正から再開した `mach build` は9分42秒で成功した。生成された Nightly 157.0 にPlaywright 1.64.1で接続し、ループバックHTTPで `AudioWorkletNode` を確認した。採取を無効にした2試行と有効にした2試行を1実行とし、研究ディレクトリからの初回と `/private/tmp` からの再実行で、各71判定に合格した。いずれも歌唱PCMと観測の基準照合を通過し、固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の17テストが通った。使用したXULのSHA-256は `8c09c589616c3cdd11e89b1f5ced590cc344ec88944a8481a08c3a56f573664a`。[ビルドログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-256-zucchini.log)・[初回実行](../runs/worklet-live-song-cubeb-output-20261121-native-a/manifest.json)・[再実行](../runs/worklet-live-song-cubeb-output-20261121-native-repeat/manifest.json)

| 採取を有効にした条件 | 構築を含むcubebコールバック | 次の予定要求まで | 次の実コールバック開始まで | 機器のサンプル時刻の飛び |
| --- | ---: | ---: | ---: | ---: |
| 未準備、2試行 | 1.431〜1.540 ms | 5.333 ms | 5.325〜5.334 ms | 0フレーム |
| 192フレーム事前描画、2試行 | 7.006〜7.045 ms | 10.667 ms | 10.684〜10.688 ms | 256フレーム |

事前描画を含む要求は、48 kHzで256フレームの処理予算5.333 msを2試行で超えた。次のコールバックに付いた機器サンプル時刻は通常の256フレームよりさらに256フレーム先だった。前後16区間のうち、飛びを観測したのは構築直後の1区間だけだった。両条件とも、cubebが返した先行音のフレーム番号22,528〜26,879は連続し、4,352フレームに欠落、繰り返し、無音はなかった。したがってこの窓で観測された差は、次の機器要求の時刻にあり、Firefoxのグラフの進行量や返却PCMの連番には現れなかった。[初回の各クロックとPCM](../runs/worklet-live-song-cubeb-output-20261121-native-a/summary.json)・[再実行の各クロックとPCM](../runs/worklet-live-song-cubeb-output-20261121-native-repeat/summary.json)

生データの独立照合では、`struct.iter_unpack('<ff', ...)` で読んだ左右PCMの差を2で割り、係数 `524288` を掛けた整数列を、上のフレーム範囲の印の式から直接生成した整数列と照合した。採取した4試行とも、4,352フレーム分が一致する位置はストリーム全体で1か所で、丸め前の値も一致した。各試行の短い別ストリームは全フレームがゼロだった。`blocks.csv` の整数ホスト時刻を `mach_timebase_info` の125/3 nsで換算し、予定時刻の差、実開始時刻の差、コールバック時間を別々に再計算した。入力568件と出力106件のサイズとSHA-256も照合し、採取成果約32.03 MBをRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-live-song-cubeb-output-20261121-native-a/manifest.json)・[再実行のマニフェスト](../runs/worklet-live-song-cubeb-output-20261121-native-repeat/manifest.json)

採取なしとの構築時間差は未準備の2試行で−0.114〜+0.053 ms、事前描画の2試行で−0.073〜+0.187 msとなり、登録した2 ms以内を全件で満たした。機器の要求時刻が飛んだ間に実際に何が再生されたかを調べるには、cubebより後ろの観測が必要になる。次は既知PCMでプロセスタップの時刻と波形を校正し、同じ構築前後の窓をcubeb側と照合する。物理出力と聴感は別途確認する。[構築時間の差](../runs/worklet-live-song-cubeb-output-20261121-native-repeat/summary.json)・[プロセスタップの対照と再開条件](worklet-live-song-output-pcm.md#再現)

## 作業ツリーとビルドログ

コミットを指定した `git fetch --depth=1 --no-tags` で取得し、約48万ファイルを外部ディスクにチェックアウトした。Playwrightの差分とcubeb計測差分の適用を確認し、cubebに同梱された40ファイルのSHA-256を照合した。[差分適用のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-prepare.log)

初回の `mach build` はインストール済みSDK 26.2を検出し、固定版Geckoが要求する26.5の下限で停止した。PyYAMLの任意の高速化処理で6.0.3と6.0.4の指定が衝突した警告も出た。構成処理はSDKの確認まで進んでいる。固定版Geckoが指定したAppleのパッケージを取得し、指定どおりのSHA-512を確認して、`pkgutil --expand-full` で外部ディスクへ展開した。[初回のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build.log)・[固定版のSDKとハッシュ](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/taskcluster/kinds/toolchain/macos-sdk.yml#L34)

2回目はClang 21の既定設定がリンカにローカルにない `MacOSX15.sdk` を渡し、`-lSystem` の解決に失敗した。`--no-default-config` でSDK 26.5を使うと、ld64とLLDで最小Cプログラムのリンクと実行に成功した。再試行ではこのClangの指定と外部ディスクのcbindgenを使う。[2回目のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-sdk265.log)・[LLDの対照ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-tmp/link-lld.log)・[再試行のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-local-toolchain.log)

WASIヘッダがなかったため、GeckoのWASI SDKと同じメジャー版の公式 `wasi-sdk-34.0-arm64-macos` を取得した。公開SHA-256に一致することを確認して外部ディスクへ展開し、C/C++のWASIヘッダとリンク検査を通過した。構成結果は `MOZ_USING_WASM_SANDBOXING=1`、`MOZ_AUDIOUNIT_RUST=1`、`ENABLE_WEBDRIVER=1` となった。[WASI SDK 34](https://github.com/WebAssembly/wasi-sdk/releases/tag/wasi-sdk-34)・[固定版GeckoのWASI SDK指定](https://github.com/mozilla-firefox/firefox/blob/fdd757a2e09c9471cddf383e64e631e4ce178499/taskcluster/kinds/fetch/toolchains.yml#L453)・[WASI追加後のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-wasi.log)

最初のホスト用プログラム `nsinstall_real` で `-lSystem` が再び解決できなかった。ターゲットの `CC` と `CXX` の追加引数は、ホストの既定値には引き継がれていなかった。`HOST_CC` と `HOST_CXX` へも `--no-default-config` を指定し、既存の構成を使うビルドの失敗を保存してから `mach configure` を明示的に実行した。[ホスト用の失敗ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-host-toolchain.log)・[再構成ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-configure-host-toolchain.log)・[ネイティブビルドログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-native.log)

構成を再生成した後は `nsinstall_real` が生成された。次のIPC定義生成でPythonが `AF_UNIX path too long` を報告したので、作業ディスク上の短いパス `scratch/gecko-tmp` に `TMPDIR` を設定した。同じPythonで `multiprocessing.Manager()` が実際にソケットを作り、終了することを先に確かめた。[パス長の失敗ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-native.log)・[短い一時領域でのビルドログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-short-tmp.log)

保存済みFirefoxプロファイルでは、構築を含む要求はコールバック列の0始まりで124番と125番だった。後8要求まで含めるには133〜134ブロックが必要になるため、試験用Firefoxでは記録上限を256に設定することにした。既定の128ブロックとPCM用の上限1 MiBは維持した。ビルドを中断してこの上限を読み取る計測差分とcubebのチェックサムを反映し、コンパイルを再開した。[128ブロックでの検証](cubeb-output-callback-probe.md#実測)・[256ブロックの登録](../cases/worklet-live-song-cubeb-output.json)・[更新した差分のチェックサム](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-prepare-256.log)

更新した差分を使う自作の対照で、`CHIMERA_CUBEB_OUTPUT_BLOCKS=256` を指定し、256ブロックと左右65,536フレームを採取できた。指定を省いた128ブロックの対照でも52判定を通過した。[拡張した自作対照の環境と実行結果](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/probe-256-a/result.json)・[128ブロックの回帰](../runs/cubeb-output-callback-20261121-block-limit-regression/manifest.json)

Geckoのビルドで `libcubeb_coreaudio-37fd6a12b2e50127.rlib` が生成された。依存記録にGeckoが同梱する `src/backend/chimera_output_snapshot.rs` のパスがあり、ライブラリ内に `CHIMERA_CUBEB_OUTPUT_DIR` と `CHIMERA_CUBEB_OUTPUT_BLOCKS` の両方が含まれることを確認した。ライブラリのSHA-256は `74f450fcacef6f80c1ed246b903529c42d4a0a839f14eff22ce228e98cc6ba40`。[ビルドログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-256.log)

ビルドの成功終了後にXULの計測設定を確認し、Playwrightの設定を試験用アプリへ配置する処理を起動した。PlaywrightでループバックHTTPのページを開き、`AudioWorkletNode` が利用できることを確認してから `worklet-live-song-cubeb-output-20261121-native-a` を実行する。計測を実行する条件はビルドの成功記録、対象ライブラリ、Jugglerによるブラウザの起動とWorkletの確認。[ビルド後の実行スクリプト](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/post-build-cubeb-song.sh)・[歌唱の実行ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-cubeb-song.log)

最初の本体ビルドは約39分42秒で停止し、歌唱の採取は始まらなかった。Clang 21のlibc++は、Zucchiniの `suffix_array_unittest.cc` が使う `std::basic_string<unsigned char>` の `char_traits<unsigned char>` を提供しない。`MakeUnsignedString` はテスト入力を符号なしバイトへ変換し、後続の `InducedSortSubstring`、`TestSuffixSort`、`TestSuffixLowerBound` はその列をランダムアクセス範囲として読む。単体テストの型別名だけを `std::vector<unsigned char>` に変更し、同じ符号なしバイト値と順序を維持した。固定版への準備手順にこの差分を追加し、既存のオブジェクトを使ってビルドを再開した。[Clang 21対応の差分](../tools/chimera-firefox-zucchini-libcxx.patch)・[初回のビルド結果](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-256.log)・[再開したビルド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-256-zucchini.log)

再開後、`obj-gecko/dist/bin/zucchini-gtest --gtest_filter='InducedSuffixSortTest.*:SuffixSortTest.*:SuffixArrayTest.*'` を実行した。全バイト値を含む `AllChar` と、部分列の一致を検査する `LowerBoundExact` を含む8件が通過した。続けてXULをリンクする工程に入った。[該当テストの実行ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-zucchini-suffix-tests.log)
