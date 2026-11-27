# MFAのケプストラム正規化と tall の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。 `FK61_02` の対照と旧舌先の先頭50 msを移したPCM16で、対象周辺のPCMが同じまま /ɔ/–/l/ が1.650秒と1.680秒に分かれた。今回はそれぞれに対照と交換条件の統計を適用する4条件を比較する。MFCCの平均を取る段で冒頭の影響が遠方へ届くか、その統計だけで境界を動かせるかを別々に確かめる。[PCM16の比較](tsp-tall-mfa-preroll.md)・[事前登録](../cases/tsp-tall-mfa-cmvn.json)

| 読んだファイルと処理 | 入力から観測まで |
| --- | --- |
| 上流 `crates/chimera-cli/src/compare/tsp.rs` の `align_synth`、`over_noise_floor`、`tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 雑音付き48 kHz PCM16を1話者1発話でMFAへ渡す。固定シードの雑音床は上流テストで反復一致する。今回は保存済みPCMと辞書を再利用する。上流の `tools/tsp/mfa.yaml` ではディザと話者適応を停止している。 |
| MFA 3.4.3の `command_line/align.py` の `align_corpus_cli` と `alignment/pretrained.py` の `align` | 辞書・音響モデル・設定から `PretrainedAligner` を構築し、特徴量と探索グラフを生成して音素区間をJSONで出力する。 |
| MFAの `corpus/features.py` の `MfccFunction` とKalpyの `feat/mfcc.py` の `compute_mfccs_for_export` | モデルの設定は16 kHz、25 ms窓、10 ms間隔、13係数。入力音声を読み、MFCCを計算して発話ごとに圧縮行列として保存する。別途、非圧縮MFCCを同じ計算器で採る。 |
| MFAの `corpus/acoustic_corpus.py` の `calc_cmvn` とKalpyの `feat/cmvn.py` の `CmvnComputer` | 各話者の発話の特徴量を読み戻し、各列の和、二乗和、フレーム数を集める。話者ごとの統計を `cmvn.ark` に収め、SCPが読み出し位置を指定する。今回の話者には1発話ずつしかない。 |
| MFAの `corpus/features.py` の `FinalFeatureFunction` とKalpyの `feat/data.py` の `FeatureArchive` | SCPの参照先の統計から各列の平均を引く。分散の正規化は既定で無効。正規化後のMFCCも圧縮して保存する。後段の `alignment/multiprocessing.py` `AlignFunction` は発話の特徴量アーカイブと音素グラフをGMM-HMM整列器へ渡す。 |

正規化入力の特徴係数を `x[t,j]`、供給元のフレーム数を `N`、列和を `S[j]` とすると、この条件の正規化は `y[t,j] = x[t,j] − S[j]/N`。計測用の別プロセスで、元のMFAが統計を集計した直後に対象話者の統計参照だけを供給元へ変える。PCM・発音・モデル・ディザと話者適応の設定を固定する。独立計算では、圧縮MFCCを読み戻した行列から和・二乗和・平均除去を再計算する。観測区間は48 kHz PCMの1.50〜1.75秒、特徴量番号145〜175付近と全発話の整列。

非圧縮MFCCでは対象周辺の係数が一致し、各発話の平均を使うと局所の差が広がると予測する。交換音声に対照の統計を使えば1.650秒へ戻り、対照に交換条件の統計を使えば1.680秒へ動くと予測する。発話全体で圧縮パラメータを決める段と整列経路にも差を伝える可能性があるため、圧縮前、読み戻し後、正規化後を区別して保存する。

## 実測

元の2条件の語9区間・音素30区間は前回と一致した。統計の供給元だけを変えた条件で、WAV、非圧縮MFCC、圧縮MFCCの読み戻しは同じ音声の対照と全件一致した。実際にジョブのSCPから読まれたCMVN行列は供給元と一致した。

| 整列用PCM16 | CMVN統計の供給元 | `tall` の /ɔ/ 終端 |
| --- | --- | ---: |
| 対照 | 対照 | 1.650秒 |
| 冒頭50 msを交換 | 冒頭50 msを交換 | 1.680秒 |
| 冒頭50 msを交換 | 対照 | 1.680秒 |
| 対照 | 冒頭50 msを交換 | 1.680秒 |

交換側の統計だけで境界は30 ms動いた。対照の統計を使えば交換音声の境界が1.650秒へ戻るという予測は外れた。最後の3条件は交換条件の語9区間・音素30区間を再現した。[4条件の要約](../runs/tsp-tall-mfa-cmvn-20261123-repeat/summary.json)

非圧縮MFCCの差は先頭6フレームに収まり、後方の145〜175フレームは一致した。MFAが保存した圧縮MFCCを読み戻すと全302フレームで差が現れ、同じ局所区間の係数差は最大0.52988になった。各発話の統計を使うと正規化後の差は最大0.62403、同じ対照統計を使うと0.52988だった。対照PCMへ交換側の統計だけを使うと、局所の差は正規化直後に最大0.09982。これらはMFCCの係数差である。次はMFAの最初のMFCC書き出しをfloat32の非圧縮アーカイブへ変え、正規化前に発話全体へ広がった差と境界への寄与を同時に測る。[採取した特徴量と統計](../runs/tsp-tall-mfa-cmvn-20261123-repeat/artifacts/features.npz)

## 初回の判定と再実行

第1版の独立計算は読み戻したMFCCをfloat64へ変換してから二乗した。列和とフレーム数は一致したが、二乗和に最大0.00350503の差があり、統計の判定を不合格にした。元の行列をfloat32で二乗しfloat64で積算すると、読み出した統計のフレーム数、列和、二乗和は全条件で一致した。第2版では二乗の精度だけを登録し、許容差と予測を維持した。正規化直後の値は独立の平均除去と最大3.52×10⁻⁶差だった。第1版と第2版で `features.npz` のSHA-256と境界は一致した。[初回の不合格](../runs/tsp-tall-mfa-cmvn-20261123-a/manifest.json)・[修正後](../runs/tsp-tall-mfa-cmvn-20261123-recheck/manifest.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4、MFA 3.4.3のPython 3.11。MFAとKalpyの参照ソースのSHA-256をケースに固定し、既存のMFAプロセス内で統計の参照を操作した。研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_mfa_cmvn.py tsp-tall-mfa-cmvn-new
```

第2版は研究ワークスペースと `/tmp` から各5判定・上流6試験に通過し、20出力のうち計時を含む2ログを除いた18出力がバイト一致した。既存のMFA入口を使った冒頭交換の回帰でも、22出力のうち実行ログ以外の21出力が一致した。入力WAV、4条件の整列JSON、各段の特徴行列はRTL9210B-CG上にある。[別ディレクトリでの再実行](../runs/tsp-tall-mfa-cmvn-20261123-repeat/manifest.json)・[冒頭交換の回帰](../runs/tsp-tall-mfa-preroll-20261123-cmvn-regression/manifest.json)
