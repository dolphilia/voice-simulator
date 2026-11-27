# MFAの最終MFCCアーカイブと tall の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。 `FK61_02` で最初のアーカイブをfloat32にし、対照CMVN統計を共用すると、正規化直後の差は先頭6フレームに収まった。最終の圧縮行列を読み戻すと全302フレームに差があり、`tall` の /ɔ/–/l/ は対照と冒頭交換がともに1.680秒だった。今回は4条件のPCMと統計の供給元を固定し、最終の行列保存だけをfloat32へ替える。[最初の保存形式の比較](tsp-tall-mfcc-input-compression.md)・[事前登録](../cases/tsp-tall-mfcc-final-compression.json)

| 読んだ入口と関数 | 入力から観測まで |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `align_synth`、`over_noise_floor` と `tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 固定シードの雑音付き48 kHz PCM16をMFAの通常入口へ渡す。今回の入力は既に作られたWAVを用い、発音辞書と本文を前回の記録へハッシュで照合する。 |
| MFA 3.4.3の `corpus/features.py` の `MfccFunction._run` と `FinalFeatureFunction._run` | 16 kHz・25 ms窓・10 ms間隔の13列MFCCを作る。両側で最初の保存はfloat32。最終段は、SCPを通じて特徴量と話者統計を読み、平均除去を適用する。今回のモデルはピッチを結合せず、最終段は行列の形式を選んで書く。元の `feats.scp` を最終アーカイブへのSCPで置き換える。 |
| MFAの `db.py` の `Job.construct_feature_archive`、`alignment/multiprocessing.py` の `AlignFunction._run` とKalpy `feat/data.py` の `FeatureArchive` | 置き換え後のSCPから最終行列を読み、モデルに応じてデルタまたは時間連結・LDAを適用する。GMM-HMMの音響尤度と発音グラフから発話全体を整列する。局所係数が揃う条件でも、発話全体の探索経路に差が残る可能性がある。 |

入力を `x[t,j]`、供給する列和を `S[j]`、件数を `N` として `y[t,j] = x[t,j] − S[j]/N` を独立計算する。両側で入力行列と統計、正規化後の行列を比較する。最終保存がfloat32の側は読み戻した行列を `y` の実測値に直接照合する。実行中のSCPが指すバイナリ型を読み、前回の `FM → CM` と今回の `FM → FM` を全4発話で確認する。

同じ対照統計の2発話では、最終読み戻しでも差が先頭6フレームに収まり、145〜175番フレームの係数差は0になると予測する。境界も一致し、前回の両側共通の1.680秒から旧対照の1.650秒に戻る、という予測を登録した。絶対時刻と2発話間の一致は別に判定する。

## 実測

全4発話で最初と最終のark種別がそれぞれ `FM → CM`、`FM → FM` だった。最終圧縮側は前回の行列と区間を再現した。両側の入力MFCC、統計、平均除去直後の行列が一致した。最終非圧縮側では平均除去直後の行列と最終読み戻しも一致した。独立計算で件数・列和・二乗和はMFAと完全一致し、平均除去の最大差は3.48×10⁻⁶だった。

| 同じ対照統計を共用した2音声の比較 | `FM → CM` | `FM → FM` |
| --- | ---: | ---: |
| 最終読み戻しで差のあるフレーム | 302 | 6（0〜5番） |
| 145〜175番の最大係数差 | 0.53006 | 0 |
| 対照PCMの /ɔ/ 終端 | 1.680秒 | 1.680秒 |
| 冒頭交換PCMの /ɔ/ 終端 | 1.680秒 | 1.680秒 |

同じ対照統計で局所係数の差がなくなり、両条件の境界は揃った。1.650秒へ戻るという予測は外れた。全4条件で保存形式を変えても語9区間・音素30区間が完全に一致した。対照PCMだけを縦に比較すると、保存形式による最終MFCCの変化は全302フレームにあり、対象周辺の最大係数差は0.32283だった。観測した係数差の範囲では、最終圧縮を変える介入で境界は動かなかった。[8条件の要約](../runs/tsp-tall-mfcc-final-compression-20261123-repeat/summary.json)・[最終非圧縮の特徴量](../runs/tsp-tall-mfcc-final-compression-20261123-repeat/artifacts/float32_both/features.npz)

## 次の切り分け

次の対照は同じPCMの最初の保存形式だけを変えた第42版の2条件で、`tall` が1.650秒と1.680秒に分かれている。MFAの `AlignFunction` は `kalpy/gmm/align.py` の `GmmAligner.export_alignments` に特徴量アーカイブと発音グラフを渡す。 `GmmAligner.align_utterance` から遷移ID列とフレーム別の対数尤度を得られる。この入口に到達した特徴行列と経路を両条件で採り、1.650秒と1.680秒の経路を選ぶ得点差を比較する。[第42版の条件](tsp-tall-mfcc-input-compression.md#実測)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4、MFA 3.4.3。固定MFAソースと音響モデルを前回の計測に照合した。研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_mfcc_final_compression.py tsp-tall-mfcc-final-compression-new
```

研究ワークスペースと `/tmp` から各6判定・上流6試験に通過した。各29出力のうち計時を含む2ログを除く27件がバイト一致した。共用の観測器を使う第42版の回帰でも29出力のうち27件が一致した。区間JSON、特徴行列、アーカイブ種別の照合結果はRTL9210B-CG上にある。[初回](../runs/tsp-tall-mfcc-final-compression-20261123-a/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-tall-mfcc-final-compression-20261123-repeat/manifest.json)・[最初の保存形式の回帰](../runs/tsp-tall-mfcc-input-compression-20261123-final-regression/manifest.json)
