# 実時間AudioWorkletでの鳴禽コール trill の周期

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。飼育室の `CallActions` から `AudioEngine.playCall`、Workletの `call` メッセージ、`engine_play_call`、`Engine::play_call` を経て、`CreatureVoice::play_call` がコールID、現在の制御時計（秒）、移調比、呼気倍率を保持する。固定条件では、上流のゴールデン試験が操作のフレームで区切りながらレンダーし、波形とテレメトリを比較する。128フレームの結果を1・77・4,096フレーム分割とも照合する。実時間試験はその経路のコール切り替えと観測で割り当てがないことを検査する。[操作画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L54)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L152)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`songbird::trill` は周期 `T = 1/16 = 0.0625 s` で18周期分のキーを生成する。各周期の0・0.08・0.62・0.75倍の時刻で無次元呼気目標を0・1・1・0へ設定する。音高のキーは周期頭の `3000 × (1 − 0.35/2) = 2475 Hz` と0.62倍時点の `3000 × (1 + 0.35/2) = 3525 Hz`。音高の上昇は指数補間で、次の周期の頭では段差で戻る。`CreatureVoice::eval_call` は制御時計の経過秒でキーを補間し、`control` はその後に手動とコールの呼気目標の大きい方へ平滑呼気を更新する。呼気の立ち上がり時定数は4 ms、減衰は12 ms。気嚢圧、鳴管と共通気道、放射・間引き、f32 PCMの順に作用する。末尾キーの0.05秒後を過ぎると識別子が消え、目標が演奏者の値へ戻る。[周期キー生成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L122)・[評価と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[CLIでの周期検証](songbird-calls.md)

## 実装前の予測と判定

48 kHz・76,800フレームの既存CLI条件を使い、73フレームにコール開始を指定する。制御の初回評価は128フレーム。128フレームの描画量子に対し、観測は0から64フレーム刻みと末尾とし、開始指示前後の72・73・127も追加する。呼気目標0.5の理想の上向き交差は、各周期頭に `T × 0.08 × 0.5` 秒を足した時刻。理想の間隔は3,000フレームなので、64フレーム格子で観測される間隔は2,944または3,008フレームになる。閾値関係の丸め誤差を含め、独立計算との差は最大1制御刻みで判定する。登録キーから計算する制御系列とも照合する。自然終了は最後の0キーと0.05秒の余裕から導く。加工前PCMはCLIとビット一致を要求し、固定上流の参照と状態・PCMの差も測る。[新規登録](../cases/worklet-songbird-trill.json)・[原ケースの第2版](../cases/songbird-calls-v2.json)・[実装前CLIの基準](../runs/songbird-trill-before-worklet-1/summary.json)

## 処理時間の再確認条件

コール・PCM・観測の判定が一致したまま、Chromiumヘッドレスシェルの追加実行で描画時間のp95が2.67 msの予算を超えた。同じケース、計時方法、閾値、ビルドを使い、ヘッドレスシェルで再計測する。ブラウザの実行ファイルをインストール済みChromeに変えた場合の結果も別の実行IDで保存する。比較する値はPCMと観測系列の同一性、処理時間の中央値・p95・p99、予算超過量子数、描画間隔。[超過が出た実行](../runs/worklet-songbird-trill-20261120-final/summary.json)

## 実装と結果

「鳴禽のコール」に `trill` の登録ケースを追加した。開始指示と制御・観測の境界は既存のWorkletで適用し、Rustの合成器とC ABIを共有する。観測は開始位置を指定できるようにし、このケースでは出力フレーム0から64の倍数を選ぶ。固定時刻周辺と末尾を加えた1,204点を採取する。比較器は `flute` と共通のPCM・状態照合を行い、`trill` の交差判定にはキーの時刻を有理数で計算した値を使う。ネイティブの割り当て試験には `trill` の開始から自然終了後までを追加した。[観測時刻の決定](../../../../web/prototypes/chimera-research/src/render-creature.ts)・[コール比較器](../tools/measure_worklet_songbird_call.py)・[周期の独立計算](../tools/measure_worklet_songbird_trill.py)

48 kHzの加工前PCMは全76,800フレームがCLI・固定上流とビット一致した。CLIと比較した29列と固定上流に共通する24列の状態は最大差0。キーから独立に計算した呼気目標も一致し、平滑呼気の最大差は `2.22e-16` だった。フレーム73で識別子が2になり、128で最初のキーを評価して音高目標は2,475 Hz、55,808で識別子が0に戻った。呼気目標0.5の上向き交差は18回、間隔は2,944または3,008フレーム、平滑呼気の交差はさらに64または128フレーム後だった。[最初の測定](../runs/worklet-songbird-trill-20261120-a/summary.json)

理想の交差が64フレーム格子に一致するパルスは8回目と16回目だった。計測した制御時計から開始時刻を引くと、8回目の21,248フレームでは理想より `2.33e-15` 秒進み、呼気目標が0.5000000000004663だった。16回目の45,248では `8.82e-15` 秒遅れ、呼気目標が0.49999999999823475だった。16回目の判定は次の45,312まで遅れた。連続的な呼気目標の差は微小でも、二値化した交差時刻は1制御刻み動く。次の対照では、累積した秒を用いる現行版と、整数フレームから各時刻を求める条件を、同一のキー列と閾値で比較できる。[境界時刻と呼気目標](../runs/worklet-songbird-trill-20261120-final/summary.json)

## 処理時間と再実行

48 kHzの128フレーム描画の予算は約2.67 ms。起動直後の8量子を除いた592量子を `Date.now` の1 ms刻みで測った。各回とも `currentFrame` は128フレーム間隔で進み、ネイティブの割り当ては0件。閾値は登録時の値を使った。

| 実行 | p95 | 予算超過量子 | 全体判定 |
| --- | ---: | ---: | --- |
| Chromiumヘッドレスシェルの最初の測定 | 2 ms | 6 | 18項目通過 |
| ヘッドレスシェルの再確認 | 3 ms | 48 | p95の判定が未達 |
| Chromeの再試行（ヘッドレス） | 2 ms | 4 | 18項目通過 |
| ヘッドレスシェルの再試行 | 2 ms | 9 | 18項目通過 |

Chromeの初回はページが暗黙に要求した `favicon.ico` の404も記録した。アイコンURLをHTMLで明示して再試行した。別ディレクトリ・両ブラウザで、WASM・WAV・再実行ケース・CLIのCSVとWAVの5ファイルのSHA-256と全1,204点の観測値が一致した。既存の `flute` と48・96 kHzの持続音もWAVと観測に差はなかった。処理時間のp95には実行間で変動が残る。次の性能対照では、同じ入力で制御区間先頭の観測と描画量子末尾だけの観測を交互に実行し、WASM呼び出し回数と時間分布を比較する。[ヘッドレスシェルの超過](../runs/worklet-songbird-trill-20261120-shell-check/summary.json)・[404のURL](../runs/worklet-songbird-trill-20261120-chrome-diagnostic/artifacts/browser-run.json)・[Chromeの再試行](../runs/worklet-songbird-trill-20261120-chrome-retry/manifest.json)・[シェルの再試行](../runs/worklet-songbird-trill-20261120-shell-retry/manifest.json)・[fluteの回帰](../runs/worklet-songbird-flute-trill-regression-20261120/summary.json)・[持続音の回帰](../runs/worklet-songbird-sustain-trill-regression-20261120/summary.json)
