# 男性発話 again の境界と周期長ジッター

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。男性発話 `MK61_01` のドリフト0・振幅シマー0の保存版を基準に、周期長ジッターだけを0.00455から旧研究版の既定値0へ戻す。初期舌先、体型、出力ゲインは固定する。前回はシマーを止めても `again` の /ɛ/–/n/ 境界が2.030秒にとどまり、旧2.050秒に対応する5窓が残った。[振幅シマーの比較](tsp-again-amplitude-shimmer-mfa.md)・[事前登録](../cases/tsp-again-male-period-jitter-mfa.json)

| 参照した処理 | 入力・状態・出力 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/render.rs` の `say` と `text_f0`、`crates/chimera/src/voice/human_voice.rs` の `apply_source` と `render` | 男性の基準F0は112 Hz、振動器の初期値は110 Hz。roughness 0.1から周期長ジッター0.00455を決める。声道の圧差（dyn/cm²）を声門に渡して面積（cm²）を更新し、流量と放射の時間差分から48 kHzのPCMを得る。 |
| 固定上流 `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::new` と `next`、`crates/chimera/src/math.rs` の `Rng::gauss` | 位相0、周期倍率1、振幅倍率1から開始する。各96 kHz内部標本で `F0 / (96000 × 周期倍率)` を位相に加える。位相が1に達した標本で周期倍率を `clamp(1 + jitter × g₁, 0.55, 1.8)` に更新し、その倍率を次の標本からの位相増分に使う。乱数種777から周期用と振幅用に順番に4個ずつ一様乱数を消費する。シマー0なのでこの比較の振幅倍率は両条件とも1。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run` と `render`、`crates/vocal-core/src/glottis.rs` の `Glottis::step` | 通常CLIの `source_variation.period_jitter` が周期倍率へ伝わる。同じケースを内部観測器にも通し、F0、位相、振幅倍率と通常PCMを照合する。 |
| 固定上流 `compare/tsp.rs` の `align_synth`、`Sig::formants`、試験 `voice_source.rs`、`golden_voice.rs`、`golden_analysis.rs` | 保存済みと同じ辞書・雑音床を使ってMFAへ入力する。固定窓と再整列窓のF2を同じ無加工PCMから測り、窓の移動と励振の変化を切り分ける。上流の試験は声門形状、固定発話PCM、LPCの公開極を検証する。 |

瞬時F0と振幅倍率は一致し、位相の初差は最初の声門周期境界の次の内部標本に出ると予測する。固定窓のF2が少なくとも1窓で1 Hz以上変化し、/ɛ/–/n/ の境界移動は10 ms以内と見込む。

## 実測

瞬時F0と振幅倍率は全232,264内部標本で一致した。最初の周期境界は標本番号871、位相の初差は次の872だった。対応する周期境界の最大時刻差は108内部標本（1.125 ms）。声門面積と流量は8,081内部標本で初めて差が生じ、圧差と放射流量の時間差分は8,082内部標本から異なった。48 kHzの通常PCMは標本番号4,060から異なった。

MFAの /ɛ/–/n/ 境界は2.030秒から2.050秒へ動き、10 ms以内という予測を超えた。 `again` の5窓はすべて旧位置まで移り、90%窓の開始位置は標本番号24,077から24,293へ移った。旧研究版の語8区間と音素25区間がすべて一致した。第34版の窓定義でも `MK61_01` の旧差10窓すべての開始位置が一致した。内訳は今回戻った `again` の5窓と、旧位置を保った `plea` の5窓だった。ほかの15窓の開始位置は旧比較の基準と同じだった。

| `again` の90%窓 | 開始標本（12 kHz） | F2 |
| --- | ---: | ---: |
| ジッター0.00455・基準境界 | 24,077 | 1,751.91 Hz |
| ジッター0・基準境界 | 24,077 | 1,762.38 Hz |
| ジッター0・再整列境界 | 24,293 | 1,803.38 Hz |

基準境界を固定した5窓でのF2差は最大19.13 Hzだった。90%窓ではジッター停止で+10.47 Hz、同じPCMの窓を再整列境界に合わせるとさらに+41.00 Hz動いた。5条件25窓のF1・F2採択値は固定Rustと独立計算で最大3.64×10⁻¹² Hz差だった。[測定要約](../runs/tsp-again-male-period-jitter-mfa-20261123-a/summary.json)・[窓別F2](../runs/tsp-again-male-period-jitter-mfa-20261123-a/artifacts/window-comparisons.json)・[第34版の窓定義](../runs/tsp-matched-pitch-drift-mfa-20261123-repeat/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_again_initial_tip_mfa.py tsp-again-male-period-jitter-mfa-new \
  --case cases/tsp-again-male-period-jitter-mfa.json
```

研究ワークスペースと `/tmp` から各10判定・上流13試験に通過した。各30出力のうち計時を含む実行ログ4件を除いた26出力がバイト一致した。振幅シマー比較の回帰でも主要26出力が一致した。PCM、MFA境界、窓別F2、瞬時F0・位相・振幅倍率をRTL9210B-CGに保存した。[計測の再実行](../runs/tsp-again-male-period-jitter-mfa-20261123-repeat/manifest.json)・[振幅シマー比較の回帰](../runs/tsp-again-amplitude-shimmer-mfa-20261123-after-male-jitter/manifest.json)
