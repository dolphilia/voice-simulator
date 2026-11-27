# 声道断面を咽頭と口腔のセルへ割り当てる

## 固定上流の経路と計算順序

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanAirway::apply` は `commit` を呼び、`HumanVocalTract::compute` の格子上の断面と中心線を `resample` に渡す。`resample` が返すのは咽頭・口腔の解剖学的な長さ（cm）と各セルの面積（cm²）。最小断面（cm²）も要求できる。次の段で `commit` は面積の変化率を制限し、音速とサンプルレートで決まる安定性条件を踏まえた長さとともに気道へ設定する。この単位の比較点は `resample` の出口。[気道の呼び出し元](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[気道へ入れる長さと断面](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L310)

成人男性では声門から2.4 cmまでを喉頭蓋付近の管として先に計算する。正規化位置0.3と0.5で断面を切り替え、それぞれの前後0.03を線形に接続する。中央部は仮声帯の制御 `ventricular` で0.95 cm²から狭まり、上部の出口は `epilarynx` に応じて1.9〜0.35 cm²になる。これらは無次元の制御値。2.16〜2.4 cmでは格子の先頭の面積へ線形につなぎ、そこから先は中心線に沿って格子の面積を線形補間する。[声門上の面積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1277)・[格子との接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)

咽頭を声門から鼻腔との分岐点まで、口腔を分岐点から唇までとして、それぞれ指定数の等長セルに分ける。各セルで8つの等間隔の小区間の中央を評価し、面積を `8／Σ(1／Aⱼ)` で代表させる。最小断面にはその8点とセル内の元の格子点の最小値を使い、代表面積を上限にする。どちらかの評価点で `A≤10⁻⁵ cm²` なら代表面積と最小断面を両方0にする。元の点はセルの両端を含めて調べ、各領域の最終セルの右端に丸め誤差分 `10⁻⁶ cm` を加える。格子の最小値を残すことで、8点の間にある細い狭窄や一点の閉鎖を拾える。[セル内の評価と閉鎖判定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1335)

上流の `geometry_continuity` は `compute` と `resample` を組み合わせて較正済み母音間のセル面積を比較する。定常狭窄のテストでは限られた長さの狭窄を最小断面として設定する。今回の単体比較は固定姿勢のセル配列を対象にし、設定したセル数と境界、8点だけでの閉鎖判定、元の点を加えた最小値を別々に照合する。[母音間の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)・[定常狭窄の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

## 実装前に登録した比較

既存の断面プロファイルを独立した8点の試算へ入れ、成人男性の固定姿勢7条件を選んだ。セルの両端を一致させ、位置の絶対差は `10⁻⁹ cm`、代表面積と最小断面は `10⁻⁹ cm²` 未満とする。

| 条件 | 予測 |
| --- | --- |
| 中立20／24セル、18／18セル | 咽頭約8.83 cm、口腔約8.30 cm。96 kHzで上流の生成式が使う18／18セルにしても最小断面は咽頭0.95 cm²、口腔約1.57 cm²。[20／24](../cases/resample-neutral.json)・[18／18](../cases/resample-neutral-96k.json) |
| 声門上と仮声帯を狭める | 咽頭の最小断面約0.35 cm²。口腔のセル列は中立と同じ。[ケース](../cases/resample-epilarynx.json) |
| 舌体の閉鎖 | 口腔26セルでは0〜7番が閉じる。0番の8点の最小は約 `5.62×10⁻⁵ cm²` で、格子点の閉鎖を拾った結果セルを閉じる。[ケース](../cases/resample-closed-roof.json) |
| 唇の閉鎖 | 口腔31セルでは29・30番が閉じる。29番の8点の最小は約0.00235 cm²で、格子点で初めて閉鎖する。[ケース](../cases/resample-compressed-lips.json) |
| 舌先の狭窄と舌側面の開口 | 舌先近くの口腔の最小値は約0.201 cm²。`lateral=0.8` で約0.28 cm²になる。[狭窄](../cases/resample-raised-tip.json)・[舌側面](../cases/resample-lateral.json) |

## 再実装と測定結果

`AreaProfile::resample` は格子上の断面列から、管の長さと、各セルの調和平均・最小断面を求める。距離順の格子を二分探索し、各セルの範囲に含まれる点を選んでから8点を調べる。閉鎖が見つかった時点で両面積を0として返す。CSVの境界は解剖学的な区間で、末端の格子点を拾うための `10⁻⁶ cm` は内部判定にだけ使う。[コア実装](../crates/vocal-core/src/anatomy/resample.rs)・[CLI](../crates/vocal-cli/src/geometry_case.rs)

上流プローブは `HumanVocalTract::resample` を直接実行した。NumPyの独立計算では、中心線と格子面積を入力とし、全セルの8点の位置を行列にして補間・調和平均・閉鎖判定を計算した。セルへの割り当て前の隙間、面積、中心線距離も上流と照合した。出力は `trace.csv`（再実装）、`upstream-trace.csv`（上流）、`independent-cells.csv`（独立計算）。独立計算のCSVには8点の最小と元の格子点の最小を別列に保存する。[上流プローブ](../tools/upstream_sagittal_probe.rs)・[計測器](../tools/measure_resample.py)

| 条件 | 観測結果 |
| --- | --- |
| 中立20／24セルと18／18セル | 咽頭8.8306 cm、口腔8.2990 cm。両分割で最小断面は咽頭0.95 cm²、口腔1.56985 cm²。口腔の調和平均の最小値は1.67101から1.72445 cm²に変わった。[20／24](../runs/resample-neutral-20261119-b/summary.json)・[18／18](../runs/resample-neutral-96k-20261119-b/summary.json) |
| 声門上と仮声帯を狭める | 咽頭の最小断面は0.35 cm²。口腔の全24セルの境界・調和平均・最小断面は中立と完全に一致した。[結果](../runs/resample-epilarynx-20261119-b/summary.json) |
| 舌体の閉鎖 | 口腔0〜7番が閉じた。0番の採取点の最小は `5.6208×10⁻⁵ cm²`。格子点の0 cm²を拾ってセルが閉じた。[結果](../runs/resample-closed-roof-20261119-b/summary.json) |
| 唇の閉鎖 | 口腔29・30番が閉じた。29番の採取点の最小は `2.3526×10⁻³ cm²`。格子点の0 cm²を拾ってセルが閉じた。[結果](../runs/resample-compressed-lips-20261119-b/summary.json) |
| 舌先の狭窄と舌側面の開口 | 口腔の最小断面は0.20083から0.28000 cm²、調和平均の最小値は0.24374から0.30751 cm²へ上がった。[狭窄](../runs/resample-raised-tip-20261119-b/summary.json)・[舌側面](../runs/resample-lateral-20261119-b/summary.json) |

各ケース21項目、合計147項目が通過した。固定上流との最大絶対差はセル境界で `7.11×10⁻¹⁵ cm` 未満、調和平均で `3.74×10⁻¹⁴ cm²` 未満、最小断面で `2.58×10⁻¹⁴ cm²` 未満。独立計算との差は境界が0 cm、両面積が `1.78×10⁻¹⁵ cm²` 未満だった。研究ディレクトリと `/tmp` から別々の実行IDで再実行し、全7ケースで両方のCSV、入力格子、独立計算、設定、要約の49ファイルが一致した。[中立姿勢の初回](../runs/resample-neutral-20261119-a/manifest.json)・[再実行](../runs/resample-neutral-20261119-b/manifest.json)

```bash
python3 tools/measure_resample.py resample-compressed-lips-local-1 resample-compressed-lips
```

次は得られた面積と最小断面を気道グラフへ渡す。静止姿勢で解剖学的な長さと音響計算に使う長さの両方を測り、口腔が短くなる姿勢で上流と同じ安定性下限が働くかを確かめる。[上流の設定処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L310)
