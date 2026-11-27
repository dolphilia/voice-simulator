# 狭い口蓋帆ポートの22倍音を予測二次損失で一度補正する

開口0.15 cm²の固定 /i/ では、22倍音内の係数差が2,310 Hzのポート損失残差の96.2%を占めた。ポートの平均を固定して22係数を実測にすると、鼻端誤差は0.528%から0.115%へ下がった。今回は同じ平均を使い、22成分の接線解へ予測した二次損失を一度だけ戻す。流量誤差の50%以上を減らし、実測差し替えの鼻端改善量の80%以上を回復すると予測した。 [狭開口での残差分解](fixed-vowel-i-velum-narrow-port-bandwidth.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.json)

固定上流の `HumanVoice::render` は肺圧と声門の開口を更新して `AirwayNetwork::step` を呼ぶ。`HumanAirway::new` が咽頭末端と鼻腔入口をポートでつなぐ。開口固定で流量 `U[n]` は `I fs(U[n]−U[n−1])+R U[n]+N(U[n])=Δp[n−1]`、`N(U)=K(U)U|U|` を満たす。流量は cm³/s、圧力は dyn/cm²。上流は流向で係数を選び、二次方程式から流量と運動量 `IU[n]` を更新する。節点圧と鼻端の並列R–L負荷を更新し、放射の和を時間差分する。観測はその差分より前の鼻端流量で行う。定常狭窄の試験は流量をベルヌーイ近似と照合し、固定管の試験は時間応答と周波数応答の共鳴帯域を照合する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

96 kHzの400〜500 msの窓を使う。全61枝の平均 `Ū` と第1〜22倍音から基準波形 `U₀` を再構成する。平均からの接線抵抗を `ΔR=2K(Ū)|Ū|` とし、各周波数で `N̂(U₀)−ΔR Û₀` を接線解に戻す。得られた `Û₁` は元の粘性節点解に等価な圧力源 `N̂(U₀)+ΔR(Û₁−Û₀)` を与えた結果と照合する。平均を固定したポート波形に補正した係数を戻して2,310 Hzの損失を再計算し、粘性節点解で鼻端放射を求める。ここでは他60枝の鼻端に対する2,310 Hzの圧力源を従来と同じ10周波数の予測に固定する。 [先行する2成分の補正式](fixed-vowel-i-velum-port-loss-feedback.md)

## 実測

| 口蓋帆ポートの条件 | 22成分の流量係数のL2相対誤差 | 2,310 Hzの鼻端複素誤差 |
| --- | ---: | ---: |
| 無補正 | 4.8667% | 0.52758% |
| 先行する2成分の予測補正 |  | 0.51012% |
| 22成分の予測補正 | 0.4307% | 0.1152567% |
| 22成分への観測損失の再投入 | 1.94×10⁻⁷% | 0.1152535% |
| 22成分の実測係数への差し替え | 0% | 0.1152535% |

22成分の個別の絶対誤差がすべて減った。22成分を合わせたL2相対誤差の減少率は91.15%、鼻端誤差の減少率は78.1538%だった。実測差し替えによる鼻端改善量を100%とした回復率は99.9992%で、流量と鼻端の事前基準を両版で満たした。予測補正と実測差し替えの鼻端複素流量比の差は、実測差し替えの鼻端流量比に対して0.0101%だった。 [22成分の流量・圧力源と鼻端応答](../runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-repeat/summary.json)

補正後のポート流量で絶対誤差の大きい周波数は110 Hz、220 Hz、550 Hzだった。この3周波数の残差に最大の寄与を持つ枝は口蓋帆ポート30→49自身だった。観測損失の対照の鼻端流量比は実測係数の差し替えと相対2.76×10⁻⁹以内で一致した。FFT、元の粘性節点解、枝源の重ね合わせ、平均と22係数の再構成、先行2成分と同じ周波数の解を照合した。数値照合の最大相対差は1.64×10⁻¹³で、両版の流量と鼻端流量比も事前許容差内だった。

### 上位倍音を加える事後対照

補正済みの22係数を保ち、0.15 cm²収録のポート流量から実測の第23〜44倍音だけを加えた。400〜500 msの窓のFFTから該当する22ビンを取り出し、保存した補正済み係数と基準平均で逆FFTした。ポート損失の変化を先の粘性節点解の鼻端ゲインで換算すると、鼻端誤差は0.11526%から0.00871%になった。実測の全選択外成分を加えた対照では0.00886%。第23〜44倍音によるポート損失の変化は、選択外の全成分を加えた複素変化方向への射影で99.88%を占めた。この比較は第23〜44倍音を予測する前の探索で、基準の判定と併記した。 [補正済み22係数](../runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-repeat/summary.json)・[狭開口の元の圧力・流量系列の実行記録](../runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat/manifest.json)

## 次の比較

基準平均と他60枝の鼻端への圧力源を固定し、第23〜44倍音を声門流量と新しい周波数の節点解から予測する。今回の補正済み22倍音へ加えたとき、第23〜44倍音を実測から加えた対照の改善量をどこまで回復できるか確かめる。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。狭開口の通常CLIと固定上流の圧力・流量系列をRTL9210B-CGから参照した。研究ワークスペースと `/tmp` からの各157判定が通り、要約はバイト単位で一致した。固定上流の `airway_adversarial` の6試験にも通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-repeat/manifest.json)

研究ワークスペースで以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_narrow_port_all_harmonic_feedback.py fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-repeat
```

第57版の全体監査は271実行・3,980成果の557判定に通過した。今回の3実行について1,657入力と12出力をSHA-256で照合した。既存の圧力・流量系列を再利用し、RTL9210B-CGの追加出力は重複統合後に8ファイル分、13,865バイトだった。 [第57版の実行記録](../runs/plan-completion-v57-fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v57-fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
