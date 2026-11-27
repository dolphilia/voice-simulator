# 固定LFの高次倍音の振幅依存性を枝ごとの圧力損失に分ける

固定 /ɑ/ で110 Hzの入力差を倍率0、±1、±0.5で与えると、660 Hzと770 Hzで半振幅の奇成分は比例、偶成分は二次の予測から外れた。今回は同じ5入力を枝状態の観測付きで再描画し、口端で観測したずれを枝ごとの圧力損失に分ける。順流式からの逆流補正が、比例・二次からの各ずれの方向に50%以上を占めると、描画前に予想した。 [事前登録](../cases/fixed-alpha-lf-fundamental-amplitude-branch-loss.json)・[前回の振幅比較](fixed-alpha-lf-fundamental-amplitude.md#実測)

## 上流の更新順序と観測

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、肺圧を設定し、声門開口を更新したあとに `AirwayNetwork::step` を呼ぶ。固定姿勢プローブでは、声門枝を閉じた固定 /ɑ/ に保存した周期流量（cm³/s）を咽頭入口から直接与える。研究版は `vocal-cli render` → `render_fixed_airway` → `AirwayNetwork::step` → `Branch::step` を実行する。上流の狭窄試験では狭窄が1セルと1/4セルを占める条件の定常流を求め、ベルヌーイ近似との相対差を15%以内で照合する。 [通常発声の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[固定姿勢プローブ](../tools/upstream_sagittal_probe.rs#L269)・[研究版の固定姿勢描画](../crates/vocal-cli/src/geometry_case.rs#L569)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

上流の枝は、更新前の節点圧と枝運動量から駆動項を組み立てる。固定姿勢で枝の流量を `U`、慣性を `L`、粘性抵抗を `R`、標本周期を `Δt` とすると、`P_a − P_b = L(U − U_prev)/Δt + RU + F(U)`。圧力は dyn/cm²、流量は cm³/s。二次損失 `F(U)` の係数は、流れの向きに応じて両端の断面と最小断面から求める。枝流量と運動量を更新し、続けて壁の流量、節点圧、放射負荷を進める。入口の注入を変えた標本では、枝流量が更新前の圧力を参照するため、まず入口圧が変わり、次の標本で入口につながる枝の流量が変わる。 [上流の損失係数と枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L975)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L189)

固定上流と研究版で、切替前1標本と切替後128標本、末尾22周期の `[134400, 153600)` とその直前1標本を採取した。枝の番号は実装間で一部異なるため、向き付き端点で対応付けた。前回の口端・壁流量などの観測と、倍率0・+1の保存済み枝状態も照合した。 [枝状態の採取](../tools/measure_fixed_alpha_branch_loss.py#L91)・[端点の対応付け](../tools/measure_fixed_alpha_branch_loss.py#L137)

## 振幅条件と圧力源の組み合わせ

順流の係数を `K₊`、逆流の係数を `K₋` とする。経路の定常流量 `Q₀` は139.8857905134376 cm³/s、側枝では0。線形化した抵抗に `2K₊Q₀` を加え、残る圧力源を `E(U) = F(U) − K₊Q₀(2U − Q₀)` とした。流量で算出した `F(U)` と、圧差の観測から慣性と粘性を引いた `F(U)` をそれぞれ使って、同じ口端差の再構成を行った。

倍率0の流量を `U₀`、各倍率の流量を `U_a`、`d = U_a − U₀` とすると、残差の変化は `2K₊(U₀ − Q₀)d`、`K₊d²`、逆流の符号と係数の補正の和になる。逆流補正は `−(K₊ + K₋)(U_a² 1[U_a < 0] − U₀² 1[U₀ < 0])`。同じ枝・標本で5条件すべてが逆流する場合と、5条件の間で逆流と非逆流が分かれる場合に、この補正項を分けた。 [前回の単一変更の損失式](../tools/measure_fixed_alpha_lf_fundamental_branch_loss.py#L95)・[5条件の圧力源の構成](../tools/measure_fixed_alpha_lf_fundamental_amplitude_branch_loss.py#L74)

正負各振幅の対を使い、圧力源と測定した出力のそれぞれで奇成分 `O(a) = (Y(a) − Y(−a))/2`、偶成分 `E(a) = (Y(a) + Y(−a))/2 − Y(0)` を求めた。比例からのずれは `2O(0.5) − O(1)`、二次からのずれは `4E(0.5) − E(1)` とした。入口流量と各枝の圧力源を、線形化した離散節点方程式で口端・壁の流量と各節点圧の複素差に換算する。枝の寄与率は、口端で観測した複素差の方向へ射影して求めた。ある項の寄与が100%を超える場合は、他の項との打ち消しがある。 [奇成分・偶成分の定義](../tools/measure_fixed_alpha_lf_fundamental_amplitude.py#L64)・[枝単位の離散応答](../tools/measure_fixed_alpha_branch_loss.py#L183)

## 実測

660 Hz・770 Hzの口端の奇・偶成分と振幅則からのずれを、枝の圧力源からピーク相対1.19×10⁻¹⁰以内で再構成した。壁の流量と節点圧は相対1.05×10⁻¹⁰以内、圧力と流量の観測から直接求めた損失による口端差は4.49×10⁻¹¹以内で一致した。入口流量の差だけが生む口端寄与は相対1.21×10⁻¹¹以下だった。 [両版の計測結果](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/summary.json)

| 周波数と比較 | 口端差の大きさ（cm³/s、DFT係数） | 流向が変わる標本の逆流補正 | 全条件で逆流する標本の補正 |
| --- | ---: | ---: | ---: |
| 660 Hz・奇成分の比例からのずれ | 0.00012716 | 100.0815% | 0.00104% |
| 660 Hz・偶成分の二次からのずれ | 0.00016026 | 100.0312% | 0.00129% |
| 770 Hz・奇成分の比例からのずれ | 0.00023891 | 100.0951% | 0.00056% |
| 770 Hz・偶成分の二次からのずれ | 0.00033332 | 100.0630% | 0.00108% |

寄与は各複素差の方向への射影。4比較で逆流補正が50%以上を占めるという予想を満たし、流向が条件間で異なる標本だけで約100%だった。順流式の積と二乗の項は、この寄与を僅かに打ち消した。全振幅の奇成分そのものへの逆流補正は660 Hzで+29.25%、770 Hzで−38.14%で、比例からのずれを対象とした場合には逆流補正の割合が大きくなった。 [成分別の係数](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/summary.json)

流向が変わる標本の逆流補正を枝別の複素寄与の大きさで順位付けすると、節点26→27、25→26、17→18が4比較すべてで上位3枝だった。流向が条件間で異なった186,990の枝・標本について、5条件の絶対流量の最大値を集計すると、中央値26.84 cm³/s、最大55.98 cm³/sだった。次は上位2枝のゼロ流量付近で損失を滑らかにつなぎ、定常点の値・傾きを保つ対照で口端応答を測る。 [各枝の複素寄与](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/artifacts/branch-contributions.csv)

全4変更と両版で、最初に変わった圧力は標本76,800の節点13、枝流量と残差は76,801の節点13→14だった。両版の全観測はピーク相対4.87×10⁻¹³以内、観測した圧力損失と流量・断面から算出した値は9.37×10⁻¹³以内で一致した。倍率0と+1の枝観測と、全5条件の従来の観測列は、保存済みの値とビット一致した。

## 再実行と保存

研究ワークスペースから未使用の実行IDで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_alpha_lf_fundamental_amplitude_branch_loss.py fixed-alpha-lf-fundamental-amplitude-branch-loss-local-01
```

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。研究ワークスペースと `/tmp` から各29判定と固定上流の狭窄試験に通過した。要約と14成果はバイト一致した。圧縮観測123,262,256バイトは作業用RTL9210B-CGに置き、2実行で共有した。 [初回](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-registered/manifest.json)・[再実行](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/manifest.json)・[全体監査](../runs/plan-completion-v23-alpha-lf-fundamental-amplitude-branches-20261124/manifest.json)
