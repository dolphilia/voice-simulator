# 一様管の口端流量から理想開口の軸上音圧を求める

## 固定上流の観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の一様管試験は、`uniform_tube` が最終節点に `add_radiation` を付ける。入口に短い流量を与え、`AirwayNetwork::step` が返した放射流量差分をFFTに掛け、角周波数で除して共鳴を測る。節点の並列R–L負荷は、節点圧と慣性枝流量を中点で連立する。慣性枝流量の旧値と新値の平均、抵抗枝の流量を足した値が `radiated_flow` の体積流量で、単位は cm³/s。 `step` の戻り値は、各放射口と重み付き壁流量の和の後退差分で cm³/s²。 `HumanVoice::render` はこの差分を間引き・直流除去・振幅制限に通す。今回は壁が振動せず放射口が一つの剛体管を使用するため、差分を取る前の放射口流量をそのまま口端流量として読む。[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[放射端の状態と差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1121)・[上流のPCM経路](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

一様管の面積3 cm²を `3×10⁻⁴ m²`、口端流量を `U[m³/s]=10⁻⁶ U[cm³/s]` に換算した。音速は35,000 cm/sから350 m/s、密度は0.00114 g/cm³から1.14 kg/m³に換算した。元のR–L負荷で求めた流量を理想バッフルに置いた一様速度の円盤への入力とし、軸上0.5・1・2 mの音圧を算出する。音圧の計算は管内の状態更新へ戻さない。ここで得るPaは、この放射モデルの仮定による値であり、人間の頭部や録音空間での音圧には別の条件が必要になる。[同じ終端の一様管比較](uniform-waveguide-matched.md)・[以前の体積流量と理想開口実験](../../autonomous-research-cycle/campaigns/nas-volume-velocity-observer-20261009-v1/report.md)

## 有限円盤と遠方近似

