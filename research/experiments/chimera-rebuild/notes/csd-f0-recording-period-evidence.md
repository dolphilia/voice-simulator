# CSD録音のF0候補を独立に照合

## 読解と比較条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song()` は録音・合成と音符の注釈を `Analyzer::note()` に渡す。音符内の5 ms格子で `Analyzer::pitch()` がPCM窓と譜面周波数を受け取り、平均二乗電力で有声を判定する。`yin_pitch()` は、遅延 `τ` ごとの二乗差 `D(τ)` を同じ数のPCM対から計算する。累積平均正規化差（CMND）は `τD(τ) ÷ ΣD(1..τ)`。短い遅延から閾値0.2を下回った最初の傾斜を局所最小まで進み、隣接3点の放物線で補間した遅延からF0をHzで求める。`Analyzer::note()` のH1−H2とビブラートは、このF0を参照する。固定上流にはYINを移植元の値と照合する試験と、既知の周期変調からビブラートを読む試験がある。[曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[窓と電力ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L499)・[YINの計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)・[分析試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L229)・[周期変調の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)

全曲比較で録音の推定差が最大だった `en001a` の第65音 `/vi/`（0起算64）について、保存済みの47窓を同じPCMと費用係数で再現する。最大差の49.42564秒と前後5窓では、20 msの波形のラグごとに、重なる両側の平均を個別に引き、内積を両側のノルムの積で割る。最大相関のラグを補間してF0を求める。もう一つの観測では、同じ中心の20 ms・40 msのHann窓でFFTのピークを検出し、200〜450 Hzの0.25 Hz格子でピークが整数倍と整合する間隔を探す。各ピークの最寄りの倍音からの誤差は24 Hzで打ち切り、二乗誤差平均が最小の間隔を採る。3本以上のピークが支持する間隔を使う。どちらもYINのCMNDや譜面の距離を候補の評価に使わない。正規化相関の窓は、重なる区間のノルムをラグごとに計算する。[事前登録](../cases/csd-f0-recording-period-evidence.json)・[計測ツール](../tools/measure_csd_f0_recording_period_evidence.py)・[窓と相関の原典](https://fon.hum.uva.nl/archive/1993/1993-ifaproc17-Boersma.pdf)

既知の316.8 Hzと348.4 Hzの波形で、正規化相関と倍音間隔の両方を先に照合する。録音には、元のPCMの閾値だけを0.15にする対照と、1.2 kHzの4次Butterworth低域通過を前後方向に適用して同じ窓を測る対照を個別に置く。低域通過でも元の有声判定を使う。焦点の候補ラグと隣接ラグは、YINと同じ固定長の差分列の片側FFTから帯域別の二乗和を求め、パーセバルの等式で総和を照合する。これらは録音の周期候補を調べる研究用の比較条件である。[ケースの判定](../cases/csd-f0-recording-period-evidence.json)

## 実測

保存済み47窓の通常・上限変更・窓ごとの候補選択・時間費用の4条件を再現した。第65音で最初に選択が変わったのは49.34064秒で、336.01 Hzから308.79 Hzへ移った。最大差は49.42564秒の164.41セントで、従来条件は127ラグ・348.39 Hz、候補選択と追跡は139ラグ・316.83 Hzだった。録音レート44,100 Hz、YIN窓596サンプル、差分に使う対は384個で、探索ラグは94〜212。短い候補のCMNDは0.196794、長い候補は0.012461だった。[第65音の再実行](../runs/csd-f0-recording-period-evidence-20261122-verified-a/summary.json)

| 49.42564秒の観測 | F0または倍音間隔 |
| --- | ---: |
| 従来のYIN・閾値0.2 | 348.39 Hz |
| YINの候補費用で選んだ値 | 316.83 Hz |
| 20 msの正規化相関 | 315.84 Hz |
| 20 msのスペクトルの倍音間隔 | 316.00 Hz |
| 40 msのスペクトルの倍音間隔 | 316.25 Hz |
| 元のPCMでYINの閾値を0.15に変更 | 316.83 Hz |
| 1.2 kHzの低域通過後、YINの閾値0.2 | 315.81 Hz |

焦点の正規化相関は127ラグで0.77845、139ラグで0.97721だった。40 msのFFTでは検出された7本すべてが316.83 Hzの整数倍から24 Hz以内に入り、348.39 Hzでは該当するピークが0本だった。前後を含む11窓で、時間費用まで適用した候補との差は正規化相関で最大0.99 Hz、40 msの倍音間隔で最大1.04 Hzだった。既知の316.8・348.4 Hzの波形ではどの方法も真値の0.11 Hz以内だった。この窓の録音の繰り返しは約316 Hzを支持する。声帯振動の独立した参照記録と実際の聴感は未取得である。[FFTのピーク](../runs/csd-f0-recording-period-evidence-20261122-verified-a/artifacts/spectral-peaks.csv)・[ラグごとの正規化相関](../runs/csd-f0-recording-period-evidence-20261122-verified-a/artifacts/normalized-correlation.csv)

焦点のCMNDは126・127・128ラグで0.197152・0.196794・0.200809だった。生PCMからスカラーの二乗差を計算し直しても、閾値0.2を最初に下回るラグは126で、次に127へ進んで止まった。閾値0.15では135から139ラグへ進んだ。127から128に進むと、1.2 kHz未満の二乗差は0.05146減るが、1.2〜3 kHzは0.05989増える。3 kHz以上を含む総和は0.00802増え、短い側の局所最小ができた。帯域別の和と元の二乗差の最大相対差は1.93×10⁻¹⁶だった。フィルタ後の焦点では、従来の閾値0.2で140ラグが選ばれた。高い帯域が短い側の極小を作る寄与はこの窓で観測した。閾値変更と低域通過の一般化は別の録音で評価する。[帯域別の差分エネルギー](../runs/csd-f0-recording-period-evidence-20261122-verified-a/summary.json)

## 再現

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1、Rust 1.94.1で実行した。研究ワークスペースと `/private/tmp` で同じケースを実行した。別ディレクトリではPythonとスクリプトを絶対パスで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python \
  tools/measure_csd_f0_recording_period_evidence.py csd-f0-recording-period-evidence-local
```

全曲比較の費用係数のスナップショットと録音を基準マニフェストでも照合するようにした後、両ディレクトリで再実行し、各6判定と4予測が成立した。固定上流の比較試験19件と分析試験1件も通過した。初回を含む4実行の要約・相関CSV・スペクトルCSVはバイト一致した。112入力・24出力をサイズとSHA-256で照合し、新しい採取物の実体342,425バイトをRTL9210B-CGに保存した。[初回](../runs/csd-f0-recording-period-evidence-20261122-a/manifest.json)・[最初の再実行](../runs/csd-f0-recording-period-evidence-20261122-repeat/manifest.json)・[参照照合後](../runs/csd-f0-recording-period-evidence-20261122-verified-a/manifest.json)・[別ディレクトリからの再実行](../runs/csd-f0-recording-period-evidence-20261122-verified-repeat/manifest.json)
