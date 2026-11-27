# GMM-HMMに入る5フレームを交換して tall の境界を測る

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第44版の `FK61_02` は同一PCM・同一GMM・同一FSTで1.650秒と1.680秒を選んだ。2経路のGMMのPDFが異なったのは0始まりの164〜168番。一方の得点から他方を引いた差は約0.0001で、合計得点の再現誤差より小さかった。今回は再採点に加え、MFAの通常の探索に渡す行列を操作して因果関係を調べる。[先行比較](tsp-tall-gmm-paths.md)・[事前登録](../cases/tsp-tall-gmm-frame-swap.json)

| 読んだ入口と関数 | 入力から観測まで |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `align_synth`、`over_noise_floor` と `tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 48 kHzの合成波形に固定シードの雑音を足してPCM16へ量子化し、辞書・転記とともにMFAを呼ぶ。今回は前回のPCM16を4条件で共有する。 |
| MFA `alignment/multiprocessing.py` の `AlignFunction._run` と `db.py` の `Job.construct_feature_archive` | 通常の特徴生成と辞書から得たFSTを用意し、Kalpyへ渡す。今回の交換点は時間連結・LDAなどの時系列変換を通った行列の出口にある。 |
| Kalpy `gmm/align.py` の `GmmAligner.export_alignments`、`align_utterances`、`align_utterance` | 1フレーム40係数の行列を `gmm_align_compiled` へ渡す。モデル・グラフと音響・遷移の重み、beam 10とretry beam 40を前回に固定する。1フレームごとの遷移ID列・語ID列・尤度を採る。 |
| 研究版 `tools/probe_mfa_tall_gmm_paths.py` の `record` と `cross_score` | 前回採取した2つの行列から行を選ぶ。固定2経路の音響項は各フレームで選んだ供給元の尤度を使い、グラフ項を加える。MFAが実際に選んだ経路のほか、保存済みの2経路の得点差を照合する。 |

圧縮開始の行列を対照とし、float32開始の行列から全行、164〜168番だけ、その補集合だけを与える。置換は処理済み特徴量の行単位で行い、PCMの生成、MFAの前処理、発音グラフの枝や重みを触らない。同じPDFを使う行では2経路の音響差が相殺されるため、固定2経路の得点差は5行の供給元で決まると予測する。この順位とビーム探索で実際に選ばれる経路を区別して記録する。5行だけで1.680秒へ動き、補集合だけなら1.650秒に留まるかを検証する。

## 実測

全4条件でPCM16・転記・辞書は同じで、通常の特徴生成が作った両arkは `CM → CM` だった。置換前にGMM-HMMへ渡る行列が、保存した圧縮開始の対照とビット一致することを確認した。置換後の302×40の全要素を採り、各行の供給元に照合した。MFAが使った実効モデル、探索FST、設定は前回と一致した。

| float32開始の特徴量を使った範囲 | /ɔ/ の終端 | 選ばれた保存済み経路 | 1.680秒経路の得点差 |
| --- | ---: | --- | ---: |
| なし | 1.650秒 | 1.650秒 | −0.00015213 |
| 全302フレーム | 1.680秒 | 1.680秒 | +0.00013016 |
| 164〜168番の5フレーム | 1.680秒 | 1.680秒 | +0.00013016 |
| その補集合の297フレーム | 1.650秒 | 1.650秒 | −0.00015213 |

2つの交換条件は、対応する対照の遷移ID・語ID列と、語9区間・音素30区間をそれぞれ再現した。全条件で再試行は0件。今回のMFA設定と2つの特徴行列では、5フレームの供給元が境界と経路を決め、固定2経路の得点差も同じ供給元で決まった。[4条件の要約](../runs/tsp-tall-gmm-frame-swap-20261123-repeat/summary.json)・[デコーダの入力行列](../runs/tsp-tall-gmm-frame-swap-20261123-repeat/artifacts/decoder-inputs.npz)

次の最小対照は、この5フレームの32部分集合を再整列する比較である。既存のフレーム別の得点からは、165番単独の重み付き増分は+0.00009410。これに166番を加えると+0.00015831、167番を加えると+0.00016149で、どちらも圧縮開始の僅差0.00015213を上回る。再構成した得点差が小さいため、通常の探索で最小の交換集合を確かめる。[既存のフレーム別音響得点](../runs/tsp-tall-gmm-paths-20261123-repeat/artifacts/path-scores.npz)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究用Python 3.14.4、MFA 3.4.3。実効モデルは外部ディスクの一時領域でハッシュを採り、特徴行列・遷移ID列・フレーム別尤度・区間JSON・FSTを成果として保存した。研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_gmm_frame_swap.py tsp-tall-gmm-frame-swap-new
```

研究ワークスペースと `/tmp` から各5判定・上流6試験に通過し、35出力のうち計時ログを除いた34出力がバイト一致した。第44版の交差採点も共用処理の変更後に再実行し、26出力のうち24出力が一致した。成果はRTL9210B-CGに保存した。[同じケースの再実行](../runs/tsp-tall-gmm-frame-swap-20261123-repeat/manifest.json)・[交差採点の回帰](../runs/tsp-tall-gmm-paths-20261123-swap-regression/manifest.json)
