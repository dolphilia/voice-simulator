# 研究版の確認女性120発話を固定上流と照合する

## 読解と比較方法

FKとFLの全120発話、固定録音と音素注釈、女性と男女の学習参照、78介入を第60版から引き継ぐ。研究版の入力は既存の女性用一致ケースを使い、本文と録音IDを発話ごとに設定する。英語、体型、休止舌先、出力ゲインと音源の揺らぎを同じ条件に揃える。 [事前登録](../cases/tsp-f2-full-held-candidate.json)・[固定上流の全120発話](tsp-f2-full-held-women.md)

| 処理 | 観測点 |
| --- | --- |
| 上流 `render::say`、研究版 `vocal-cli inspect` と `render-pcm` | 英語本文から計画するIPA、強勢、開始終了フレーム、出力長を比べる。通常のCLIで出力した48 kHzのfloat32 PCMについて、最初の差、許容差1e-6を超える位置、最大差を測る。 |
| 上流 `align_synth`、`match_phones` | 研究版のPCMを、上流で使うG2P辞書・整列用雑音・量子化・MFA設定に通す。元録音との対応を録音音素番号で突き合わせ、録音境界と合成境界を読み分ける。 |
| 上流 `measure_pair`、`Sig::formants` | 整列用の雑音を付ける前の合成PCMで、強勢付き `/ɛ/` のF2を測る。音素の35・50・65%の窓のLPCをPythonでも解き、採択の有無と中央値を確認する。再計算用に使った窓を残す。 |
| 上流 `values`、`over_sets`、`costs` | 文集合別の有限F2のHz中央値を `log2` にして集合ごとに集約する。同じ女性中心と評価幅で費用を計算し、第60版で0だった介入が正に変わるかを数える。 |

予定区間は全発話で一致し、PCMには許容差を超える例があると予測した。PCMの差から、少なくとも一つの対応境界かF2の値が変わり、上端まで約0.140 Hzだった女性参照の費用0判定が変わると予測した。最初の差は発話計画・PCM・整列・F2の順に確認する。 [通常CLIの比較入口](../tools/measure_tsp_f2_full_held_candidate.py)・[固定上流の発話・レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs)・[固定上流の計測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)

## 実測

研究版の通常入口で120発話を描画した。IPA、強勢、予定フレーム、PCMの長さは120発話すべてで固定上流と一致した。値が異なるPCM標本は全発話にあり、最も早い差は17発話のフレーム1989（48 kHzで約41.44 ms）に現れた。最大絶対差は `FK65_05` の `1.49e-8`。許容差 `1e-6` を超えた発話は0件だった。 [発話計画・PCM差・音素対応](../runs/tsp-f2-full-held-candidate-20261123-a/artifacts/collection/native.json)

| 観測点 | 結果 |
| --- | --- |
| 音素の対応と秒区間 | 全120発話で一致 |
| 今回の強勢付き `/ɛ/` の合成F2 | FK34件・FL36件、値と採否がすべて一致 |
| 研究版WAVからの独立LPC | 70件。最大差 `3.77e-11 Hz`、採択判定の差0件 |
| 上流と研究版の `over_sets` 集約値 | 両方2,048.24 Hz相当 |
| 女性参照・男女参照の費用0 | 両実装とも、それぞれ78 / 78条件 |

PCM差が許容差を超える、整列または対象F2に差が出る、女性参照の費用0判定が変わるという3つの予測は外れた。他の母音の合成F2には6値で差があり、最大は `FL70_07` の `/ɪ/` の `1.01e-8 Hz` だった。費用0の上端まで約0.140 Hzの条件も、強勢付き `/ɛ/` の値が一致したため、費用は同じだった。 [計画・整列・F2の比較](../runs/tsp-f2-full-held-candidate-20261123-a/summary.json)・[固定参照の費用](../runs/tsp-f2-full-held-candidate-20261123-a/artifacts/native.json)

過去に通常CLIで計測した共通のFKの6発話では、保存した両実装のPCMから差が最初に出る位置と最大値を再計算し、今回の測定値に一致した。最も早いPCM差は予定した先頭音素より前だった。次はそのうち `FK61_01` を使い、放射、間引き、DC除去、float32への変換から、差が最初に現れる段を一発話で絞る。 [過去のPCM](../runs/tsp-held-out-matched-speech-20261123-repeat/artifacts/matched-pcm.npz)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、MFA 3.4.3。試験のビルド、WAVの一時出力、MFAの作業をRTL9210B-CGに置いた。通常CLIへの固定入力、WAVハッシュ、音素対応、独立計算用のLPC窓、上流の集約結果と実行ログを保存した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=8053063680 \
  ../../.venv/bin/python tools/measure_tsp_f2_full_held_candidate.py \
  tsp-f2-full-held-candidate-new
```

研究ワークスペースと `/tmp` からの再実行で、各3判定と上流6試験を通過した。研究版の入力、レンダーのハッシュ、音素対応、LPC窓と集約結果を含む12出力がバイト一致した。整列中の出力を先に読んだ確認は空ファイルで止まり、整列完了後に同じ実行の出力を再読した。 [再実行](../runs/tsp-f2-full-held-candidate-20261123-repeat/manifest.json)
