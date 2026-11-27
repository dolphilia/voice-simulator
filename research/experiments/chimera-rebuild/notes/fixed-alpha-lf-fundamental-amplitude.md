# 固定LFに加える基本波の振幅と極性を変える

固定 /ɑ/ で声門流量の110 Hzだけを変えたとき、入力係数が等しい660 Hz・770 Hzの口端流量にも複素差が現れた。前回はこの差を枝の圧力損失で説明した。今回は110 Hzの入力差を正負両向き・半振幅で与え、口端で観測した差の振幅依存性を測る。 [事前登録](../cases/fixed-alpha-lf-fundamental-amplitude.json)・[枝からの再構成](fixed-alpha-lf-fundamental-branch-loss.md#実測)

## 入力から口端まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、肺圧を設定して声門前後の圧差から開口を更新し、`AirwayNetwork::step` を呼ぶ。固定姿勢プローブは咽頭入口への体積流量（cm³/s）を保存した周期入力から与え、固定 /ɑ/ の気道網を進める。研究版は `vocal-cli render` から `render_fixed_airway` を通って同じ更新を行う。96 kHz、0.80秒の定常流、19,200標本の周期列4回は前回と共通で、切替直後128標本と最後の2ブロックを保存した。 [上流の通常発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の固定姿勢](../tools/upstream_sagittal_probe.rs#L357)・[研究版の固定姿勢描画](../crates/vocal-cli/src/geometry_case.rs#L569)

枝では前標本の節点圧・枝運動量から駆動項 `c`（dyn/cm²）を組み、`c = BU + F(U)` を解く。 `B = R + L/Δt` は粘性抵抗と慣性の項、`U` は枝流量（cm³/s）、`F` は順流・逆流の係数を使った二次損失。枝流量と運動量を更新してから、壁と節点の収支、放射負荷を進める。元の流量が周期的に変わると、微小な差に対する損失の傾き `dF/dU = 2K_s|U|` も周期的に変わる。流量がゼロを横切ると傾きは連続だが、その傾きの変化率は流向で切り替わる。無変更の周りで測る応答の比例関係や二次の近似は、この流量域の影響を受ける。狭窄の上流試験は、定常流を1セルと1/4セルの狭窄で測り、ベルヌーイ近似との相対差が15%以内であることを確認する。 [上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[研究版の枝](../crates/vocal-core/src/airway/network.rs#L189)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

## 正負の描画で測る量

固定LFの入力を `q_LF[n]`、保存済みの「110 Hzを通常発声に合わせた入力」との差を `d[n]` とする。入口に `q_LF[n] + a d[n]` を与え、倍率 `a` を0、±0.5、±1とした。倍率0と+1には保存済みの入力そのものを使う。全ビンのFFTを照合し、110 Hzの係数だけが倍率に合わせて変わり、平均とそれ以外の係数が固定LFと一致することを確認した。 [入力の構成](../tools/measure_fixed_alpha_lf_fundamental_amplitude.py#L48)

ある周波数で観測した流量の複素係数を `Y(a)` とする。符号を変えると反転する奇成分は `O(a) = (Y(a) − Y(−a))/2`、平均に残る偶成分は `E(a) = (Y(a) + Y(−a))/2 − Y(0)`。比例する応答なら `2O(0.5) = O(1)`、二次の応答なら `4E(0.5) = E(1)` となる。全振幅と無変更だけを使う半振幅の予測は `Ŷ(a) = Y(0) + a O(1) + a² E(1)` とした。最後の22周期で複素係数を求め、差の時系列を直接DFTした結果と、各描画のFFT後に差を取る経路を照合する。前のブロックでも同じ奇成分・偶成分を求め、残留過渡が測定結果へ影響していないか確認した。 [奇成分・偶成分と補間](../tools/measure_fixed_alpha_lf_fundamental_amplitude.py#L64)

入力変更の最初の標本では、前標本の節点圧から枝流量を更新するため、入口圧の差は `Δp = Δq·Δt/C` で求められる。`C` は入口節点の有効コンプライアンス。口端流量への伝搬には経路の35枝に相当する標本数がかかる。4つの変更条件についてこの初期応答を照合した。 [離散節点と入口のコンプライアンス](../tools/measure_fixed_alpha_periodic_flow.py#L136)

## 実測

研究版の口端流量の複素差を以下に示す。大きさの比は半振幅を全振幅で割った値で、位相差は半振幅の位相から全振幅の位相を引いた値。比例・二次からのずれはそれぞれ `|2O(0.5) − O(1)|/|O(1)|` と `|4E(0.5) − E(1)|/|E(1)|` で求めた。上流でも同じ傾向だった。

| 周波数 | 全振幅の偶成分／奇成分 | 奇成分の大きさの比 | 奇成分の位相差 | 比例からのずれ | 偶成分の大きさの比 | 二次からのずれ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 110 Hz | 0.000775% | 0.5000 | +0.000067° | 0.000361% | 0.2288 | 9.16% |
| 660 Hz | 27.22% | 0.4979 | +5.74° | 10.01% | 0.3340 | 46.33% |
| 770 Hz | 30.23% | 0.4875 | −9.01° | 15.71% | 0.4083 | 72.51% |

660 Hz、770 Hzともに、偶成分が奇成分の10%未満、比例からのずれが1%未満、二次からのずれが25%未満という3つの事前予想を外れた。半振幅の奇成分の大きさはいずれも全振幅の約半分だが、位相差によって複素係数のずれが大きくなった。全振幅と無変更から求めた二次式で半振幅の差を予測すると、660 Hzでは正負それぞれ11.25%、11.89%、770 Hzでは10.07%、32.85%の相対誤差が残った。 [複素係数と二次式の予測誤差](../runs/fixed-alpha-lf-fundamental-amplitude-20261124-windowed-repeat/summary.json)

入力の全ビンは目標スペクトルとピーク相対2.04×10⁻¹⁶以内で、両版の時系列はピーク相対2.03×10⁻¹⁴以内で一致した。直接DFTとFFTで求めた奇成分・偶成分の差は奇成分を基準として相対1.98×10⁻¹²以内、最後の2ブロック間の差は9.96×10⁻¹¹以内だった。全振幅と半振幅での最初の入口圧の差はそれぞれ±590.4714、±295.2357 dyn/cm²で、すべての口端流量差が入力変更の35標本後に初着した。

## 初回の停止と再実行

初回と別ディレクトリからの再実行では、負の全振幅の実行名の末尾が、共通の計測処理で全履歴を残す場合の接尾辞と一致した。描画は終わったが、負の全振幅の開始区間を独立に保存する処理が省かれ、集計が `KeyError` で停止した。全履歴を残すケースを呼び出し側から明示する形に直し、初回の全履歴から切替直後と末尾2ブロックを切り出して修正後とビット照合した。既存の周期再入力と全履歴の再入力も描画し直し、保存済みの要約と7成果に一致した。 [初回の停止記録](../runs/fixed-alpha-lf-fundamental-amplitude-20261124-registered/failure.json)・[別ディレクトリの停止記録](../runs/fixed-alpha-lf-fundamental-amplitude-20261124-repeat/failure.json)・[既存ケースの回帰確認](../runs/fixed-alpha-periodic-flow-20261124-explicit-windows-regression/manifest.json)

研究ワークスペースから未使用の実行IDで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_alpha_lf_fundamental_amplitude.py fixed-alpha-lf-fundamental-amplitude-local-01
```

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。修正後は研究ワークスペースと `/tmp` から各25判定と固定上流の狭窄試験に通過し、要約と7成果が一致した。圧縮観測21,626,262バイトは作業用RTL9210B-CGに置いて2実行で共有した。 [修正後](../runs/fixed-alpha-lf-fundamental-amplitude-20261124-windowed/manifest.json)・[再実行](../runs/fixed-alpha-lf-fundamental-amplitude-20261124-windowed-repeat/manifest.json)・[全体監査](../runs/plan-completion-v22-alpha-lf-fundamental-amplitude-20261124/manifest.json)
