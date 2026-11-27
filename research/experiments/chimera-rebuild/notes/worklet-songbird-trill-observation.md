# 鳴禽 `trill` の観測位置とWorkletの処理時間

固定上流の飼育室はコールID、移調、振幅を `AudioEngine.playCall` からWorkletへ渡す。Workletの `call` から `engine_play_call` を通った要求を `CreatureVoice` が制御時計とともに保持する。上流Workletの `process` は量子ごとに `engine_render` を1回呼び、テレメトリは描画の計時後に6量子ごとに取得する。テレメトリには気道断面や窓の圧力RMSがあり、読出しは集計をリセットする。上流のRustテストはコールを含む固定波形とテレメトリを照合し、開始・停止・観測を含む描画の割り当てを調べる。[コール受付と量子処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[固定波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[割り当て試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

鳴禽の `trill` は周期 `T=1/16` 秒の18パルスを生成する。無次元の呼気目標は各周期の `0, 0.08T, 0.62T, 0.75T` に `0, 1, 1, 0` を与え、制御の評価後に `g ← g+(g*−g)(1−exp(−Δt/τ))` で更新する。平滑ゲート `g` と圧力目標（kPa）を掛け、さらに10,000倍して気嚢の境界圧（dyn/cm²）とする。鳴管の左右の開口から断面積（cm²）を求め、気道を伝搬させて放射・間引き・DC除去を経た `f32` PCMを出力する。48 kHzの出力1フレームは内部192 kHzの4サンプルに対応し、出力フレーム `i` の観測は内部サンプル `4(i+1)−1` にある。[周期キーと気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[従来の周期測定](worklet-songbird-trill.md)

研究用Workletは、PCMと同じ時刻の状態を保存するために、次の描画量子の終点、イベントの直前、観測フレームの直後のうち最も早い境界でRustの呼び出しを区切る。Rustの制御カウンタは呼び出しをまたいで継続する。上流の画面用テレメトリと研究用のサンプル観測では観測内容と計時範囲が異なるため、今回の性能値は研究用Workletの中で比較する。先行実行では、64フレーム刻みの同じ条件でもp95が2 msと3 msに分かれた。[研究用の処理ループ](../../../../web/prototypes/chimera-research/src/creature-processor.ts#L90)・[先行の処理予算超過](../runs/worklet-songbird-trill-20261120-shell-check/summary.json)

## 事前登録

48 kHz、76,800フレーム、開始要求73の既存ケースを使用する。各条件で開始前後の72・73・127と末尾を記録し、他の観測点だけを変更する。描画量子は128フレーム、Rustの最大呼出長も128フレーム。量子内で重なるイベント境界と観測境界は1回と数える。したがって第1量子だけ各条件で追加2回、残り599量子では表の呼び出し回数になる。[登録条件と試行順](../cases/worklet-songbird-trill-observation.json)・[先行の登録条件](../cases/worklet-songbird-trill.json)

| 観測位置 | 通常量子における境界 | WAV全体のWASM描画呼び出し | 観測点 |
| --- | --- | ---: | ---: |
| 制御区間の先頭、64フレーム刻み | 量子内の1・65・128で終了 | 1,802 | 1,204 |
| 制御区間の末尾、64フレーム刻み | 64・128で終了 | 1,202 | 1,202 |
| 量子の末尾、128フレーム刻み | 128で終了 | 602 | 602 |

64フレームの末尾条件と128フレームの末尾条件を比較して、量子内で揃う観測位置のうち毎回入れる点だけを減らす。先頭・末尾の64フレーム条件からは、同じ頻度で位置を動かしたときの分割回数を比較できる。3条件を一組として、順序の全6通りを同じブラウザプロセスで続けて測る。各試行の最初の8量子を処理時間の集計から除き、同じ計時法の中央値・p95・p99と予算 `128/48000×1000 ≈ 2.67 ms` を超えた量子数を保存する。予算の合否は試行ごとに保持し、入力・PCM・観測・描画回数の再現条件と別に報告する。

音響の合否条件はCLIとの加工前PCMのビット一致、全観測点におけるCLIの状態との差0、条件間の共通観測点の一致、固定上流の既定許容差。すべての描画量子の連続性、描画呼び出し数と各量子の境界の独立計算、従来条件の18呼気パルス、ネイティブ境界の描画中の割り当て0件も確認する。

## 実装

既存の「鳴禽のコール」から3つの観測条件を選べるようにした。各条件とも同じ入力をRustへ送り、同じ `trill` ケースを書き出す。Workletには計測時のみ事前確保する量子別の計数配列を追加し、描画を終えたときにPCMと内部状態とともに転送する。`vocal_songbird_render` は各呼び出しで最後の内部状態を観測バッファへ書く。現行の計測にはこの書き込みと呼び出し境界の処理、観測値のコピーが含まれる。Pythonの比較器は量子、イベント、観測の境界を集合として独立に列挙し、量子別計数を照合する。[再生条件](../../../../web/prototypes/chimera-research/src/main.tsx)・[Worklet](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[WASMの描画と観測](../crates/vocal-wasm/src/songbird.rs#L193)・[比較器](../tools/measure_worklet_songbird_trill_observation.py)

最初の実行では18回のブラウザ描画とCLI出力の保存後、比較器がブラウザの部分列をCSV全体の列定義として渡したため照合を中断した。既存の鳴禽コール比較器と共通の39列でCSVを読み、必要な29列を取り出すように直した。保存済みデータを再照合して182項目を確認し、同じ入力と登録条件で実時間計測をやり直した。[最初の失敗と保存した入力・出力](../runs/worklet-songbird-trill-observation-20261120-a/manifest.json)

## 描画分割と音響の結果

すべての観測条件で量子別のWASM呼び出しが事前の独立計算と一致した。最初の量子では開始境界を含めて5、4、3回、以後は3、2、1回だった。64フレーム刻みを末尾に揃えるだけで全体の1,802回から1,202回へ減り、量子末尾だけでは602回になった。開始直後を除いた592量子での合計は1,776、1,184、592回だった。[各試行の呼び出し回数](../runs/worklet-songbird-trill-observation-20261120-b/summary.json)

加工前PCMは各試行76,800フレームでCLIとビット一致した。従来の先頭観測条件は固定上流とも加工前PCMがビット一致し、共通の内部状態24列は最大差0だった。CLIとの内部状態29列は全試行・全観測点で最大差0。先頭とほかの条件の共通観測点はそれぞれ4点で、64フレーム末尾と128フレーム末尾は602点すべてで一致した。先頭観測での呼気パルス数18、ゲートの交差時刻、自然終了は従来の判定を通過した。[固定上流・CLI・観測条件間の判定](../runs/worklet-songbird-trill-observation-20261120-b/summary.json)

## 処理時間の結果

各条件を6回ずつ測る実行を2回行った。集計は1 ms刻みの `Date.now` で、各試行の起動直後の8量子を除いた592量子が対象。試行のp95を2.67 msの予算と比べ、個々の量子の超過も数えた。

| 観測位置 | 試行別p95の範囲 | 試行別p99の範囲 | p95が予算内の試行 | 予算超過量子の合計 |
| --- | ---: | ---: | ---: | ---: |
| 制御区間の先頭・64フレーム刻み | 1〜2 ms | 1〜3 ms | 12/12 | 54 / 7,104 |
| 制御区間の末尾・64フレーム刻み | 1〜3 ms | 1〜3 ms | 11/12 | 127 / 7,104 |
| 描画量子の末尾・128フレーム刻み | 1〜3 ms | 1〜3 ms | 10/12 | 152 / 7,104 |

同じ組の64フレーム末尾と128フレーム末尾を比べると、観測を減らした条件のp95は12組のうち1組で短く、8組で同じ、3組で長かった。この計時方法では、呼び出し回数の減少による安定した処理時間短縮を確認できなかった。p95が予算を超えた試行も、加工前PCM・観測値・描画間隔の判定には通過した。計測値と同時に音声処理スレッドの実行時間を採取する対照や、観測位置を固定したままWASM呼び出しだけをまとめる対照で、今回の計時の揺れと分割処理の影響を調べられる。[第1回の全試行](../runs/worklet-songbird-trill-observation-20261120-b/summary.json)・[第2回の全試行](../runs/worklet-songbird-trill-observation-20261120-repeat/summary.json)

## 再現と回帰

`/tmp` からの2回の本計測で各183項目を通過した。各18試行の観測18,048行と量子別の呼び出し回数が一致し、WASM、ケース、PCM、CLI出力の計39ファイルのSHA-256も一致した。従来の `trill` を研究ディレクトリから再実行し、18項目が通過した。以前の実行と観測1,204行、ケースとCLI出力を含む4ファイルが一致した。ネイティブ境界の描画中の割り当ては0件。Rustの整形・Clippy・試験39件と、ブラウザのTypeScript・Vite本番ビルドも通過した。[第1回の実行環境とコマンド](../runs/worklet-songbird-trill-observation-20261120-b/manifest.json)・[第2回の実行環境とコマンド](../runs/worklet-songbird-trill-observation-20261120-repeat/manifest.json)・[従来条件の回帰](../runs/worklet-songbird-trill-observation-regression-20261120/manifest.json)

研究ディレクトリで固定上流と照合済みの基準を指定して実行する。実行IDには未使用の名前を使う。

```bash
python3 tools/measure_worklet_songbird_trill_observation.py worklet-songbird-trill-observation-local-1 songbird-trill-before-worklet-1
```
