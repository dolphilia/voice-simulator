# 先行音が鳴るAudioContextに発声ノードを追加する

## 固定上流とブラウザの経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` は `AudioEngine` がグラフと出力を持ち、`ChimeraProcessor` のコンストラクターでWASMをインスタンス化する。コールバックでは出力チャンネルの長さをフレーム単位で `engine_render` に渡し、戻り値のポインターからPCMをコピーする。Rustの `Engine::render` は内部の出力フレーム位置 `pos` を持ち、64フレームの境界までの残りと出力残量の小さい方ずつ描く。ブロック長1・77・128・4,096・48,000フレームで、同じ操作時刻のPCMをビット照合するテストがある。上流の画面は立ち上がり2秒の負荷をレート変更の判定から除外する。[上流の音声グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[Rustのブロック処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流の分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

候補の通常画面は指定レートの `AudioContext` を再開し、WorkletモジュールとWASMの準備が済むと発声ノードを出力へつなぐ。前回の実験オプションは、同じ発声ノードのコンストラクター内でWASMのレンダー入口を0フレーム指定で呼ぶ。Rustは状態更新前に戻り、準備回数1,000でV8が同期コンパイルした。ブラウザ仕様では一つのContextのWorkletは同じオーディオレンダリングスレッドに属し、`currentFrame` は処理量子の先頭フレームを表す。既存の音が鳴っているときは、新しい発声ノードの採取前にも他の出力がそのスレッドを使っている。[候補の接続順](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)・[0フレームの準備](worklet-wasm-wrapper-warmup.md)・[Web Audio仕様のAudioWorklet](https://www.w3.org/TR/webaudio-1.1/#AudioWorklet)

## 観測点と予測

通常画面から96 kHzの固定 /i/ を開始する。テストだけがモジュール読み込み時に、先行する `AudioBufferSourceNode` とパススルーの観測Workletを同じContextへ接続する。既存音の採取が96量子に達してから通常の発声ノードを作る。出力先は同じ `destination` で、先行音だけを混合の手前で観測する。観測Workletは入力をそのまま出力し、絶対フレームと1,536量子分のPCMを事前に確保したバッファに記録する。[事前登録](../cases/worklet-wasm-wrapper-shared-context.json)・[先行音と接続](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[観測Worklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)

先行音の予定開始フレームを `S` とし、Contextフレーム `f` のサンプル番号を `n = f − S` とする。32ビット浮動小数点PCMを `((421 n + 173) mod 65,521 − 32,760) / 524,288` で決めた。量子ごとに先頭フレームが128増え、PCMがこの式と一致すると予測する。実際のPCMをバイトで保存し、NumPyの整数計算から独立に得た系列と照合する。発声側は通常の出力と同じ候補CLI・固定上流の比較に加え、前回の単独ContextのPCM・音響状態ハッシュを照合する。[判定コード](../tools/measure_worklet_shared_context.py)・[発声の比較基準](../cases/worklet-realtime-release-alignment.json)

コンストラクターの前後と先行音の各コールバックに絶対フレーム付きのトレース印を置く。Chromiumの処理区間に入っている印で先行音側のイベントを特定し、残る発声側のイベント数を採取と起動待ちの和に照合する。コンパイルは準備なしなら合成の1,000量子目、1,000回の準備ならコンストラクター内に1回と予測する。壁時計では、前後8量子、コンストラクターを挟む隣接コールバック、先行音だけの基準区間を µs で記録する。Contextのフレームが連続しながら、壁時計でコールバックがまとめて実行されることはありうる。1.333 msの量子予算を超えた間隔や構築時間と、グラフ内のPCM欠落は別に判定する。[Chromiumの量子トレース](https://chromium.googlesource.com/chromium/src/%2B/main/third_party/blink/renderer/modules/webaudio/audio_worklet_processor.cc#533)・[Chromiumのタイムスタンプ実装](https://chromium.googlesource.com/chromium/src/%2B/refs/heads/main/third_party/blink/renderer/core/inspector/thread_debugger_common_impl.cc)

## 結果

確定実行と `/tmp` からの再実行で各166判定を通過した。全12試行で両Workletのトレースが同じオーディオスレッドに対応した。先行音は各1,536量子、196,608フレームが連続し、全2,359,296サンプルが独立計算とビット一致した。発声音は単独Contextの記録とPCM・音響状態のハッシュが同じで、候補CLIのPCMにも全フレームで一致した。固定上流との最大PCM差は2.92×10⁻¹¹未満、ゲートの独立計算との差は最大2.11×10⁻¹⁵。[確定実行](../runs/worklet-wasm-wrapper-shared-context-20261121-c/summary.json)・[再実行](../runs/worklet-wasm-wrapper-shared-context-20261121-repeat/summary.json)

| 事前呼び出し | 同期コンパイル | コンストラクター全体（ms） | 構築をまたぐ先行音のコールバック間隔（ms） |
| --- | --- | ---: | ---: |
| 0回の6試行 | 採取の1,000量子目に各1回 | 4.452〜6.178 | 5.543〜9.880 |
| 1,000回の6試行 | コンストラクター内に各1回。0.215〜0.402 ms | 4.653〜6.179 | 5.325〜7.348 |

構築をまたぐ間隔は、先行音だけの同じ試行の最大値を12回中11回で超えた。先行音だけでも各試行の最大間隔は5.339〜5.365 msで、128フレームの1.333 msと一致しない。Chromiumのバッチ実行を含む壁時計であり、フレーム列とグラフ内PCMには欠落を観測しなかった。両条件で構築時の間隔が延びたため、この比較から事前呼び出しだけが延長を作ったとは判定できない。物理出力の期限や聴感は計っていない。[試行別の構築前後の時刻](../runs/worklet-wasm-wrapper-shared-context-20261121-c/summary.json)・[再実行の時刻](../runs/worklet-wasm-wrapper-shared-context-20261121-repeat/summary.json)

採取の最初の発声量子は準備なしで6回中4回、準備ありで6回中5回、予算を超えた。生トレースから先行音の区間を除き、`startupCallbacks` 件の直後の区間を抽出したところ、12試行すべてでWASM関数本体の遅延コンパイルを観測した。準備なしで11件、準備ありで10件。イベント期間の和は0.417〜0.501 msだった。これはラッパーの `CompileJSToWasmWrapper` と別の `wasm.CompileLazy` で、0フレームで早期に戻る準備では発声の計算経路がまだ呼ばれない。1,000回の準備で解消したのは採取の1,000量子目の同期コンパイルで、先頭量子の予算超過は別の比較を要する。[確定実行の生トレースの所在](../runs/worklet-wasm-wrapper-shared-context-20261121-c/manifest.json)・[V8の関数本体のコンパイル](https://chromium.googlesource.com/v8/v8/%2B/main/src/runtime/runtime-wasm.cc#373)・[ラッパーの計測点](https://chromium.googlesource.com/v8/v8/%2B/refs/heads/main/src/wasm/function-compiler.cc#220)

## 欠測と再現

初回はPlaywrightページのルート差し替えがWorkletの取得に適用されず、Viteが同じURLへHTMLを返した。発声採取を待つ試行を中断し、リクエストと応答MIMEの生トレースを残した。計測用Viteプレビューで同じURLをJavaScriptとして配信して解消した。2回目は6試行のWAVとトレースを取得したが、区間の合否に含まれたNumPyの真偽値を標準JSONへ直列化できなかった。Pythonの真偽値に変換し、保存済み6試行の先行音とトレースを再解析して全照合を通過した。確定実行は元の事前登録のまま新しいIDで採った。[HTML応答と中断の記録](../runs/worklet-wasm-wrapper-shared-context-20261121-a/manifest.json)・[直列化で失敗した実行と生データ](../runs/worklet-wasm-wrapper-shared-context-20261121-b/manifest.json)

研究ワークスペースから次のコマンドを実行する。実行IDは新しく指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=400000000 \
  ../../.venv/bin/python tools/measure_worklet_shared_context.py worklet-wasm-wrapper-shared-context-next
```

macOS 15.6.1 arm64、Headless Chromium 156.0.8078.4、V8 15.6.75、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で実行した。先行音PCM、発声WAVと観測JSON、生トレースは実行後に可逆圧縮し、主比較2実行の約23.96 MBをRTL9210B-CGに置いた。個々の入力、実行コマンド、出力のパス・ハッシュを保存した。[確定実行のマニフェスト](../runs/worklet-wasm-wrapper-shared-context-20261121-c/manifest.json)・[再実行のマニフェスト](../runs/worklet-wasm-wrapper-shared-context-20261121-repeat/manifest.json)

先行音を追加しない従来経路でラッパーの呼び出し予算も再照合し、85判定を通過した。欠測と回帰を含む5実行の197出力をマニフェストのSHA-256と照合した。[従来経路の回帰](../runs/worklet-wasm-wrapper-threshold-20261121-shared-regression/summary.json)

後続の対照では、ラッパー準備後に残っていた10関数を使い捨ての発声状態で先に呼び、本番の先頭量子から遅延コンパイルが移ることを確認した。[WASM関数本体の事前描画](worklet-wasm-dsp-warmup.md)
