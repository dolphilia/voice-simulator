# 整列用PCMの冒頭50 msと tall の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。女性発話 `FK61_02` の旧ゲイン・音源3変動0の比較で、旧舌先への変更は整列用PCM16の4,679標本を変えた。差のある範囲は標本16〜12,071（最大約251 ms）。 `tall` の前後で波形が一致していても、MFAの /ɔ/–/l/ 境界は1.650秒から1.680秒へ動いた。[旧舌先の計測](tsp-tall-initial-tip-mfa.md)・[事前登録](../cases/tsp-tall-mfa-preroll.json)

| 読んだファイルと関数 | 入力から観測まで |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `over_noise_floor` と `align_synth`、同 `wav.rs` の `write` | 960標本ごとの平均二乗の95パーセンタイルを基に、固定xorshift32の雑音を加える。雑音と波形の和をfloat32化した後、±1に制限して32,767倍し、丸めて符号付き16 bitにする。同じ発話を1話者1ファイルとして保存し、辞書・文字列・音響モデルをMFAに渡す。出力JSONの始端・終端は秒単位で、無音ラベルを除く。 |
| 固定上流の `tools/tsp/mfa.yaml` と `compare::tsp::tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 特徴量のディザと話者適応を切る。上流試験は固定雑音の末尾半分における目標音量との誤差と再実行一致を検査する。今回の入力は、前回のMFAで使った量子化済みWAV。 |
| 固定上流 `compare/tsp.rs` の `Sig::new` と `crates/chimera/src/analysis/lpc.rs` の `estimate_formants`、上流試験 `crates/chimera/tests/golden_analysis.rs` | 無加工の48 kHz波形を12 kHzに間引いた25 ms窓から自己相関を求め、Levinson–DurbinでLPC係数を解き、極から周波数と帯域幅を推定する。公開極と採択値は固定上流と独立Pythonで照合する。 |
| 研究版 `tools/measure_tsp_phone_boundaries.py` の `alignment_wav`、`mfa_run`、`tiers` | 通常の前処理では発話全体の電力から雑音を計算する。今回はその工程の出力を操作する。既存のMFA呼び出しと境界パーサーを使い、前処理の再計算を避ける。 |

対照を `C`、旧舌先条件を `O` とし、48 kHzの標本番号 `k = 2400` で分ける。前半・後半がどちらの波形かだけを変え、`C[:k] + O[k:]` と `O[:k] + C[k:]` を元の2条件と並べて再整列する。ここで `+` はサンプル列の連結を表す。量子化済みWAVのサンプルをPython標準のWAV読み出しとバイト連結で別途照合する。全条件のLPCには共通の無加工波形を使い、整列の入力とそこから得た時刻だけを変える。

旧舌先によるPCM差の最大値が冒頭50 ms内にあるため、先頭2,400標本だけを替えた場合に1.680秒へ動くと予測した。補集合の交換を行う条件は、冒頭50 msの変更がこの分割で必要かを調べる対照である。F2では固定窓の値を共通の基準とし、各MFA区間が選ぶ窓の位置と値を比較する。どちらの半区間でも旧位置へ動く場合や、両方を組み合わせたときだけ動く場合も区別して記録する。

## 実測

同じMFA 3.4.3、音響モデル、発音辞書、文字列、設定で、元の2条件の語9区間と音素30区間を再現した。全4条件で `tall` 周辺の1.50〜1.75秒にあるPCM16の12,000標本が一致した。

| 旧舌先から使ったPCM16 | 対照から変わった標本数 | `tall` の /ɔ/ 終端 | 90%窓開始（12 kHz） | 90%窓のF2 |
| --- | ---: | ---: | ---: | ---: |
| なし | 0 | 1.650秒 | 19,505 | 1,270.70 Hz |
| 冒頭50 msのみ | 2,367 | 1.680秒 | 19,829 | 1,528.49 Hz |
| 50 ms以後のみ | 2,312 | 1.680秒 | 19,829 | 1,528.49 Hz |
| 全体 | 4,679 | 1.680秒 | 19,829 | 1,528.49 Hz |

2つの交換条件は、いずれも旧舌先の全語・音素区間を再現した。50 ms以後だけを交換すると対照の1.650秒に留まるという予測は外れた。旧波形に由来する変更は、どちらの区間でもこの切り分けで境界を動かすのに十分だった。全条件で同じ無加工波形を使ったLPCの20窓は固定上流と独立計算で一致し、F1・F2の最大差は4.71×10⁻¹¹ Hz。最大のF2変化は、窓が324標本遅れた90%点の+257.79 Hzだった。[4条件の要約](../runs/tsp-tall-mfa-preroll-20261123-repeat/summary.json)・[窓別測定](../runs/tsp-tall-mfa-preroll-20261123-repeat/artifacts/window-comparisons.json)

## 次の切り分け

使用した `english_us_arpa` の `meta.json` は16 kHz・25 ms窓・10 ms間隔のMFCCと `uses_cmvn: true` を指定しており、今回のログにも `Calculating CMVN` がある。インストール済みMFAの `corpus/acoustic_corpus.py` の `calc_cmvn` は話者に属する発話の統計を集め、Kalpyの `feat/data.py` の `FeatureArchive` はその統計を特徴量に適用する。1発話1話者なので、冒頭の特徴量が変わると、全発話の統計を通じて後半の特徴量にも差が届く可能性がある。次は同じ2テープで正規化前後の特徴量と対照の正規化統計を共用した条件を比較する。今回の結果では、正規化とGMM-HMMの整列経路それぞれの寄与は分離していない。[MFAログ](../runs/tsp-tall-mfa-preroll-20261123-repeat/artifacts/cargo.log)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_mfa_preroll.py tsp-tall-mfa-preroll-new
```

研究ワークスペースと `/tmp` から各7判定と上流7試験を通過した。22出力のうち実行時間を含む2ログを除いた20件はバイト一致した。4条件のWAV、語・音素区間、LPC窓と予測の採否をRTL9210B-CGに保存した。[初回](../runs/tsp-tall-mfa-preroll-20261123-a/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-tall-mfa-preroll-20261123-repeat/manifest.json)
