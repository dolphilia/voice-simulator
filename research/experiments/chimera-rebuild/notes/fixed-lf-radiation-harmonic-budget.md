# 固定 /ɑ/ のLF駆動で流量と放射のRMS差を分解する

前回の固定 /ɑ/、基本周波数110 Hz、内部96 kHz、出力48 kHzの通常発声と固定LFを読み直した。固定LFは、平均を通常発声に合わせたLF流量を、声門枝の両端の節点収支へ同じ大きさ・逆符号で与える。旧比較は口端流量と総放射がともに5%以上変わると予測した。口端流量の交流RMS低下は2.85%、総放射では31.61%で、旧判定は不合格だった。今回は同じデータを内部標本38,400〜57,599の22周期で比較する。 [事前登録](../cases/fixed-lf-radiation-harmonic-budget.json)・[旧比較と流量の設定](fixed-lf-glottal-flow.md#結果)

## 発声から放射までの観測点

上流の `HumanVoice::render` は、肺の固定圧と声門開口を更新してから内部時刻を1標本進める。通常発声では声門前後の圧差から `ParametricGlottis::next` が開口面積を決め、`AirwayNetwork::step` が枝の慣性・抵抗と節点圧力から体積流量を更新する。固定LFでは前回の計測差分と同じ処理で声門枝を切り、保存済みの流量を両節点へ挿入する。壁の速度 (v) を前回の速度・変位と現在の圧力から求め、壁面積を掛けて体積流量とする。各壁の放射重みを掛けた和 (U_w) を先に作り、口端 (U_l)、鼻端 (U_n) の並列R–L負荷で得た流量を順に足す。各流量は cm³/s。総放射の観測値はこの和と前回値の差を時刻幅で割った cm³/s²。ここから先の間引き、DC除去、リミッターを通した値がPCMになる。 [上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[壁と節点の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[総和と差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)

固定上流の保存された流量計測差分を隔離ビルドに適用し、壁流量和、口端・鼻端、今回の総和、前回の総和と差分を同時に出力した。定常窓の直前の1標本も採取した。研究版を通常の `vocal-cli render` と `render-pcm` から再描画し、両版の流量・圧力・放射とPCMを当時の保存出力に照合する。上流の `voice_source` 試験は音源の明るさと差分の平均二乗の比を、`lung_port` 試験はその前段の肺圧と声門での挙動を照合する。 [上流の声門試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voice_source.rs#L25)・[肺ポート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L36)・[再描画と解析CLI](../tools/measure_fixed_lf_radiation_budget.py)

## 交流平均二乗と差分の閉包

窓長を `N=19200` とし、FFTを `N` で割る。DCを除き、片側の各ビンの二乗振幅には係数2を掛ける。ナイキストの係数は1。合計を時間系列の分散と照合する。交流RMSはこの平方根であり、加算・差分の内訳は平均二乗で計算する。周波数5 Hz刻みのうち22ビンごとが110 Hzの整数倍で、第1〜24倍音とそれ以降、および倍音以外を区別する。三成分の複素和では、自己項に加えて各組との交差項 `2 Re(A conj(B))` を同じビン重みで集計する。

差分の周波数応答は `fs·(1−exp(−2πi k/N))`。FFTにおける循環差分は窓の最後の標本を先頭の前回値とみなす。実際の前回値を使う差分を復元するため、各ビンに `fs·(u[N−1]−u[−1])/N` を足す。独立の変換結果を、保存した直前標本を使って時系列で差分した結果に照合する。口端流量の基本波は同じビンの通常発声の複素係数で置き換え、逆FFTの交流RMSと電力だけを置き換えた場合の両方を比較する。 [差分とParsevalの検算](../tools/measure_fixed_lf_radiation_budget.py#L143)

## 観測結果

通常発声・LF駆動の上流と研究版のPCMは、保存波形と全28,800フレームで一致した。両条件で直接採取した壁・口端・鼻端の流量を足すと、上流の総和、前回の総和、放射差分をビット一致で再構成できた。複素スペクトルの平均二乗と時系列で求めた分散の誤差は相対5.15×10⁻¹⁶以内。窓先頭を補正した差分の複素応答はピーク相対3.50×10⁻¹⁴以内で時系列の差分に一致し、複素交差項を含む総放射の平均二乗は相対2.58×10⁻¹⁶以内で閉じた。 [再描画と観測の照合](../runs/fixed-lf-radiation-harmonic-budget-20261124-registered/summary.json)

| 観測点 | 通常発声の交流RMS | 固定LFの交流RMS | 通常発声からの変化 |
| --- | ---: | ---: | ---: |
| 口端流量（cm³/s） | 149.96 | 145.68 | −2.85% |
| 口端流量の差分（cm³/s²） | 201,930 | 138,789 | −31.27% |
| 壁の寄与の差分（cm³/s²） | 5,672 | 3,761 | −33.70% |
| 総放射（cm³/s²） | 206,436 | 141,188 | −31.61% |

口端流量の交流平均二乗では、基本波が+1,521、その他の成分が−2,786で、差し引き−1,265 `(cm³/s)²` だった。LFの基本波の係数だけを通常発声に戻した逆FFTでは、口端流量の交流RMSが140.37 cm³/sとなり、通常発声からの低下は6.40%だった。この置換は保存波形のスペクトル上の対照で、気道の描画条件は変えていない。 [倍音別の差と基本波置換](../runs/fixed-lf-radiation-harmonic-budget-20261124-registered/summary.json)

差分後の口端成分の平均二乗の減少のうち、第6倍音（660 Hz）は27.55%、第7倍音（770 Hz）は34.68%を占め、合計62.24%だった。総放射の交流平均二乗の減少には、口端の差分の自己項が94.85%、口端と壁の交差項が5.07%、壁の自己項が0.08%寄与した。鼻端は閉じた軟口蓋の条件でゼロ。3つの予測は成立した。旧5%判定は、保存された実測の口端流量2.85%に対して不合格の状態を保持する。 [第1〜24倍音の平均二乗差](../runs/fixed-lf-radiation-harmonic-budget-20261124-repeat/artifacts/harmonic-power-deltas.csv)・[全ビンの収支](../runs/fixed-lf-radiation-harmonic-budget-20261124-repeat/summary.json)

次は660 Hzと770 Hzで複素比 `口端流量 / 声門流量` を両条件と固定姿勢の線形応答で照合する。第6・第7倍音の差を入力の倍音振幅・位相と声道内の応答に切り分ける。

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。事前登録のSHA-256は `79b58a8a74881755d57bbf9a338b02131f7ee65d9361e3fec2827ca72cd06d41`。隔離ビルドと一時CSVを含む最大容量を1 GiBと見積もり、空き331 GiBとUUIDを確認したRTL9210B-CGに直接出力した。

研究ワークスペースと `/tmp` からの2回で固定上流の声門・肺ポートの5試験と各21判定に通過した。 [初回](../runs/fixed-lf-radiation-harmonic-budget-20261124-registered/manifest.json)・[別ディレクトリからの再実行](../runs/fixed-lf-radiation-harmonic-budget-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_lf_radiation_budget.py fixed-lf-radiation-budget-new
```
