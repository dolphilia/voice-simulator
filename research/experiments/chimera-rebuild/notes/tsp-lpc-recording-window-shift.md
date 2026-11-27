# 実録音で窓の開始をずらしたときのF2候補

先行の録音6窓を確認して、`MK61_01` の `seems` の強勢母音 `IY1`、区間中央値0.50の窓を選んだ。既定のLPC次数14はF1を327.42 Hz、F2を993.37 Hzとし、2323.81 Hzも採択条件を満たしていた。低域極とF1との差は665.95 Hzあり、合成対照で効いた200 Hz境界から離れている。基準で低域極の幅は508.89 Hzだった。窓を前後5 msずらしたとき、高域極は候補に残り、低域の幅が600 Hzを超えた窓では高域へ移ると予測した。1周期程度に相当する全幅10 msを観測し、録音波形を元の標本位置から切り出す。局所的な音響変化と励振位相がともに動くため、この比較で分かるのは窓位置に対する採択の変化である。[先行の次数比較](tsp-lpc-order-recordings.md)・[合成対照](tsp-f2-intervening-phase-midpoint.md)・[実行前のケース定義](../cases/tsp-lpc-recording-window-shift.json)

上流の `compare tsp` から `measure_pair` へ進むと、48 kHzの録音と合成を読み、`match_phones` で音素対応を決める。`Sig::new` は `decimate` を用いてカットオフ5,400 Hz、95タップのBlackman窓付きsincで各出力標本を計算する。出力標本 `n` の入力中心は `4n` で、入力範囲外は0とみなす。`Sig::formants` が母音区間の35・50・65%から300標本を取ったところを観測境界とした。中央値用の3窓のうち中央1窓を基準とし、音素区間も標本化も固定する。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[録音との対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[低域通過と間引き](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L438)

`estimate_formants` は前標本の初期値を0にして窓内で0.97のプリエンファシスを行い、Hamming窓を掛ける。自己相関はラグ順に計算し、ラグ0を除いて40 Hzを尺度とする重みを掛ける。Levinson–Durbin法で係数と誤差を次数順に更新し、Durand–Kerner法で根を求める。複素根の偏角を `fs/(2π)` 倍した値が周波数、半径の自然対数を `-fs/π` 倍した値が帯域幅で、両方ともHz。上半平面から150 Hz以上・600 Hz幅以下の根を周波数順に公開する。TSPは1,300 Hz未満かつ幅500 Hz未満の先頭をF1に、F1より200 Hzを超えて上で3,500 Hz未満の先頭をF2に選ぶ。固定Rustの生根からこの選別を追い、独立したToeplitz方程式で結果を照合する。TypeScript基準試験とTSPの音素照合・欠測処理も確認する。[上流の採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[上流LPC](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[LPC基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[TSP試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

## 前後5 msの結果

母音の約1.340〜1.410秒の区間内で、300標本窓の開始を12 kHzの16,290〜16,410標本まで1標本ずつ動かした。全121窓で983.01〜996.26 Hzの低域極がF2に選ばれ、高域の2.3 kHz近傍にも適格な極が残った。低域極の帯域幅は436.96〜558.54 Hzで、F1との差は655.91〜670.84 Hzだった。高域の候補の幅は49.92〜73.27 Hz。帯域幅の600 Hz上限で低域極が落ちるという予測は外れ、候補も採択も欠測なく記録できた。前回の合成対照では候補の切り替わりを位相で起こせた。今回の録音では、窓位置を動かしても周波数順の規則で同じ帯域が選ばれ続けた。

別途保存されていた母音開始側10%の窓は、今回の基準から28 ms早い16,014標本で始まり、2,318.26 Hzを採っている。今回の結果の範囲は中央の前後5 msである。この録音でどの極が実際のF2に近いかを評価するには、同じ窓に対する人の注釈が必要になる。中央値だけでは候補の共存が見えないため、次は既存のTSP評価から各窓の候補・帯域幅・選択順を出す診断を用意し、同じ録音の評価で照合する。[全窓の候補と判定](../runs/tsp-lpc-recording-window-shift-20261123-repeat/summary.json)・[先行の上流全窓](../runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/artifacts/upstream-formants.json)

## 再実行と照合

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使った。元の48 kHz録音を先行のWAVとSHA-256で照合した。SciPyは追加の非音声チャンクを読み飛ばす警告を出した。PCMは期待した48 kHz・モノラルの16 bitで、間引き後の420標本は独立したタップ和と最大2.78×10⁻¹⁷の振幅差だった。開始位置をずらさない窓は保存済みのLPC係数・残差・生根・公開極・採択に一致し、全121窓の独立計算との最大複素根差は2.93×10⁻¹³、公開極の周波数・帯域幅の最大差は1.43×10⁻¹⁰ Hzだった。

2回目は `/tmp` から絶対パスで実行した。各回で計測5判定、固定上流のLPC基準1試験・TSP 6試験が通過し、要約・固定上流出力・圧縮NPZはバイト一致した。重なる窓を再現するのに必要な420標本をNPZに保存し、出力の実体をRTL9210B-CGに置いた。[初回マニフェスト](../runs/tsp-lpc-recording-window-shift-20261123-a/manifest.json)・[再実行マニフェスト](../runs/tsp-lpc-recording-window-shift-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_lpc_recording_window_shift.py tsp-lpc-recording-window-shift-new
```
