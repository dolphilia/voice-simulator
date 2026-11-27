# 固定LFの基本波変更による高次倍音の差を枝ごとに追う

固定 /ɑ/ の声門入力の110 Hzだけを通常発声に合わせても、口端の660 Hzと770 Hzが僅かに変わった。今回は固定LFと基本波を合わせた2条件の節点圧と枝流量を再観測し、各枝の損失が口端の複素差にどれだけ寄与したかを求める。元の固定LFの線形近似からの差で寄与が大きかった咽頭3枝について、今回も各周波数で25%以上を占めると描画前に予想した。 [事前登録](../cases/fixed-alpha-lf-fundamental-branch-loss.json)・[基本波を合わせた結果](fixed-alpha-lf-fundamental.md#実測)・[元の固定LFの二次損失](fixed-alpha-branch-loss.md)

## 上流の枝更新と観測位置

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は肺圧と声門面積を設定して `AirwayNetwork::step` を呼ぶ。固定姿勢では保存した声門流量を咽頭入口に与え、声門枝を閉じた状態で同じ気道網の枝・壁・節点を進めた。研究版は `vocal-cli render` から `render_fixed_airway` と `Branch::step` を通る。上流の狭窄試験では、狭窄が1セルと1/4セルを占める2形状で流量を測り、ベルヌーイ近似との相対差を15%と照合する。 [通常発声の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[固定姿勢プローブ](../tools/upstream_sagittal_probe.rs#L269)・[研究版の固定姿勢](../crates/vocal-cli/src/geometry_case.rs#L569)・[研究版の枝](../crates/vocal-core/src/airway/network.rs#L189)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

上流は、各枝の順流・逆流の損失係数を、両端断面と最小断面の逆数の差から求める。広がりと狭まりの両方を含み、狭まりの係数には0.1を掛ける。枝にかかる圧差を `P_a − P_b`、枝流量を `U`（cm³/s）、慣性と粘性抵抗を `L` と `R`、標本周期を `Δt` とする。固定姿勢で枝を駆動する圧差には更新前の節点圧を使い、`P_a − P_b + LU_prev/Δt = (L/Δt + R)U + F(U)` を満たす `U` を求める。枝流量と運動量を保存して節点の流量収支に加え、続けて壁の流量、節点圧と放射負荷を更新する。観測した前標本の圧差から慣性と粘性を引くと、残る圧力が損失 `F(U)`（dyn/cm²）になる。これを、断面と流量から算出した `K_s U|U|` と照合した。 [上流の損失係数と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L975)・[損失を観測から求める計測](../tools/measure_fixed_alpha_loss_tangent.py#L290)

固定 /ɑ/ の形状、2つの周期入力、96 kHzの内部レートを前回の実行から引き継ぐ。切替前の標本76,799と直後128標本、末尾22周期 `[134400, 153600)` とその直前の1標本を採取した。枝番号は実装ごとに異なるので向き付きの両端点で対応付けた。切替の標本では枝が前標本の圧を参照するため、まず入口節点圧、次の標本で入口に接続する枝の流量に差が出ると予想した。 [枝状態の採取と対応付け](../tools/measure_fixed_alpha_branch_loss.py#L86)

## 複素差を求める式

咽頭入口から口端までの経路に定常流量 `Q₀ = 139.8857905134376` cm³/sを設定し、側枝の定常流量はゼロとする。順流の二次損失を定常点で線形化して抵抗に `2K₊Q₀` を加えると、残りの圧力源は `E(U) = F(U) − K₊Q₀(2U − Q₀)` で表せる。2条件の残差差分をフーリエ変換し、各枝の両端の節点に大きさが同じで逆向きの流量源として与える。流量源への換算に使う枝インピーダンスは `Z = R + 2K₊Q₀ + L(1 − exp(−2πifΔt))/Δt`。節点方程式でこの枝ごとの複素寄与を求め、入口流量の差の寄与も加える。口端流量・壁の放射寄与・節点圧の実測複素差と照合する。 [枝ごとの離散応答](../tools/measure_fixed_alpha_branch_loss.py#L183)・[比較処理](../tools/measure_fixed_alpha_lf_fundamental_branch_loss.py#L117)

元の流量を `U₀`、基本波を合わせた流量を `U₁`、差を `d = U₁ − U₀` とすると、同じ残差差分は次の3項の和になる。

| 項 | 圧力差 |
| --- | --- |
| 元の流量の偏差と流量差の積 | `2K₊(U₀ − Q₀)d` |
| 流量差の二乗 | `K₊d²` |
| 逆流の符号と係数の補正 | `−(K₊ + K₋)(U₁² 1[U₁ < 0] − U₀² 1[U₀ < 0])` |

最後の項は、順流式を全流量に延長したときに、逆流で符号と係数が異なる分を補う。3項の圧力差を別々に伝搬させ、総和と各成分を保存した。枝の寄与率は、枝が生む複素流量差を口端で測った複素差の方向に射影し、観測した差の大きさで割って求めた。射影には正負があり、枝や圧力成分が打ち消し合う場合がある。 [圧力差の分解](../tools/measure_fixed_alpha_lf_fundamental_branch_loss.py#L95)

## 実測

入力流量の複素差から直接計算した口端の寄与は、観測差に対して相対8.77×10⁻¹²以下だった。枝の損失を流量から算出した場合、口端の複素差は相対1.05×10⁻¹¹以内、壁流量と節点圧の複素差は1.22×10⁻¹¹以内で再構成した。圧力と流量の観測から慣性・粘性を引いて求めた損失を使っても、口端の複素差を相対9.98×10⁻¹²以内で再構成した。両版の観測時系列はピーク相対4.81×10⁻¹³以内、算出した枝損失と観測値は9.37×10⁻¹³以内で一致した。 [両版の再構成](../runs/fixed-alpha-lf-fundamental-branch-loss-20261124-repeat/summary.json)

| 周波数 | 口端の複素差の大きさ（cm³/s、標本数で正規化） | 咽頭3枝の寄与率 | 流量の積 | 流量差の二乗 | 逆流補正 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 660 Hz | 0.0009558 | 42.87% | 94.5116% | 0.00563% | +5.4828% |
| 770 Hz | 0.0019716 | 49.09% | 106.6796% | 0.00666% | −6.6862% |

節点25→28の咽頭3枝は両周波数で事前予想の25%を超えた。枝ごとの複素寄与を大きさで順位付けすると、660 Hzの最大は節点17→18、770 Hzは節点26→27。側枝を足した寄与の大きさは、口端で観測した差の0.092%以下だった。最初の差は両版とも標本76,800の咽頭入口（節点13）の圧力に出た。次の標本76,801に節点13→14の流量と圧力残差に差が現れた。 [枝ごとの係数と順位](../runs/fixed-alpha-lf-fundamental-branch-loss-20261124-repeat/artifacts/branch-contributions.csv)

## 再実行と保存

研究ワークスペースから未使用の実行IDで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_alpha_lf_fundamental_branch_loss.py fixed-alpha-lf-fundamental-branch-loss-local-01
```

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。研究ワークスペースと `/tmp` から各20判定と固定上流の狭窄試験に通過した。要約と8成果はバイト一致した。圧縮観測49,301,909バイトは作業用RTL9210B-CGに置き、2実行で共有した。 [初回](../runs/fixed-alpha-lf-fundamental-branch-loss-20261124-registered/manifest.json)・[再実行](../runs/fixed-alpha-lf-fundamental-branch-loss-20261124-repeat/manifest.json)・[全体監査](../runs/plan-completion-v21-alpha-lf-fundamental-branches-20261124/manifest.json)
