# CSDの音量包絡と句の有声開始

調整用 `en001a` と確認用 `en005a` の保存済みWAVで、曲全体の音量変化と句単位のタイミングを測った。録音は評価用で、44.1 kHz PCM16の左右を平均して振幅を32768で割る。合成は48 kHzのモノラルfloat32を振幅補正なしで読む。固定上流・候補はどちらも先行実行の録音長にそろえ、入力をハッシュで照合した。[事前登録](../cases/csd-envelope-timing.json)・[調整用WAVの検証](csd-acoustic-f0-en001a.md)・[確認用WAVの検証](csd-acoustic-f0-en005a.md)

## 固定上流の測定経路

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `main.rs` は `compare csd` を `compare::csd` に渡す。 `compare_song` は `load_notes`・`read_wav` から音符と録音を取り、 `render_notes` に録音秒数を渡す。上流は評価に描画時の `f32` を `f64` に拡張して使い、保存済み基準も `--float` で同じサンプルを保持する。 `Analyzer::new`・`Analyzer::note` が使う音符時計と、曲全体の包絡時計は独立している。[CLIの分岐](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L114)・[録音の読み込み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L331)・[曲の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)

`envelope_db` はサンプル0から幅 `js_round(0.01 × fs)` の非重複窓を取る。録音は441、合成は480サンプルで、最後の短い窓は実サンプル数を分母にする。窓内の平均二乗を `P` とし、 `max(−80, 10 log₁₀(P + 10⁻³⁰))` をdBで保存する。 `envelope_lag` は両配列の短い方の長さを取り、整数ラグ `l = −30 … +30` の順に参照の `i` と比較側の `i + l` を重ねる。各ラグの重なり内で平均を別々に引き、Pearson相関が最大になった時点を採る。厳密な同値では先に検査した小さいラグが残り、分散ゼロで候補がなければ欠測になる。秒への換算は `l × 0.01` で、正値は比較側の遅れ。窓より細かな時差をこの値から直接は読めない。[包絡とラグ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L728)

