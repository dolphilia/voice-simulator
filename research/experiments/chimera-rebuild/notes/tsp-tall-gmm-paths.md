# 同一PCMから得た2つのMFA境界を経路得点で照合する

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第42版の `FK61_02` は、同じ対照PCMで最初のMFCC保存が圧縮なら /ɔ/ の終端が1.650秒、float32なら1.680秒だった。双方とも最終保存は圧縮。今回は対照PCMの1発話を各形式で再実行し、GMM-HMMに実際に渡った行列と選択経路を採る。[最初の保存形式の比較](tsp-tall-mfcc-input-compression.md)・[事前登録](../cases/tsp-tall-gmm-paths.json)

| 読んだ入口と関数 | 入力から観測まで |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `align_synth`、`over_noise_floor`、`tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 固定シードの雑音付き48 kHz PCM16と本文・発音辞書を通常のMFAに渡す。保存済みの対照PCMを2条件に共用する。 |
| MFAの `db.py` の `Job.construct_feature_archive` と `alignment/multiprocessing.py` の `AlignFunction._run` | 最初と最終のアーカイブの後、デルタまたは時間連結・LDAを含むモデル用特徴行列と、発音を制約する探索FSTを作る。実行時の変換後の行列を観測する。 |
| Kalpyの `gmm/align.py` の `GmmAligner.export_alignments`、`align_utterances`、`align_utterance` | 発話ごとの特徴量、モデルとグラフを `gmm_align_compiled` に渡す。戻り値に1フレーム1件の遷移ID、語ID列、発話全体と各フレームの尤度が含まれる。実際に使われたモデルと引数を記録する。 |
| Kaldiの `gmm-align-compiled` と `AlignUtteranceWrapper` | 重み付きの遷移確率をグラフに加え、探索の経路費用としてグラフ費用と音響費用を足す。フレームの音響量と発話全体の得点を別に照合する。[Kaldiの遷移重み](https://kaldi-asr.org/doc/gmm-align-compiled_8cc.html)・[Kaldiの整列と得点](https://kaldi-asr.org/doc/decoder-wrappers_8cc_source.html) |

経路の各遷移IDをGMMのPDF番号へ対応づける。特徴行を `x` とし、対角GMMの各成分の項を `gconst + (mean × inv_var)·x − inv_var·(x²)/2` として、成分方向に対数和指数を計算する。重み付き得点は、フレーム別の音響対数尤度の和に音響スケールを掛け、経路のグラフ費用を引く。グラフ費用は遷移ID・語IDの固定列と重み付きFSTの合成から求める。独立再採点の対角が通常MFAの値と照合できたときに、2つの入力と2つの経路を交差採点する。

予測は10 ms刻みの165〜167番フレームで音素IDが異なり、各入力で通常MFAが選んだ経路の合計得点が高いこと。145〜175番フレームを `tall` 周辺として、局所の音響差と発話全体での得点差を比較する。

## 初回と修正

初回は通常MFAで両方の境界を再現した。交差採点中に、`FloatMatrix.from_numpy` をクラスから直接呼んだため `TypeError` で停止した。Kalpyのこの版では空のインスタンスに対する読み込みメソッドであり、インスタンスを作ってから行列を読み込むよう修正した。初回の特徴行列、遷移ID・語ID、探索FST、MFA出力と停止ログを保存した。[初回のマニフェスト](../runs/tsp-tall-gmm-paths-20261123-a/manifest.json)

## 実測

圧縮開始で1.650秒、float32開始で1.680秒の区間を再現した。対照PCM・辞書・本文と、探索FST・実効GMMモデル・デコーダ引数のハッシュまたは値が一致した。デコーダが読んだ行列は302行×40列で、全302フレームで係数差を観測した。最大係数差は全体で0.0546042、対象周辺で0.00837517。遷移IDが異なるのは164〜169番、PDFの違いは164〜168番、音素IDの違いは事前予測どおり165〜167番にあった。

| 入力の最初の保存 | 遅い経路の音響得点差（重み付き） | 遅い経路のグラフ得点差 | 遅い経路の合計得点差 |
| --- | ---: | ---: | ---: |
| 圧縮 | −0.01861533 | +0.01846320 | −0.00015213 |
| float32 | −0.01833304 | +0.01846320 | +0.00013016 |

各列は、1.680秒の経路から1.650秒の経路を引いた値。音響項はどちらの入力でも早い経路が上回り、グラフ項は遅い経路を支持した。対象周辺の音響項だけで全発話の音響差を再現した。PDFが同じ区間の音響項は2経路の差に寄与しない。同じグラフで音響項がわずかに変わると、2経路の再計算上の順位が反転した。[採点の要約](../runs/tsp-tall-gmm-paths-20261123-repeat/summary.json)・[フレーム別得点とID](../runs/tsp-tall-gmm-paths-20261123-repeat/artifacts/path-scores.npz)

Kalpyが返したフレーム尤度と合計値は、今回の環境ではともに音響スケールを適用する前の単位だった。フレーム尤度を再計算した差は最大7.63×10⁻⁶。独立した対角GMM式とKaldiの尤度差は最大1.03×10⁻⁵。重み付き合計値の照合差は圧縮側0.00015744、float32側0.00058640で、どちらも上表の経路間差より大きかった。通常MFAの選択と再採点の順位は一致した。小さな得点差で選択がどれだけ安定するかは、次の直接介入で確認する。

次は2経路でPDFが異なった164〜168番の5行だけを、もう一方の入力の特徴量へ入れ替える。残りの行だけを入れ替えた補集合も比較し、元のFSTと音響モデルを使って、境界を動かすのにどの範囲が十分か確かめる。再採点で比較した2経路以外が選ばれた場合も遷移ID列を保存する。

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4、MFA 3.4.3。実効モデルは作業用ディスクの一時領域で保存・再読込みし、永続成果にはモデルのSHA-256、実際のFST、特徴量、経路、フレーム別尤度と再採点を残した。研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_gmm_paths.py tsp-tall-gmm-paths-new
```

研究ワークスペースと `/tmp` から各7判定・上流6試験に通過した。26出力のうち計時を含む2ログを除いた24件がバイト一致した。初回停止の2つの `decoder.npz` も修正後とバイト一致した。成果はRTL9210B-CGに保存した。[修正後の実行](../runs/tsp-tall-gmm-paths-20261123-recheck/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-tall-gmm-paths-20261123-repeat/manifest.json)
