# CSD全曲でF0の探索上限を変えた対照

標準の上限+7半音と、過去の1音符対照で使った+5半音を、既存の調整用 `en001a`・`en012a` と確認用 `en005a`・`en035a` に適用した。4曲486音符について、録音・固定上流・候補のPCM、曲の区分、時刻、5 ms格子、YIN閾値0.2、探索下限−7半音を固定した。通常の報告と試聴素材を基準として参照した。[今回のケース](../cases/csd-f0-search-sensitivity.json)・[1音符の先行対照](csd-long-note-vibrato.md#第3倍音がビブラート推定に入る対照)・[試聴の条件](csd-listening.md)

## 上流の経路と計算

固定上流の `compare_song` は録音と合成の両方を `Analyzer::note` に渡す。通常の音符では開始側30%と終端側20%、メリスマでは両端の各10%を外した区間を5 ms刻みで読む。 `Analyzer::pitch` は譜面周波数に対してYINの探索範囲を設定する。サンプルレートを `fs` とすると、最短遅延は `max(2, floor(fs / 上限Hz))`、最長遅延は `min(floor(fs / 下限Hz), floor(窓長/2))`。今回変更したのは最短遅延に使う上限Hzだけ。最長遅延と差分のサンプル数を共有し、未正規化差分 `D(τ) = Σ(x[i]−x[i+τ])²` と累積平均正規化差 `τD(τ)/Σ D(j)` を同じ列から読む。正規化差が0.2未満に初めて達した位置から、差が減る間だけ遅延を進める。3点補間で得た遅延をHzに変換し、電力ゲートを通った窓のF0を保存する。しきい値を満たす遅延がない窓にも、探索範囲内の最小の正規化差を非周期性として記録する。[固定上流の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[YINと電力ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L499)・[差分と遅延の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)

H1−H2は同じHann窓のFFT電力から、採用F0の1倍と2倍の近傍のピークの差を取る。ビブラートでは有声窓のセント系列から最長の連続区間を選び、線形傾斜を除いた後に自己相関から周波数と深さを求める。0.4秒以上連続して有声の区間が評価対象になる。上流の通常報告の音符別H1−H2と、調整用スコアの丸め前の値を照合した。元のF0、非周期性、ビブラートの入力と検出も、保存済みの先行実行と比較した。固定上流の `compare::tests` と `golden_analysis` を再実行し、既知の倍音比・周期変調・波形窓・YINの基準を確認した。[H1−H2の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L531)・[ビブラートの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)・[固定上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1329)・[分析の基準](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L95)

今回の計測器では遅延した窓を配列で並べて差分を計算した。変更があった窓と固定251窓ごとの窓は、既存の `NotePitch.at` でも両方の上限を指定して照合した。影響を受けたH1−H2では同じFFT電力の配列を共有する。ビブラートの直線と積の和は以前の独立再計算も適用した。曲ごとの要約は、上流が母音の時刻で採用した音符から集計した。[計測器](../tools/measure_csd_f0_search_sensitivity.py)・[通常のF0](../tools/measure_csd_song_f0.py)・[H1−H2の実測条件](csd-note-spectrum.md)

## 4曲の結果

3波形の計88,344窓を照合した。広い探索で譜面から+600セント以上だった合成の677窓は、狭い探索で全件が600セント未満になった。変わったF0はこの677窓。録音のF0と全波形の有声・無声の判定は全件一致し、両条件で85,940窓が有声。既存の実装で再計算した1,340窓、H1−H2の通常報告、調整用の丸め前の値、先行1音符の対照も一致した。[全曲の対照指標](../runs/csd-f0-search-sensitivity-20261121-a/summary.json)

| 曲 | 固定上流の+600セント以上の窓 | 候補の+600セント以上の窓 | 固定上流のH1−H2中央値（dB） | 候補のH1−H2中央値（dB） |
| --- | ---: | ---: | ---: | ---: |
| `en001a` 調整用 | 216 → 0 | 215 → 0 | 2.767 → 2.767 | 2.713 → 2.713 |
| `en005a` 確認用 | 0 → 0 | 0 → 0 | 8.563 → 8.563 | 8.506 → 8.506 |
| `en012a` 調整用 | 0 → 0 | 0 → 0 | 4.361 → 4.361 | 4.334 → 4.334 |
| `en035a` 確認用 | 118 → 0 | 128 → 0 | −3.250 → −2.905 | −3.297 → −2.912 |

H1−H2は計345窓、延べ22音符の中央値が変化した。最初のF0差は `en001a` の第30音、21.780秒で、固定上流・候補とも115サンプルの遅延から174サンプルになった。同曲の候補第73音のH1−H2中央値は−55.86から−1.98 dBへ変わり、曲全体の中央値は2.713 dBだった。 `en035a` の候補は第14音の22.22701秒で最初のF0差を記録し、遅延が145から215サンプル、F0は336.11から223.52 Hzになった。[調整用の窓ごとの対照](../runs/csd-f0-search-sensitivity-20261121-a/artifacts/en001a-frames.csv.gz)・[確認用の窓ごとの対照](../runs/csd-f0-search-sensitivity-20261121-a/artifacts/en035a-frames.csv.gz)

`en035a` のビブラート評価対象は両合成で39音。固定上流の検出は37から39音、候補は38から39音になった。固定上流の第21音 `/lʌ/` と、両合成の第98音 `/flaɪ/` が新たに検出された。第98音は広い条件で範囲外の周波数を返し、狭い条件では固定上流35.24、候補34.05セント。録音の検出は17/39音で一致し、 `en012a` の録音29/44音・両合成44/44音も一致した。残る2曲は最長有声区間が0.4秒未満で、両条件ともビブラートの評価対象は0音だった。[音符別の検出と欠測](../runs/csd-f0-search-sensitivity-20261121-a/summary.json)

非周期性は981窓で変化し、うち59窓は録音。例えば `en001a` の録音の3.38630秒では、双方とも周期を検出できず、最小差を返した遅延が118から238に移り、非周期性が0.7611から0.7687になった。録音の曲別中央値は4曲とも同値だった。F0の有声率と非周期性は異なる判定段階の値として保持した。[通常と上限変更後の非周期性](../runs/csd-f0-search-sensitivity-20261121-a/summary.json)

## 譜面より高い既知音の対照

MIDI 61の譜面約277.18 Hzに対し、既知のF0を+675セントの409.3506 Hzに設定した。譜面通りの既知音も同じ方法で生成した。標準の+7半音条件は純音と第2・第3倍音を含む波形の双方で409.36 Hz前後を返した。+5半音条件では、倍音を含む入力が235サンプルの遅延を選び、**204.68 Hz** と約1オクターブ低くなった。純音は最短遅延129の正規化差0.19689を採った後、3点補間で約116.79サンプルに戻り、**411.00 Hz** を返した。整数の探索開始位置を決める369.99 Hzを、補間後の推定は上回り得る。いずれも前後の有声判定は有声のままだった。[既知音の登録](../cases/csd-f0-search-detuned-tone.json)・[遅延・補間の実測](../runs/csd-f0-search-detuned-tone-20261121-a/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。通常条件の照合を含む4曲37判定、既知音3判定、固定上流20試験を通過した。 `/tmp` で両比較を再実行し、要約と圧縮CSVがバイト一致した。圧縮CSVの全窓数と音符別H1−H2中央値も別集計で確認した。全曲の正式成果は約7.95 MBで、既存のWAVを参照し、フレーム表は作業用RTL9210B-CGに置いた。[全曲の実行](../runs/csd-f0-search-sensitivity-20261121-a/manifest.json)・[全曲の再実行](../runs/csd-f0-search-sensitivity-20261121-repeat/manifest.json)・[既知音の再実行](../runs/csd-f0-search-detuned-tone-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_csd_f0_search_sensitivity.py csd-f0-search-sensitivity-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=16777216 ../../.venv/bin/python tools/measure_csd_f0_detuned_tone.py csd-f0-search-detuned-tone-local-1
```
