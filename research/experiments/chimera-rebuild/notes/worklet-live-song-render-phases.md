# Firefoxの歌唱開始時の描画量子を処理ごとに測る

## 固定上流と候補の処理順

固定上流の `src/worklet/processor.ts` の `process` は、出力のチャンネル長を `engine_render` に渡す。WASMから返るPCMの位置を `Float32Array` で参照し、出力へコピーする。第2チャンネル以降も同じPCMで埋め、サンプルレートと量子長からミリ秒の予算を求める。6ブロックごとのテレメトリは `engine_telemetry` を別に呼び、管理領域の観測値をメインに送る。Rustの `Engine::render` は内部ブロックの位置を保ち、境界で制御を更新して進める。エンジン試験はホストの分割を変えても出力が一致することを検査し、歌唱試験は拍と母音核、句末の開大を照合する。[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[上流エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[分割に対する試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[歌唱の拍](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[句末](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)

候補の通常歌唱は48 kHz、128フレーム量子で、1量子の時間予算は `128 / 48,000 × 1,000 = 2.667 ms`。96 kHzの内部更新を出力ステージで間引く。 `FixedProcessor.process` は予定開始を過ぎるまで無音を出し、出力フレームが観測点の手前に来るたびに描画を分割する。今回の先頭4測定量子はどれも64フレームずつ2回の `FixedVoiceEngine.renderInto` を呼ぶ。Rustの `vocal_render` は状態を進めてPCMを書き、最後の観測値をハンドルの領域に保存する。 `renderInto` はその呼び出しを囲み、WASMのPCM領域からWeb Audioの出力へ転送する。 `readObservation` は歌唱の観測領域を参照し、JS側の既確保の行に値をコピーする。[候補のWorklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[WASMホスト](../crates/vocal-wasm/host/fixed-voice.ts#L316)・[RustのABI](../crates/vocal-wasm/src/lib.rs#L775)

## 事前登録と計測方法

実時間歌唱の研究用クエリ `songRenderPhaseTrace=1` で境界を記録する。Firefoxの `console.timeStamp` はWorkletから使え、`ConsoleTiming` を呼び出したスレッドに書く。その後に通常のConsole処理があるため、マーカー間隔には計時処理も含まれる。先行無音の最後の量子で8個のマーカーを連続で記録する。マーカーを入れない対照は同じFirefox、スコア、プロファイラーで行う。WASM・辞書の本文はどちらも歌唱完了後に確認する。[事前登録](../cases/worklet-live-song-render-phases.json)・[FirefoxのWorkletでのConsoleの公開範囲](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/webidl/Console.webidl)・[FirefoxのConsoleTimingの発行](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/console/Console.cpp#L1456)

先頭2量子と冒頭32量子を描画した直後の2量子で、`vocal_render`、`renderInto`、JS観測コピーの前後を採る。マーカーへ出力フレームと量子内のオフセットを付ける。 `GraphRunner` の `WorkletNodeEngine::ProcessBlock` と `AudioWorkletNodeEngine::CallProcess` は、報告された起動待ち量子と先行無音量子を読み合わせ、該当する同一のネイティブ区間に位置づける。各区間は後の時刻から先の時刻を引いたミリ秒。WASMの割合は、先頭のWASM合計から定常2量子の中央値を引き、同じ式で求めた先頭の外側区間の増分で割る。 `vocal_render` 内部で行う音響観測値の計算はWASMの区間に含まれる。[Geckoの処理区間](https://github.com/mozilla-firefox/firefox/blob/437dd728/dom/media/webaudio/AudioWorkletNode.cpp#L422)・[従来の計時](worklet-song-firefox-ipc-stack.md#標準の歌唱採取)・[計測CLI](../tools/measure_worklet_live_song_render_phases.py)

## 初回の照合

3組で全58判定を通過した。各計時付き試行で64個のマーカーを観測し、描画中の56個を予定した4量子に、較正用8個を最後の先行無音量子に対応づけた。先頭量子が定常部より長くなった分の83.1〜84.8%は、2回の `vocal_render` の呼び出し区間に現れた。先頭のJS観測コピーは0.041〜0.043 msで、定常との差は0.034〜0.036 msだった。先頭量子の外側区間は、無印3回が3.521〜4.088 ms、計時付き3回が3.867〜3.988 ms。組ごとの時間差の中央値は+0.147 msだった。[初回の比較](../runs/worklet-live-song-render-phases-20261121-a/summary.json)

## 再実行と処理時間の分布

`/tmp` からの再実行も58判定すべて通過した。計時付きの全6試行で、先頭量子と定常比較用の2量子の時間差の83.1〜86.8%がWASM呼び出し区間にあった。予測した50%以上を全6試行で満たした。較正の隣接マーカーの最大間隔は18.3 µs。先頭量子の外側区間について、計時付きから同じ組の無印を引いた差の中央値は初回+0.147 ms、再実行+0.157 msだった。[再実行](../runs/worklet-live-song-render-phases-20261121-repeat/summary.json)

| 出力フレーム | 外側の処理区間 | 2回分のWASM呼び出し | 2回分のJS観測コピー |
| --- | ---: | ---: | ---: |
| 0 | 3.680〜3.988 ms | 3.312〜3.507 ms | 0.036〜0.047 ms |
| 128 | 2.643〜3.031 ms | 2.563〜2.850 ms | 0.010〜0.084 ms |
| 4,096 | 1.394〜1.458 ms | 1.312〜1.353 ms | 0.006〜0.021 ms |
| 4,224 | 1.351〜1.389 ms | 1.304〜1.326 ms | 0.006〜0.012 ms |

無印の6試行では、先頭量子が全6回で2.667 msの予算を超え、第2量子が超えたのは1回だった。計時付きでは第2量子が6回中5回で超えた。第2量子の予算超過の頻度には計時条件による差が残る。無印の冒頭32量子を除くネイティブp99は1.683〜1.756 msだった。次は本番と同じWASMインスタンスで0フレーム呼び出しと使い捨ての実描画を比較し、呼び出し経路の準備と描画を一度通した効果を分ける。[無印を含む実測](../runs/worklet-live-song-render-phases-20261121-repeat/summary.json)・[先行するChromiumでの事前描画対照](worklet-wasm-dsp-warmup.md)

## 再現と保存

macOS 15.6.1 arm64、Firefox 157.0（ビルド20261002115412）、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4を用いた。両実行で固定上流の歌唱とエンジンの各17試験を通過した。Firefoxの12試行でPCM各91,200点、音響観測1,425行、予定拍、調音計画と資産ハッシュが基準と一致し、固定上流との最大PCM差は2.33×10⁻¹⁰だった。プロファイルとWAVをgzipで可逆圧縮し、成果約33.72 MBをRTL9210B-CGに保存した。[初回マニフェスト](../runs/worklet-live-song-render-phases-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-render-phases-20261121-repeat/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_render_phases.py worklet-live-song-render-phases-next
```
