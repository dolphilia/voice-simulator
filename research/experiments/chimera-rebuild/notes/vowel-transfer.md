# 成人男性の固定母音の線形伝達関数

## 固定上流の姿勢と観測点

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の較正コマンドは、調音量から `rest_tip` などを使って舌先を求め、`HumanAirway::apply(a, 0.0)` の目標断面を線形要素に変換する。成人男性の内部レートは96 kHz。120〜4600 Hzの対数間隔700点を使い、150 Hz以上の局所ピークを採る。較正結果には丸めた調音値と整数Hzのピークが保存されている。今回の静止姿勢は連続性テストと同じく、表の調音パッチを中立姿勢へ適用し、表に収録された舌先の座標も使う。発話プランナーの `vowel_artic` は普通の母音で舌先座標を省き、動的な調音器で舌先を追従させる。[較正コマンド](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/calibrate.rs#L109)・[較正表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/vowelTargets.generated.json)・[プランナー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L166)・[形状の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)

基準は咽頭入口に単位体積速度を注入し、理想流量源の内部インピーダンスを無限大とみなして声門ポートを切断する。気道の枝は `R + jωL`、節点の空気は `jωC` のアドミタンスを持つ。枝の開閉と慣性には代表面積、節点コンプライアンスには面積下限0.02 cm²を使う。壁のアドミタンスは壁面積を `R_w + j(ωM_w − K_w/ω)` で割り、口端と鼻端は並列の放射抵抗・放射慣性で受ける。線形化では流量に二次で効く狭窄損失と、時間領域の分岐安定化用コンプライアンス下限を省く。[線形要素](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1196)・[周波数領域の求解](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)

求解は、注入節点につながる木を見つけ、末端から `Y/(1+ZY)` を親へ足す。根で単位流量に対する圧力を求め、圧力降下 `Z × U` を引きながら末端まで伝える。口端・鼻端の流量比に壁面流量比の放射成分を複素数として足す。上流の共鳴ピークはこの合計の流量比の絶対値 `|H|` から求め、`20 log₁₀(ω|H|)` は放射圧力に比例する別の表示。単位円上の離散時間応答や、PCMのLPCで測るフォルマントとは測定条件が異なる。ピーク位置は対数振幅の隣接3点から補間し、−3 dBの交点が両方あるときに帯域幅を求める。[伝達関数とピーク検出](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs)・[上流のゴールデンテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L92)

## 実装前に登録した比較

較正表の成人男性の `/i ɑ u/` と、`/i/` の軟口蓋だけを0.3 cm²に指定した対照を登録した。固定上流の読み取りで姿勢・節点・枝の係数・周波数・合計振幅・放射レベル・ピークを照合する。複素数の口端・鼻端・壁面・合計の各応答は、Python/NumPyによる全節点の連立方程式で独立に確かめる。判定基準と観測範囲は各ケースに固定した。

| 条件 | 事前の予測 |
| --- | --- |
| [固定 /i/](../cases/vowel-transfer-i.json) | 最初の3ピークは337・2225・2901 Hz付近 |
| [固定 /ɑ/](../cases/vowel-transfer-alpha.json) | 最初の3ピークは731・1337・2541 Hz付近 |
| [固定 /u/](../cases/vowel-transfer-u.json) | 最初の3ピークは378・997・2238 Hz付近 |
| [軟口蓋を開いた /i/](../cases/vowel-transfer-i-open-velum.json) | 鼻端にも流量が現れ、約696 Hzの浅いピークでは−3 dB帯域幅が欠測になる |

## 実装と測定結果

`AirwayNetwork::linear_elements` は枝の慣性・抵抗と壁面積の計算を時間領域モデルと共有し、線形解析に使う開閉判定と幾何コンプライアンスを選ぶ。木を根から走査して親と順序を決め、複素数で後退消去と前進代入を行う。注入点から到達できる枝に循環がある場合はエラーを返す。計測器は固定上流の線形要素を使って独立に節点行列を組み立て、全節点の圧力を求めて口端・鼻端・壁面への流量を逆算した。[線形要素](../crates/vocal-core/src/airway/network.rs)・[木の求解](../crates/vocal-core/src/airway/frequency.rs)・[独立計算](../tools/measure_vowel_transfer.py)

| 固定条件 | 総放射の最初の3ピーク (Hz) | 口端のみの最初の3ピーク (Hz) |
| --- | --- | --- |
| [/i/](../runs/vowel-transfer-i-20261119-b/summary.json) | 336.56、2225.38、2901.12 | 336.43、2225.38、2901.14 |
| [/ɑ/](../runs/vowel-transfer-alpha-20261119-b/summary.json) | 730.81、1336.55、2541.22 | 730.82、1336.56、2541.21 |
| [/u/](../runs/vowel-transfer-u-20261119-b/summary.json) | 377.92、997.18、2237.52 | 378.03、997.25、2237.52 |
| [軟口蓋を開いた /i/](../runs/vowel-transfer-i-open-velum-20261119-b/summary.json) | 409.69、695.74、1317.35 | 404.72、605.09、1366.72 |

固定3母音の総放射の最初の3ピークは、整数Hzに丸めると較正表の値に一致した。音響上の目標値との差は、たとえば `/i/` の第2ピークが約−96.62 Hz、`/u/` の第3ピークが約−105.48 Hz。較正表は目標値と実測ピークの両方を記録している。[固定 /i/](../runs/vowel-transfer-i-20261119-b/summary.json)・[固定 /u/](../runs/vowel-transfer-u-20261119-b/summary.json)

軟口蓋を開いた `/i/` では、最大鼻端流量比は最大口端流量比の48.44%。総放射の695.74 Hzのピークでは、−3 dBを横切る両側の点が得られなかったため、帯域幅はCSVで空欄、要約で `null` にした。固定上流でも同じピークが欠測だった。[軟口蓋開放の測定](../runs/vowel-transfer-i-open-velum-20261119-b/summary.json)

4条件の計64項目が通過した。固定上流との差は、流量比の絶対値で各条件のピーク比 `7.41×10⁻¹⁴` 未満、放射レベルで `9.81×10⁻¹³ dB` 未満、ピーク周波数で `8.19×10⁻¹² Hz` 未満。独立計算との複素応答の最大差は各成分のピーク比 `4.96×10⁻¹³` 未満。研究ディレクトリと `/tmp` からの再実行で設定、CSV、要約48ファイルが一致し、既存9ケースでは63ファイルが直前の通過版と一致した。[測定環境・コマンド・ハッシュ](../runs/vowel-transfer-i-20261119-b/manifest.json)・[固定姿勢の回帰](../runs/fixed-airway-short-20261119-f/manifest.json)・[PCMの回帰](../runs/pcm-voiced-20261119-n/manifest.json)

```bash
python3 tools/measure_vowel_transfer.py vowel-transfer-i-local-1 vowel-transfer-i
python3 tools/measure_vowel_transfer.py vowel-transfer-i-open-velum-local-1 vowel-transfer-i-open-velum
```
