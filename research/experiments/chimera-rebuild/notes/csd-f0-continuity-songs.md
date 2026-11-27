# CSDの4曲でF0の候補選択と追跡を比較

## 上流の処理と観測条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song()` は、録音と上流の合成を同じ注釈で `Analyzer::note()` に渡す。通常音符は始端30%と終端20%、メリスマは両端10%を除いた区間を5 ms刻みで読む。`pitch()` は譜面の周波数の±7半音で遅延を探し、YINの累積平均正規化差（CMND）が0.2を下回る最初の傾斜から局所最小まで進む。3点補間した遅延をHzに直し、平均二乗電力が閾値未満ならF0を欠測とする。採択後のF0と無次元のCMNDが音符の集計へ進む。[上流の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[音符の窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)・[YIN](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)

`Analyzer::power()` は2窓おきにHann窓の片側FFT電力を作る。`harmonic_db()` は採択F0の1倍・2倍の各周辺から、±3%または±2ビンの広い方で最大の電力を選ぶ。隣接3ビンのdBを補間して差を取った値がH1−H2である。ビブラートは連続有声の最長区間が0.4秒以上のとき、セント系列の傾斜を除いてから自己相関を計算する。固定上流の比較試験は既知の周期変調を検出し、直音・スクープを棄却する。分析の移植試験はYINのF0と非周期性を固定値に照合する。[H1−H2](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L531)・[ビブラート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)・[上流の比較試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)・[YINの照合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L229)

調整用 `en001a`・`en012a` と確認用 `en005a`・`en035a` の486音符を、録音・固定上流・再実装の同じPCMで比較した。計88,344窓の音符・波形・時刻、平均二乗電力、従来の+7・+5半音の結果を前回のCSVへ照合する。新条件は±7半音で得た複数の候補から、CMNDと遅延の長さに応じた費用で窓ごとに選ぶ方法と、隣接窓の音高差にも費用を加えて連続有声区間の経路を選ぶ方法である。費用係数0.02と0.5は1音符の試行時と同じ事前登録をハッシュで確認した。音符をまたぐ経路は作らない。`en035a` 第21音は方式を先に試した音符として、全曲の結果でもその点を区別する。[今回の登録](../cases/csd-f0-continuity-songs.json)・[先行の1音符と既知波形](csd-f0-continuity.md)・[調整用と確認用の元の区分](../cases/csd-f0-search-sensitivity.json)

各条件の倍音レベルは同じFFT電力を参照し、変化が最初に出た窓で直接DFTからも確認する。長い遅延候補や時間費用を選んだ最初のF0の変化と、その結果H1−H2が最初に変わった窓を別に残す。曲別中央値と音符内の隣接窓差は上流が整列を認めた音符から集計し、譜面から±600セント以上離れた窓の件数は全登録窓から数える。譜面は探索の基準とし、録音の実際のF0を判定する真値は別途必要である。[全曲の比較ツール](../tools/measure_csd_f0_continuity_songs.py)

## 実測

全条件で有声と判定された窓は85,940で、窓の位置も一致した。従来の+7半音では、固定上流334窓、再実装343窓で譜面より600セント以上高かった。新方式では、窓ごとの候補選択の時点で計677窓が0になった。従来の+5半音もこの4曲では0窓だった。1音符の先行対照では、+7半音の範囲を使う新方式で、+5半音条件が約204.68 Hzとした既知の409.35 Hzを推定できた。全曲の音符内で、隣接する有声窓のF0が600セント以上変化した回数は従来の両合成で88、新方式で0だった。[全曲の結果](../runs/csd-f0-continuity-songs-20261122-a/summary.json)・[既知波形の対照](csd-f0-continuity.md#実測)

| 波形 | 従来の+7半音から追跡までにF0が変わった窓 | 窓ごとの候補選択から追跡までにF0が変わった窓 | 従来の+7半音からH1−H2が変わった窓 | H1−H2の中央値が変わった音符 |
| --- | ---: | ---: | ---: | ---: |
| 録音 | 365 | 9 | 2 | 0 |
| 固定上流 | 345 | 5 | 170 | 11 |
| 再実装 | 349 | 2 | 175 | 11 |

時間費用だけで選び直されたのは、録音・両合成を合わせて16窓だった。うち11窓でH1−H2を測り、値は窓選択条件と一致した。他の5窓は2窓おきの採取位置に該当しなかった。ビブラートの検出件数も、全曲で窓選択条件と追跡条件が一致した。従来の+7半音と比べると、確認曲 `en035a` の固定上流で37/39音から39/39音、再実装で38/39音から39/39音に増えた。録音は `en012a` で29/44音、`en035a` で17/39音だった。残りの2曲はビブラートの評価長に達する音符が0件だった。[曲別・音符別の指標](../runs/csd-f0-continuity-songs-20261122-a/summary.json)

録音で最初に変わったF0は、`en001a` 第1音 `/eɪ/` の2.645秒だった。候補のラグ149・159サンプルのうち、短い側の295.77 Hzから277.17 Hzに変わり、CMNDは0.1805から0.04575になった。録音の変更の最大は第65音 `/vi/` の49.42564秒で、348.39 Hzから316.83 Hzへ164.41セント下がった。一方、録音の曲別中央値の変化は最大0.473セントだった。曲別の要約だけでは一部の窓で起きた大きな選択差を捉えられない。録音でどちらの候補が実際のF0に近いかは、この分析から確定できない。[録音の窓別結果](../runs/csd-f0-continuity-songs-20261122-a/artifacts/en001a-continuity-frames.csv.gz)

`en001a` 第30音の固定上流では21.780秒に、採択F0が415.94 Hzから276.41 Hzへ移り、H1−H2は−48.80から−1.89 dBへ動いた。同じFFTで参照した1倍・2倍のピークはビン16・35から12・24へ変わった。記録した最初のH1−H2変化を直接DFTと照合した差は最大2.21×10⁻¹³ dB。音符中央値が変わったのは両合成で延べ22音符で、`en035a` の曲別中央値は固定上流−3.250→−2.905 dB、再実装−3.297→−2.912 dBだった。[倍音の窓別結果](../runs/csd-f0-continuity-songs-20261122-a/artifacts/en001a-continuity-frames.csv.gz)・[曲別指標と直接DFTの照合](../runs/csd-f0-continuity-songs-20261122-a/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1を使用した。研究ワークスペースと `/private/tmp` から1回ずつ実行し、各54判定と6予測に合格した。両実行の要約と4曲の圧縮CSVがバイト一致した。固定上流の比較試験19件と分析試験1件も通過した。追跡の独立照合の呼び出し方を変更した後、従来の1音符・既知波形計測を再実行し、各結果が保存済みのCSV・要約とバイト一致した。3実行の174入力・21出力をサイズとSHA-256で照合し、採取物10,780,065バイトをRTL9210B-CGに保存した。[初回](../runs/csd-f0-continuity-songs-20261122-a/manifest.json)・[再実行](../runs/csd-f0-continuity-songs-20261122-repeat/manifest.json)・[1音符の回帰](../runs/csd-f0-continuity-20261122-songs-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python \
  tools/measure_csd_f0_continuity_songs.py csd-f0-continuity-songs-local
```

別ディレクトリではPythonとスクリプトを絶対パスで指定する。評価は登録された音符の中央部で行った。音符間の実時間の遷移、録音で候補が分かれた窓の実際のF0、人による試聴は未評価である。
