# 発話中の /i/ の形状から線形共鳴を求める

先行の同じ発話 `seems` の /i/ では、中央の高域LPC極は固定上流2,228.15 Hz、研究版2,212.45 Hzだった。固定母音 /i/ の線形応答の第2ピーク2,225.38 Hzを手掛かりに、今回は発話途中の実際の形状を固定すると、両版で高域の線形ピークがPCMの候補に近づき、2版間の差も同じ符号になると予測した。測定区間は元の12 kHz・300標本窓の中央1.165秒で、48 kHzでフレーム55,919を出し終えた状態とする。音声の区間と比較帯域を結果を見る前に登録した。[事前登録](../cases/tsp-seems-tract-transfer.json)・[先行の発話LPC](tsp-f2-source-comparison.md)・[較正用の固定母音](vowel-transfer.md)

上流の `compare tsp` の `say_all` と、通常CLIの `render text` は `render::say` を通る。男性の基準F0 112 Hz、50 ms後に始まる語・音素の計画、300 msの末尾を使い、`HumanVoice::render` は制御カウンタが尽きたときに新しい調音目標を作る。内部96 kHzの各標本で断面とポートの状態を更新し、流量と放射を計算し、間引いたPCMを出力する。 `AirwayNetwork::linear_elements` は上流では**目標**面積・長さを読む。この比較では流れやPCMを計算した実際の `area`、`dx`、`port_area` を作業コピーの気道の複製へ渡す。研究版では `network.section` と `linear_elements` が現在断面を読み、寸法は通常CLIの断面CSVとも照合できる。断面積はcm²、長さはcm。[固定上流の発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の線形要素](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1199)

線形化後は声門枝を切り、咽頭入口に単位体積速度を与える。節点の空気が `jωC`、枝が `R + jωL`、壁が `S/(R_w + jωM_w + K_w/(jω))` のアドミタンスを持つ。口端・鼻端の抵抗と慣性は並列で、放射する壁の流量を足す。木の末端から `Y/(1 + ZY)` を親へ集め、流量を設定した根から圧力を伝えて放射流量比を得る。Pythonでは全節点の複素連立方程式を組み、同じ量を照合する。高さは総放射流量比の絶対値で測る。PCMの高域候補は、この定常・微小信号のピークとは異なる条件で求めたLPC値である。一様管の四分の一波長試験と、固定応答をTypeScriptと照合する基準試験も実行する。[上流の周波数求解](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)・[一様管の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[TypeScript基準](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L111)

## 発話中の断面と共鳴

1.165秒の咽頭18セルと口腔18セルで、対応する代表面積の差は最大5.87×10⁻¹⁴ cm²だった。咽頭の長さは両版とも8.16108 cm、口腔の長さは8.52997 cm。声門枝を切った線形応答は、高域の最も強いピークが両版とも2,187.47 Hz、帯域幅が20.84 Hzだった。PCMの高域LPC極への距離は、固定上流40.68 Hz、研究版24.98 Hzで、どちらも登録した180 Hz以内だった。この時刻の固定断面だけでは、PCMに残る15.70 Hzの差を説明できない。

| 音源 | 断面固定での高域ピーク | PCMの高域LPC極 |
| --- | ---: | ---: |
| 固定上流 | 2,187.47 Hz | 2,228.15 Hz |
| 研究版 | 2,187.47 Hz | 2,212.45 Hz |

初版は線形ピーク差−4.09×10⁻¹² Hzの符号で、PCMとの差の符号も一致すると判定した。別の求解法によるピークの最大差は1.73×10⁻¹¹ Hzで、この符号は数値誤差より小さい。第2版では先行のピーク照合の許容差0.1 Hzを符号の判別にも適用し、結論を判別不能とした。初版のケース、結果、出力を保存し、第2版ではピークとPCMの数値が同じことを確認した。次は同じ25 ms窓の声門流量と口端放射を採り、高域のスペクトルが分かれる段を確認する。[初版の判定](../runs/tsp-seems-tract-transfer-20261123-a/summary.json)・[第2版の判定](../runs/tsp-seems-tract-transfer-20261123-resolved/summary.json)

## 再実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。両版の通常CLIで保存済みWAVにバイト一致し、断面を出すプローブでも各版の116,132 PCMフレームと全点一致した。研究版の36セルは通常CLIの断面CSVとも一致した。891周波数点で、複素節点方程式と木の求解の最大相対差は、固定上流の応答振幅で8.08×10⁻¹⁴、研究版の複素応答で1.35×10⁻¹³だった。

初版は別の作業ディレクトリからの再実行も含め、各4判定と、固定上流の一様管等3試験・TypeScript基準1試験、研究版の17試験を通過した。第2版も同じ試験と5判定を通過した。初版2回の要約、全3断面・応答ファイルはバイト一致し、第2版の断面と応答も初版とバイト一致した。断面・線形応答・実行ログの実体はRTL9210B-CGに置いた。[初版のマニフェスト](../runs/tsp-seems-tract-transfer-20261123-a/manifest.json)・[初版の再実行](../runs/tsp-seems-tract-transfer-20261123-repeat/manifest.json)・[第2版のマニフェスト](../runs/tsp-seems-tract-transfer-20261123-resolved/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_seems_tract_transfer.py tsp-seems-tract-transfer-new
```