距離を `r`、円盤の半径を `a`、面積を `A=πa²`、音速を `c`、密度を `ρ` とする。円盤上の半径 `s` の環から観測点までは `R=√(r²+s²)`。Rayleigh積分に一様速度 `U/A`、環の面積 `2πs ds` を入れ、`dR=(s/R)ds` で積分すると、軸上の音圧は次式になる。[Oelzeの円形ピストン講義](https://jontallen.ece.illinois.edu/uploads/473.F18/Lectures/Chapter_7b.pdf)

```text
p(t) = (ρc/A)[ U(t−r/c) − U(t−√(r²+a²)/c) ]
```

遠方近似では二つの遅延差が短いため、前方の時刻で流量を微分し `p(t)≈ρ/(2πr)·dU(t−r/c)/dt` とする。後退差分の複素応答は `(1−e⁻ʲΩ)/Δt` で、連続微分に対して `−Ω/2` の位相を持つ。差分をそのまま伝える条件と、伝搬遅延を0.5サンプル短くして差分の時刻を補正する条件を測る。半ステップ補正後も `sin(Ω/2)/(Ω/2)` の振幅と、有限円盤の縁の追加経路の差が残る。[既存の9タップ微分による遠方近似](../../autonomous-research-cycle/campaigns/nas-volume-velocity-observer-20261009-v1/report.md)

## 実装と事前登録

`vocal-cli observe-axis` は、観測設定JSONと `sample,mouth_flow_cm3_s` の2列CSVを受け取る。流量はCLIでSIへ換算し、Rustコアの循環履歴へ1点ずつ入れる。中心、縁、半ステップ補正を使う中心の計3経路を8点Lagrangeで読み出す。円盤の縁と中心の経路差には `a²/(√(r²+a²)+r)` を使う。補間が伝搬時刻より前に出力しないように、すべての系列へ5サンプルの処理遅延を加える。入力終了後は最大遅延ぶんの無音を入力し、有限長の流量の応答を最後まで書く。軸上圧力は有限円盤、遠方近似、半ステップ補正付き遠方近似をPaで保存する。[Rustの観測器](../crates/vocal-core/src/axial.rs)・[CSVの入口](../crates/vocal-cli/src/axial_case.rs)

入力は以前の一様管の96 kHz・粘性ありと192 kHz・粘性なしから取る。再実装と固定上流の両方を使い、192 kHzでは波動管も加える。保存済みの元系列と6 kHz FIRの来歴をハッシュで確認した。先頭0.25秒に同じFIRを適用し、最後の20 msを半コサインで0に落とす。切り出しの時刻と面積を共通にした。各距離で流量、到達、音圧波形、250〜4,000 Hzの複素応答を比較する。振幅が距離にほぼ反比例することと、同じ観測器を通したとき波動管とFDTDの相対複素比が保たれることも判定する。[事前登録](../cases/uniform-axial-observation.json)

独立計算は50〜4,000 Hzを50 Hz刻みでRayleighの環積分を行い、閉形式に照合する。時間領域では8次元のモーメント方程式から補間係数を求め、全入力へ畳み込む。元の放射差分を口端流量から再計算し、音圧計算に入る前の観測点を確認する。[測定と独立計算](../tools/measure_axial_observer.py)

## 結果

| 96 kHz・粘性ありの候補 | 0.5 m | 1 m | 2 m |
| --- | ---: | ---: | ---: |
| 開口中心からの伝搬時間 ms | 1.429 | 2.857 | 5.714 |
| 開口の縁を通る追加時間 µs | 0.273 | 0.136 | 0.068 |
| 有限円盤のピーク音圧 Pa | 0.11148 | 0.05562 | 0.02763 |
| 4 kHzでの位相差、後退差分 − 有限円盤 | −7.30° | −7.40° | −7.45° |
| 4 kHzでの位相差、半ステップ補正後 − 有限円盤 | +0.196° | +0.098° | +0.049° |

元CSVの流量差分は口端流量からの再計算に1.15×10⁻¹⁶以内の相対ピーク誤差で一致し、cm³/s→m³/s変換値は独立計算と一致した。R–Lの放射を円盤へ渡して得た音圧は、固定上流の入力と候補の入力で相対ピーク誤差1.64×10⁻¹³未満だった。192 kHzで、共通の音圧観測を行う前後の波動管とFDTDの複素比は1.19×10⁻¹²未満の差に収まった。[各距離の波形と複素比](../runs/uniform-axial-observation-20261121-b/summary.json)

Rayleigh積分と閉形式は最大2.39×10⁻¹⁴、Rustの結果と有限円盤の連続時間式は最大2.46×10⁻⁷の相対複素誤差だった。96 kHzで後退差分の期待位相は4 kHzで−7.5°。実測の円盤との差は−7.30〜−7.45°で、半ステップ補正後の残りは最大0.197°だった。192 kHzでは補正前の差は−3.55〜−3.70°で、補正後は同じ範囲の残差になった。補正した遠方近似と円盤の最大複素差は0.440%。伝搬位相を含まない振幅の距離比は、`1/r` から最大0.0074%外れた。[事前基準と実測](../runs/uniform-axial-observation-20261121-b/summary.json)

最初の差は音圧を計算する段で出る。96 kHzの0.5 mでは、口端流量の最初の非ゼロはサンプル39。補正なしと有限円盤は178、半ステップ補正ありは177で始まった。この最初の非ゼロは補間の支持によって決まり、表の伝搬時間は物理経路の遅延を示す。距離そのものの遅延、共通の5サンプル、後退差分の半サンプルを区別する。[96 kHz・0.5 mの短い観測CSV](../runs/uniform-axial-observation-20261121-b/artifacts/96k-viscous-fdtd/0.5/observation-prefix.csv.gz)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1。候補の41試験と固定上流の一様管3試験、Clippy、WASMコンパイル検査に通過した。従来の一様管CSVは保存済みの基準とバイト一致した。観測距離や面積を範囲外にした設定、空の入力、欠番、非有限流量、口端流量列を欠く入力は出力前に拒否した。

最初の実行では、末尾をテーパーしていない定常流量の補助試験で、96 kHz・0.5 mに42 cm³/sを500点与えたときに、停止による最後の非ゼロ値の点で結果CSVが終わった。無音への復帰を確かめられるよう、最後の応答の後に1点を追加した。定常区間と最後の出力が厳密に0であることを回帰判定に加え、元の測定と合否基準は保持した。[最初の実行](../runs/uniform-axial-observation-20261121-a/manifest.json)・[定常流量を含む確定実行](../runs/uniform-axial-observation-20261121-b/manifest.json)

全区間で判定した後、各条件で最初の20 msを可逆圧縮して作業用のRTL9210B-CGへ保存した。確定実行の計測成果は約1.80 MB。出力32点を検査し、元の作業ディレクトリと `/tmp` から実行した観測設定・短いCSVの計30点が一致した。入力の元系列とLagrange補間の設定から全時間の観測を再実行できる。固定距離の出力は線形の外部観測なので、口・鼻・壁の各放射経路を使う発声へ拡張する際は、経路ごとの開口、位置、流量を分けて定義する必要がある。[出力の相対パスとハッシュ](../runs/uniform-axial-observation-20261121-b/manifest.json)・[別ディレクトリからの初回条件の再実行](../runs/uniform-axial-observation-20261121-repeat/manifest.json)

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=65000000 ../../.venv/bin/python tools/measure_axial_observer.py uniform-axial-observation-local-1
cargo run --locked --release -p vocal-cli -- observe-axis 観測設定.json 口端流量.csv 音圧.csv
```
