# 出力ゲインを旧値に戻したときの tall の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。4発話で音源の3変動を止めたところ、旧比較との境界差は `FK61_02` の `tall` の /ɔ/–/l/ 境界1か所に残った。ドリフト、周期長ジッター、振幅シマーは0、体型、初期舌先と気道の設定は固定し、ゲインだけを `4.8125×10⁻⁷` から旧値の `5.5×10⁻⁷` へ戻す。[前回の全区間比較](tsp-matched-source-variation-zero-mfa.md)・[事前登録](../cases/tsp-tall-output-gain-mfa.json)

| 参照した処理 | 入力と観測点 |
| --- | --- |
| 固定上流 `crates/chimera/src/voice/human_voice.rs` の `HumanVoice::new` と `render` | 基本ゲインに体型の線形寸法に応じた係数を掛ける。既定の女性体型は係数0.875。96 kHzの放射流量の時間差分を48 kHzへ間引き、ゲインを掛け、25 HzのDC除去、包絡に応じた振幅制限、float32変換を順に行う。 |
| 研究版 `crates/vocal-core/src/output.rs` の `OutputStage::new`、`push` と `crates/vocal-cli/src/timing_case/speech_voice.rs` の `render` | ゲイン適用後の値を `x` とするとDC除去は `y[n] = x[n] − x[n−1] + a × y[n−1]`、`a = exp(−2π×25/48000)`。25 msのホールドと0.2秒のリリースで包絡を追い、0.75を超える包絡に応じて出力を縮める。0.85を超える値にはソフトクリップを適用する。通常CLIの波形と内部観測器で、入力放射からPCMまでの各変化点を照合する。 |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `over_noise_floor` と `align_synth` | 20 ms窓の平均二乗の95パーセンタイルの平方根に比例する雑音振幅を用いる。乱数列は固定で、雑音を加えたfloat32をPCM16へ丸めてMFAに渡す。比例拡大はPCM16上の丸め境界を変えるため、整列は実行して確かめる。 |
| 固定上流の `golden_voice.rs`、`golden_analysis.rs` と `compare::tsp::tests` | 固定発話PCM、LPC公開極、整列用雑音床を照合する。ここでは出力段の独立FIR・IIR・制限計算も使い、同じ音素窓と再整列した窓のF2を比較する。 |

保存済み基準PCMのピークは0.423で、8/7倍すると0.483になる。振幅制限の閾値0.75を下回るため、固定窓のF2は0.05 Hz以内で一致すると予測する。 `tall` 付近の基準波形を8/7倍した値が旧PCMに近いことから、ゲインを戻すとMFAの /ɔ/–/l/ 境界も旧位置の1.680秒に揃うと予測する。

## 初回の停止と再実行条件

初回 `tsp-tall-output-gain-mfa-20261123-a` は通常PCMと出力段を採取した後、MFA共通処理が計測設定内の `sample_rate_hz` を読む箇所で `KeyError: 'sample_rate_hz'` を返した。今回のケースは出力段の独立計算に合わせてルートにサンプルレートを置いた。計測設定へ同じ値を渡すよう修正し、ケースと予測を保持して別IDで再実行した。初回の入力スナップショット、CLIログと途中採取のPCMを保存した。[初回のログ](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/tsp-tall-output-gain-mfa-20261123-a/artifacts/cargo.log)・[初回の計測コード](../runs/tsp-tall-output-gain-mfa-20261123-a/artifacts/source/research/experiments/chimera-rebuild/tools/measure_tsp_tall_output_gain_mfa.py)

## 実測

放射と間引き後の全標本は一致し、最初の差はゲイン適用の出力標本番号2,439だった。包絡のピークは0.42284から0.48325に増えた。両条件ともリミッターとソフトクリップの作動は0標本。FIR・DC除去・包絡の独立計算を照合し、観測値から復元した制限後のPCMは各144,727標本で通常CLIとビット一致した。基準のfloat32 PCMを8/7倍した波形と、旧ゲインで再描画した波形の最大差は2.98×10⁻⁸だった。

同じ窓で測ったF2の差は最大2.86×10⁻⁵ Hzだった。MFAを再実行しても、/ɔ/–/l/ 境界は1.650秒で、語9区間・音素30区間は基準と一致した。旧位置1.680秒の再現という予測は外れた。

旧ゲインで描画した無加工PCMと旧研究版を比較すると、`tall` を含む1.50〜1.75秒は12,000標本すべて一致した。整列用PCM16もこの区間で一致した。両発話の雑音床の基準電力は0.03438986686071663で等しく、整列用PCM16の差4,679標本は、無音部分を含む先頭から約251 ms以内に収まった。局所のPCM16が同じ区間で旧境界との差が残ったため、次は旧ゲインのまま初期舌先だけを旧設定へ戻し、冒頭の差と境界位置の両方を照合する。[出力段と整列の要約](../runs/tsp-tall-output-gain-mfa-20261123-repeat/summary.json)・[窓別F2](../runs/tsp-tall-output-gain-mfa-20261123-repeat/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_tall_output_gain_mfa.py tsp-tall-output-gain-mfa-new
```

研究ワークスペースと `/tmp` から各9判定と上流8試験に通過した。各24出力のうち実行時間を含む2ログを除いた22出力がバイト一致した。条件別のPCM、MFA入力、境界、LPC窓と独立再計算に使う共通の間引き出力をRTL9210B-CGに保存した。[修正後の実行](../runs/tsp-tall-output-gain-mfa-20261123-recheck/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-tall-output-gain-mfa-20261123-repeat/manifest.json)
