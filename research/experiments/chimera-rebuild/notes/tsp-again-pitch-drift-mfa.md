# 低速F0ドリフトだけを戻したときの again の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。確認用 `FK61_01` の女性体型、初期姿勢、ゲイン、周期長ジッター0.00455、振幅シマー0.042を揃え、低速F0ドリフトだけを5セントから旧研究版の既定値0へ戻す。[前回のジッター比較](tsp-again-period-jitter-mfa.md)

| 参照した処理 | 入力・状態・出力 |
| --- | --- |
| `crates/chimera-cli/src/render.rs` の `say` と `text_f0`、`crates/chimera/src/voice/human_voice.rs` の `apply_source`、`control`、`render` | 辞書で作った発話計画から調音・呼気・目標F0を設定する。女性体型の基準は205 Hz、声帯振動器は110 Hzから開始する。既定ドリフトは5セントで、ビブラートの深さとfryは0。圧差（dyn/cm²）から面積（cm²）、声門流量（cm³/s）、放射の時間差分（cm³/s²）、出力PCMへ進む。 |
| `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::new` と `next` | 96 kHzの内部標本番号0から32標本ごとにドリフトを更新し、倍率を次の更新まで保つ。ドリフト値を `D`、深さを `d` セントとすると、この発話のピッチ倍率は `2^(d × D / 1200)`。瞬時F0を決めてから位相を `F0 / (96000 × 周期倍率)` ずつ進める。位相が一周すると周期倍率と振幅倍率を更新する。 |
| `crates/chimera/src/math.rs` の `Drift::new`、`step`、`Rng::gauss` | 種4242と初期値0から、更新レート3,000 Hzで0.3、0.9、2.7 Hzの3状態を進める。係数は `a = exp(−2πf/3000)`、更新式は `y = a × y + sqrt(1 − a²) × g`。出力は `(y₁ + y₂/2 + y₃/3) / 1.4`。深さを0にしても乱数と状態の更新は進む。 |
| `crates/chimera/tests/voice_source.rs`、`golden_voice.rs`、`golden_analysis.rs` | 声門閉鎖、高域の変化、固定発話PCM、公開LPC極を照合する。源ごとの乱数と位相は既存の独立Python計算で検算する。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run` と `render`、`crates/vocal-core/src/glottis.rs` の `PitchModulation::step` | 通常CLIの `source_variation.pitch_drift_cents` を声帯振動器へ渡す。瞬時F0の比をセント換算し、上流と同じ係数で独立に計算した系列と全標本で照合する。 |
| 固定上流 `compare/tsp.rs` の `over_noise_floor` と `align_synth` | 同じ発音辞書、MFA設定、雑音床で語・音素の時間区間を比較する。固定窓と再整列窓のF2を分けて測る。 |

瞬時F0と位相は最初の内部標本から異なり、周期番号で揃えた振幅倍率は一致すると予測する。固定窓ではF2が少なくとも1窓で2 Hz以上変わり、再整列での /ɛ/–/n/ 境界移動は10 ms以内と予測する。[事前登録](../cases/tsp-again-pitch-drift-mfa.json)

## 実測

瞬時F0と位相の初差は予測どおり96 kHzの標本番号0だった。5セント条件の瞬時F0を0セント条件で割ってセントに直すと、全232,264内部標本で独立計算との差は最大2.89×10⁻¹³セントだった。5セントはフィルターを通した雑音に掛ける倍率で、実測の変動範囲は−10.20〜+8.20セントだった。周期番号で揃えた振幅倍率は一致し、対応する周期境界の最大時刻差は193内部標本（約2.01 ms）だった。

声門面積と流量は標本番号8,083、声門の圧差と合計放射の時間差分は8,084、48 kHzのPCMは4,060から異なった。最初の50 msの無加工PCMは一致した。両条件の観測器のPCMは通常CLIの各116,132標本と一致した。

MFAの /ɛ/–/n/ 境界は2.040秒から2.060秒に動いた。**事前の10 ms以内という予測は外れた。** 同じ発話では語8区間・音素25区間すべてが旧研究版の保存境界と一致した。基準条件から変化した音素区間は `again` の /ɛ/ の終了と、隣接する /n/ の開始の2区間だった。

| 母音90%窓の条件 | 開始標本（12 kHz） | F2 |
| --- | ---: | ---: |
| 5セント、基準境界 | 24,185 | 2,034.56 Hz |
| 0セント、基準境界 | 24,185 | 2,032.53 Hz |
| 0セント、再整列境界 | 24,401 | 2,134.20 Hz |

基準境界を固定したときの90%窓の変化は−2.03 Hz。0セントの同じPCMに再整列境界を使うと、窓が216標本移動してF2は+101.67 Hz、基準条件からの合計は+99.65 Hzだった。固定した5窓での最大差は5.32 Hz。設定の総合差があった旧比較から、低速F0ドリフトだけを止めてもこの発話の境界差が生じると確認した。残る3発話は、同じ単一変更での再整列が必要になる。[全標本の要約](../runs/tsp-again-pitch-drift-mfa-20261123-a/summary.json)・[固定窓と再整列窓](../runs/tsp-again-pitch-drift-mfa-20261123-a/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースから次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_again_initial_tip_mfa.py tsp-again-pitch-drift-mfa-new \
  --case cases/tsp-again-pitch-drift-mfa.json
```

研究ワークスペースと `/tmp` から各11判定と上流13試験に通過した。各31出力のうち、計時を含む3実行ログを除いた28出力がバイト一致した。ジッターの回帰でも各30出力のうち実行ログ以外の25出力が一致した。波形、MFA区間、窓別F2、周期系列とピッチ比をRTL9210B-CGに保存した。[再実行](../runs/tsp-again-pitch-drift-mfa-20261123-repeat/manifest.json)・[ジッター比較の回帰](../runs/tsp-again-period-jitter-mfa-20261123-after-drift/manifest.json)
