# MFAの最初のMFCCアーカイブと tall の境界

## 読解と事前登録

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。 `FK61_02` の冒頭50 msだけを取り替えたとき、非圧縮MFCCの差は先頭6フレームに収まった。MFAが最初の圧縮MFCCを読み戻した時点では全302フレームに差があり、対照のCMVN統計を共用しても古い1.680秒の境界が残った。今回はPCM16とCMVN統計の供給関係を前回の4条件に固定し、最初のMFCCアーカイブの保存形式だけを変える。[正規化の比較](tsp-tall-mfa-cmvn.md)・[事前登録](../cases/tsp-tall-mfcc-input-compression.json)

| 読んだファイルと処理 | 入力から観測まで |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `align_synth`、`over_noise_floor` と `tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 48 kHz・PCM16と辞書をMFAに渡し、JSONから秒単位の境界を読む。雑音床は固定シードで前処理し、今回は前回の量子化済みWAVと辞書をハッシュで固定する。 |
| インストール済みMFA 3.4.3 `corpus/features.py` の `MfccFunction._run` とKalpy `feat/mfcc.py` の `compute_mfccs_for_export` | 16 kHz・25 ms窓、10 ms間隔で得た13列のMFCCを、通常は `CompressedMatrix` にして `CompressedMatrixWriter` で書き出す。実験ではこの関数が動く間だけ `compress=False` と `BaseFloatMatrixWriter` を組み合わせる。MFAはSCPにアーカイブ内のオフセットを出力する。 |
| MFA `corpus/acoustic_corpus.py` の `calc_cmvn` と `corpus/features.py` の `FinalFeatureFunction._run` | 最初のアーカイブを読み、前回の供給関係に従う話者統計を参照し、`y[t,j] = x[t,j] − S[j]/N` を計算する。ここで `S[j]` は列和、`N` は供給元のフレーム数。正規化後はMFAの通常の圧縮保存を使う。 |
| MFA `alignment/multiprocessing.py` の `AlignFunction` と `db.py` の `Job.construct_feature_archive` | 後段のアーカイブへ時系列変換を適用し、GMM-HMMと発音グラフで音素区間を求める。今回の観測点はこの処理の入力アーカイブまでと最終境界とする。 |

アーカイブの種別はSCPが示す位置から読み、4発話すべてについて `CM`（圧縮行列）と `FM`（float32行列）を照合する。比較側で変更するのは最初の書き出しだけで、2回目の圧縮は両側に残す。圧縮側の特徴量と全区間を前回に照合し、比較側の最初のアーカイブを保存前のMFCCと全要素で照合する。

最初をfloat32で保存すると、差があるフレームは正規化前に6件へ戻ると予測する。対照の平均を共用する場合、145〜175番フレームの正規化直後の差は0になる。 `tall` の境界も同じ保存形式の対照へ戻ると予測し、その前に最終圧縮で局所差が再発するかを記録する。境界の採否と、介入どおりに保存形式を制御できたかの判定は別に保存する。

## 実測

圧縮側では全4発話で `CM → CM`、最初を非圧縮にした側では `FM → CM` を実ファイルのヘッダーから確認した。圧縮側の特徴行列と全音素・語区間は前回と一致した。非圧縮側では最初のアーカイブを読み戻した行列が、元の非圧縮MFCCと全要素で一致した。PCM、転記、辞書は両側で同じファイルを用いた。

| PCM・CMVN統計の組み合わせ | 圧縮で開始 | float32で開始 |
| --- | ---: | ---: |
| 対照PCM・対照統計 | 1.650秒 | 1.680秒 |
| 冒頭交換PCM・交換側統計 | 1.680秒 | 1.680秒 |
| 冒頭交換PCM・対照統計 | 1.680秒 | 1.680秒 |
| 対照PCM・交換側統計 | 1.680秒 | 1.680秒 |

非圧縮側の4条件で語9区間と音素30区間が共通になった。圧縮側の交換条件と同じ区間である。対照統計を共用した場合に同じ保存形式の対照と境界が揃う、という事前判定は通った。揃った理由は、最初の圧縮を外すだけで対照の境界が1.680秒へ動いたことにある。冒頭交換PCMの終端はどちらの保存形式でも1.680秒だった。[各条件と事前判定](../runs/tsp-tall-mfcc-input-compression-20261123-repeat/summary.json)

対照の統計を共用したとき、最初をfloat32にすると正規化前と正規化直後の差はともに先頭6フレームに収まり、145〜175番フレームの係数は完全一致した。最終の圧縮アーカイブを読み戻すと全302フレームへ差が広がり、同じ局所区間で最大0.53006の係数差が現れた。各発話の統計を使用した場合は、正規化直後にも局所差0.10052が残った。次は最初の保存をfloat32に固定し、後段の保存だけをfloat32へ替えて、局所差と境界を照合する。[非圧縮開始時の特徴量](../runs/tsp-tall-mfcc-input-compression-20261123-repeat/artifacts/float32/features.npz)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4、MFA 3.4.3。固定MFAソースのハッシュ、モデル、設定を前回のケースに照合した。研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_mfcc_input_compression.py tsp-tall-mfcc-input-compression-new
```

研究ワークスペースと `/tmp` から各5判定・上流6試験に通過した。29出力のうち計時を含む実行ログを除いた28件がバイト一致した。独立計算では両形式ともCMVNの列和・二乗和・件数が全要素で一致し、平均除去の最大差は圧縮側3.52×10⁻⁶、非圧縮側3.48×10⁻⁶だった。区間JSON、特徴行列、ヘッダー照合結果をRTL9210B-CGに保存した。[初回](../runs/tsp-tall-mfcc-input-compression-20261123-a/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-tall-mfcc-input-compression-20261123-repeat/manifest.json)

共用の観測器を変更したため、第41版のCMVN統計交換を元の入口で再実行した。20出力のうち計時ログ2件を除いた18件がバイト一致した。[CMVNの回帰](../runs/tsp-tall-mfa-cmvn-20261123-mfcc-regression/manifest.json)
