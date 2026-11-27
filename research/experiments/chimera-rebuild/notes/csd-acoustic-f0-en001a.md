# CSDの調整用1曲で実測F0を比較する

CSD v1.1の調整用 `en001a` を使う。前回の実験で計画を確認した全50句・86音符を、候補CLIで64.8秒のモノラル48 kHz float32 WAVへ描画する。比較対象はハッシュを確認した実録音（44.1 kHz・2チャンネルPCM16）と、固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の通常比較で得た全曲WAV。録音はチャンネル平均にして、各波形は元のサンプルレートで計る。音声の時間座標はファイル先頭を共通の原点とする。[登録条件](../cases/csd-acoustic-f0-en001a.json)・[注釈と歌唱計画の照合](csd-song-planning.md)・[先頭2句の状態の比較](csd-continuous-song.md)

## 固定上流の測定

`compare::csd` から `compare_song` を呼び、注釈のMIDI番号と開始・終了秒を `Analyzer::note` に渡す。通常の音符では先頭30%と末尾20%を除き、メリスマでは各端10%を除く。残る範囲の始点から5 ms間隔で波形の窓を採る。 `Analyzer::new` は曲内の最低MIDIより7半音低い周波数を基準に、最低周波数の2.5周期分を窓のサンプル数とする。 `Analyzer::pitch` は同じ長さの窓を中心秒のサンプル番号から切り出し、探索範囲は各音符の譜面音高から上下7半音に限る。波形ごとに10 ms区間の平均二乗を並べ、床−80 dBを適用し、昇順の95%位置の値を基準に35 dB下を有声判定の電力下限とする。[上流の窓とゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L450)・[上流の音符別計測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)・[上流の音量包絡](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L728)

`yin_pitch` は遅延 `k` サンプルに対して共通の幅で `Σ(xᵢ−xᵢ₊ₖ)²` を求める。累積平均で正規化した値が0.2を下回る最初の谷を選び、隣り合う3点で遅延を補間する。F0はサンプルレートを補間後の遅延で割ったHz。有声の中央値は `1200 × log₂(実測F0 / MIDIの目標F0)` のセントでも保存する。候補の計測器は NumPyの独立YINを再利用し、範囲外、電力不足、周期が見つからない場合を各フレームで記録する。固定上流の通常レポートのF0偏差と有声率に照合し、既知330 Hz、無音、ファイル外に窓が出る条件も別に検査する。固定上流の `golden_analysis` はYINの基準出力と照合し、`compare::tests` は変調音や欠測を検証する。[YINの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)・[固定上流の基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L230)・[候補の計測器](../tools/measure_csd_song_f0.py)

## PCMの出力経路

