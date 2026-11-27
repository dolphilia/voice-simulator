# 励振のF0を変えたときの低域共鳴とTSPのF2採択

前回はF0 125 Hzで、追加共鳴を760 Hzから800 Hzに動かしたとき、設計F2が2075 Hzのまま全6窓で低域の極が採択された。今回はこの2種類の追加共鳴と追加なしを固定し、F0を100〜400 Hzの7条件で変える。上流のLPCが返した極を読み、推定されたF1からの間隔、設計F2に対応する候補、採択先を比較する。[前回の実測](tsp-f2-intervening-resonance.md#固定したf0での実測)・[事前登録](../cases/tsp-f2-intervening-excitation.json)

固定上流では `compare::tsp::run` が `measure_pair` で録音と合成を対応させる。`Sig::new` は48 kHzの音声を低域通過させ12 kHzにし、`measure` が対応した母音を `Sig::formants` に渡す。母音の35・50・65%を中心とする25 ms窓は各300標本。公開の `estimate_formants` はプリエンファシス0.97、Hamming窓、自己相関、40 Hzラグ窓、Levinson–Durbin法で予測係数を得る。次数は12または14で、根の偏角と半径を周波数・帯域幅のHzに換算する。150 Hz以上・帯域幅600 Hz以下の極から、TSPは1300 Hz未満・帯域幅500 Hz未満の最初の極をF1とし、推定F1＋200 Hzより高く3500 Hz未満の最初の極をF2とする。上流試験は係数、根と公開結果に加え、音素の対応と欠測の扱いを検査する。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[録音と合成の対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[採択の実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[上流の推定器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[LPC基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L95)・[TSP基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

合成対照は12 kHzで先頭から一定間隔のインパルスを与える。二次節の状態は直前2標本の出力で、始めに0とする。設計極から定まる定常応答 `H(kF0)` を各条件の末尾1周期のDFTと照合する。F0が変わると、伝達関数を観測する倍音位置と、固定時刻に切り出した窓の先頭の励振位相が変わる。各窓ではこの位相を周期内の標本数で記録する。低域650〜1100 Hzの最強倍音、追加共鳴に近い公開極の間隔、設計F2候補の適格性と採択先を別々に観測する。[倍音間隔の先行対照](tsp-f2-harmonic-spacing.md)・[追加共鳴の設計](tsp-f2-intervening-resonance.md)

## 7種類のF0での採択結果

追加共鳴なしの42窓は全件で設計F2の120 Hz以内を採った。追加した条件では48窓が低域の公開極を採択し、いずれも設計F2近傍の極は候補に残った。うち33窓の採択値は追加した極の120 Hz以内、15窓はそれより離れた915.92〜946.53 Hzだった。同じ共鳴・次数・窓中心でF0 125 Hzと比較した72組のうち33組で、採択の分類が変わった。[全126窓と候補](../runs/tsp-f2-intervening-excitation-20261123-repeat/summary.json)

各セルは「設計F2近傍 / 追加極近傍 / その他」の窓数。各条件は2次数×3窓。

| F0（Hz） | 追加共鳴760 Hz | 追加共鳴800 Hz |
| ---: | ---: | ---: |
| 100 | 3 / 3 / 0 | 0 / 6 / 0 |
| 125 | 6 / 0 / 0 | 0 / 6 / 0 |
| 150 | 6 / 0 / 0 | 0 / 6 / 0 |
| 200 | 0 / 6 / 0 | 0 / 6 / 0 |
| 240 | 6 / 0 / 0 | 3 / 0 / 3 |
| 300 | 0 / 0 / 6 | 0 / 0 / 6 |
| 400 | 6 / 0 / 0 | 6 / 0 / 0 |

125 Hzと比較して設計F2近傍と追加極近傍が入れ替わった18組では、両方のF0で設計F2に近い極が候補に残り、追加極近傍の公開極と推定F1との間隔が200 Hzをまたいだ。追加760 Hzの12次中央窓では、F0を125 Hzから200 Hzに上げると間隔は198.48 Hzから244.08 Hzへ増え、F2の採択は2070.32 Hzから862.75 Hzに移った。この2条件の最強倍音はそれぞれ750 Hzと800 Hzだった。200 Hzと400 Hzは最強倍音がともに800 Hzで、F2の採択先は異なった。400 Hzの追加条件12窓では、採択されたF1も790.86〜803.83 Hzとなった。実録音のF2の正誤は人手注釈の取得後に照合する。[上流の生根と公開極](../runs/tsp-f2-intervening-excitation-20261123-repeat/artifacts/upstream-envelopes.json)

## 再現と検証

共鳴を加えない7波形と42窓を先行の倍音対照に照合し、125 Hzの3波形と18窓を前回の追加共鳴比較に照合した。設計伝達関数と定常1周期DFTの相対差は全21波形で最大 `5.99×10⁻¹⁵`。先行の独立計算とは別に、Toeplitz解法とコンパニオン行列で126窓の複素根を求め直し、根の対応距離は最大 `2.22×10⁻¹⁰` だった。両実行は各5判定、固定上流のLPC基準試験1件とTSP試験6件に通過し、2仮説を支持した。要約、全波形、上流の生根・公開極はバイト一致した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行し、採取物6,539,572バイトをRTL9210B-CGに保存した。次の対照ではF0と追加共鳴を固定し、窓内の周期インパルスの位相だけを動かす。[初回](../runs/tsp-f2-intervening-excitation-20261123-a/manifest.json)・[別作業ディレクトリからの再実行](../runs/tsp-f2-intervening-excitation-20261123-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-tsp-f2-intervening-excitation-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_intervening_excitation.py tsp-f2-intervening-excitation-new
```
