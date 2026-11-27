# 確認曲 `en035a` での録音F0候補の独立照合

## 上流の経路と比較条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song()` は録音・合成それぞれに解析器を作り、`Analyzer::note()` にPCMと音符の注釈を渡す。`note()` は音符内の5 ms格子で `pitch()` を呼ぶ。`pitch()` は曲の最低音から定めた長さのPCM窓を取り、譜面音高の±7半音を `yin_pitch()` に渡す。最終的な有声判定にはPCM窓の平均二乗電力と曲ごとのゲートを使う。`note()` は得られたF0を譜面からのセント差、ビブラート、H1−H2に使う。[曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[窓と集計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L499)

`yin_pitch()` は各遅延 `τ` について固定数のサンプル対の二乗差 `D(τ)` を計算する。遅延はサンプル単位で、無次元の累積平均正規化差（CMND）は `τD(τ) ÷ ΣD(1..τ)`。探索下限から、最初に閾値0.2を下回った点を探し、CMNDが下がる間だけ遅延を進める。停止点の両隣を使う放物線補間で遅延を精密化し、標本化周波数をその遅延で割ってF0をHzで返す。非周期性には補間前の停止点のCMNDを返す。閾値を下回る点が無い場合のF0は0で、非周期性には探索範囲内の最小CMNDを返す。[YINの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)・[分析の参照値試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L229)・[周期変調の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)

事前登録では第36音 `/dɹimz/`（0起算35）の49.72006秒を固定し、20 msの波形相関と40 msの倍音間隔がそれぞれ長い候補の12 Hz以内に入ると予測した。元のPCMの閾値を0.15にする対照と、同じPCMを1.2 kHzで前後方向に低域通過して閾値0.2を使う対照は個別に測った。有声ゲートは両対照とも元のPCMに基づく。調整曲で使った316.8・348.4 Hzに加え、今回の候補に近い276.3・301.1 Hzの4倍音波形でも照合した。[今回の事前登録](../cases/csd-f0-recording-period-evidence-held-out.json)・[調整曲の計測条件](csd-f0-recording-period-evidence.md#読解と比較条件)

計測CLIは固定上流の比較報告、長音符用の保存済み録音と描画、全曲比較の追跡係数を読み、保存済み83窓の状態、F0、CMND、選択ラグ、電力を照合する。通常の安定区間は49.71506秒から始まる。焦点前後5点の条件を満たすため、音符内の49.69506〜49.71006秒に補助4窓を置いた。補助窓を含むCSVは窓番号−4〜6で、保存済み83窓の追跡は元の範囲で行う。[計測CLI](../tools/measure_csd_f0_recording_period_evidence.py)・[全曲比較](csd-f0-continuity-songs.md#実測)

## 実測

録音は44,100 Hzで、YIN窓の893サンプルから各遅延について655対を比較した。探索範囲は106〜238ラグ。第36音で最初に選択が変わった通常窓は49.71506秒で、298.44 Hzから274.93 Hzへ移った。最大差は次の49.72006秒の148.53セントだった。[窓ごとの判定](../runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/summary.json)

| 49.72006秒の観測 | F0または倍音間隔 |
| --- | ---: |
| 従来のYIN・閾値0.2 | 301.06 Hz（146ラグ） |
| YINの窓ごとの候補選択・追跡 | 276.30 Hz（160ラグ） |
| 20 msの正規化相関 | 276.23 Hz |
| 20 msのスペクトルの倍音間隔 | 275.50 Hz |
| 40 msのスペクトルの倍音間隔 | 275.75 Hz |
| 元のPCMでYINの閾値を0.15に変更 | 276.30 Hz（160ラグ） |
| 1.2 kHz低域通過後のYIN・閾値0.2 | 275.58 Hz（160ラグ） |

焦点の相関は146ラグで0.79009、160ラグで0.96045だった。40 msの10ピークのうち、各候補の整数倍から24 Hz以内に入ったのは短い候補で1本、長い候補で6本だった。前後を含む11窓で長い候補との差は相関で最大0.67 Hz、40 msの倍音間隔で最大1.02 Hzだった。既知の4波形の最大誤差は0.15 Hzだった。[ラグ別の相関](../runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/artifacts/normalized-correlation.csv)・[FFTのピーク](../runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/artifacts/spectral-peaks.csv)

| ラグ `τ` | 総二乗差 `D(τ)` | 1.2 kHz未満 | 1.2〜3 kHz未満 | 3 kHz以上 | CMND |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 145 | 0.714055 | 0.503369 | 0.097195 | 0.113492 | 0.207702 |
| 146 | 0.679912 | 0.441956 | 0.142524 | 0.095432 | 0.198863 |
| 147 | 0.676679 | 0.384104 | 0.198616 | 0.093960 | 0.199004 |
| 160 | 0.129736 | 0.005767 | 0.058306 | 0.065662 | 0.040973 |

元のPCMからスカラーで二乗差を再計算し、閾値0.2を最初に下回るのが146ラグ、0.15を最初に下回るのが156ラグと確認した。146→147では1.2〜3 kHzの差が0.05609増え、1.2 kHz未満の減少0.05785をほぼ相殺した。総二乗差は0.00323減ったが、`τD(τ)` は0.206%増え、累積和の増加は0.136%だったため、正規化後にCMNDが上がり146で停止した。調整曲では同じ帯域の増加で総二乗差も増えた。確認曲では累積平均による正規化の段階で局所最小が現れた。帯域別の和と二乗差の最大相対差は2.14×10⁻¹⁶だった。[二乗差とCMND](../runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/summary.json)・[調整曲の帯域比較](csd-f0-recording-period-evidence.md#実測)

前後11窓で長い候補から8 Hz以内に入ったのは、閾値0.15で10窓、低域通過で11窓だった。補助窓49.69506秒では短い候補のCMNDが0.148142で、閾値0.15でも287.01 Hzが選ばれた。その窓の相関は269.24 Hz、40 msの倍音間隔は269.25 Hz、低域通過後は269.21 Hzだった。二つの音符で評価したのは録音の音響周期で、声帯振動の独立した参照記録と試聴評価は未取得である。[補助窓を含む測定結果](../runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/summary.json)

## 再現

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1、Rust 1.94.1で実行した。研究ワークスペースでは次のコマンドを使う。`/private/tmp` からの再実行ではPython・スクリプト・ケースを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python \
  tools/measure_csd_f0_recording_period_evidence.py csd-f0-recording-period-evidence-held-out-local \
  --case cases/csd-f0-recording-period-evidence-held-out.json
```

両実行で各6判定・4予測と固定上流20試験が通過し、要約・相関CSV・スペクトルCSVはバイト一致した。旧ケースの既定コマンドでも同じ3ファイルが従来の保存基準と一致した。3実行のマニフェストに載る108入力・18出力をサイズとSHA-256で確認した。マニフェストに記載された採取物259,380バイトは作業用RTL9210B-CGにあり、録音と長曲の描画は保存済みファイルを参照した。[初回](../runs/csd-f0-recording-period-evidence-held-out-20261122-a/manifest.json)・[別ディレクトリの再実行](../runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/manifest.json)・[調整曲の回帰](../runs/csd-f0-recording-period-evidence-20261122-held-out-regression/manifest.json)
