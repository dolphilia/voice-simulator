# 口蓋帆ポートの770 Hzと1,320 Hzに損失を戻す

固定 /i/ の口蓋帆ポートで、追加12成分のうち複素流量の絶対差が大きかった2成分を調べる。流量係数で先に差が出ていたため、前回の接線抵抗を固定し、二次圧力損失の残差を1回だけ戻す。2周波数のポート流量誤差を50%以上、2,310 Hzの鼻端誤差を25%以上減らすと予測した。 [前回の流量係数](fixed-vowel-i-velum-port-middle-harmonics.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-port-loss-feedback.json)

上流の `HumanVoice::render` は内部標本ごとに肺圧と声門開口を更新し、`AirwayNetwork::step` を呼ぶ。`HumanAirway::new` では咽頭末端と鼻腔入口のポートに、収縮と拡大の損失係数を設定する。この固定形状で、枝の現在流量 `U[n]` は `I fs(U[n]−U[n−1]) + R U[n] + N(U[n]) = Δp[n−1]`、`N(U)=K(U)U|U|` を満たす。流量は cm³/s、圧力と損失は dyn/cm²。上流は符号別の二次方程式の根を取り、運動量 `I U[n]` と各節点への流入を更新する。節点圧と鼻端のR–L負荷を更新した後、全放射流量の差分を出力する。今回はその差分を取る前の鼻端体積流量を参照する。定常狭窄試験では管内の流量をベルヌーイ近似と照合し、別の試験では固定管の応答と線形周波数解の共鳴・帯域幅を照合する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

400〜500 msの96 kHz系列を使う。基準の平均流量を `Ū` とすると、追加抵抗は `ΔR=2K(Ū)|Ū|`。全61枝で平均と第1〜22倍音を含む接線解の波形 `U₀` を作る。時系列で二次損失を計算して2周波数を取り出し、接線項を引いた `N̂(U₀)−ΔR Û₀` を圧力源として接線解を一度解き直す。接線解の `Û₁` は、元の粘性モデルに `N̂(U₀)+ΔR(Û₁−Û₀)` を入れた解にも一致する。実測対照では実測波形の損失に窓端項を加え、接線項を差し引く。 [前回の接線と粘性の節点解](fixed-vowel-i-pharynx-predicted-radiation.md)

2,310 Hzの鼻端の比較では、補正した2成分をポートの波形だけに反映する。ポートの平均と残りの20成分は前回のままとし、他60枝の2,310 Hzの圧力源には前回と同じ10周波数の基準を使う。この条件で補正によるポートの二次損失と鼻端への影響を照合する。

## 実測

| 指標 | 7.2 cmH₂O | 5.76 cmH₂O |
| --- | ---: | ---: |
| 2成分のポート流量のL2相対誤差、補正前 → 補正後 | 9.926% → 0.4240% | 7.127% → 0.2523% |
| 2成分の流量誤差の減少率 | 95.73% | 96.46% |
| 2,310 Hzの鼻端複素誤差、補正前 → 補正後 | 0.06559% → 0.05869% | 0.04417% → 0.03898% |
| 鼻端誤差の減少率 | 10.52% | 11.74% |
| 観測損失を2成分へ戻したときの鼻端複素誤差 | 0.05840% | 0.03887% |

2成分の流量は両肺圧・両版で50%の減少率基準を満たした。鼻端は25%の減少率基準に両肺圧・両版で届かなかった。観測の損失を使うと2成分の実測流量を相対6.44×10⁻⁸以内で復元でき、その流量を使った鼻端誤差の減少は10.96%と11.98%だった。この差し替え条件で鼻端に届いた複素変化を補正前の残差方向に射影すると、予測損失で11.18%と11.74%、観測損失でも11.62%と11.98%だった。2成分を正確にするだけで説明できる鼻端の残差は小さい。 [複素流量・圧力・鼻端流量比](../runs/fixed-vowel-i-velum-port-loss-feedback-20261124-repeat/summary.json)

2成分の流量に残る誤差を枝の圧力源の誤差とその感度に分解すると、両肺圧・両周波数で最大の寄与は口蓋帆ポート30→49自身だった。接線解と元の粘性抵抗に等価な枝源を入れた独立解、二次損失のFFT、口蓋帆ポート流量に対する枝源の重ね合わせ、前回の基準を照合した。最大相対差は6.91×10⁻¹⁴で、両版の複素流量と鼻端伝達の照合も事前許容差10⁻⁸以内だった。

## 次の比較

そのままの予測波形で、各倍音の複素流量係数を少し動かしたときの2,310 Hz二次損失を、`N'(U)=2K(U)|U|` とフーリエ射影から求める。その感度に予測と観測の係数差を掛け、残差を減らす方向への寄与を第1〜22倍音で求める。1成分ずつ実測値に置き換えた差と照合し、鼻端の誤差を減らす成分の候補を確認する。今回の補正が実証された範囲は、固定 /i/ の2肺圧・固定開口での2周波数の流量まで。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用し、保存済みの通常CLIと固定上流の収録を参照した。研究ワークスペースと `/tmp` からの実行で各56判定中55判定が通った。鼻端の25%基準だけが偽で、終了コードは1になった。両実行の要約はバイト単位で一致し、固定上流の `airway_adversarial` の6試験は通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-port-loss-feedback-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-loss-feedback-20261124-repeat/manifest.json)

研究ワークスペースから以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_port_loss_feedback.py fixed-vowel-i-velum-port-loss-feedback-20261124-repeat
```

第51版の全体監査は鼻端の仮説が不成立だったことも復元し、253実行・3,864成果の521判定に通過した。今回の3実行の1,540入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に8ファイル分、13,595バイトだった。 [第51版の実行記録](../runs/plan-completion-v51-fixed-vowel-i-velum-port-loss-feedback-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v51-fixed-vowel-i-velum-port-loss-feedback-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
