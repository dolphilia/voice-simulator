# 設定を揃えたPCMでTSPの強勢母音を再計測する

確認用12発話で、音源、初期舌先、体型別ゲインを固定上流に揃えると、全PCMの最大差が1.86×10⁻⁹になった。既存TSP評価の4発話・12母音を同じ録音、窓、LPC設定で再計測する。両版それぞれに保存されたMFA境界を使う比較に加え、研究版PCMを固定上流と同じ窓へ入れて、PCMと窓位置の影響を調べる。保存済みの計画では、`FK61_01` の語尾、`MK61_01` の `plea` と語尾の計15窓で、合成間の開始標本が異なる。[事前登録](../cases/tsp-matched-speech-formants.json)・[設定合わせのPCM比較](tsp-held-out-matched-speech.md)・[先行のF2候補](tsp-f2-candidate-report.md)

## 上流の読解

- `crates/chimera-cli/src/compare/tsp.rs` の `measure_pair` と `measure` は録音と合成で対応する音素区間を得て、母音ごとに `Sig::formants` を呼ぶ。入力は48 kHzの波形と秒の音素境界。 `Sig::new` と `decimate` は95タップのBlackman窓付きsincを中心揃えで適用し、5,400 Hzで低域を通して4標本に1標本を取り、12 kHzにする。25 msは300標本。区間の35・50・65%から窓を取り、今回の比較では従来の10・90%窓も記録する。
- `crates/chimera/src/analysis/lpc.rs` の `estimate_formants` は係数0.97のプリエンファシス、Hamming窓、自己相関、40 Hzのラグ窓の順で適用する。LPC次数は女性12、男性14。`levinson` が予測多項式を求め、`poly_roots` が複素根を反復計算する。上半平面の根を周波数・帯域幅（Hz）に変換し、150 Hz未満か帯域幅600 Hzを超える極を除く。周波数順でF1は1,300 Hz未満かつ帯域幅500 Hz未満の最初の極。F2はそのF1より200 Hz超上で3,500 Hz未満の最初の極を選ぶ。両方が見つかった35・50・65%窓の中央値を要約し、窓外や採択候補が揃わない場合は欠測を記録する。
- `tests/analysis.rs` は既知の共鳴でのLPC推定、`tests/golden_analysis.rs` は固定入力の分析結果、`compare::tsp::tests` は計測・音素対応・集計の条件を確認する。独立Python計算では自己相関の線形方程式を解いて多項式の根を求め、固定Rustの窓・公開極・中央値に照合する。ナイキスト付近の見かけの公開極は、従来の負の実根と帯域幅の1対1対応に従い、元の出力と分けて記録する。

初回の `tsp-matched-speech-formants-20261123-a` は、先行データのハッシュ照合に使う `sha256` のインポート漏れで計測前に終了した。数値結果と実行ディレクトリは生成されなかった。インポートを追加し、実行ID `tsp-matched-speech-formants-20261123-b` で同じ入力を照合する。

## 実測

設定を揃えた固定上流のPCMは保存済みWAVと全標本でビット一致した。実録音と固定上流の計測値も先行の保存結果と全件一致した。研究版には、保存した同じfloat32 PCMを渡し、旧研究版のMFA境界と旧固定上流のMFA境界を使う2条件を作った。録音、固定上流、研究版の2条件を含めた240窓と48中央値で固定Rustと独立Pythonを照合した。開いた上半平面の極の最大誤差は9.16×10⁻⁹ Hzで、ナイキスト軸上の8件は従来の規則で対応した。録音の1窓、波形外・無音の対照5窓が欠測で、合成の欠測は0件だった。

| 比較 | 開始標本が異なる窓 | F2差が0.05 Hzを超えた窓 | 最大F2差（Hz） | 欠測判定が変わった窓 |
| --- | ---: | ---: | ---: | ---: |
| 設定合わせ後の両版、固定上流の同じ窓 | 0 / 60 | 0 / 60 | 1.01×10⁻⁷ | 0 |
| 設定合わせ後の両版、それぞれの保存MFA境界 | 15 / 60 | 15 / 60 | 109.53 | 0 |
| 研究版の同一PCMで、共通窓と保存MFA境界を切り替え | 15 / 60 | 15 / 60 | 109.53 | 0 |
| 研究版の保存MFA境界を固定して、設定合わせ前後のPCMを比較 | 0 / 60 | 60 / 60 | 20.20 | 0 |

共通窓では公開極の周波数・帯域幅の最大差が5.90×10⁻⁷ Hz、候補順の差が0件、F1・F2の中央値の最大差が3.29×10⁻¹⁰ Hzだった。MFA窓だけの切り替えでは、最大差は `FK61_01` の `again` の /ɛ/ の90%窓。開始が216標本（18 ms）ずれ、F2が2,034.56 Hzから2,144.09 Hzへ動いた。候補順は2窓で変わり、欠測の増減はなかった。

`MK61_01` の `seems` の50%窓では両合成が2,228.15 Hz、実録音が993.37 Hzを採った。差は1,234.78 Hzで、録音には第2候補の2,323.81 Hzも残った。録音の正解F2は人の注釈を待つ。次は設定を揃えた両版から、既存のMFAノイズ添加・PCM16変換の条件で入力を作り直す。入力がビット一致するかを確認し、必要な場合は音素境界を再取得して15窓の差を照合する。[計測の要約](../runs/tsp-matched-speech-formants-20261123-repeat/summary.json)・[公開極と採択の明細](../runs/tsp-matched-speech-formants-20261123-repeat/artifacts/f2-candidates.json)

## 再実行

`research/experiments/chimera-rebuild` で別の実行IDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_matched_speech_formants.py tsp-matched-speech-formants-new
```

固定出力は `upstream-formants.json`、候補の順序と欠測は `f2-candidates.json`、条件ごとの窓・中央値比較は `window-comparisons.json` にある。環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。SciPyは一部WAVで非音声チャンクを読み飛ばす警告を出した。サンプルレート、型、有限性、固定上流とのPCM同一性を照合した。ビルドと計測成果にはRTL9210B-CGを使った。[修正後の初回](../runs/tsp-matched-speech-formants-20261123-b/manifest.json)・[再実行](../runs/tsp-matched-speech-formants-20261123-repeat/manifest.json)

実験ディレクトリと `/tmp` の両方から実行し、固定出力、候補の順序と欠測、窓・中央値比較、要約がバイト単位で一致した。両回とも計測7判定と固定上流7試験に通過した。[分析の試験ログ](../runs/tsp-matched-speech-formants-20261123-repeat/artifacts/upstream-golden-analysis.log)・[TSPの試験ログ](../runs/tsp-matched-speech-formants-20261123-repeat/artifacts/upstream-tsp-tests.log)
