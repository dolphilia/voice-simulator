# 追加共鳴780 Hzで励振位相とF2採択を比較する

F0 125 Hz・追加共鳴760 Hzの先行対照では、次の低域極が採択F1から最も離れた位相でも、次数12で199.31 Hz、次数14で195.97 Hzだった。800 Hzを追加した先行の遅延0では、次数12で228.66〜235.22 Hz、次数14で217.78〜218.95 Hz離れ、全6窓で低域極を採った。両端の測定を手掛かりに、中点780 Hzでは次数12が全位相で200 Hzを超え、次数14では位相に応じて境界の両側に分かれると予測した。候補の間隔に加え、設計F2近傍の極が採択条件を満たして残るか確認する。[760 Hzの全位相](tsp-f2-intervening-phase.md)・[800 Hzの遅延0](tsp-f2-intervening-excitation.md)・[事前登録](../cases/tsp-f2-intervening-phase-midpoint.json)

`chimera-cli` の `compare tsp` は `measure_pair` で録音と合成の音素を揃え、`Sig::formants` が12 kHzの系列から300標本の窓を3本取る。LPCは窓ごとに前標本を0から始め、`x[n] - 0.97 x[n-1]` にHamming窓を掛ける。自己相関には40 Hzを尺度とするラグ窓を掛け、Levinson–Durbin法で次数12または14の係数を更新し、Durand–Kerner法で複素根を求める。複素根の偏角から周波数、半径の自然対数から帯域幅をHzで計算する。公開極は正の虚部、150 Hz以上、帯域幅600 Hz以下とし、周波数昇順に並べる。F1は1,300 Hz未満かつ幅500 Hz未満の先頭、F2は `F1 + 200 Hz < F2 < 3500 Hz` を満たす先頭で、両者を拾えた窓について中央値を返す。この比較は、中央値が隠し得る窓ごとの採択を観測する。固定Rustの公開極と生根を、独立したToeplitz行列の解と複素根に照合する。固定版のTypeScript対照試験と、TSPの整列・欠測を含む試験も実行する。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[TSPの採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[LPC](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[LPC基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[TSP試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

## 780 Hzの実測

F0 125 Hzと幅140 Hzを固定し、励振を0〜95標本の範囲で遅らせた。他の共鳴は620・2075・2915 Hz、LPCの窓は中央0.35・0.50・0.65秒の25 ms。760 Hzの対照と全576窓の相対位相、時刻、次数を揃えた。780 Hzにすると462窓で追加共鳴付近が採択され、いずれの窓でも、2075 Hzから120 Hz以内でF2の条件を満たす公開極が残っていた。生根の推定や公開極の選別で設計F2付近が消える例はなく、最終採択で先に来る低域極が選ばれた。予測3件が成立し、欠測と間隔の規則の例外は0件だった。

| LPC次数 | 追加共鳴の近傍を採った位相 | 設計F2の近傍を採った位相 | F1と低域極の間隔 | 200 Hzをまたいで採択が変わった隣接位相の組 |
| --- | ---: | ---: | ---: | ---: |
| 12 | 96 | 0 | 205.07〜214.47 Hz | 0 |
| 14 | 58 | 38 | 198.47〜209.62 Hz | 12 |

たとえば次数14で相対位相26から27標本へ移ると、低域極とF1との差は203.893 Hzから199.952 Hzへ減る。位相26では838.061 HzがF2に選ばれ、設計F2側の2049.525 Hzも候補に残る。位相27では低域極828.818 Hzの間隔が足りず、2066.041 Hzが選ばれる。12 kHzの1標本は約83 µsで、両窓ともF2上限より十分下に2つの公開極がある。次は登録済みの実録音窓で、観測された低域と高域の極に同様の候補関係があるかを照合する。実録音でどちらが妥当なF2かは、人の注釈と照らして判定する。[全576窓と仮説の判定](../runs/tsp-f2-intervening-phase-midpoint-20261123-repeat/summary.json)

## 検証と再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。初回と `/tmp` からの再実行で各6判定、固定上流のLPC基準1試験とTSP 6試験が通過した。定常1周期の複素DFTと理論の最大相対差は9.70×10⁻¹⁵、固定上流と独立計算の最大差は生根で7.53×10⁻¹⁰、周波数・帯域幅で8.47×10⁻⁸ Hz。3中心で同じ相対位相に揃えた窓の最大相対標本差は2.88×10⁻¹⁵だった。2回の要約、Rustの出力、圧縮NPZはバイト一致した。比較処理を共通化した後に760 Hzの従来のCLIも再実行し、既存の3出力とバイト一致した。波形とログの実体はRTL9210B-CGに保存した。[初回](../runs/tsp-f2-intervening-phase-midpoint-20261123-a/manifest.json)・[再実行](../runs/tsp-f2-intervening-phase-midpoint-20261123-repeat/manifest.json)・[760 Hzの回帰確認](../runs/tsp-f2-intervening-phase-20261123-midpoint-control/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_intervening_phase_midpoint.py tsp-f2-phase-midpoint-new
```
