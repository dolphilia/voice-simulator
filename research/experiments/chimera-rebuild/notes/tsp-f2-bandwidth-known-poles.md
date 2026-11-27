# 既知の全極フィルタでのTSP方式のF2選択

[前回の確認用90窓](tsp-f2-bandwidth-held-out.md)では、帯域幅300 Hz未満の条件を加えたとき、録音 `FK61_01` の `again` でF2の中央値が2073 Hzから2913 Hzに移った。両方の近くにスペクトルの局所最大があった。今回は周波数に正解を置ける小さな全極フィルタを使い、帯域幅条件だけでF2の取り違えを起こせるか調べた。[事前登録](../cases/tsp-f2-bandwidth-known-poles.json)

## 固定上流の読解

- `compare tsp` を起動すると `tsp::run`、`measure_pair`、`measure`、`Sig::formants` の順に進む。通常はMFAの母音開始・終了時刻を秒で読み、48 kHz波形から作った12 kHz列に25 ms窓を置く。中心は母音の35・50・65%。標本位置への切り捨て後、その150標本前から300標本を採る。今回の波形は12 kHzで作り、標本化済みの列に入るところから同じ窓を使う。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[対応付け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と極の採用](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)
- LPCでは窓の先頭の前標本を0とし、係数0.97のプリエンファシス、Hamming窓、自己相関、40 Hzのラグ窓を順に適用する。Levinson–Durbin法が次数ごとに反射係数、予測多項式、残差を更新し、Durand–Kerner法が予測多項式の根を推定する。TSPの12次と14次を同じ波形に適用した。根の偏角と半径から周波数と帯域幅をHzで求め、150 Hz以上・帯域幅600 Hz以下の推定極を残す。[LPC係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)・[根の探索](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L54)・[推定器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)
- F1は1300 Hz未満・帯域幅500 Hz未満の最初の極、F2はF1＋200 Hzより高く3500 Hz未満の最初の極。両方が得られた窓の中央値を使う。今回の比較規則はF2の採用時だけ帯域幅300 Hz未満を要求する。固定上流のテストはTypeScriptの基準値で自己相関、係数、残差、極、包絡を照合し、別の比較試験では欠測を扱う。[F2の規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L538)・[LPCの基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[欠測の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1528)

## 対照波形と測定

設計極の周波数は620・2075・2915 Hz。F1の帯域幅100 Hz、F3の帯域幅155 Hzを固定し、F2だけ180・430 Hzの2条件に変えた。周波数 `f`・帯域幅 `B` から、共役極の半径 `r = exp(−πB/fs)` と偏角 `θ = 2πf/fs` を求める。各二次節は `y[n] = x[n] + 2r cos(θ)y[n−1] − r²y[n−2]` で、節ごとに直前2標本の出力を状態に持つ。3節を順に通し、初期状態を0、励振を96標本周期（125 Hz）・振幅0.015のインパルス列に揃えた。窓の開始は4050・5850・7650標本。窓中心のパルスに対する位相は3窓で異なる。[共役極、共鳴周波数、帯域幅の式](https://www.dsprelated.com/freebooks/filters/Two_Pole.html)

[研究CLI](../tools/measure_tsp_f2_known_poles.py)は、二次節の連結と6次の差分方程式、多項式から復元した極と設計値、極の因数積と多項式の周波数応答を照合する。設計のF2は2075 Hzの共役極、推定対象は有限長の励振波形、観測したピークは局所最大としてそれぞれ記録する。有限長の波形を固定RustのLPCと独立のToeplitz直接解法で比較し、包絡は複素多項式と直接DFTで照合する。300 Hz未満で選んだ結果は、設計極から120 Hz以内ならその共鳴に対応したと数える。採用極が離れたときは、推定極の段、固定の周波数順、追加した帯域幅条件のどこで最初に差が出たかを窓別に記録した。

## 実測

| 設計F2の帯域幅 | LPC次数 | 固定規則のF2中央値 | 300 Hz条件付きのF2中央値 | 設計極との対応 |
| ---: | ---: | ---: | ---: | --- |
| 180 Hz | 12 | 2098.08 Hz | 2098.08 Hz | 両方F2 |
| 180 Hz | 14 | 2083.13 Hz | 2083.13 Hz | 両方F2 |
| 430 Hz | 12 | 2206.75 Hz | 2916.76 Hz | 固定は設計F2から+131.75 Hz、条件付きはF3 |
| 430 Hz | 14 | 2089.76 Hz | 2910.10 Hz | 固定はF2、条件付きはF3 |

430 Hz・14次では、設計F2の近くに帯域幅309–311 Hzの推定極が3窓とも得られた。固定規則はこの極を採り、300 Hz未満の条件を加えた時点で初めて選択が変わった。移動先は設計F3の2915 Hzから約5 Hz。430 Hz・12次では、固定規則が採る低い極が先に約132 Hzずれた。50%窓の多項式を別に解くと、そこに2205.57 Hz・帯域幅546.12 Hzの極があった。LPC包絡の近傍のピークは2175 Hzで、平滑化ピリオドグラムでは2110 Hzだった。14次の同じ波形・標本のLPC包絡は2100 Hzにピークがある。12次で設計F2との差が出た段は極の推定、14次で候補規則が真のF2を飛ばした段は帯域幅による選択だった。[12窓の要約](../runs/tsp-f2-bandwidth-known-poles-20261122-repeat/summary.json)・[固定Rustの係数・極](../runs/tsp-f2-bandwidth-known-poles-20261122-repeat/artifacts/upstream-envelopes.json)

設計フィルタの周波数応答は両条件とも2075 Hzと2905 Hzに局所最大を持った。後者は設計F3の偏角2915 Hzと10 Hzずれており、極の周波数と応答の局所最大を個別に扱う必要がある。全12窓で値が出た。狭いF2を両規則で保持する予測と、幅広いF2を300 Hz条件が飛ばす予測は成立した。幅広いF2でも固定規則が両次数で設計F2から120 Hz以内に収まる予測は、12次で反証された。TSP録音のF2ラベルは未確定のため、この結果は既知の対照波形での取り違えの再現として扱う。[設計・LPC・FFTの数値](../runs/tsp-f2-bandwidth-known-poles-20261122-repeat/artifacts/spectra.json.gz)

## 再現

研究ワークスペースで実行する。保存する波形は各1秒のfloat64標本列で、サンプルレートはケース定義にある。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_known_poles.py tsp-f2-bandwidth-known-poles-new
```

macOS 15.6.1 arm64、Python 3.14.4、rustc 1.94.1、NumPy 2.4.4、SciPy 1.17.1で実行した。二次節と差分方程式の最大標本差は `4.44×10⁻¹⁶` 未満、設計極を再計算したときの最大差は `1.10×10⁻¹¹ Hz` 未満、解析応答と多項式評価の差は `2.60×10⁻¹³ dB` 未満。固定RustのLPC極と独立計算の最大差は `1.97×10⁻¹⁰ Hz` 未満だった。診断包絡はLPCで `1.67×10⁻¹³ dB` 未満、FFTと直接DFTで `1.70×10⁻¹² dB` 未満。

初回と `/private/tmp` からの再実行で各5判定と固定上流の基準試験1件が通過した。要約・2波形・包絡データ・固定RustのJSONがバイト一致し、保存データから局所最大を別に計算した。2実行の44入力・14出力をサイズとSHA-256で照合し、1,521,952バイトの採取物をRTL9210B-CGに保存した。[初回](../runs/tsp-f2-bandwidth-known-poles-20261122-a/manifest.json)・[再実行](../runs/tsp-f2-bandwidth-known-poles-20261122-repeat/manifest.json)