候補の通常の `render-pcm` に `--no-trace` を追加した。共有のWAV出力経路は発声器、ブロック分割、間引きと出力段を通った同じPCMを書き、指定時は出力段のCSVを作らない。先行する2句の測定では全長の出力段CSVだけで1.67 GBあった。音高計測はWAVを読み、音符窓の検査に使う小さなCSVを別に保存する。全曲を128・77フレームずつ描画した比較に加え、前回と同じ2句の入力で、CSVを省いたWAVを既存のCSV付きWAVに照合する。[共有PCM出力](../crates/vocal-cli/src/network_case/pcm.rs)・[前回の容量の記録](csd-continuous-song.md#実行と保存)

## 全曲の測定

候補は50句・86音符を描画し、録音長と同じ3,110,400フレームになった。128・77フレーム分割でWAVはバイト一致し、前回と同じ先頭2句の入力はCSVの有無でも一致した。全曲の最初の192,000フレームも既存の2句の描画と一致した。通常上流とのPCMはフレーム0でビット差があり、フレーム13で絶対差が `1×10⁻⁶` を超えた。全曲の最大差は1.4581。先行する同じ先頭区間では、フレーム0の瞬時F0と口端流量まで差を遡っている。[全曲のPCM・計画・指標](../runs/csd-acoustic-f0-en001a-20261121-final/summary.json)・[先頭の状態を調べた対照](csd-continuous-song.md#実測)

| 波形 | F0を取得した音符 | 有声フレーム | 電力不足 | 周期不検出 | 譜面との絶対差の中央値（セント） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 録音 | 86 | 3,772 | 35 | 225 | 11.62 |
| 固定上流 | 86 | 3,859 | 53 | 120 | 5.95 |
| 候補 | 86 | 3,859 | 55 | 118 | 5.20 |

各波形の4,032フレームで同じ中心秒を使った。上流の通常レポートに対し、録音と固定上流の各音符のセント値を最大0.005セント未満、有声率を最大0.005の丸め幅で再現した。録音に対する音符ごとのF0絶対差の中央値は固定上流11.58セント、候補12.01セント。候補と固定上流の間は3.34セントだった。最初の音符の窓は2.535〜2.760秒で、中央値は録音277.829 Hz、固定上流279.853 Hz、候補279.292 Hz。先頭の計測時刻2.535秒で、2合成の推定値にはすでに差があった。既知330 Hzの波形では44.1 kHzで330.0055 Hz、48 kHzで330.0031 Hzを得た。[フレーム別のF0と欠測](../runs/csd-acoustic-f0-en001a-20261121-final/artifacts/note-f0-frames.csv)・[全音符の図](../runs/csd-acoustic-f0-en001a-20261121-final/artifacts/note-f0.png)

## 4音符の倍音を調べた対照

通常条件で両合成が600セント以上高く推定された音符は、0始まりで29、30、72、73だった。すべて譜面のMIDI 61（277.183 Hz）で、`/naʊ/` と `/aɪ/` が2回ずつ現れた。初回の成績を基準として固定し、この4音符について探索上限だけを+7から+5半音に狭める別ケースを登録した。フレーム、下限−7半音、波形とゲートが同じため、変化は短い遅延を探索から外した効果として比較できる。[対照の登録](../cases/csd-f0-third-harmonic-en001a.json)・[対照の実行結果](../runs/csd-f0-third-harmonic-en001a-20261121-verified/summary.json)

21.940秒では、40 msのHann窓で得た最大スペクトルピークが固定上流833.50 Hz、候補836.43 Hzで、第3倍音付近だった。同じ時刻のF0を最も近い整数遅延に戻すと、通常条件では115・114サンプルで、正規化差は0.129・0.117。譜面付近の173・172サンプルの遅延では0.00162・0.00077だった。YINは正規化差が0.2を下回る最初の谷を選ぶので、後に現れる正規化差の小さい谷に進まなかった。上限だけを狭めると4音符のF0中央値が両合成とも譜面の16セント以内に収まり、録音の4音符の値と全12組の有声フレーム数は一致した。277.183 Hzとその第2・第3倍音の既知波形でも、通常条件の415.982 Hzが上限変更で277.189 Hzになった。通常条件のレポートも保存した。[通常条件](../runs/csd-acoustic-f0-en001a-20261121-a/summary.json)・[スペクトルと遅延の照合](../runs/csd-f0-third-harmonic-en001a-20261121-verified/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4。通常計測は初回と `/tmp` からの再実行で各8判定、第3倍音の対照は各5判定、固定上流の比較19試験と `golden_analysis` 1試験、候補CLIのClippyを通過した。従来のCSVを指定した `song-voice-flat` は既存のWAVとCSVを再現した。正式成果はRTL9210B-CG上の約14.31 MB。全長のCSVを作らず、複製のWAVはハッシュが一致した後に作業用の一時出力から取り除いた。録音のSHA-256、登録した先行成果のハッシュ、実行引数はマニフェストにある。[正式実行](../runs/csd-acoustic-f0-en001a-20261121-final/manifest.json)・[対照の実行](../runs/csd-f0-third-harmonic-en001a-20261121-verified/manifest.json)

`research/experiments/chimera-rebuild` で、新しい実行IDを指定して再実行する。第3倍音の対照の基準は最初の全曲計測に固定している。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 ../../.venv/bin/python tools/measure_csd_song_f0.py csd-acoustic-f0-en001a-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_f0_third_harmonic.py csd-f0-third-harmonic-en001a-local-1
cargo clippy --locked --offline -p vocal-cli -- -D warnings
```
