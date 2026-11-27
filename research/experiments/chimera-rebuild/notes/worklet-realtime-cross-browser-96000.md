# FirefoxとChromiumで96 kHz固定発声を照合する

## 上流と再実装の入口

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine` はレートを指定して `AudioContext` を作り、WorkletとWASMをつなぐ。固定上流の通常の開始レートは48 kHz。Workletはグラフから得る実際の `sampleRate` を `engine_new` に渡す。各コールバックでは出力バッファのフレーム数を `engine_render` に渡し、Rust側のPCM領域から32ビット値をコピーする。Rustは内部状態の位置を進め、64出力フレームの境界で制御を更新する。同じ絶対フレームに操作を適用すればブロックの分け方を変えても波形がビット一致することを上流のテストで確認できる。今回の固定上流の96 kHzデータは同じ姿勢とゲート時刻を渡すプローブから得る。[上流の音声グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[上流の描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補は通常画面から96 kHzを要求し、`LiveProcessor` はWorkletの実レートが要求と等しいことを検査する。起動時は8量子が連続するまでPCMを採らず、以降のゲート操作は採ったフレーム数で決める。発声開始8,448、停止104,448、76,800フレームの減衰を経て採取終了181,248。量子末尾に、累計フレーム、ゲート、声門面積と流量、位相、発声係数、F0、放射量を保存する。ゲート制御は64サンプルごとに行い、内部と出力のレートが同じ96 kHzなので `f` 番目の出力サンプルは同じ番号の内部状態に対応する。[候補の接続と波形保存](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)・[採取の順序](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[起動時の連続性](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[従来の96 kHzケース](../cases/worklet-realtime-voice-96000.json)

## 事前登録と判定

Web Audioの `currentFrame` は音声グラフ内の処理フレームを表し、観測したコールバック間の壁時計とは別の座標である。FirefoxのWebIDLにも `currentFrame` と `sampleRate` がある。グラフの出力レートが実デバイスと異なる場合の再標本化は後段で行われるので、ここでは採取したグラフ内の96 kHzを測定する。候補はWorklet内の `performance.now` が使えるならそれを選び、使えなければ `Date.now` で量子処理時間を測る。試行ごとの実際の時計名、処理時間とコールバック間隔の記録値をµsに丸めた最大公約数を観測上の刻みの目安として保存する。物理出力や完了通知後までの処理時間はこの観測からは得られない。[Web Audio仕様](https://www.w3.org/TR/webaudio-1.1/#AudioWorklet)・[FirefoxのWorkletグローバル定義](https://searchfox.org/firefox-main/source/dom/webidl/AudioWorkletGlobalScope.webidl)

FirefoxとChromiumで通常画面の開始・自動停止・WAVと観測JSONの保存を行う。以前のChromium実行とWASMバイナリのハッシュを照合し、ブラウザと候補CLIのPCMが全フレーム、ブラウザ同士の累計フレームと音響観測が全1,416量子でビット一致すると予測した。CLIはホスト分割77と128も照合する。固定上流との差とゲートの独立計算、発声中のp99・減衰・停止位置には従来の判定を使う。Firefoxの起動・採取時のフレームの飛びや時計の細かさは実測で確認する。[事前登録](../cases/worklet-realtime-cross-browser-96000.json)・[比較コード](../tools/measure_worklet_cross_browser.py)・[以前の通常Chromium](../runs/worklet-rate-96000-20261121-wrapper-regression/summary.json)

## 通常条件の結果

初回と `/tmp` からの再実行の計12試行で、Firefox 157.0とChromium 156.0.8078.4はいずれも実測96 kHz・128フレームだった。全試行のPCM 181,248サンプルと音響観測1,416行が保存済みChromiumとビット一致し、採取中のグラフのフレーム欠落は0件だった。CLIの77・128フレーム分割も一致した。固定上流との最大PCM差は2.92×10⁻¹¹未満、ゲートの独立計算との差は最大2.11×10⁻¹⁵だった。[初回の各判定](../runs/worklet-realtime-cross-browser-96000-20261121-a/summary.json)・[再実行](../runs/worklet-realtime-cross-browser-96000-20261121-repeat/summary.json)

| 各6試行 | Worklet時計 | 記録値で予算を超えた量子（発声／全区間） | 発声p99の範囲（ms） |
| --- | --- | ---: | ---: |
| Chromium | Date.now、観測上1 ms刻み | 0／2 | 1.00 |
| Firefox | Date.now、観測上1 ms刻み | 20／41 | 1.00〜1.51 |

初回のFirefoxの1試行は750発声量子中8件が2 msだった。線形補間のp99は1.51 msになり、予算1.333 msの判定を不通過とした。初回は98/99判定、再実行は99/99判定。両者を別々の実行IDで保存した。壁時計のコールバック間隔は最大5 msと10〜11 msだった。生の観測からChromiumで3 ms以上、Firefoxで6 ms以上の間隔を拾うと、各試行で同じ4量子または8量子周期の境界に集中した。オーディオグラフの出力フレームはその境界でも連続していた。[初回の時計とフレーム](../runs/worklet-realtime-cross-browser-96000-20261121-a/summary.json)・[再実行の時計とフレーム](../runs/worklet-realtime-cross-browser-96000-20261121-repeat/summary.json)

## Firefoxのネイティブな時計との照合

予算を超えた表示値が実際の長い処理に対応するか、通常条件とは別に事前登録した。Firefox内蔵プロファイラーで `audiocallbacktracing` を有効にすると、`WorkletNodeEngine::ProcessBlock` とその中の `AudioWorkletNodeEngine::CallProcess` の境界を取得できる。通常画面・Workletコード・WASMを使い、プロファイラーだけ有効にする。最初の取得ではJSONのマーカー行の省略可能な `data` を読めずに中断した。取得済みのプロファイルと音声を残し、行の長さを確かめてから読むように修正した。[追加診断の事前登録](../cases/worklet-realtime-firefox-native-clock-96000.json)・[最初の中断と取得済みデータ](../runs/worklet-realtime-firefox-native-clock-96000-20261121-a/interruption.json)・[GeckoのWorklet処理](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp)・[プロファイラーの起動と保存](https://firefox-source-docs.mozilla.org/testing/debugging-intermittents/index.html#use-the-firefox-profiler)

修正後の計4試行で `GraphRunner` 上の1,424区間が起動待ち8量子と採取1,416量子に対応した。6 ms以上の開始間隔は各176件で、Workletの記録とネイティブ計測の出現位置は全件一致した。開始間隔の平均絶対差は0.302〜0.363 msで、ネイティブ系列を±1量子ずらすと2.459〜2.547 msになった。発声中の外側のネイティブp99は0.216〜0.350 ms、全区間の最大は0.792 ms。Workletが2 msと記録した18量子は、同じ試行のネイティブ区間で0.177〜0.662 msだった。音声と観測はこの4試行でもビット一致した。[初回の詳細](../runs/worklet-realtime-firefox-native-clock-96000-20261121-b/summary.json)・[再実行と時刻合わせ](../runs/worklet-realtime-firefox-native-clock-96000-20261121-repeat/summary.json)

単純に両端を1 msに切り捨てた差だけでは、0.2 ms前後の区間が2 msになることは説明できない。Geckoの時刻精度縮減には区間ごとの丸め境界を変える処理があり、今回の組み合わせと整合する。各時刻に実際に適用された丸め境界は測っていない。通常条件の初回の不合格は当時の判定として残す。追加診断は同じ試行の2種類の計測値が示した差であり、実デバイスへの出力期限は未計測。[Geckoの時刻精度縮減](https://searchfox.org/firefox-main/source/toolkit/components/resistfingerprinting/nsRFPService.cpp)・[通常条件の初回判定](../runs/worklet-realtime-cross-browser-96000-20261121-a/summary.json)

## 再現と保存

Firefoxは外部に配置済みのPlaywright Firefox 157.0を使う。macOS 15.6.1 arm64、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4、NumPy 2.4.4で計測した。研究ワークスペースで次のコマンドを使い、実行IDを新しく指定する。

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=240000000 \
  ../../.venv/bin/python tools/measure_worklet_cross_browser.py worklet-realtime-cross-browser-96000-next
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=120000000 \
  ../../.venv/bin/python tools/measure_worklet_firefox_native_clock.py worklet-realtime-firefox-native-clock-96000-next
```

音声・観測・Firefoxのプロファイルを可逆圧縮し、通常条件の2実行と診断の2実行の約24.64 MBをRTL9210B-CGに保存した。密なCLI・固定上流のCSVは作業領域に置いて比較し、WAVと比較に使った量子末尾の参照系列を保存した。[通常再実行マニフェスト](../runs/worklet-realtime-cross-browser-96000-20261121-repeat/manifest.json)・[追加診断マニフェスト](../runs/worklet-realtime-firefox-native-clock-96000-20261121-repeat/manifest.json)