句の先頭は前の音符との空きが80 msを超える位置。 `Analyzer::note` は `max(音符開始−250 ms, 前の音符終端+30 ms)` から、 `音符開始+min(300 ms, 音符長×0.5)` の直前まで5 msずつ進める。各時刻に中心を置いた窓を信号固有の電力ゲートへ通し、譜面F0の±7半音で正規化差0.2未満のYIN推定が初めて出た窓の中心を採用する。符号付きの観測値はその中心から注釈時刻を引いた秒数。開始ラベルは母音、無声子音、有声子音の3種で、有声子音から始まる場合はその子音に反応し得る。 `compare_song` の種別中央値は有効な計画の音符と有限値を対象とする。固定上流の `compare::tests` に歌唱の分析、 `score::tests::a_song_reads_back_from_score_json_as_it_was` にスコア列の往復、 `golden_analysis::analysis_matches_typescript` にYINの基準がある。包絡の既知時差は登録した独立対照で確認した。[句の分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L127)・[窓と有声開始](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L449)・[スコア列](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/score.rs#L65)・[比較テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1329)・[YINの基準テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L95)

## 曲全体の実測

配列の区間和と全サンプルのスカラー直接集計で包絡を別々に計算し、ラグは中心化した内積と一次・二次の和から独立に照合した。登録した3組の比較で全366ラグの重なり数が一致し、独立計算の最大差は包絡 `1.42×10⁻¹⁴ dB`、相関 `9.88×10⁻¹⁵`。両レートで−300 ms・+40 msの既知時差、振幅2倍の時差0 ms、17サンプルの末尾窓、無音による欠測の対照も通った。 `en005a` の最終窓は録音272、合成296サンプルだった。[全ラグと窓の比較](../runs/csd-envelope-timing-20261121-final/summary.json)

| 曲 | 窓数／波形 | 録音と固定上流のラグ／相関 | 録音と再実装のラグ／相関 | 固定上流と再実装のラグ／相関 |
| --- | ---: | ---: | ---: | ---: |
| `en001a` 調整用 | 6,480 | 0 ms／0.875346 | 0 ms／0.874937 | 0 ms／0.999858 |
| `en005a` 確認用 | 7,385 | +10 ms／0.878440 | +10 ms／0.878410 | 0 ms／0.999879 |

固定上流と録音の比較では、通常の `report.json` にあるラグ（調整用0 ms、確認用+10 ms）と相関の報告値0.88を再現した。 `score.json` の区分ごとの相関は調整用0.875、確認用0.878で、それぞれ3桁の丸め範囲内だった。調整用に保存される丸め前の相関とは `2.78×10⁻¹⁵` の差で、有声開始は録音・固定上流それぞれ50件が丸め前でも完全一致した。確認用の丸め前の音符別データは上流スコアに含まれず、通常報告と区分の報告で照合した。[固定上流の通常報告](../runs/csd-song-planning-20261121-final/artifacts/csd/report.json)・[スコア](../runs/csd-song-planning-20261121-final/artifacts/csd/score.json)・[ラグ全点のCSV](../runs/csd-envelope-timing-20261121-final/artifacts/en005a-correlations.csv)

両合成の包絡はどちらの曲も先頭10 msから異なった。固定上流の平均二乗は0で床適用後−80 dB、候補は `1.4854×10⁻⁶` で−58.28 dB。確認用の既存の先頭20 ms対照も同じ区間を集計し、姿勢・声源変動・ゲインを同時にそろえた固定上流の値が候補と一致することを確認した。両合成の全曲ラグは0 msで、局所の差は包絡相関に残る。録音と通常の固定上流は先頭の床適用前から異なり、床適用後の最初の差は `en001a` で1.50秒、 `en005a` で2.89秒だった。[各窓の振幅と床](../runs/csd-envelope-timing-20261121-final/artifacts/en005a-envelope.csv)・[先頭PCMの対照とマニフェスト](../runs/csd-acoustic-f0-en005a-startup-20261121-a/manifest.json)

## 句ごとの実測

全86句で3波形それぞれに有声開始が得られた。候補と録音の開始差の絶対値の中央値は `en001a` で15 ms、 `en005a` で20 msで、固定上流と録音でも同じ中央値だった。両合成の有声開始は86句中82句で同時刻。調整用では第34音の `/eɪ/` で候補が5 ms遅れ、確認用では3句で差があり最大10 msだった。最初に判定が分かれた窓のエネルギーはどちらもゲートを超え、調整用は23.99880秒でYINの正規化差が固定上流0.194、候補0.206。確認用は31.84570秒で0.172、0.212だった。候補はどちらも次の5 msの窓で有声になった。[句ごとの絶対時刻と欠測](../runs/csd-envelope-timing-20261121-final/artifacts/en005a-phrase-onsets.csv)・[最初に判定が分かれた窓](../runs/csd-envelope-timing-20261121-final/summary.json)

確認用で録音と両合成の差が最大の句は、第45音の `/tʃɝp/` の210 ms。録音の有声窓は注釈の−200.8 msで、前の同じ音節の注釈終端27.923秒に30 msを足した探索の左端だった。両合成では+9.2 msだった。この窓がどの音節に由来するかは探索時刻と周期性だけでは確定しない。前の音節の余韻と対象音節の開始を見分ける対照が残る。[音符注釈と探索結果](../runs/csd-envelope-timing-20261121-final/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。事前登録第1版の13判定に通過後、通常報告を補うスコアの照合を第2版に登録した。初回は有声開始の列参照を `APER`（0始まりの列番号11）に取り違えて不合格となった。固定上流の `ONSET = 10` を確認して列を修正し、許容差を維持して17判定に通過した。第1版と不合格の結果および実行時点のソースをそれぞれ保持した。固定上流の比較19試験と基準分析1試験も通過。正式成果は作業用RTL9210B-CGに約4.00 MB。波形は先行実行を参照し、今回は包絡、相関、句別のCSVを保存した。[第1版の結果](../runs/csd-envelope-timing-20261121-a/summary.json)・[列参照を誤った実行](../runs/csd-envelope-timing-20261121-score/summary.json)・[正式実行とハッシュ](../runs/csd-envelope-timing-20261121-final/manifest.json)・[別ディレクトリからの再実行](../runs/csd-envelope-timing-20261121-repeat/manifest.json)

`research/experiments/chimera-rebuild` から、新しい実行IDで再実行できる。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_envelope_timing.py csd-envelope-timing-local-1
```
