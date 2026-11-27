# 固定 /ɑ/ の咽頭2枝でゼロ流量付近の損失を平滑化する

固定LFの110 Hzだけを変更した5条件では、660 Hz・770 Hzの振幅則からのずれに、条件によって流向が変わった標本の逆流補正が大きく寄与した。複素寄与が上位だった節点26→27と25→26で、ゼロ流量付近の損失を滑らかにつないで再描画した。流向の異なる標本の絶対流量の最大値55.98 cm³/sを基に、変更区間の端を60 cm³/sとした。 [事前登録](../cases/fixed-alpha-lf-fundamental-smoothed-branches.json)・[前回の枝別の観測](fixed-alpha-lf-fundamental-amplitude-branch-loss.md#実測)

## 呼び出しと圧力式

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`HumanVoice::render` が肺圧と声門開口を更新して `AirwayNetwork::step` を呼ぶ。固定姿勢のプローブは同じ気道網の咽頭入口に流量を直接与える。研究版は `vocal-cli render` から `render_fixed_airway` を通り、`AirwayNetwork::step` 内で各 `Branch::step` を呼ぶ。上流の定常狭窄試験は1セルと1/4セルの狭窄を通る流量をベルヌーイ近似と15%以内で照合する。 [通常発声の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[固定姿勢プローブ](../tools/upstream_sagittal_probe.rs#L269)・[研究版の固定姿勢](../crates/vocal-cli/src/geometry_case.rs#L569)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

前標本の節点圧と枝の運動量から駆動圧 `c` を作り、粘性抵抗 `R`、慣性 `L`、標本周期 `Δt` に対し `c = BU + F(U)` を解く。`B = R + L/Δt`、`U` は流量（cm³/s）、`c` と損失 `F` は dyn/cm²。固定断面での元の損失は、順流・逆流ごとの係数 `K_s` を用いる `F(U) = K_s U|U|`。枝流量と枝運動量を更新してから壁の流量、節点圧と放射を更新する。 [固定上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L964)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L189)

## 平滑化と数値解

幅 `w = 60` cm³/s、`x = |U|/w` とし、`|U| ≤ w` で損失に `g(x) = 1 − (1 − x)^3` を掛けた。`g` は0から1へ単調に増加し、`g(1) = 1`、`g′(1) = g″(1) = 0`。ゼロ付近では損失が流量の三次の大きさになるため、両向きで二階微分まで流量0で連続になる。±60 cm³/sでも二階微分まで元の式につながる。損失の符号は流量と同じで、`UF(U)` は非負となる。

流量の符号を駆動圧から決め、`|c| < Bw + K_s w²` の場合は、流量の絶対値が `[0, w]` に入る。絶対値に対する駆動圧の式は単調に増加するため、56回の二分法で解いた。区間外では既存の二次方程式を使う。選択した2枝だけで標本76,800から変更し、両版のソースは隔離ビルドに写して差分を適用した。 [区間内の解法と隔離ビルド](../tools/measure_fixed_alpha_loss_tangent.py#L31)

固定 /ɑ/・96 kHzで110 Hzの入力量を前回と同じ倍率0、±1、±0.5で与えた。切替の直前1標本・直後128標本、末尾の19,200標本と直前1標本を採取した。定常流だけを与える対照も描画した。観測した前標本の節点圧差から慣性と粘性を引いて損失を求め、流量および断面から計算した式と照合した。仕事率の観測にはこの圧力損失と流量の積を使った。 [損失と仕事率の計測](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py#L55)

## 口端応答への寄与

元の流量を `U₀`、平滑化後の流量を `U_s`、定常点の接線を `T` とする。枝ごとの圧力源の差は `ΔE = F_s(U_s) − T(U_s) − [F(U₀) − T(U₀)]`。このうち、元の流量に両方の式を適用した差 `F_s(U₀) − F(U₀)` を直接効果とし、残りを流量が変わった分に割り当てた。同じ振幅の描画を比べるため入口流量の差はゼロ。両圧力源を離散節点方程式で口端・壁流量と節点圧へ換算し、観測した差と照合した。 [圧力源と複素応答の計測](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py#L82)

出力の奇成分 `O(a)` と偶成分 `E(a)` は前回と同じ方法で計算した。比例からのずれは `2O(0.5) − O(1)`、二次からのずれは `4E(0.5) − E(1)`。平滑化後と無変更のそれぞれについて、この複素差の大きさを比較した。 [奇成分と偶成分の定義](fixed-alpha-lf-fundamental-amplitude.md#正負の描画で測る量)

## 実測

| 周波数と比較 | 無変更の口端複素差の大きさ（cm³/s、DFT係数） | 平滑化後（cm³/s） | 無変更からの増減 |
| --- | ---: | ---: | ---: |
| 660 Hz・奇成分の比例からのずれ | 0.00012716 | 0.00016333 | +28.45% |
| 660 Hz・偶成分の二次からのずれ | 0.00016026 | 0.00016791 | +4.77% |
| 770 Hz・奇成分の比例からのずれ | 0.00023891 | 0.00028633 | +19.85% |
| 770 Hz・偶成分の二次からのずれ | 0.00033332 | 0.00029240 | −12.28% |

ずれが減るという予想を満たしたのは770 Hzの偶成分だけだった。元の枝流量に両方の損失式を適用した直接効果が、全4比較の複素差をほぼ説明した。流量が変わった分は、口端での平滑化効果に対して最大0.166%だった。流量・断面の式を使った再構成の最大相対誤差は口端で9.82×10⁻¹⁰、壁流量と節点圧で1.17×10⁻⁹。慣性・粘性を引いた観測損失を与えた計算は、口端で4.63×10⁻¹⁰以内で一致した。 [平滑化前後の複素応答と再構成](../runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/summary.json)

定常流だけを与えた対照の圧力・流量・放射は両版ともビット一致した。早期窓と定常窓の損失は式に相対1.11×10⁻¹²以内で一致し、丸め許容差を超える負の仕事率は0標本だった。両版の再描画の時系列はピーク相対1.97×10⁻¹⁴以内で一致した。最初の差は、110 Hzの変更倍率+1で標本76,818、ほかの4条件で76,817。枝25→26の流量と両端の節点圧に現れ、元の対応枝の絶対流量が60 cm³/sを初めて下回った標本と一致した。 [定常流・最初の差・仕事率](../runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/summary.json)

## 次の幅を決める予測

保存済みの無変更の枝流量に幅15、30、60 cm³/sの各損失式を適用し、その直接効果だけを離散節点方程式で口端に伝搬させた。幅60 cm³/sでは、直接効果だけでも今回の再描画と同じ増減の向きになった。幅30 cm³/sの計算では、660 Hzの奇成分で+8.48%、偶成分で−0.76%、770 Hzの奇成分で+16.08%、偶成分で+7.91%と予測した。次は同じ2枝・5入力で幅30 cm³/sを再描画し、特に770 Hzの偶成分で幅60 cm³/sとは異なる向きになるか照合する。 [無変更の枝流量と設定](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/manifest.json)・[直接の圧力源と離散節点計算](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py#L74)

## 再実行と保存

研究ワークスペースから未使用の実行IDで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py fixed-alpha-lf-fundamental-smoothed-branches-local-01
```

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` から各45判定と固定上流の狭窄試験に通過した。既存の接線、受動化、高流量側のみ、低流量側のみの隔離差分は、それぞれ保存済みの上流・研究版・プローブの差分に一致した。要約と6成果がバイト一致し、圧縮観測125,018,229バイトを作業用RTL9210B-CG上で2実行から共有した。 [初回](../runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-registered/manifest.json)・[再実行](../runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/manifest.json)・[全体監査](../runs/plan-completion-v24-alpha-lf-smoothed-branches-20261124/manifest.json)
