# 実時間発声を進めずにWASMラッパーを準備する

## 固定上流と比較する境界

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor` は、コンストラクターでWASMをインスタンス化し、グラフの実サンプルレート（Hz）を `engine_new` に渡して準備完了を返す。音声コールバックは生存中のハンドルと出力チャンネルの長さ（フレーム）を `engine_render` に渡す。Rustはレンダー長を出力バッファ容量に収め、`Engine::render` が更新した浮動小数点PCMのポインターを返す。Workletは先頭チャンネルにコピーし、上流のエンジン試験は同じ操作時刻でホストのブロック分割を変えてもPCMが一致することを検査する。上流のコンストラクターから `engine_render` を事前に呼ぶ経路は見当たらない。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[上流のWASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[上流のEngine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[ブロック分割のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

候補の `startRealtimeVoice` はコンパイル済みモジュールとゲート0の入力を渡し、`LiveProcessor` の `FixedVoiceEngine` が発声器とPCM・観測へのビューを用意する。起動待ちの量子を終えるまで発声は進まない。その後、量子境界でゲートの目標を適用し、`renderInto` が `vocal_render(handle, 128)` を呼んでPCMを取り出す。Rustの `vocal_render` は生存中のハンドルと1〜4,096フレームを取り、成功1を返す。範囲外の0はこの関数に入るが、呼気・声門・気道・出力段と累計 `rendered`、PCMと観測を書き換えるループへ入る前に0を返す。Rustの割り当て検査にもこの呼び出しを加えた。[接続と経過時刻の入口](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)・[Workletの起動と量子処理](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[ホスト実装](../crates/vocal-wasm/host/fixed-voice.ts)・[候補のABIとテスト](../crates/vocal-wasm/src/lib.rs)

## 予測と操作

V8の汎用JS→WASMラッパーは呼び出しに入った段階で残り回数を1減らす。WASM側の入力検査が0フレームを拒否しても、JS側で同じエクスポートの呼び出しとして数えられると予測した。標準設定の予算を1,000とすると、起動時の呼び出し回数 `k < 1000` では採取の `1000 − k` 量子目（1始まり）でコンパイルし、`k = 1000` では採取前になる。発声状態を少しでも進めれば、絶対サンプル番号やゲート・出力段がずれるため、全量子の状態列と全PCMを照合する。[V8のカウンター更新](https://chromium.googlesource.com/v8/v8/%2B/3a18fc10da54a9f1c961da2acdb386de29531b1f/src/builtins/js-to-wasm.tq#510)・[前回の呼び出し予算の対照](worklet-realtime-release-alignment.md)・[事前登録](../cases/worklet-wasm-wrapper-warmup.json)

通常の画面と同じWorkletコンストラクターに実験用設定を渡し、同じインスタンスの同じエクスポートをその場で0・999・1,000回呼ぶ。試行ごとにChromiumを既定設定で起動する。ゲートは発声を66量子目、停止を816量子目の境界（0始まり）で行い、96 kHz・128フレームずつ1,728量子を採取する。入力は固定 /i/、F0 110 Hz、肺圧7.2 cmH₂O。9試行は3条件の順を入れ替えた。[計測コード](../tools/measure_worklet_wrapper_warmup.py)・[呼気と発声の条件](../cases/worklet-realtime-release-alignment.json)

WorkletはWASMのエンジン初期化と事前呼び出しの所要時間（ms）を別々に記録する。コンストラクターが呼び出されたときの `currentFrame`、起動待ちの最初、および採取した最初のContextフレームも保存する。Chromiumのトレースでは、起動待ちを含む `process()` の先頭に対するコンパイルの位置、先頭と1,000量子目の処理時間（µs）を照合する。コンストラクターも同じオーディオスレッドで動くので、採取前に移せても、既に別のノードが鳴っているグラフへの負荷は別に調べる必要がある。[Chromiumの量子処理の計測点](https://chromium.googlesource.com/chromium/src/%2B/main/third_party/blink/renderer/modules/webaudio/audio_worklet_processor.cc)・[トレース判定](../tools/measure_worklet_wrapper_threshold.py)

PCMはホスト分割77・128のCLIと固定上流へ照合し、さらに前回の通常Chromium設定で得たWAVのハッシュと比較する。ゲートは64サンプルごとの指数更新を独立の閉形式で計算し、量子末尾に合わせた。ビット比較用の状態列には採取内の累計フレーム数と全音響観測を使い、Contextの絶対フレームと時計は別に評価する。[CLI・ゲートの比較](../tools/measure_worklet_release_alignment.py)・[独立ゲートの式](worklet-realtime-release-alignment.md#呼気停止時刻の比較)

## 結果

初回と `/tmp` からの再実行で各156判定に合格した。6試行ずつ、計18試行で同じスレッド上の同期コンパイルを1回ずつ観測した。1,000回条件では最初の起動待ちコールバックより7.136〜7.779 ms前にコンパイルが終わり、採取中には出なかった。どの試行も起動待ちの後はContextフレームが連続し、WASM線形メモリが伸びなかった。PCMと量子末尾の状態は全条件でビット一致し、既存の通常Chromium設定ともWAVのSHA-256が一致した。固定上流との最大PCM差は2.92×10⁻¹¹未満、ゲートの独立計算との最大差は2.11×10⁻¹⁵。[初回の結果](../runs/worklet-wasm-wrapper-warmup-20261121-a/summary.json)・[再実行の結果](../runs/worklet-wasm-wrapper-warmup-20261121-repeat/summary.json)

| 事前呼び出し | コンパイルの位置 | コンパイル（ms） | 最初の採取量子（ms） | 1,000量子目（ms） |
| --- | --- | ---: | ---: | ---: |
| 0回 | 採取の1,000量子目 | 0.348〜1.915 | 0.994〜1.048 | 0.723〜3.164 |
| 999回 | 採取の最初の量子 | 0.230〜0.243 | 1.191〜1.270 | 0.264〜0.816 |
| 1,000回 | 起動待ちの前 | 0.213〜0.251 | 0.931〜0.998 | 0.236〜0.902 |

準備なしの6回では、同期コンパイルを含む量子が2回、末尾が1回、1.333 msの予算を超えた。999回では別の発声中の量子と末尾が1回ずつ、1,000回では末尾だけが1回（2.236 ms）超えた。1,000回の事前呼び出し全体はWorkletの1 ms刻みの時計で0〜1 ms。WASMエンジンの初期化は全条件で3〜4 ms、画面で使う接続から発声通知までの値は全条件で約109〜119 msに重なった。初期化や通知の差の大きさは、この試行数と計測分解能では判定しない。[全試行の予算超過と起動時計](../runs/worklet-wasm-wrapper-warmup-20261121-repeat/summary.json)

準備回数は研究用のWorkletオプションにした。標準画面は従来の準備なしの経路を使う。Chromiumのトレースが示すのはライブ処理区間内の同期コンパイルを起動側へ移せること。ブラウザの別エンジン、既に再生中のノードへの影響、実機の物理出力は未計測。末尾量子の完了通知と出力の転送は、準備を適用した条件でも次の切り分けに残る。[実験オプションと完了処理](../../../../web/prototypes/chimera-research/src/live-processor.ts)

## 再現と保存

研究ワークスペースから次のコマンドで実行する。実行IDは新しく指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  ../../.venv/bin/python tools/measure_worklet_wrapper_warmup.py worklet-wasm-wrapper-warmup-next
```

