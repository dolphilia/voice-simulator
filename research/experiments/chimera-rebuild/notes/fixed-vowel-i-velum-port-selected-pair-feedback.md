# 選んだ2倍音を予測した二次圧力損失で補正する

前回は7.2 cmH₂Oで鼻端の複素残差を最も小さくする組として、1,320 Hzと2,420 Hzを選んだ。実測係数への差し替えでは鼻端の誤差が7.2と5.76 cmH₂Oで31.26%と17.61%減った。今回はこの組を固定し、声門の観測流量と形状からポート流量を予測する。従来の一度だけの圧力補正で、2成分の流量誤差の50%以上を減らし、実測差し替えの鼻端改善量の80%以上を回復すると予測した。 [先行する有限差し替え](fixed-vowel-i-velum-port-complex-pair.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-port-selected-pair-feedback.json)

固定上流では `HumanVoice::render` が肺圧と声門の開口を更新し、`AirwayNetwork::step` に進む。口蓋帆ポートは `HumanAirway::new` で咽頭末端から鼻腔入口へ接続される。固定開口で枝の流量 `U[n]` は `I fs(U[n]−U[n−1]) + R U[n] + N(U[n]) = Δp[n−1]`、`N(U)=K(U)U|U|` を満たす。流量は cm³/s、圧力は dyn/cm²、`K(U)` は収縮と出口拡大の係数を流向に応じて使う。現在の流量を求めて運動量を保存した後、節点圧と鼻端の並列R–L負荷を更新する。今回の鼻端流量は放射の和を時間差分する前に観測する。固定上流では短い狭窄の定常流量をベルヌーイ近似に、共鳴帯域幅を固定管の時間解と線形周波数解に照合する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

96 kHzの400〜500 msの窓を使う。基準の枝平均 `Ū` による抵抗 `ΔR=2K(Ū)|Ū|` を固定する。1,320 Hzは追加した倍音群、2,420 Hzは元の10周波数に入る。どちらも同じ22倍音の基準波形 `U₀` から損失の複素係数を読み、`N̂(U₀)−ΔR Û₀` を接線節点解へ加える。元の粘性方程式に `N̂(U₀)+ΔR(Û₁−Û₀)` を入れた独立な解にも一致することを確かめる。観測した枝の流量と圧力は実測対照および検証に使う。鼻端の比較では補正したポート流量の2成分だけを差し替えて2,310 Hzの損失を再計算する。 [一度だけ補正する式と有限窓の対照](fixed-vowel-i-velum-port-loss-feedback.md)

## 実測

| 指標 | 7.2 cmH₂O | 5.76 cmH₂O |
| --- | ---: | ---: |
| 2成分のポート流量のL2相対誤差、補正前 → 補正後 | 12.18% → 0.370% | 8.30% → 0.286% |
| ポート流量の誤差減少率 | 96.96% | 96.55% |
| 2,310 Hzの鼻端複素誤差、補正前 → 補正後 | 0.06559% → 0.04538% | 0.04417% → 0.03540% |
| 鼻端誤差の減少率 | 30.82% | 19.85% |
| 実測係数の差し替えによる鼻端誤差の減少率 | 31.26% | 17.61% |
| 実測差し替えの改善量に対する回復率 | 98.58% | 112.74% |

流量と鼻端の事前基準を両肺圧・両版で満たした。5.76 cmH₂Oで回復率が100%を超えたのは、予測補正と実測差し替えで鼻端の複素変化の方向が異なったため。補正前の鼻端残差で正規化した変化は予測補正で `0.222+0.193i`、実測差し替えで `0.210+0.235i` だった。予測補正の方が残差を減らす方向の成分が大きく、直交成分が小さかった。 [ポート流量・枝の圧力源・鼻端伝達](../runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-repeat/summary.json)

2,420 Hzのポート流量の絶対誤差は7.2 cmH₂Oで0.00188から0.000354 cm³/s、5.76 cmH₂Oで0.00133から0.000230 cm³/sに減った。補正後の流量誤差に対する枝の寄与を分解すると、両肺圧・両周波数とも最大は口蓋帆ポート30→49自身の圧力源だった。観測損失を使う対照では2成分の実測流量をL2相対誤差8.64×10⁻⁸以内で復元し、前回の実測差し替えの鼻端伝達に相対1.95×10⁻¹⁰以内で一致した。 [成分ごとの流量と圧力源の寄与](../runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-repeat/summary.json)

接線解と元の粘性抵抗に等価な枝源を与えた解、枝源の重ね合わせ、損失のFFT、ポート平均と20成分の保持を照合した。数値照合の最大相対差は2.78×10⁻¹³だった。補正対象を元の10周波数と追加倍音のどちらからも選べるよう共通の計算を変更し、先行の770 Hzと1,320 Hzの全判定と測定値が保存済み要約と一致することを再計算で確認した。 [先行する2成分の比較](fixed-vowel-i-velum-port-loss-feedback.md#実測)

## 次の比較

肺圧7.2 cmH₂Oと声道輪郭を固定し、音響ポート面積だけを0.30から0.15 cm²へ変える。候補の通常CLIと固定上流の両方で、同じ窓と前標本を含む枝流量・圧力・鼻端流量を収録する。開口ごとの形状と抵抗を使い、選び直さずに1,320 Hzと2,420 Hzを一度補正する。先行する0.30 cm²の比較と同じ流量・鼻端の尺度で判定する。 [枝ごとの収録入口](../tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py#L41)・[輪郭と開口の独立対照](fixed-vowel-i-velum-port-only.md)

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用し、通常CLIと固定上流の保存済み系列を参照した。研究ワークスペースと `/tmp` の各60判定に通過し、要約はバイト単位で一致した。固定上流の `airway_adversarial` の6試験にも通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-repeat/manifest.json)

研究ワークスペースで以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_port_selected_pair_feedback.py fixed-vowel-i-velum-port-selected-pair-feedback-20261124-repeat
```

第54版の全体監査は262実行・3,900成果の539判定に通過した。今回の3実行について1,586入力と12出力をSHA-256で照合した。既存の時系列を再利用し、RTL9210B-CGの追加出力は重複統合後に8ファイル分、13,757バイトだった。 [第54版の実行記録](../runs/plan-completion-v54-fixed-vowel-i-velum-port-selected-pair-feedback-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v54-fixed-vowel-i-velum-port-selected-pair-feedback-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
