# 実時間AudioWorkletでのウェッデルアザラシの `chug`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの `AudioEngine.playCall` はWorkletの `call`、WASMの `engine_play_call` 経由で `CreatureVoice::play_call` を呼ぶ。手動変更は `cparams` が索引に直して演奏値を更新する。公式CLIは先行する `whistle` の状態を引き継いで、392,160から69,600フレームを描画する。上流の `seal-call-chug` はPCMと10 ms窓のRMS、テレメトリ、ブロック分割による違いを検査する。実時間試験はコール操作と観測を含む描画の割り当ても確認する。[画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

64出力フレームごとにコールキーを評価する。目標音高90 Hzと呼気パルス11 Hz、深さ1、デューティ0.35が設定される。ゲートは0.9秒まで1、0.95秒まで直線で0へ下がる一方、粗さの目標は0秒から0.95秒の間に0.3から0.05へ下がる。粗さは無次元で時定数50 ms。呼気位相（周期）を平滑パルス周波数で進め、半正弦を用いて無次元ゲートと圧力（cmH₂O）から固定肺圧（dyn/cm²）を作る。声門では別の位相を `(f₀/fs)/L` ずつ進める。折り返しで、その時点の平滑粗さ `c` を使い `x ← (2.9 + 1.1c)x(1−x)` を更新して、次周期の倍率 `L` に `0.45c(x−0.5)` を加える。面積（cm²）にも粗さに応じた振幅の変化が加わる。声門前後の圧力差を使って得た開口面積を気道に反映し、放射の差分を間引きとDC除去を経てPCMへ渡す。[キー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L123)・[制御から声門へ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[周期の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L183)・[圧力差と気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)

## 事前登録

48 kHz公式デモ、44.1 kHzで120 Hzに移調して呼気圧と粗さを同時変更する条件、96 kHzで初期音高90 Hz・パルス11 Hzの条件を使う。48・44.1 kHzでは64フレームごとと指示の前後、96 kHzではレンダー開始から末尾まで全フレームの状態を保存する。44.1 kHzの9,891で圧力目標12 cmH₂Oが反映され、コール終了44,288まで手動粗さ0.5は保留されると予測する。3レートでCLIとのPCMのビット一致・観測差0、固定上流と独立計算は第2版の許容差を適用する。

96 kHzの観測から、内部位相が折り返した直後の増分と瞬時F0で周期長倍率を逆算する。シード777の周期ジッターと、全周期の折り返しで進める独立写像を使い、倍率の誤差を `1e-9` 以下とする。呼気位相はコール中に11回、声門位相は80〜100回折り返すと予測する。ジッター分を差し引いた周期倍率のRMSは、開始制御から0.15〜0.45秒に比べ0.77〜0.90秒で小さくなると予測する。独立肺圧は第2版と同じく半正弦の傾きの上限 `Aπ/d` に独立位相と観測位相の円周差を掛けて位相差の寄与を評価し、上界を超える残差と、生の圧力誤差を両方保存する。[ブラウザ登録条件](../cases/worklet-seal-chug.json)・[第2版の登録条件](../cases/seal-chug-v2.json)・[CLIの独立計算](seal-chug.md)

## ブラウザの実装と実測

研究画面に3レートの `chug` を接続した。C ABIの観測に無次元の粗さと目標、内部サンプルごとの声門位相、瞬時F0（Hz）、開口面積（cm²）を追加した。アザラシの出力倍率は48・44.1 kHzで2、96 kHzで1。倍率1の2番目の観測枠は0になる。観測の指定があるケースはCLIへ同じフラグを書き出し、既存の持続音とコールでは元の列数を使う。[C ABI](../crates/vocal-wasm/src/seal.rs)・[WASMホストの列定義](../crates/vocal-wasm/host/seal.ts)・[比較器](../tools/measure_worklet_seal_chug.py)

| 出力レート | PCMフレーム・観測点 | 指示 → 初回制御 → 終了（出力フレーム） | 条件 |
| --- | --- | --- | --- |
| 48 kHz | 461,760・7,220 | 392,160 → 392,192 → 440,256 | 公式デモ全体 |
| 44.1 kHz | 53,000・837 | 73 → 128 → 44,288 | 120 Hzへの移調と手動変更 |
| 96 kHz | 108,000・108,000 | 17 → 64 → 96,064 | 初期の音高90 Hz・呼気パルス11 Hz |

全622,760 PCMフレームはCLIとビット一致し、35系列の計116,057観測点も一致した。44.1 kHzでは9,891で圧力目標の12 cmH₂Oが反映され、粗さ0.5の指定はコール中の曲線に影響せず、44,288で目標に復帰した。公式デモの48 kHzでゲートの目標が1のまま粗さ目標は0.17509まで下がった。ゲートの減衰中にも粗さの平滑値が目標を追った。[ブラウザの制御観測](../runs/worklet-seal-chug-20261120-a/summary.json)

### 96 kHzの二つの周期

コールの制御が有効な1秒の間に、呼気位相は11回、声門位相は88回折り返した。開始前と終了後を含む全108,000フレームから100周期分の倍率を復元し、ジッターと粗さの写像から計算した独立値との最大差は `2.22e-16` だった。ジッター分を引いた周期倍率の偏差RMSは前半0.02129（26周期）、後半0.00755（11周期）。音高目標90 Hzと呼気パルスの目標11 Hzを保ったまま、粗さに由来する揺らぎが小さくなった。[位相と周期倍率](../runs/worklet-seal-chug-20261120-a/summary.json)

追加集計では、96 kHzの出力フレーム `[64, 96064)` で `glottis_phase_0[n] − glottis_phase_0[n−1] < −0.5` を満たす88点のうち、59点で `gate[n] > 0` かつ `lung_pressure_dyn_cm2[n] = 0` だった。最初は3,218フレームで、該当点の瞬時F0は89.909〜90.155 Hz。深さ1の呼気パルスが肺境界圧を0にする区間でも、声門の位相は進んでいた。声門開口の振動振幅は局所圧差の平滑値にも依存するため、局所圧差と開口面積を揃えて比較する対照を次の調査候補に残した。[保存した96 kHzの全観測](../runs/worklet-seal-chug-20261120-repeat/artifacts/steady-pitch-96000.json)・[位相進行と振幅](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L163)

### 固定上流との差

全条件で音高・粗さ・呼気の目標と平滑値、肺圧、声門位相と瞬時F0が固定上流と一致した。最初に数値差が出たのは壁面放射で、声門面積の最初の差より早かった。48 kHzの公式 `chug` 区間69,600フレームのPCMは自然終了後の449,105に1件の差があり、その絶対差は `6.78e-21`。全条件の最大PCM絶対差は44.1 kHzの `1.14e-13` だった。独立肺圧では48 kHzの生の最大絶対差が `2.45e-7 dyn/cm²`、位相差の寄与の上界を差し引いた最大残差は `2.30e-9 dyn/cm²` だった。第2版の閾値内で、生の誤差と残差はどちらも保存した。[ブラウザの比較と独立計算](../runs/worklet-seal-chug-20261120-a/summary.json)・[固定上流との基準計測](../runs/seal-chug-before-worklet-1/summary.json)

### 実時間と再実行

研究ディレクトリと `/tmp` から実行し、各88項目が通過した。WAV・再実行ケース・CLIのCSV・WASMの13ファイルと、ブラウザ観測の全行が一致した。44.1 kHzのネイティブ描画の割り当ては0。128フレームの量子は計測中に連続し、先頭8量子を除いたp95は48・44.1・96 kHzの順に2・2・1 msで予算内だった。48 kHzは初回に5回、再実行に2回、44.1 kHzは両実行で1回ずつ、96 kHzは再実行に3回、個別量子の予算超過を記録した。計時は1 ms分解能の `Date.now`。96 kHzの全フレーム保存の観測JSONは約62 MiBで、ファイルの生成時間は描画時間の計測区間外となる。[初回](../runs/worklet-seal-chug-20261120-a/manifest.json)・[再実行](../runs/worklet-seal-chug-20261120-repeat/manifest.json)

`whistle` の101項目と、声門観測を使わない持続音の44項目も通過し、WAV・観測列と全観測行・CLIのCSV・再実行ケースが変更前と一致した。Rustの整形、Clippy、ワークスペース試験30件を確認した。[whistleの回帰](../runs/worklet-seal-whistle-chug-regression-20261120/manifest.json)・[持続音の回帰](../runs/worklet-seal-sustain-chug-regression-20261120/manifest.json)

```bash
python3 tools/measure_seal_chug.py seal-chug-local-1 --revision 2
python3 tools/measure_worklet_seal_chug.py worklet-seal-chug-local-1 seal-chug-local-1
```
