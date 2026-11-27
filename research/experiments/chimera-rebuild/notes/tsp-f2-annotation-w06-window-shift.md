# 人手注釈資料W06の中央窓を動かすF2対照

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。人手注釈資料W06は、実録音 `FK61_01` の `again` の `EH1`（音素番号23）の中央窓を指す。録音の同じPCM16と、保存された母音区間1.970〜2.080秒を使う。12 kHzの解析区間は半開区間 `[24149, 24449)`。窓開始を前後5 ms、1標本刻みの計121点動かす。全窓が元の母音内に収まる。資料のWAVは元録音から切り出した範囲とバイト単位で照合し、候補極は研究用の出力に保存する。[事前条件](../cases/tsp-f2-annotation-w06-window-shift.json)・[注釈資料](tsp-f2-annotation.md)

| 読み直した入口 | 状態と観測点 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `measure_pair`、`Sig::new` と `Sig::formants` | 48 kHzの波形を95タップのBlackman窓付き低域通過で処理し、4標本ごとの12 kHz系列を保持する。比較CLIの既定は35・50・65%の窓の中央値。今回は中央窓だけを基準とする。 |
| `crates/chimera/src/analysis/lpc.rs` の `estimate_formants`、`autocorr`、`levinson`、`poly_roots` | 300標本に係数0.97のプリエンファシスとHamming窓を掛け、40 Hzのラグ窓付き自己相関から次数12の係数を更新する。根の角度を `f = arg(z) × 12000 / (2π)` Hz、半径を `B = −ln(|z|) × 12000 / π` Hzに換算する。150 Hz以上・帯域幅600 Hz以下の極を周波数順にし、F1を決めてから、F1+200 Hzより高く3500 Hz未満の最初の極をF2にする。 |
| 上流の `crates/chimera/tests/golden_analysis.rs` と比較CLIの `a_missing_measurement_has_no_cost`、研究版の `measure_tsp_lpc_recording_window_shift.py` | ゴールデン試験は自己相関・係数・根と公開極を照合し、CLIは欠測を得点に含めない。共通の観測CLIは始点ごとのフィルタ出力を直接和と畳み込みで照合し、固定Rustと独立したToeplitz連立方程式・根の計算を比較する。 |

基準の次数12はF1 620.18 Hz、F2 2,073.45 Hzを採り、帯域幅はそれぞれ147.55 Hzと431.58 Hz。F2候補には2,913.42 Hz・幅150.18 Hzの極も残る。より低い1,503.29 Hzの根は幅1,284.84 Hzで公開から外れる。2,073.45 Hz側は幅の上限から168 Hz離れており、全幅10 msでは全窓で2.1 kHz側を採り、2.9 kHz側も候補に残ると予測する。2帯域の範囲は[1900,2200]と[2750,3050] Hzに固定する。[基準の次数比較](../runs/tsp-lpc-order-recordings-20261122-repeat/summary.json)・[別録音の先行対照](tsp-lpc-recording-window-shift.md)

## 実測

| F2候補 | 周波数の範囲（Hz） | 帯域幅の範囲（Hz） | 適格窓数 | 採択窓数 |
| --- | ---: | ---: | ---: | ---: |
| 2.1 kHz側 | 2,011.31〜2,108.41 | 398.87〜448.99 | 121 | 121 |
| 2.9 kHz側 | 2,895.74〜2,929.81 | 130.87〜168.97 | 121 | 0 |

窓を前後5 ms動かしても、2.1 kHz側の幅は600 Hz未満で、2.9 kHz側と共に全窓で候補となった。選ばれた側の周波数は97.10 Hz動いた。帯域間の切り替わりと欠測は0件。資料W06の音声9,600標本と元録音の切り出しがバイト一致し、資料上の87.4167〜112.4167 msが12 kHzの元の窓に対応した。[121窓の候補と判定](../runs/tsp-f2-annotation-w06-window-shift-20261123-repeat/summary.json)

固定Rustと独立計算は全窓で一致し、公開極の周波数・帯域幅の最大差は2.82×10⁻¹¹ Hz、採択値は2.46×10⁻¹¹ Hz以内。間引きを直接和で検算した差は1.39×10⁻¹⁷以内だった。前後5 msの範囲では既定の選択が安定していた。人手の判定は資料と対応する回答が届いた時点で照合する。[固定上流の極](../runs/tsp-f2-annotation-w06-window-shift-20261123-repeat/artifacts/upstream-envelopes.json)・[人手回答の取込](tsp-f2-human-intake.md)

W06に記録されたプリエンファシスを外した対照の採択は708.24 Hzだった。次は元の窓を固定し、プリエンファシスだけを既定の0.97と0の間で変え、候補の出現・除外と順位が最初に切り替わる区間を求める。[先行のプリエンファシス比較](tsp-lpc-pre-emphasis-recordings.md)・[W06の資料定義](../runs/tsp-f2-annotation-20261122-repeat/artifacts/reference.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4。研究ワークスペースで次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_lpc_recording_window_shift.py \
  tsp-f2-annotation-w06-window-shift-new --case cases/tsp-f2-annotation-w06-window-shift.json
```

研究ワークスペースと `/tmp` からの2実行は各7判定と上流7試験に通過した。要約・上流極・間引き系列・上流試験ログの5出力はバイト一致し、ビルドと実行のログ1件に差があった。同じCLIの既定ケース `seems` の回帰でも、保存済みの計測を再現した。成果をRTL9210B-CGに保存した。[初回](../runs/tsp-f2-annotation-w06-window-shift-20261123-a/manifest.json)・[再実行](../runs/tsp-f2-annotation-w06-window-shift-20261123-repeat/manifest.json)・[既定ケースの回帰](../runs/tsp-lpc-recording-window-shift-20261123-w06-regression/manifest.json)
