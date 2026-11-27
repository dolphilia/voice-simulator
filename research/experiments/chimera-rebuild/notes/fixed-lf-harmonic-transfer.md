# 固定 /ɑ/ の第6・第7倍音で声門入力と口端伝達を分ける

成人男性の固定 /ɑ/、基本周波数110 Hz、内部96 kHzで、通常発声を平均流量の揃った固定LF駆動と比較する。前回の22周期で見つかった口端流量の差について、660 Hzと770 Hzだけを調べる。声門流量と口端流量の複素比は1%未満しか変わらず、口端流量の複素差に占める伝達比の項は5%未満と事前登録した。 [ケース定義](../cases/fixed-lf-harmonic-transfer.json)・[前回の放射成分の照合](fixed-lf-radiation-harmonic-budget.md)

## 通常発声と線形応答の入口

上流の `HumanVoice::render` は、各内部標本で肺圧を更新し、声門下・声門上の圧差を声門モデルに渡して開口を決める。`AirwayNetwork::step` は枝の慣性と抵抗、流量に依存する損失を使って声門枝の流量を計算する。その後に壁の速度と変位、節点の圧力、口端の並列R–L負荷を更新する。観測する声門流量は声門枝、口端流量は放射負荷の流量で、どちらも cm³/s。固定LFでは声門枝の流量を指定し、声門の両側に逆符号で加える。両条件の値は、放射差分と出力フィルタを通る前の同じ内部標本で採取した。 [上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[気道の標本更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[固定流量の観測差分](../tools/measure_fixed_lf.py#L45)

較正CLIの `formants` は固定姿勢を適用し、`linear_elements` が取り出した目標形状のコンプライアンス、枝の慣性と粘性抵抗、壁と開口の負荷を使う。このとき平均流量ゼロまわりで線形化し、流速に依存する二次損失を省く。声門枝を切り、咽頭入口に単位流量を入れる。上流の `transfer_function` は入口から到達できる枝を走査し、末端から入口に向かって枝のインピーダンス `Z` と負荷のアドミタンス `Y` を `Y/(1+ZY)` にまとめる。入口の圧力を解いて末端へ戻り、節点圧力と放射アドミタンスの積から複素流量を求める。総放射の流量の大きさと、その時間微分から計算した相対レベルが公開結果になる。既存ゴールデン試験は母音・単純な気道網に対して、倍率・相対レベル・ピークをTypeScript版の保存結果と照合する。 [較正CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/calibrate.rs#L138)・[線形化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1199)・[上流の複素計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L95)

隔離した固定上流に、各開口の複素流量と総和を出力する観測点を加えた。上流の公開振幅が観測した複素総和の絶対値と一致することを確かめた。研究版は通常の `vocal-cli transfer` を使い、独立計算は保存した節点と枝から全節点の流量収支を複素連立方程式として解いた。出力した節点・枝と注入点は保存済みの固定母音比較のデータとバイト一致した。線形計算の複素数は注入流量1に対する比で、閉じた軟口蓋の条件では鼻端流量はゼロだった。 [研究版CLI](../crates/vocal-cli/src/geometry_case/transfer.rs#L72)・[独立計算](../tools/measure_vowel_transfer.py#L68)・[隔離した上流の観測差分](../runs/fixed-lf-harmonic-transfer-20261124-repeat/artifacts/upstream-observation.patch)

## 複素差と平均二乗の計算

内部標本38,400〜57,599の19,200点を矩形窓にし、FFT係数を窓長で割る。各周波数を直接投影するDFTで、複素声門流量 `Q` と複素口端流量 `U` のFFT係数を検算する。対象は5 Hz刻みのビン132、154。各条件の `H=U/Q` を求める。通常発声から固定LFへの口端流量の複素差 `ΔU` は、`mean(H)·ΔQ + mean(Q)·ΔH` と恒等的に一致する。両条件を対称に扱い、`|mean(Q)·ΔH|/|ΔU|` で伝達比の項の大きさを報告する。

口端流量の後退差分では、上の二項それぞれに `fs·(1−exp(−2πi k/N))` を掛け、実際の窓直前値を使った端補正の条件間差を足す。最終的な複素係数を `D`、`D_LF` とすると、各項 `d` の平均二乗への寄与は `2 Re((D_LF+D)·conj(d))` で求まる。項を全て足して以前の口端差分の平均二乗差を復元した。 [時間系列と差分の照合](../tools/measure_fixed_lf_harmonic_transfer.py#L140)・[複素比と平均二乗の照合](../tools/measure_fixed_lf_harmonic_transfer.py#L187)

## 観測結果

| 周波数 | 固定LFの声門流量振幅の変化 | 口端流量振幅の変化 | 複素伝達比の変化 | 口端流量の複素差に対する伝達比の項 |
| --- | ---: | ---: | ---: | ---: |
| 660 Hz | −66.14% | −66.13% | 0.03787% | 0.01650% |
| 770 Hz | −44.23% | −44.32% | 0.17119% | 0.05437% |

声門入力の項が、差分後の口端成分の平均二乗の減少を両周波数でほぼ全て説明した。伝達比の項は660 Hzで減少を約0.020%打ち消し、770 Hzで減少の約0.087%を加えた。窓端の補正を含めると、各周波数の平均二乗の差は前回の値に相対3×10⁻¹⁵以内で一致した。全帯域の口端流量RMSに関する旧5%判定は、元の実測に対して不合格のまま保持した。 [2周波数の計算結果](../runs/fixed-lf-harmonic-transfer-20261124-repeat/summary.json)・[旧判定](../runs/fixed-lf-glottal-flow-20261121-b/summary.json)

固定姿勢の線形口端応答は660 Hzで `6.845570−2.036624i`、770 Hzで `−12.020321−5.682343i`。口端・鼻端・壁・総和を上流と照合した最大誤差は、各周波数の口端振幅に対して研究版が1.28×10⁻¹⁴、節点連立計算が4.34×10⁻¹⁴だった。有声の観測比と線形応答の振幅差は通常発声で +0.2421%、+0.1939%、固定LFで +0.2790%、+0.0342%。位相差は通常発声で −0.0630°、+0.0571°、固定LFで −0.0580°、+0.0929°だった。この差には連続時間の線形化と有声の時間領域計算の条件差が含まれる。次は同じ姿勢を零平均流の小入力で時間領域から励振し、この差を調べる基準にする。 [複素応答CSV](../runs/fixed-lf-harmonic-transfer-20261124-repeat/artifacts/upstream-complex.csv)・[有声波形との照合](../runs/fixed-lf-harmonic-transfer-20261124-repeat/summary.json)

## 実行と保存

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。隔離ビルドは最大1 GiBを見込み、成果と一時領域をRTL9210B-CGに置いた。研究ワークスペースと `/tmp` からの2回で、上流のゴールデン試験1件と各22判定に通過した。要約、派生ケース、複素出力、観測差分、線形要素を含む9ファイルがバイト一致した。 [初回](../runs/fixed-lf-harmonic-transfer-20261124-registered/manifest.json)・[別ディレクトリからの再実行](../runs/fixed-lf-harmonic-transfer-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_lf_harmonic_transfer.py fixed-lf-harmonic-transfer-new
```
