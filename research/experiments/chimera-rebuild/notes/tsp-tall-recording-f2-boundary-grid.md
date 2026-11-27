# 実録音の tall で母音終端とF2の感度を測る

## 読解と事前登録

第47版の同じ合成PCMでは母音終端を30 ms動かした4条件で、中央3窓のF2中央値が23.98 Hz、90%窓が257.79 Hzの幅を示した。今回は保存済み録音 `FK61_02` の同じ語 `tall` に限定する。2回のMFAの語・音素区間は一致し、1.590秒から1.690秒が `AA1`、直後が `L`。開始とラベルを固定し、終端を1.670〜1.700秒の10 ms刻みで動かす。1.690秒を実測の整列時刻とし、他の3点は指定時刻とする。前回と同じく秒値はfloat32へ丸める。[事前条件](../cases/tsp-tall-recording-f2-boundary-grid.json)・[合成対照](tsp-tall-f2-boundary-grid.md#実測)

| 固定上流の読み直した入口 | 入力、更新と出力 |
| --- | --- |
| `crates/chimera-cli/src/compare/tsp.rs` の `measure_pair`、`match_phones`、`measure` と `crates/chimera/src/phonetics/english.rs` のARPABET変換 | `read_wav` は48 kHzの録音を読み、PCM16の整数を32768で割って倍精度波形へ変換する。 `match_phones` は編集距離を更新してIPA一致の添字のみ返す。今回の録音はAA1 → /ɑ/、前回の合成はAO1 → /ɔ/。今回の比較は録音内で完結し、上流の録音と合成の音素対応規則はそのまま使う。 |
| `tsp.rs` の `Sig::new`、`Sig::formants` と `crates/chimera/src/analysis/lpc.rs` の `estimate_formants` | 95タップの低域通過後に4:1で12 kHzに間引く。開始 `a` と終端 `b` に対し、位置 `q` の窓開始は `trunc((a + q(b−a)) × 12000) − 150`。300標本にプリエンファシス、Hamming窓、40 Hzラグ窓付き自己相関を適用し、LPC次数12で係数と根を求める。F1とF2が得られた中央3窓の周波数の中央値を取る。90%窓の採択と欠測も別途保存する。 |
| `crates/chimera/tests/golden_analysis.rs` の `analysis_matches_typescript`、`tsp.rs` の `a_missing_measurement_has_no_cost`、研究版 `tools/upstream_tsp_formant_probe.rs` | ゴールデン試験で係数と極を、比較試験で欠測を検証する。プローブは上流の中央値を直接呼び、追加で各窓の公開極を出す。PythonはToeplitz連立方程式と多項式の根で独立計算し、開始標本・候補極・採択・欠測の順に差を調べる。 |

録音でも90%窓の幅が中央中央値より大きく、100 Hz以上と予測する。中央中央値の幅は100 Hz未満を仮説とした。母音の長さが80〜110 msなので、90%窓の半幅12.5 msは中心から指定終端までの8〜11 msより長い。指定終端と元の整列終端の両方に対する窓のはみ出しを記録し、採択極の順位や欠測と合わせて読む。[基準の窓・許容差](../cases/tsp-stressed-vowel-formants-held-out.json)

## 初回の標本位置判定

初回は窓が毎回42・60・78・108標本移動するとしており、1.680秒から1.690秒の移動で60・78・108が61・79・109となったため不合格になった。たとえば90%窓の中心標本は、float32秒値から有理数で計算すると1.680秒で20,051.999473572、1.690秒で20,160.000658035だった。切り捨て後から150標本を引くと開始は19,901と20,010になる。第2版はこの丸めを含めた16点を登録し、判定し直した。初回と再実行の上流極と独立計算はバイト一致した。[第1版の条件](../runs/tsp-tall-recording-f2-boundary-grid-20261123-a/artifacts/source/research/experiments/chimera-rebuild/cases/tsp-tall-recording-f2-boundary-grid.json)・[第1版の判定](../runs/tsp-tall-recording-f2-boundary-grid-20261123-a/summary.json)

入力WAVには `LIST` と `afsp` の補助チャンクがあり、SciPyは未認識の非音声チャンクを飛ばす警告を1件出した。RIFFの各チャンク長を読み、Python標準のWAV読み出しで得たモノラルPCM16全135,977標本とSciPyの標本がバイト一致することを確認した。[入力WAVのマニフェスト](../runs/tsp-phone-boundaries-held-out-20261121-a/manifest.json)

## 実測

| 指定した母音終端（秒） | 中央3窓のF2中央値（Hz） | 90%窓のF2（Hz） | 90%窓が元のMFA終端を越えた長さ（ms） |
| ---: | ---: | ---: | ---: |
| 1.670 | 1,119.50 | 1,112.02 | 0 |
| 1.680 | 1,109.69 | 1,130.54 | 0 |
| 1.690 | 1,107.88 | 1,150.75 | 2.50 |
| 1.700 | 1,114.32 | 1,184.22 | 11.50 |

F2の変動幅は中央中央値で11.62 Hz、90%窓で72.21 Hz。90%窓の幅が大きいという予測は一致し、100 Hz以上という予測は外れた。元のMFA終端より前に収まる2窓間でも18.52 Hz動いた。全4条件で周波数順の2番目の極が90%窓のF2に選ばれ、欠測は0件だった。合成側の変動幅は中央23.98 Hz、90%窓257.79 Hzで、同じ語の録音と合成の両方で窓による感度の差を確認した。両者はそれぞれAA1とAO1の母音区間で、数値は各区間内での変動幅を示す。[4条件の結果](../runs/tsp-tall-recording-f2-boundary-grid-20261123-repeat/summary.json)・[公開極](../runs/tsp-tall-recording-f2-boundary-grid-20261123-repeat/artifacts/upstream-formants.json)

固定上流と独立計算は全16窓の開始・採択で一致した。採択F1・F2の最大差は1.34×10⁻¹⁰ Hz、公開極の周波数・帯域幅では4.82×10⁻⁹ Hz以内。次は人手注釈の既存資料に含まれる `FK61_01` の `again` で、候補極が複数ある中央窓の位置を少しずらし、周波数順の採択がどの範囲で安定するかを診断する。同じ資料IDに対する人手回答は既存の入口で受け付ける。[窓別照合](../runs/tsp-tall-recording-f2-boundary-grid-20261123-repeat/artifacts/window-comparisons.json)・[人手注釈の取込](tsp-f2-human-intake.md)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4。研究ワークスペースで次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_tall_recording_f2_boundary_grid.py tsp-tall-recording-f2-boundary-grid-new
```

研究ワークスペースと `/tmp` で実行した第2版は各5判定と上流7試験を通過し、要約・上流極・独立計算・ゴールデンログの4出力はバイト一致した。差のある2件は実行ログだった。[修正後の実行](../runs/tsp-tall-recording-f2-boundary-grid-20261123-resolved/manifest.json)・[再実行](../runs/tsp-tall-recording-f2-boundary-grid-20261123-repeat/manifest.json)

録音と合成で窓の照合処理を共用した。合成側の回帰では要約・上流極・独立計算が第47版とバイト一致し、差は3件の実行ログだった。[合成の回帰](../runs/tsp-tall-f2-boundary-grid-20261123-recording-regression-v2/manifest.json)
