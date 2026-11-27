# CSDの確認用全曲で実測F0と倍音の対照を照合する

確認用 `en005a` の全36句、106音符を登録した。録音はCSD v1.1の44.1 kHz・2チャンネルPCM16。固定上流の比較結果とモデル出力は先行実行のハッシュで照合し、再実装は同じ音符と絶対時刻から48 kHzのWAVを生成した。調整用と同じ90%の被測定音符の条件を106音符へ換算すると96音符になる。音高差の大きさは観測値として扱う。倍音の対照も計測前に条件を登録した。[確認用ケース](../cases/csd-acoustic-f0-en005a.json)・[探索上限の対照](../cases/csd-f0-upper-bound-en005a.json)・[調整用と確認用の分割](csd-song-planning.md)

## 上流経路と比較条件

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare::csd` から `compare_song` を呼ぶ。 `render_notes` は録音長の出力時計に各句と音符を置く。 `Analyzer::note` は注釈の先頭30%と末尾20%を除いた範囲で、5 msごとに同じ秒座標を使う。メリスマは先頭・末尾を各10%除く。 `Analyzer::new` は曲の最低音−7半音の2.5周期分を窓幅（サンプル数）とし、区間電力から波形ごとのゲートを決める。 `Analyzer::pitch` では各音符の譜面F0から上下7半音の範囲で、遅延差の累積平均正規化値が0.2を下回る最初の谷を使う。推定値はHzで保持し、 `1200 × log₂(実測F0 / 目標F0)` でセントへ変換して音符ごとの中央値を求める。固定上流の `golden_analysis` はYIN推定値を、 `compare::score::tests::every_fifth_song_is_held_out_in_both_keys` は確認用の分割を検証する。[固定上流の音符測定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L450)・[YINの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)・[曲の分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/score.rs#L81)

既存の `measure_csd_song_f0.py` をケース指定で再利用した。2曲で音符窓、電力、探索範囲の設定は一致する。確認用の全曲の計画を一つの発声器で描画し、全長と同じ計画を6秒で打ち切った出力を照合した。CSV付きの先行基準との照合には、調整用の同じ2句を使用した。両合成はモノラル48 kHz、録音は2チャンネルの平均を44.1 kHzのまま計測した。音符のF0と有声率は、上流の通常レポートと独立したPython実装で照合した。[計測器](../tools/measure_csd_song_f0.py)・[調整用の窓と検査](csd-acoustic-f0-en001a.md#固定上流の測定)

## 確認用の結果

録音長の3,544,616フレームを描画した。128・77フレーム分割の全曲WAVがバイト一致し、6秒に切った計画の先頭288,000フレームも全曲と一致した。調整用のCSVの有無の回帰も通過した。各波形で4,707のフレーム中心を測定し、全106音符でF0を取得した。固定上流の通常レポートに対して、録音と上流合成のセント値の差は最大0.005セント未満、有声率の差は最大0.00490だった。[全音符とWAV](../runs/csd-acoustic-f0-en005a-20261121-final/summary.json)・[比較図](../runs/csd-acoustic-f0-en005a-20261121-final/artifacts/note-f0.png)

| 波形 | F0を取得した音符 | 有声フレーム | 電力ゲートで除外 | 周期不検出 | 譜面との絶対差の中央値（セント） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 録音 | 106 | 4,389 | 22 | 296 | 20.25 |
| 固定上流 | 106 | 4,496 | 92 | 119 | 6.25 |
| 候補 | 106 | 4,495 | 92 | 120 | 7.54 |

全106音符での録音とのF0絶対差の中央値は固定上流17.98セント、候補19.25セントで、両合成の間では2.78セントだった。最初の音符 `/bʌ/` の窓では録音529.077 Hz、固定上流524.799 Hz、候補525.516 Hzが中央値で、最初の採取時刻3.83075秒から3者の推定値に差があった。両合成の有声判定が分かれたのは第58音 `/tɝ/` の43.21648秒の1フレーム。どちらも電力ゲートを通過し、YINの正規化差が固定上流0.179、候補0.210で、0.2のしきい値をまたいだ。音符全体のF0中央値は両合成で取得できた。[フレームごとのF0・電力・欠測](../runs/csd-acoustic-f0-en005a-20261121-final/artifacts/note-f0-frames.csv)

## 探索上限の対照

全106音符を使い、通常条件に保存した各フレームの中心秒をそのまま読み、下限−7半音、電力ゲート、窓長を固定して上限だけを+7から+5半音へ変更した。両合成が同時に+600セント以上を返したフレームは0。録音・固定上流・候補の14,121フレームすべてでF0（欠測を含む）と有声判定が一致した。調整用で見つけた第3倍音による誤推定は、この曲では比較できる例がなかった。通常条件と対照を別実行にし、両方の数値を保持した。[所定の対照条件](../cases/csd-f0-upper-bound-en005a.json)・[全音符の対照と集計](../runs/csd-f0-upper-bound-en005a-20261121-a/summary.json)・[対照の全フレーム](../runs/csd-f0-upper-bound-en005a-20261121-a/artifacts/upper-bound-frames.csv)

## PCMの最初の差を調べた対照

口端放射と声門の差を調べるため、初回の全曲実行とは別に同じ音符から先頭960フレームの状態を採取した。候補と通常固定上流のPCMは、それぞれ先行の全曲WAVの先頭と一致した。フレーム0のゲートは両方0、平滑化F0は113.835620 Hz。瞬時F0は通常固定上流113.840657 Hz、候補113.835620 Hzで、通常上流の偏差 `+0.0766053` セントは調整用の独立計算値と一致した。口端流量も同フレームで通常上流0、候補 `−3.1660×10⁻⁷ cm³/s` と分かれた。通常条件のPCM差が `1×10⁻⁶` を初めて超えたのはフレーム13。姿勢、変動設定、ゲインを合わせた対照では、先頭20 msのPCMの最大絶対差は `2.12×10⁻²²` まで縮んだ。調整した設定の個別の寄与と歌唱中の波形への影響は未分離。[先頭20 msの対照条件](../cases/csd-acoustic-f0-en005a-startup.json)・[状態差とPCM](../runs/csd-acoustic-f0-en005a-startup-20261121-a/summary.json)・[調整用での独立式](csd-continuous-song.md#実測)

## 実行と保存

実行環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4。確認用の通常計測は各8判定、探索上限の対照は各4判定、先頭20 msの対照は5判定を通過した。通常計測で固定上流の比較と音響分析の20試験を実行した。ケース指定を加えた後の調整用の再実行は、以前のWAV、F0のCSV、要約とバイト一致した。通常計測の正式成果はRTL9210B-CGに約17.66 MB、探索上限の対照は約1.53 MB。[通常の実行条件とハッシュ](../runs/csd-acoustic-f0-en005a-20261121-final/manifest.json)・[調整用の回帰](../runs/csd-acoustic-f0-en001a-20261121-regression/summary.json)

`research/experiments/chimera-rebuild` で新しい実行IDを指定して再実行する。対照が参照する通常例はケースの実行IDで固定してある。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 ../../.venv/bin/python tools/measure_csd_song_f0.py csd-acoustic-f0-en005a-local-1 --case cases/csd-acoustic-f0-en005a.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_f0_upper_bound.py csd-f0-upper-bound-en005a-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_f0_startup.py csd-acoustic-f0-en005a-startup-local-1
```
