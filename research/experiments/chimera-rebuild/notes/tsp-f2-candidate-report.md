# TSP評価に窓ごとのF2候補を出す

実録音 `seems` の母音中央では、1 kHz付近が採られ、2.3 kHz付近も候補だった。既定の評価要約では採択された対と中央値を使うため、候補の順位や除外理由を調べるには保存した極と突き合わせる必要がある。固定上流の公開極を使って、既存CLIに窓単位の診断を加える。先行の中央窓では993.37、2323.81、2862.40 Hzの3極が昇順に候補として並び、993.37 Hzが採られると予測した。実録音、固定上流の合成、研究版の合成の4発話と、欠測を含む既存の対照を比較する。[事前登録](../cases/tsp-f2-candidate-report.json)・[実録音の窓比較](tsp-lpc-recording-window-shift.md)

上流の `compare tsp` は `measure_pair` で48 kHzの録音と合成音の音素を照合し、各母音を `Sig::formants` に渡す。 `Sig::new` は95タップのBlackman窓付きsincで5,400 Hz低域通過を施し、入力4標本につき1標本を取る。母音の35・50・65%の中心から300標本を取り、窓内の前標本を0とした0.97のプリエンファシス、Hamming窓、40 Hzを尺度とする自己相関のラグ窓、Levinson–Durbin法、Durand–Kerner法の順に計算する。根の偏角を `fs/(2π)` 倍すると周波数、半径の自然対数を `-fs/π` 倍すると帯域幅を得る。上半平面の150 Hz以上・帯域幅600 Hz以下の極が周波数昇順で公開される。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[音素と録音の対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[LPCの更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)

F1は1,300 Hz未満かつ幅500 Hz未満の先頭の極。F2候補は `F1 + 200 Hz < 周波数 < 3500 Hz` を満たす極で、F2にはその先頭を使う。候補に入っても後順なら採られず、F1なしや波形外なら窓全体が欠測になる。F1・F2の対が揃った基準中心だけを母音の中央値に使う。上流Rustの直接の中央値と、研究用プローブが採取する窓の公開極・選択結果を照合する。独立したToeplitz解法と複素根による結果、およびRustとTypeScriptの既存対照試験も使う。[採択と中央値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[TSPの欠測試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)・[LPCの基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L187)・[固定上流の観測入口](../tools/upstream_tsp_formant_probe.rs)

## 診断の実行

`--f2-candidates` を指定すると、`runs/<実行ID>/artifacts/f2-candidates.json` に、発話・音源・音素番号・窓位置ごとの公開極、周波数と帯域幅、候補順位、採択・除外理由を保存する。 `f2_rank` が1の極が採られ、2以上の極は周波数順で後に続く。 `used_in_median` から、母音の中央値に入った窓を確認できる。[候補レポートの実例](../runs/tsp-f2-candidates-20261123-on/artifacts/f2-candidates.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_stressed_vowel_formants.py tsp-f2-candidates-new --f2-candidates
```

## 照合結果

4発話の録音・固定上流・研究版の180窓と対照5窓に、公開極860件を出力した。185窓中177窓に複数のF2候補があり、欠測はF1なし3窓と波形外3窓だった。固定上流の母音中央値と独立LPCの選択を再現し、追加の既知極で `F1 + 200 Hz` と3,500 Hzの等号を除外すること、F2が取れないときにF1が残ることも照合した。

`seems` の中央50%では993.37 Hz、2,323.81 Hz、2,862.40 Hzの順で候補が並び、第1候補の幅は508.89 Hz、第2候補の幅は59.45 Hzだった。開始側10%では約1 kHzの極が公開極に現れず、2,318.26 Hzが第1候補になった。この境界窓は中央値に入らない。人の注釈を受け取った際は、同じ窓において選ばれた極と残った候補の両方を照合できる。[照合結果と中央窓の詳細](../runs/tsp-f2-candidate-report-20261123-verify/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使った。既定CLIとオプション付きCLIを別の作業ディレクトリから実行し、先行の評価要約と固定上流出力にバイト一致した。オプション付きの再実行も3出力が同じだった。各計測で固定上流のLPC基準1試験、TSP 6試験が通過した。録音PCMを読むときにSciPyが非音声チャンクを読み飛ばす警告を出した。診断実体とログはRTL9210B-CGに保存した。[既定の実行](../runs/tsp-f2-candidates-20261123-off/manifest.json)・[診断付きの実行](../runs/tsp-f2-candidates-20261123-on/manifest.json)・[再実行](../runs/tsp-f2-candidates-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/verify_tsp_f2_candidate_report.py tsp-f2-candidates-verify-new \
  --default-run tsp-f2-candidates-20261123-off --diagnostic-run tsp-f2-candidates-20261123-on
```
