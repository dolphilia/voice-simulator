# 4発話で音源の3変動を止めたときのMFA境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。前回の男性発話 `MK61_01` では、ドリフト・周期長ジッター・振幅シマーを止めた条件で旧比較の10窓と全音素区間を再現した。この条件を残り3発話にも適用する。4発話の全60窓について旧開始位置に戻る窓を数え、評価外の `FK61_02` の `he`–`lent` と /i/–/l/ の境界も確認する。[事前登録](../cases/tsp-matched-source-variation-zero-mfa.json)・[単独発話](tsp-again-male-period-jitter-mfa.md)

| 参照した処理 | 入力と観測点 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/render.rs` の `say`、`crates/chimera/src/voice/human_voice.rs` の `apply_source` と `render` | 本文・辞書・体型から発話を計画する。音源設定は既定のドリフト5セント、無次元の周期長ジッター0.00455、振幅シマー0.042。声門面積を内部96 kHzで更新し、放射の時間差分を間引いて48 kHzのPCMを得る。 |
| 固定上流 `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::next`、`crates/chimera/src/math.rs` の `Drift::step` | ドリフトは32内部標本ごとに瞬時F0へ掛ける倍率を更新する。周期長ジッターは次周期の位相増分、シマーは周期内の面積パルスに掛ける振幅倍率を変える。3係数を0にすると既定に対するF0比は `2^(5D/1200)`、周期倍率と振幅倍率は1になる。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run` と `render` | 同じ本文、初期舌先や呼気、ゲインのケースで3つの係数だけを0にする。通常CLIの全出力フレーム末尾の瞬時F0を、固定上流と同じフィルターの独立計算へ照合する。 |
| 固定上流 `compare/tsp.rs` の `over_noise_floor`、`align_synth`、`Sig::formants` と試験 `golden_analysis.rs` | MFAには発話全体の電力に応じた固定種の雑音を加えたPCM16を渡す。同じ辞書、ラベル、モデルで整列する。LPCは無加工PCMの12 kHz・25 ms窓を使い、女性次数12、男性次数14で採択する。固定Rustと独立計算の開始標本、採択値、欠測を照合する。 |

旧差15窓すべての開始位置を再現し、残る45窓は同じ開始位置を保つと予測する。ドリフトだけを止めたときに70 ms早まった `FK61_02` の境界は、旧研究版の0.330秒に戻ると見込む。F2は波形と窓の組合せを変えて測り、旧研究版の波形も旧窓で再計算する。

## 実測

音源の3変動を0にした条件で、旧比較の15窓すべてが同じ開始標本を再現した。内訳は女性の `again` 5窓、男性の `plea` と `again` の計10窓。残る45窓は基準の開始位置を保った。 `MK61_01` は前回の各0条件と通常PCM・MFA区間が一致した。

| 発話 | 評価窓 | 旧差を再現した窓 | 旧研究版と一致した語／音素区間 |
| --- | ---: | ---: | ---: |
| `FK61_01` | 25 | 5 | 8／25 |
| `MK61_01` | 25 | 10 | 8／25 |
| `FK61_02` | 5 | 0 | 9／28 |
| `MK61_02` | 5 | 0 | 9／30 |

`FK61_02` の `he`–`lent` と /i/–/l/ の境界は、ドリフトだけを0にすると0.260秒に早まった。3変動を0にすると旧位置の0.330秒へ戻った。この発話で残った旧研究版との差は、`tall` の /ɔ/–/l/ 境界1か所だった。3変動0では1.650秒、旧版では1.680秒で、30 ms差の両側に当たる2音素区間が異なる。出力ゲインは今回の `4.8125×10⁻⁷`、旧研究版の `5.5×10⁻⁷` と異なるので、次の対照ではゲインだけを旧値へ戻してこの境界を測る。

固定窓でのF2差は最大20.20 Hzだった。同じ3変動0のPCMに再整列窓を使ったときの最大変化は110.54 Hzで、女性の `again` の90%窓だった。3変動0と旧研究版のPCMをそれぞれ同じ旧開始位置で測った60窓では、F2差は最大3.09×10⁻⁵ Hzだった。4発話521,718出力フレームのF0比は独立計算と最大2.90×10⁻¹³セント差で、5条件300窓のF1・F2採択値は固定Rustと独立LPCで最大8.07×10⁻¹¹ Hz差だった。[全境界の要約](../runs/tsp-matched-source-variation-zero-mfa-20261123-a/summary.json)・[窓別比較](../runs/tsp-matched-source-variation-zero-mfa-20261123-a/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_matched_pitch_drift_mfa.py tsp-matched-source-variation-zero-mfa-new \
  --case cases/tsp-matched-source-variation-zero-mfa.json
```

研究ワークスペースと `/tmp` から各8判定と上流7試験に通過した。各59出力のうち実行ログ2件を除く57出力がバイト一致した。ドリフトのみの比較も再実行し、同じ57出力が従来版と一致した。通常PCM、MFA入力、全語・音素境界、窓別評価とF0の照合をRTL9210B-CGに保存した。旧波形は既存のアーカイブを参照した。[再実行](../runs/tsp-matched-source-variation-zero-mfa-20261123-repeat/manifest.json)・[ドリフトのみの回帰](../runs/tsp-matched-pitch-drift-mfa-20261123-after-variation-zero/manifest.json)
