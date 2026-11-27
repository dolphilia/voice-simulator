# CSDのビブラートと非周期性

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` を基準に、調整用 `en001a` と確認用 `en005a` の保存済みF0表とWAVを照合した。2曲の全192音符は既定のビブラート条件を満たす長さに届かなかったため、別に1.6秒の母音を描画し、ビブラートの深さを35セントと0セントに変えて検出経路を確認した。[実曲のケース](../cases/csd-vibrato-aperiodicity.json)・[長母音の対照ケース](../cases/csd-vibrato-long-vowel.json)

## 固定上流の入力と測定順序

`compare::csd` から `compare_song` を呼び、録音・合成をそれぞれ `Analyzer::note` で測る。音符の開始30%・末尾20%（メリスマは各10%）を除いた範囲を5 ms刻みで走査する。 `pitch` は中心窓の平均二乗とYINを計算し、電力がゲートを下回った場合はF0だけを0 Hzとして返す。窓がPCMの範囲外ならF0なし、非周期性1.0。上流はYINの累積平均正規化差をそのまま非周期性に使い、周期を採用した窓は採択した遅延の値、採用できなかった窓は探索内の最小値を返す。比が1を超えることもある。音符の非周期性は全窓の有限値の中央値で、有声率はF0が得られた窓の比率。先行F0表では電力ゲートを先に適用したので、今回だけ同じPCM窓で省略された非周期性を補完した。[曲の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[ゲートとYINの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L499)・[非周期性を返す分岐](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)

ビブラートには有声窓だけを渡し、 `1200 log₂(F0 / 譜面F0)` のセント系列と元の格子番号を保持する。 `vibrato` は最長の連続区間を選び、同長では先頭を残す。対象となる条件は窓数×5 msが0.4秒以上。上流のファイル先頭の概要には0.35秒の記述があるが、実装のしきい値は `VIB_MIN_RUN = 0.4`。区間の平均と格子番号に対する最小二乗の直線傾斜を除き、残差 `r` の平均二乗 `E` を求める。遅延 `j` で重なる積の平均を `E` で割って自己相関を正規化する。最初の局所最大で0.5以上のものを選び、3点で放物線補間して周期の逆数をHzにする。受理範囲は4–9 Hz。最初の山から得た周波数が範囲外ならそこで終了する。深さは `√(2E)` セント。音符が対象外、残差0、該当の山なし、範囲外の各理由を分けて保存した。[音符の採取格子](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)・[ビブラート推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)

曲の要約とスコアでは母音の計画時刻が許容範囲にある音符を対象とする。ビブラートの検出割合は対象となる音符を分母とし、対象が0件なら欠測。深さと周波数は検出値の中央値。通常報告の各音符・曲の値に加え、調整用はスコアの列6・7・8・9・11の丸め前と照合した（0始まり）。確認用はスコアの区分集計を追加で照合した。固定上流の `compare::tests` に4.5、5.5、8.5 Hzの受理、10、12、40 Hzの棄却、ジッタと単調な音高変化の対照がある。 `golden_analysis` のYINの基準と `score` の生データの往復も確認した。[曲の集計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L905)・[スコア列](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/score.rs#L60)・[変調の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1329)・[基準分析](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L95)

## 既知周期と2曲の結果

50セントの合成セント系列の推定周波数は4.486、5.486、8.487 Hzで、深さは49.81〜49.95セントだった。10、12、40 Hzでは最初にとらえた山が受理範囲外になった。線形傾斜を加えても検出値は数値誤差内で一致した。159窓の連続系列は検出でき、中央の1窓を欠測にすると79窓ずつに分かれて対象外になった。79窓と80窓の境界および同長区間の選択も照合した。330 Hzの強い正弦波とゲート以下の同じ正弦波は、非周期性がともに0.000173。無音と波形外は1.0になった。[既知周期と弱い正弦波の結果](../runs/csd-vibrato-aperiodicity-20261121-a/summary.json)

| 曲 | 最長の連続有声区間（3波形） | ビブラート評価対象（各波形） | 録音の非周期性 | 固定上流 | 再実装 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `en001a` 調整用 | 320 ms | 0 | 0.005667 | 0.003551 | 0.000881 |
| `en005a` 確認用 | 290 ms | 0 | 0.004448 | 0.003096 | 0.000927 |

3波形合わせて26,217窓を照合した。ゲートで省かれた349窓の非周期性を補完し、F0の判定は保存値と一致した。音符・波形の組み合わせ54件で、補完の有無により非周期性の中央値が変化した。最大の差は確認用の第97音 `/tʃɝp/`。固定上流では24窓中15窓がゲート以下で、中央値は先行表の0.019915から1.435709になった。再実装も0.020950から1.428059へ変化した。固定上流・候補とも同音のF0取得は8窓。計算した正規化差は64.73954秒で1を超えた。調整用の丸め前のスコア列の最大差は `6.66×10⁻¹⁶`。実曲の最初の非周期性の差は両曲とも最初の音符の先頭窓で、 `en001a` の2.535秒では固定上流0.001815、再実装0.000508だった。[全音符と通常報告の照合](../runs/csd-vibrato-aperiodicity-20261121-a/summary.json)・[確認用の全窓](../runs/csd-vibrato-aperiodicity-20261121-a/artifacts/en005a-pitch-periodicity-frames.csv)

## 長母音の描画による対照

同じ成人女性の条件でMIDI 64の `/ɑ/` を1.6秒予約し、通常の再実装CLI `render-pcm --no-trace` と固定上流の比較用プローブを使った。上流の `matched` は再実装の初期姿勢、ゲイン、音高ドリフト量、ジッタ、シマーにそろえる。安定区間の0.83〜1.63秒の161窓はどちらの深さでもすべて有声で、波形差は上流と再実装の間で最大 `5.82×10⁻¹¹` だった。[対照のケース](../cases/csd-vibrato-long-vowel.json)・[固定上流の比較プローブ](../tools/upstream_csd_continuous_probe.rs)・[実測](../runs/csd-vibrato-long-vowel-20261121-a/summary.json)

35セントでは両合成PCMで **5.79058 Hz、33.94497セント**、上流の瞬時F0を平滑化F0で割った変調系列で **5.79130 Hz、34.10299セント**。0セントでは声門の変調残差が0、両合成PCMの残差RMSが0.0674セントで、相関の山は受理されなかった。深さを変えた最初のPCM差は48 kHzのフレーム16,401（約0.3417秒）。上流の歌唱計画はブレンド付きのビブラートジェスチャーを置くため、拍より前から波形が変わり得る。[PCMと声門の格子](../runs/csd-vibrato-long-vowel-20261121-a/artifacts/stable-frames.csv)・[ビブラートジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L115)

声門の5 ms格子を使い、セントの負側から正側へ移る時刻を線形補間して周期を別に測った。連続する4周期の逆数は6.038、5.850、5.710、5.718 Hzだった。固定上流の声門は32内部サンプルごとに位相を更新し、設定が6 Hzでも位相増分に `1 + 0.04 × drift_value` を掛ける。 `matched` で無効化したのは音高をセントで直接揺らすドリフト量で、位相増分には内部のドリフト値が使われる。位相増分と有限の測定窓が、推定の5.79 Hzにどれだけ寄与するかは別の対照が必要。[声門の位相更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L146)・[周期を読んだ格子](../runs/csd-vibrato-long-vowel-20261121-a/artifacts/stable-frames.csv)

## 実行と再開

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。実曲は17判定、長母音は6判定、固定上流の比較19試験と基準分析1試験を通過した。先行F0計測の通常経路も再実行してCSV、要約、候補WAVが一致した。新しい正式成果は実曲約4.08 MB、長母音約1.79 MB。作業用RTL9210B-CGにCSV・PCMを置き、長母音の高密度状態は先行計画に従って分析に使った161窓と元のハッシュ・サイズを記録した。[実曲の実行](../runs/csd-vibrato-aperiodicity-20261121-a/manifest.json)・[実曲の再実行](../runs/csd-vibrato-aperiodicity-20261121-repeat/manifest.json)・[長母音の実行](../runs/csd-vibrato-long-vowel-20261121-a/manifest.json)・[長母音の再実行](../runs/csd-vibrato-long-vowel-20261121-repeat/manifest.json)・[F0回帰](../runs/csd-acoustic-f0-en001a-20261121-aperiodicity-regression/manifest.json)

`research/experiments/chimera-rebuild` から新しい実行IDで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_vibrato_aperiodicity.py csd-vibrato-aperiodicity-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_csd_vibrato_long_vowel.py csd-vibrato-long-vowel-local-1
```

今の作業用CSDは登録済みの2曲のみ。録音のビブラートは、配布ZIPの注釈から安定区間で80窓以上を取り得る音符を先に探し、音響結果を見ずに調整用・確認用の曲を別ケースへ登録して検証する。[既存曲の選定条件](../cases/csd-song-planning.json)・[部分取得の既存処理](../tools/fetch_csd_inputs.py)
