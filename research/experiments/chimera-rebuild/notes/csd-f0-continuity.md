# 歌唱F0の周期候補と連続性

## 読解

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song()` は録音と合成を読み、曲の最低音からYINの窓長を決める。`Analyzer::note()` は各音符の中央部を5 ms刻みで測り、`Analyzer::pitch()` はPCMの平均二乗電力と曲全体から得たゲートを使う。探索範囲は譜面のF0の±7半音。YINの出力はHzと無次元の非周期性で、ゲート以下の窓はF0なしとする。`vibrato()` は連続有声窓の最長区間を選び、線形トレンドを除いたF0のセント系列を自己相関に渡す。[曲の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[音符窓とYINの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L499)・[ビブラート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)

`yin_pitch()` はサンプル単位の遅延 `τ` ごとに、同じ数の対を使って二乗差の和 `d(τ)` を作る。`d(τ) × τ ÷ Σd(1..τ)` が累積平均正規化差（CMND）。歌唱評価では整数遅延の短い側から走査し、0.2を下回った最初の傾斜を局所最小まで下り、隣の2点を使って放物線補間する。出力F0は `サンプルレート ÷ 補間後の遅延`。ここで採った候補が、後で非周期性とビブラートの入力に使われる。固定上流の試験は移植元のYINの出力、既知の周期変調の深さ・周波数、直音やスクープの判定を照合している。[YINの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)・[YINの参照試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L229)・[ビブラートの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)・[YIN原論文](https://doi.org/10.1121/1.1458024)

## 比較条件

先行実験の+5半音の上限では、基本音と第2・第3倍音を含む既知の409.3506 Hzが中央の窓で204.6750 Hzと推定された。今回は上限+7半音のCMNDから、閾値未満の局所最小を候補として記録する。各候補の費用は `CMND + 0.02 × log₂(候補の遅延 ÷ 最短候補の遅延)`。時間方向の条件ではさらに、隣接する候補のF0の比に対する `0.5 × |log₂(F0の比)|` を加え、動的計画法で合計費用の最小経路を選ぶ。音符と無声窓の境界で経路を分ける。同じ候補に時間費用を0とした比較も通し、窓ごとの選択で生じた変化を区別する。F0の候補を後段へ渡す考え方はpYINにもあり、ここで比較する条件はCMNDと決定論的な費用で定義した。[事前登録](../cases/csd-f0-continuity.json)・[比較ツール](../tools/measure_csd_f0_continuity.py)・[既知音の先行対照](csd-f0-search-sensitivity.md#譜面より高い既知音の対照)・[pYIN論文](https://doi.org/10.1109/ICASSP.2014.6853678)

第1版では、既知の定常音4波形と、277.18 Hzから409.35 Hzへ連続して上がる波形、途中に無音を挟む波形を事前登録した。確認には保存済みの `en035a` 第21音を使い、録音・固定上流・再実装で各80窓を照合した。第1版では時間費用の有無で確認曲のF0が同じだった。時間費用だけが効く場面を判定するため、第2版で200 Hzと第2倍音を含み基本音だけを短時間弱める波形を先に登録してから加えた。費用の係数と先行判定は第1版から継続した。[第1版の判定](../runs/csd-f0-continuity-20261122-a/summary.json)・[第2版の登録](../cases/csd-f0-continuity.json)

## 実測

| 400 Hz付近を選びやすい200 Hzの既知波形 | 従来の+7半音 | 窓ごとの候補選択 | 時間方向の追跡 |
| --- | ---: | ---: | ---: |
| 約1オクターブ上の窓 | 12 | 12 | 0 |
| 真値200 Hzからの最大誤差 | 203.81 Hz | 203.81 Hz | 1.24 Hz |

既知の200 Hzで最初に時間費用が選択を変えた0.255秒では、121サンプルの候補が398.152 HzでCMND 0.00551、241サンプルの候補が199.564 HzでCMND 0.00320だった。長い遅延への費用を足すと窓ごとの判定は短い遅延を選ぶ。前後のF0の差を含めると長い遅延が残った。32通りを全列挙した独立計算も、別の5窓の例で動的計画法と同じ経路を返した。[第2版の結果](../runs/csd-f0-continuity-20261122-b/summary.json)・[窓別の全候補](../runs/csd-f0-continuity-20261122-b/artifacts/pitch-tracks.csv)

409.3506 Hzの倍音付き波形は、窓ごとの候補選択と時間方向の追跡とも中央で409.3547 Hzを返した。上限を+7半音に保つことで真の周期を候補にでき、定常音4波形の全窓で誤差は最大0.024 Hzだった。277.18→409.35 Hzの連続上昇では追跡の途中の最大差が7.61セント。無音を挟む対照では中央17窓に候補が生じず、両側の音高をそれぞれ復元した。[既知波形の結果](../runs/csd-f0-continuity-20261122-b/summary.json)

確認曲第21音では、譜面より600セント以上高い窓が固定上流・再実装とも4件から0件になった。いずれも窓ごとの候補選択で変化し、時間費用を加えたF0は全80窓で同じだった。例えば上流の26.84078秒では、従来の129サンプルの候補は375.445 Hz、CMND 0.18710。193サンプルの候補は248.804 Hz、CMND 0.00100だった。候補側でも最初の変化は26.84578秒の129→193サンプルで、独立に計算した候補のCMNDと最大1.39×10⁻¹⁶の差だった。録音の80窓も有声数・F0ともに同じだった。ビブラートは固定上流で未検出から30.97セント・6.080 Hz、候補で225.07から33.08セント・6.081 Hzになった。[確認曲の結果](../runs/csd-f0-continuity-20261122-b/summary.json)・[上限変更時の比較](../runs/csd-long-note-vibrato-f0-control-20261121-repeat/summary.json)

実録音での音高の正解時系列は得ていない。時間方向の追跡の効果は、基本音の振幅を制御した既知波形で確認した。録音を含む曲全体の音符遷移、ビブラート、H1−H2への影響と、人による試聴は次の評価に残る。

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1を使用した。研究ワークスペースで新しい実行IDを渡す。別ディレクトリからはPythonとスクリプトを絶対パスで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python \
  tools/measure_csd_f0_continuity.py csd-f0-continuity-local
```

第1版は20判定・9予測、第2版は初回と `/private/tmp` からの再実行で各20判定・11予測が成立した。第2版の要約と1,027窓のCSVは両実行でバイト一致した。固定上流の比較試験19件とYINを含む移植照合1件も通過した。既存の4曲を通常の探索上限比較で再解析し、88,344窓の37判定と、従来の要約・4本の圧縮CSVのバイト一致を確認した。4実行の169入力・23出力をサイズとSHA-256で照合し、新しい計測成果6,485,037バイトをRTL9210B-CGに保存した。録音、合成PCM、上流の通常報告は保存済みの入力を参照した。[第2版の記録](../runs/csd-f0-continuity-20261122-b/manifest.json)・[再実行](../runs/csd-f0-continuity-20261122-repeat/manifest.json)・[4曲の回帰](../runs/csd-f0-search-sensitivity-20261122-continuity-regression/manifest.json)
