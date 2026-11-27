# GMM-HMMの境界を動かす特徴行の部分集合

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第45版では `FK61_02` のGMM-HMM入力で164〜168番の5行を入れ替えると、`tall` の /ɔ/–/l/ 境界が1.650秒から1.680秒へ移った。残り297行だけの交換では1.650秒だった。今回は5行の部分集合をすべて試し、どの組に切り替えの効果があるかを調べる。[5行の交換](tsp-tall-gmm-frame-swap.md)・[登録したケース](../cases/tsp-tall-gmm-frame-subsets.json)

| 読んだ入口と処理 | 入力と観測点 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `align_synth`、`over_noise_floor`、`tests::a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 固定シードの雑音を加えた48 kHz波形をPCM16に量子化してMFAへ渡す。今回は保存済みの同じWAV・転記・発音辞書を全条件で使用する。 |
| MFAの `alignment/multiprocessing.py` の `AlignFunction._run` とKalpyの `gmm/align.py` の `GmmAligner.align_utterance` | 語列のFSTと処理済み特徴行列を `gmm_align_compiled` へ渡し、フレーム別の遷移IDと語IDを出す。交換点は時間連結・LDAなどを通った302行×40列の入力。ビーム、モデル、FSTは第45版に揃える。 |
| 研究版 `probe_mfa_tall_gmm_frame_swap.py` の `replace_features` と `measure_tsp_tall_gmm_frame_swap.py` の `two_path_margins` | 選んだ行だけを、最初にfloat32で保存した条件の入力行列から取る。固定した2経路の各フレームの音響得点をその行の供給元から取り、グラフ費用と合成する。再整列後は全区間、境界および遷移・語ID列を照合する。 |

集合を `S` とし、1.680秒経路と1.650秒経路の重み付き得点差を `D(S) = D(∅) + Σ d[i]` として計算する。和の対象は `i ∈ S` で、`d[i]` は行を入れ替えたときの音響項の差。第44版の尤度から `D(∅) ≈ −0.00015213`。165番単独は+0.00009410で、165・166番の組と165・167番の組はそれぞれ+0.00015831と+0.00016149の増分を与える。最小はこの2組と予測する。空集合と5行全体は第45版の対照、残り30条件は実際のビーム探索と固定2経路の順位を比較する。最小行数と、成功する真部分集合を持たない包含極小集合をそれぞれ数える。

## 初回の入力照合

初回の実行IDは `tsp-tall-gmm-frame-subsets-20261123-a`。第44版の対照の区間JSONを `artifacts/aligned/FK61_02-control/FK61_02-control.json` で照合し、`ValueError` で停止した。 `artifacts/compressed/aligned/FK61_02-control/FK61_02-control.json` が保存時のパスだった。入力照合は実行記録の作成前なので、初回は区間・特徴量・実行マニフェストが生成されていない。マニフェストの出力一覧から正しいパスを確認し、第1版の事前条件を保持して別IDで再実行した。[第44版の出力一覧](../runs/tsp-tall-gmm-paths-20261123-repeat/manifest.json)

次の実行 `tsp-tall-gmm-frame-subsets-20261123-recheck` は、全体の `cmvn.scp` を観測器が `scp,s,cs` で開くところで停止した。MFAの `_write_spk2utt` は数値の話者ID順で索引を書き、Kalpyの `CmvnComputer.export_cmvn` はその順序でCMVNを出す。 `1, 2, 10` の3キーで同じ例外を再現し、順序を仮定しない `scp` では全キーを読めることを確認した。観測器で全体のCMVNを開く引数だけを `sorted=False` にした。MFAが特徴量生成に使うジョブ別索引は従来どおり文字列で整列した。失敗時の入力行列・実行ログを外部ディスクに保存した。[CMVNの読み取りで停止した実行](../runs/tsp-tall-gmm-frame-subsets-20261123-recheck/manifest.json)

## 実測

通常MFAで32部分集合すべてを整列した。デコーダ入力が登録の行構成とビット一致し、実効モデル・FST・設定は全条件で第45版と一致した。空集合および全5行は、第45版の全語・音素区間、特徴行列、遷移・語ID、フレーム別尤度を再現した。全32条件で固定2経路の得点差から予測した経路を選び、別の経路を選んだ条件は0件だった。

| 交換した行数 | 条件数 | 1.680秒を選んだ条件数 |
| --- | ---: | ---: |
| 0 | 1 | 0 |
| 1 | 5 | 0 |
| 2 | 10 | 2 |
| 3 | 10 | 6 |
| 4 | 5 | 5 |
| 5 | 1 | 1 |

最小は165・166番と165・167番の2組で、合計の得点差はそれぞれ+0.000006179、+0.000009358だった。166・167・168番の3行も、成功する真部分集合を持たない包含極小集合だった。今回のPCM・モデル・探索設定では14条件で1.680秒、18条件で1.650秒を得た。第44版で観測した得点の照合誤差より小さな得点差の組も、通常の探索で境界が切り替わることを確認した。[32条件の要約](../runs/tsp-tall-gmm-frame-subsets-20261123-repeat/summary.json)・[デコーダ入力行列](../runs/tsp-tall-gmm-frame-subsets-20261123-repeat/artifacts/decoder-inputs.npz)

次は1.650秒と1.680秒の整列結果が得られた同じ無加工PCMを用い、10 ms刻みの4つの終端候補に対するF2の感度を診断する。記録済みの両端と、1.660秒・1.670秒へ終端だけを動かした対照では、同じ25 msのLPC窓を使う。中央3窓の中央値と90%窓を比較し、終端候補によってどの程度変わるかを記録する。1.660秒・1.670秒は感度測定用の条件とする。[先行の固定窓と再整列窓](tsp-tall-initial-tip-mfa.md#実測)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4、MFA 3.4.3。入力と全条件の特徴、遷移ID・尤度、探索FST・区間をRTL9210B-CGに保存した。研究ワークスペースで次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_tall_gmm_frame_subsets.py tsp-tall-gmm-frame-subsets-new
```

研究ワークスペースと `/tmp` からの2実行は各6判定と上流CLIのTSP単体試験6件を通過した。203出力のうち202件がバイト一致した。残りの1件は実行ログだった。CMVNの読む順序を修正したあとに前回の5行交換も再実行し、35出力のうち33件がバイト一致した。差がある2件は実行ログだった。[修正直後の実行](../runs/tsp-tall-gmm-frame-subsets-20261123-resolved/manifest.json)・[別ディレクトリからの再実行](../runs/tsp-tall-gmm-frame-subsets-20261123-repeat/manifest.json)・[5行交換の回帰](../runs/tsp-tall-gmm-frame-swap-20261123-subsets-cmvn-regression/manifest.json)
