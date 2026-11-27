# 固定 /i/ の440 Hzと2,310 Hzで口蓋帆の効果を分ける

前回は輪郭とポート面積の4条件を描画した。2つの輪郭で開口効果を引き合わせたPCMに、440 Hzと2,310 Hzで大きな成分があった。固定上流の `transfer_function` と研究版CLIの `transfer` は、声門枝を切って咽頭入口に単位体積流量を与える。壁・端の放射と節点圧縮性を並列に、枝の抵抗・慣性を直列に扱う。枝のインピーダンスは `R + jωL` となり、末端から入口へ `Y/(1+ZY)` で負荷をまとめ、逆順で各節点圧と放射を得る。線形要素には平均流量ゼロまわりの係数を使う。上流の一様管試験では、壁の有無ごとにこの計算とインパルス応答のピークを照合する。 [前回の4条件](fixed-vowel-i-velum-port-only.md#実測)・[上流の線形伝達](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)・[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[研究版CLI](../crates/vocal-cli/src/geometry_case/transfer.rs)

時間離散化では枝流量と壁速度を先に解き、各節点の圧力を更新する。1標本の遅延を `d = exp(−jωΔt)`、後退差分を `s = (1−d)/Δt` とすると、枝のアドミタンスは `d/(R+Ls)`。壁の表面積を `A` とするとアドミタンスは `dA/[ms + r(1+d)/2 + kd/s]` になる。端の放射負荷は中点で解くため、`b=(1+d)/2` を使って `b/R + b²/(Ls)`。この式で時刻差を揃えて全節点の収支を解き、通常レンダーに注入した微小流量から得た応答を独立に照合する。圧力は dyn/cm²、体積流量は cm³/s、流量同士で割った伝達は無次元。 [枝と壁の更新](../crates/vocal-core/src/airway/network.rs#L719)・[放射負荷の更新](../crates/vocal-core/src/airway.rs#L89)・[研究版の分岐節点](../crates/vocal-core/src/airway/network.rs#L384)・[事前登録](../cases/fixed-vowel-i-velum-harmonic-transfer.json)

通常発声の複素係数は400〜500 msから求めた。110 Hzで11周期なので、440 Hzと2,310 HzはそれぞれDFTのビン44と231に対応する。直接DFTとFFTを照合し、放射微分の係数には後退差分に加えて有限窓の両端の差を入れた。両輪郭で求めたポート開口の効果の差を `I` とし、通常発声の声門流量を `Q`、閉条件の流量を `Q₀`、離散線形伝達を `H`、放射流量を `U` とする。`I(U)` を `I(H) Q₀`、`I(H(Q−Q₀))`、`I(U−HQ)` の3項に分ける。最後の項には、微小信号の伝達と通常発声の差が入る。 [観測と解析のコード](../tools/measure_fixed_vowel_i_velum_harmonic_transfer.py)

## 実測

通常CLI・固定上流の連続時間伝達と、全節点の独立連立計算は、全条件・全放射成分で相対1.19×10⁻¹³以内で一致した。各0.001 cm³/sの2音による微小入力では、連続時間伝達と実測の総放射の複素誤差は最大6.52%だった。離散時間のモデルでは最大1.20×10⁻⁶（相対値）で、4条件の各2周波数で連続時間より実測に近かった。 [連続時間と離散時間の応答](../runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/summary.json)

通常発声では、実測した総放射の複素比と離散線形モデルの差が最大1.90%だった。ポートだけを開いた条件の2,310 Hzに現れ、位相差は−1.05°。差の方向への射影は鼻端82.74%、口端17.10%、壁0.17%だった。「少なくとも1条件で3%以上」という仮説は、再実行でも基準に届かなかった。合否基準を維持し、両方の不合格判定を保存した。 [条件別の応答と判定](../runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/summary.json)

輪郭によって開口効果が変わる成分の方向に射影すると、440 Hzでは線形負荷79.14%、声門流量21.77%、微小信号伝達との差−0.91%だった。2,310 Hzでは線形負荷と声門流量の各項の大きさが総差の2.84倍と2.77倍、相対位相は159.38°。両項が打ち消し合い、残った総差への射影は線形負荷71.09%、声門流量29.55%、微小信号伝達との差−0.64%になった。3項の和は複素総差を相対5.86×10⁻¹⁶以内で再構成した。 [周波数別の3項と位相](../runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/summary.json)

## 実行記録

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースから次を実行し、再実行は `/tmp` からPythonとスクリプトを絶対パスで指定した。両実行で19判定中18判定が成立し、固定上流の一様管試験も通過した。要約と41成果はバイト一致した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_velum_harmonic_transfer.py fixed-vowel-i-velum-harmonic-transfer-20261124-registered
```

[初回マニフェスト](../runs/fixed-vowel-i-velum-harmonic-transfer-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/manifest.json)

第37版の全体監査は、事前仮説の不合格を照合した上で209実行・3,619成果・433判定に通過した。研究版のRustテスト53件、固定上流の17件、現行Webのビルドも通過した。今回の3実行の1,537入力・110出力をSHA-256で照合した。RTL9210B-CG上の107出力は同一内容の実体を共有し、47ファイル分の62,569,718バイトを使用する。 [全体監査の要約](../runs/plan-completion-v37-fixed-vowel-i-velum-harmonic-transfer-20261124/summary.json)・[監査マニフェスト](../runs/plan-completion-v37-fixed-vowel-i-velum-harmonic-transfer-20261124/manifest.json)
