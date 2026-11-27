# 固定 /ɑ/ のインパルスで連続時間と離散時間の口端応答を照合する

前回と同じ成人男性の固定 /ɑ/ を採用し、声門枝と軟口蓋ポートを閉じた。内部96 kHzで全圧力・流量をゼロに初期化し、咽頭入口の標本0に10⁻⁸または10⁻⁶ cm³の体積インパルスを入れた。数値はケースに事前登録し、口端流量と壁流量、咽頭入口と口端の圧力の660 Hz・770 Hzでの複素応答を計測した。 [ケース定義と版の記録](../cases/fixed-alpha-discrete-impulse.json)・[前回の有声時の計測](fixed-lf-harmonic-transfer.md)

## 時間領域の入口と状態の更新

上流側では既存の `write_fixed_airway` が `HumanAirway::apply` で姿勢を設定し、`snap_to_targets` で現在の面積と長さを目標値に揃える。起点となる `ext_flow` には注入体積とサンプルレートの積を入れる。`AirwayNetwork::step` がその値を節点の収支に移し、元の値をゼロにするので、励振は1標本だけ。研究版は通常の `vocal-cli render` の `render_fixed_airway` から同じ入口に注入する。直接比較する圧力は dyn/cm²、流量は cm³/s、放射流量差分は cm³/s²。上流の一様管試験では、壁あり・なしで時間領域のピークを線形解析に照合する。分岐試験では極端に狭い三叉点の安定性を検査する。 [上流用プローブ](../tools/upstream_sagittal_probe.rs#L212)・[研究版CLI](../crates/vocal-cli/src/geometry_case.rs#L495)・[上流の姿勢更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[分岐の安定性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L16)

固定姿勢では面積・長さの補間と動壁の体積押し出しが消える。枝は前標本の圧力と前標本の運動量を使い、慣性、粘性、流れの方向ごとの二次損失から流量を解く。続いて壁の速度を前標本の圧力・速度・変位から更新し、速度を積分して変位とする。節点では正味流量をコンプライアンスで圧力変化に換える。口端では節点圧力と並列R–L負荷を同時に更新し、抵抗流と慣性を流れる流量の両時刻平均を出力する。放射では口端・鼻端・壁流量の和から前回の和を引いて時間刻みで割る。 [注入から枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[壁・節点・放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)

## 独立した離散節点方程式

圧力の添字を更新後の標本に揃える。1標本の遅れを `z=exp(−2πif/fs)`、後退差分を `D=fs(1−z)`、両時刻平均を `M=(1+z)/2` とする。枝の二次損失はゼロ流量まわりで微分するとゼロになり、定係数の枝は `z/(R+L D)`。壁の質量 `m`、抵抗 `r`、ばね定数 `k`、壁面積 `S` から、圧力に対する壁流量は `S·z / (m·fs+r/2−(m·fs−r/2)·z+k·z/D)`。開口の圧力に対する流量は `M·(1/R_rad+M/(L_rad·D))`。この三つとコンプライアンスの `C D` を流量収支の連立方程式に入れ、咽頭入口を単位流量で励振する。接続数3以上の節点では、開いている枝の逆慣性の和を使い、コンプライアンスに `Σ(1/L)/(2.4·fs²)` の下限を適用する。今回、この下限で値が変わる節点は0個だった。 [幾何要素を取り出す上流関数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1199)・[独立計算](../tools/measure_fixed_alpha_discrete_impulse.py#L116)

インパルス実測は、各系列を標本0の注入流量で割ってから、複素指数への直接投影とFFTを照合した。全波形の後半で小さな振動が残り、0.20秒の初回は0.15秒以降の口端応答がピークの7.64×10⁻⁶、後半を除いた複素比の誤差は最大3.30×10⁻⁵。小入力の離散モデル照合でも咽頭入口圧が最大3.36×10⁻⁶となり、3判定が不合格だった。25 msごとの尾部の振幅低下を手掛かりに0.60秒へ延長し、末尾0.10秒で再判定した。許容差は同じ値で、最初の19,200標本は両振幅・両版で初回の記録とビット一致した。 [0.20秒の不合格](../runs/fixed-alpha-discrete-impulse-20261124-registered/summary.json)・[0.60秒の照合](../runs/fixed-alpha-discrete-impulse-20261124-repeat/summary.json)

## 結果

上流・研究版の12列は全57,600標本で、各列の最大振幅に対して相対4.37×10⁻¹⁴以内で一致した。圧力の初期値は注入体積をコンプライアンスで割った値に一致し、口端流量の初着は35番目の標本で、口端までの最短の枝数と揃った。0.50秒以降の口端応答はピークの1.81×10⁻¹²以内、末尾0.10秒を外した複素応答との相対差は最大7.06×10⁻¹²だった。小入力の複素口端応答は独立計算と両周波数で相対2.39×10⁻⁹以内、4観測点で相対3.91×10⁻⁹以内だった。 [波形と複素応答の結果](../runs/fixed-alpha-discrete-impulse-20261124-repeat/summary.json)

| 周波数 | 連続時間から離散時間への振幅変化 | 位相変化 | 通常発声と離散応答の差 | 固定LFと離散応答の差 |
| --- | ---: | ---: | ---: | ---: |
| 660 Hz | +0.03131% | −0.00713° | +0.21072%、−0.05585° | +0.24765%、−0.05087° |
| 770 Hz | −0.04357% | −0.00594° | +0.23761%、+0.06309° | +0.07777%、+0.09880° |

注入量を100倍にしたとき、口端の正規化複素応答の差は最大2.36×10⁻⁷。各列のピークを基準に10⁻¹⁰を初めて超えた標本は、咽頭入口圧の1番だった。咽頭入口から最初に出る枝13→14について、圧力差 `p₀`、`B=fs·L+R`、順方向損失係数 `K=4.5780130800×10⁻⁶` を使った。口側流量を `2p₀/(B+sqrt(B²+4Kp₀))` とし、これと壁流量 `S·p₀/(fs·m+r/2)` を入口収支から引くと、両振幅の上流の標本1の圧力を再現した。二次損失を外した計算との差は小入力で約6.92×10⁻¹³ dyn/cm²、大入力で約6.92×10⁻⁹ dyn/cm²だった。 [枝の二次損失と流量計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L967)・[入口近傍の時系列](../runs/fixed-alpha-discrete-impulse-20261124-repeat/artifacts/impulse-traces.npz)

離散化を含めても発声時との差が残る。次は固定した声門流量に、平均成分ゼロと通常発声の平均流量を与える2条件を用意する。同じ微小励振を重ねた差波形で、零バイアスの離散応答に対する複素比を測る。

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。容量は一時CSVを含め512 MiBを見込み、RTL9210B-CGに書き出した。4系列の全時系列を1つの圧縮NPZに保持し、列と標本番号を検証した一時CSVは実行中に扱った。研究ワークスペースと `/tmp` から、各21判定と上流の2試験に通過した。計測条件、形状、圧縮時系列の5成果と要約はバイト一致した。 [初回のマニフェスト](../runs/fixed-alpha-discrete-impulse-20261124-registered/manifest.json)・[延長](../runs/fixed-alpha-discrete-impulse-20261124-extended/manifest.json)・[再実行](../runs/fixed-alpha-discrete-impulse-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_alpha_discrete_impulse.py fixed-alpha-discrete-impulse-new
```
