# 実時間AudioWorkletでのウェッデルアザラシの持続音と停止

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`AudioEngine` の種選択と呼気操作はWorkletの `creature` と `gate` を経て、WASMの `engine_set_creature` と `engine_set_gate` に届く。前者がアザラシの気道とレンダー状態を作り、後者が `Engine::set_gate` から `CreatureVoice` の手動呼気を設定する。出力は `engine_render` から取得する。ゴールデン試験は操作位置でブロックを分け、PCM・包絡・テレメトリを比較し、ブロック長1・77・128・4,096でもPCMを照合する。実時間試験はウォームアップ後の呼気・コール・観測中の割り当てを数える。[Workletの入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L130)・[種の設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L465)・[呼気操作](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L119)・[WASMの出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L16)・[割り当て試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`CreatureVoice::control` は64出力フレームごとに無次元の呼気目標 `g*` と現在値 `g` を使い、`g* + (g−g*) × exp(−Δt/τ)` で更新する。アザラシの時定数は立ち上がり6 ms、減衰30 ms。`Seal::control` は位相にパルス周波数と制御周期の積を足して1周期に戻し、デューティより小さい位相で半正弦 `h=sin(πφ/duty)` を作る。肺圧は `pressure_cm_h2o × 980.665 × g × (1−depth+depth×h)` dyn/cm²。出力開始前に無呼気の制御を一回行うので、最初の観測フレームの位相は2刻み進んでいる。声門の流量を気道へ入れ、口端・鼻端・壁面の放射流量（cm³/s）を合計し、内部サンプル間で時間差分を取る（cm³/s²）。このケースの鼻腔経路には放射口があるが、口鼻をつなぐ通路が閉じている。出力48 kHzでは内部96 kHzから2倍間引きし、出力96 kHzでは同じ内部レートを直接使う。スケーリング・12 HzのDC除去・飽和を通してf32 PCMになる。[呼気と波形の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[アザラシのパルスと声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[口鼻の構造](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs)・[再実装の呼気](../crates/vocal-core/src/seal_breath.rs)・[出力](../crates/vocal-core/src/seal_voice.rs#L210)

## 実装前の予測と判定

公式CLIの先頭と対応する48 kHz・76,800フレーム、量子途中の指示を含む96 kHz・57,600フレームを使う。48 kHzは0と57,600、96 kHzは145と16,001に呼気目標を指示する。反映はそれぞれ0と57,600、192と16,064で、96 kHzの指示直後は次の64フレーム制御まで保持する。加工前PCMはCLIとビット一致し、固定上流とは既存の `1e-6` 以内で一致すると予測した。96 kHzのCLI基準にある上流との差も最初に現れる合成段を調べる。[登録ケース](../cases/worklet-seal-sustain.json)・[基準ケースと許容差](../cases/seal-sustain-pcm.json)・[CLIの読解](seal-sustain-pcm.md)

観測は64フレームごとの制御更新直後と、指示・反映・放射開始の前後、末尾。両方の内部スロットを保存する。壁面開始は内部39・231、口端は95・287、PCMは出力19・231。鼻端は観測した全点で0、停止後の末尾20 msと停止前のRMS比は基準の `3e-5` 以下とする。独立に計算する呼気・肺圧と、CLIの内部放射から独立に再構成する間引き・DC除去・PCMを追加で比較する。描画128フレームの間隔を追い、先頭8ブロックを除いたp95を各出力レートの描画予算と照合する。[固定上流とCLIの基準](../runs/seal-sustain-before-worklet-1/summary.json)

## 実装と実測

研究画面の「ウェッデルアザラシの持続音」は、登録した時刻に呼気の開始と停止を再生する。共通の動物用Workletは、描画量子の途中でも操作と観測点でレンダーを分ける。アザラシ用C ABIは最大128フレーム分の記憶域を確保し、CLIと同じ `SealVoice` を進める。Workletは出力フレーム、対応する最後の内部サンプル、ゲート目標・平滑値、肺圧、壁面・口端・鼻端・総放射の内部スロット、間引き後・DC除去後の値を保存する。倍率1では第2スロットが0になる。画面から保存したケースは `vocal-cli render-pcm` で再実行できる。[Worklet](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[アザラシ用C ABI](../crates/vocal-wasm/src/seal.rs)・[比較器](../tools/measure_worklet_seal_sustain.py)

| 出力レート | PCMフレーム・観測点 | 呼気の指示 → 反映（出力フレーム） | 壁面／口端／PCMの開始 | 末尾20 msのRMS／定常時のRMS |
| --- | --- | --- | --- | --- |
| 48 kHz | 76,800・1,206 | 0 → 0、57,600 → 57,600 | 内部39／内部95／出力19 | `1.69e-8` |
| 96 kHz | 57,600・910 | 145 → 192、16,001 → 16,064 | 内部231／内部287／出力231 | `1.13e-8` |

両レートとも、呼気目標が正になってから内部39サンプルで壁面、95サンプルで口端が放射し、鼻端は全観測点で0だった。口端までの追加56サンプルは内部96 kHzで約0.583 msに当たる。96 kHzの制御待ちは開始47フレーム、停止63フレームで、描画量子の境界と制御境界を分けて再現できた。独立に計算した肺圧の最大絶対差は両条件で `4.13e-10 dyn/cm²` 未満。CLIの総放射から独立に再構成した間引き、DC除去、PCMも事前の許容差内だった。[出力と観測の比較](../runs/worklet-seal-sustain-20261120-repeat/summary.json)

ブラウザとCLIは全PCMフレームでビット一致し、13観測列の数値差は全点で0だった。48 kHzは上流公式デモの先頭ともビット一致した。96 kHzでは上流とのPCM差が減衰中の20フレームに残った。最初は31,980、最大絶対差は `7.11e-15` で、事前の許容差 `1e-6` を満たした。固定上流とのゲートと肺圧は全フレームで一致する一方、壁面流量と総放射の差は最初の非ゼロ内部サンプル231で既に現れていた。最初に差を確認できた計測位置は壁面放射で、その上流の圧力・流量に差が現れる位置はこのケースの観測範囲外。[最初の差と最大差](../runs/worklet-seal-sustain-20261120-repeat/summary.json)・[ネイティブ基準での独立再構成](seal-sustain-pcm.md#実装と実測)

## 実行と実時間の判定

研究ディレクトリと `/tmp` から実行し、各44項目を通過した。WAV・ネイティブCSV・書き出したケース・WASMの9ファイルはハッシュが一致し、ブラウザ観測の全行も一致した。両レートのネイティブ描画中の割り当ては0。ブラウザでは計測開始後の128フレーム間隔が連続し、p95は48 kHzで2 ms、96 kHzで1 msだった。時計は `Date.now` で分解能は1 ms。初回の48 kHzでは先頭8ブロックを除いた区間に7 msの量子が1回あり、再実行の最大は2 msだった。各条件で計測前の開始待ちに1回の不連続を記録した。[初回](../runs/worklet-seal-sustain-20261120-a/manifest.json)・[別ディレクトリでの再実行](../runs/worklet-seal-sustain-20261120-repeat/manifest.json)

共通Workletを使う鳴禽では `buzz → trill` の回帰22項目と96 kHzの `buzz` の回帰20項目を確認した。変更前に保存していたWAV、再実行ケース、ネイティブCSVとブラウザの全観測値に一致した。Rustの整形、Clippy、ワークスペース試験26件も通過した。[切り替えの回帰](../runs/worklet-songbird-switch-seal-regression-20261120/summary.json)・[96 kHzの回帰](../runs/worklet-songbird-buzz-seal-regression-20261120/summary.json)

```bash
python3 tools/measure_seal_sustain_pcm.py seal-sustain-local-1
python3 tools/measure_worklet_seal_sustain.py worklet-seal-sustain-local-1 seal-sustain-local-1
```