macOS 15.6.1 arm64、Headless Chromium 156.0.8078.4、V8 15.6.75、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で実行した。WAV、観測JSON、生トレースを計測後に可逆圧縮し、2実行の約21.35 MBをRTL9210B-CGに置いた。入力のスナップショット、実行条件、個々の成果ハッシュはマニフェストから参照できる。[初回のマニフェスト](../runs/worklet-wasm-wrapper-warmup-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/worklet-wasm-wrapper-warmup-20261121-repeat/manifest.json)

事前呼び出しの設定を渡さない従来経路で呼び出し予算の対照を再実行し、85判定を通過した。Rustは `cargo test --locked -p vocal-core -p vocal-wasm` の41試験、`cargo clippy --locked -p vocal-wasm --all-targets -- -D warnings` と `cargo fmt -p vocal-wasm -- --check` を通過した。ワークスペース全体の整形検査では、既存の `vocal-core/src/phonetics.rs` のモジュール宣言順に差が出た。該当箇所は今回の変更範囲外。[従来経路の回帰](../runs/worklet-wasm-wrapper-threshold-20261121-warmup-regression/summary.json)・[整形差の箇所](../crates/vocal-core/src/phonetics.rs#L8)

後続の同一Contextの対照では、先行音のグラフ内PCMとフレームを照合した。ラッパーを準備しても最初の発声量子にはWASM関数本体の遅延コンパイルが残った。[先行音を流した比較](worklet-wasm-wrapper-shared-context.md)
