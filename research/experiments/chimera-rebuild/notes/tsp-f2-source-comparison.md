# 同じ母音の録音と合成でF2候補の差を追う

前回の候補レポートから、録音 `MK61_01` の `seems` に対応する強勢母音 /i/ を1つ選んだ。基準の中央窓で録音が採った約1 kHzの極は、固定上流と研究版の公開極には見えず、2.3 kHz付近に3音源で比較できる候補がある。比較帯域を850〜1150 Hzと2050〜2500 Hzに登録した。録音との差は高域極どうしを比べると150 Hz以内に縮まり、低域の候補差はF1からの200 Hz間隔より前に生じると予測した。各音源の相対的な母音時刻で揃える。元のPCMの時間や励振位相を揃える比較とは条件が異なる。[候補レポート](tsp-f2-candidate-report.md)・[事前登録](../cases/tsp-f2-source-comparison.json)

固定上流の `compare tsp` から `run`、`measure_pair`、`measure`、`Sig::formants` を辿った。音素対応は `match_phones` が決め、単母音の区間ごとに12 kHz・25 msの窓を取る。標準評価に用いる中心は35・50・65%で、今回は音素境界近くの窓への感度を調べた先行の10・90%も残す。 `Sig::new` の最初の `decimate` は48 kHz録音と合成を、カットオフ5,400 Hz・95タップのBlackman窓付きsincで低域通過し、入力の4標本ごとに1標本を出力する。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[音素の対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[採択と中央値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)

各窓で前標本を0とし、`x[n] - 0.97 x[n-1]` にHamming窓を掛ける。自己相関を求め、40 Hzを尺度とするラグ窓を掛け、Levinson–Durbin法で次数14の係数と残差を求める。Durand–Kerner法で得た根の偏角が周波数 `arg(z) fs/(2π)`、半径が帯域幅 `-log(|z|) fs/π` を与え、いずれもHzで記録する。上半平面で150 Hz以上、帯域幅600 Hz以下の極を周波数順に公開する。周波数1,300 Hz未満・幅500 Hz未満の先頭がF1で、F1より200 Hzを超えて上かつ3,500 Hz未満の先頭がF2となる。固定Rustと独立したToeplitz解法を照合し、候補が生根、公開極、F2適格性、最終の周波数順のどこで異なるか記録する。[LPCの実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[TypeScript由来の比較試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L187)・[TSPの欠測処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

各窓で選ばれたF2を `S`、登録した高域の最初の適格極を `H` とする。合成と録音の差 `S合成 - S録音` を、`(H合成 - H録音) + (H録音 - S録音) + (S合成 - H合成)` と書き、同じ帯域を比較したときの差と、各音源内での採択先の差を記録する。窓別の差と母音中央値は個別に計算する。高域で対応させた極を、実録音の正解F2とは扱わない。

## 3音源の標準窓と端の窓

母音の相対時刻が35・50・65%の3窓では、録音で約1 kHzの低域極が第1候補で、高域極は第2候補だった。固定上流と研究版は高域極が第1候補で、両版の6窓とも850〜1150 Hzの極は生根の段階から得られなかった。合成側のF1を録音側の値へ固定しても、全6窓で合成の選択は保たれた。採択値の差は1,192.04〜1,320.22 Hzで、同じ高域の候補同士の差は−111.36〜+4.16 Hzだった。事前の予測3件が成立した。

| 音源 | 母音中央の採択F2 | 母音中央の高域候補と順位 | 標準3窓の採択中央値 | 標準3窓の高域候補の中央値 |
| --- | ---: | ---: | ---: | ---: |
| 録音 | 993.37 Hz | 2,323.81 Hz・第2候補 | 993.17 Hz | 2,309.23 Hz |
| 固定上流 | 2,228.15 Hz | 2,228.15 Hz・第1候補 | 2,228.15 Hz | 2,228.15 Hz |
| 研究版 | 2,212.45 Hz | 2,212.45 Hz・第1候補 | 2,212.45 Hz | 2,212.45 Hz |

中央で研究版の採択値は録音より1,219.08 Hz高かった。同じ高域の極を比べると研究版の方が111.36 Hz低い。録音内で993.37 Hzを採ったことが、この窓での差に1,330.44 Hzを加えた。母音開始側10%では録音にも低域の生根がなく、3音源とも高域を採った。このとき合成と録音の差は−177.38〜−157.18 Hzで、標準窓に登録した150 Hzの範囲を外れた。次は合成2版の母音中央で、声道断面から計算した線形共鳴を、PCMで観測した高域極と照合する。[15窓の根と適格性](../runs/tsp-f2-source-comparison-20261123-repeat/summary.json)

## 検証と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で測定した。3音源のWAVを先行マニフェストに照合し、SciPyは録音に付いた非音声チャンクを読み飛ばした。固定上流の生根と独立計算の最大複素距離は1.78×10⁻¹²。先行の公開極と独立計算はナイキストの対応を含めて最大3.46×10⁻¹¹ Hzで一致した。窓の採択と中央値を保存済みのTSPへ照合した。4判定、固定上流のLPC基準1試験・TSP 6試験を各回で通過し、`/tmp` からの再実行で要約・固定上流出力・窓のNPZはバイト一致した。波形とログの実体はRTL9210B-CGに保存した。[初回](../runs/tsp-f2-source-comparison-20261123-a/manifest.json)・[再実行](../runs/tsp-f2-source-comparison-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_source_comparison.py tsp-f2-source-comparison-new
```
