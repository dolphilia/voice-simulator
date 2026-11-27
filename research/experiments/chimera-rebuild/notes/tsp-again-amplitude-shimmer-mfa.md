# 男性発話 again の境界と周期振幅シマー

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。4発話のドリフト停止で再現できなかった5窓は、男性発話 `MK61_01` の `again` にある。第34版のドリフト0のケースを基準に、体型、初期姿勢、出力ゲイン、ドリフト0、周期長ジッター0.00455を固定し、振幅シマーだけを0.042から0へ変える。[4発話の境界](tsp-matched-pitch-drift-mfa.md)・[事前登録](../cases/tsp-again-amplitude-shimmer-mfa.json)

| 参照した処理 | 入力・状態・出力 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/render.rs` の `say`、`crates/chimera/src/voice/human_voice.rs` の `apply_source` と `render` | 男性の既定興奮源の基準F0は112 Hz。roughness 0.1から、無次元の周期長ジッター0.00455とシマー0.042を設定する。圧差から声門面積を求めて気道を進め、流量の時間差分を間引いて48 kHzの出力PCMを得る。 |
| 固定上流 `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::next`、`crates/chimera/src/math.rs` の `Rng::gauss` | 位相を96 kHzで進め、一周した内部標本で先に周期倍率、次に振幅倍率を更新する。有声振動の振幅倍率は初期値1、境界ごとに `max(0.12, 1 + shimmer × g₂)`。乱数種は777。周期長用に一様乱数4個を消費した後、次の4個の和から2を引いて1.7320508倍し `g₂` を得る。シマー0でも同じ個数を消費し、その境界標本から新しい振幅倍率が面積パルスに効く。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run` と `render`、`crates/vocal-core/src/glottis.rs` の `Glottis::step` | 通常CLIの `source_variation.amplitude_shimmer` を `set_amplitude_shimmer` に渡す。両条件の通常PCMを内部観測器のPCMへ照合し、F0、位相、周期ごとの振幅倍率を独立計算で再現する。 |
| 固定上流 `compare/tsp.rs` の `align_synth` と `Sig::formants`、`tests/voice_source.rs`、`golden_voice.rs`、`golden_analysis.rs` | 同じ辞書、雑音床、MFAモデルでPCM16を整列する。F2は無加工PCMから、12 kHzの25 ms窓と男性条件の次数14で測る。固定試験で声門の形状・高域出力と固定PCM・LPCを照合する。 |

瞬時F0、位相、周期境界の時刻は両条件で一致し、振幅倍率は最初の周期境界で分かれると予測する。固定5窓のうちF2が1 Hz以上動く窓があり、/ɛ/–/n/ 境界は2.030秒にとどまると見込む。旧研究版の2.050秒で得た5窓の開始位置を対照とする。

## 実測

瞬時F0と位相は全232,264内部標本で一致した。振幅倍率は最初の周期境界である標本番号871で1.0006967と1.0に分かれた。シマー0.042の倍率範囲は0.89046〜1.11722、0の倍率は全区間で1だった。独立した乱数・位相計算で両条件の276周期境界と振幅倍率を再現した。

声門面積と流量は8,081内部標本、圧差と合計放射の時間差分は8,082内部標本から分かれた。通常PCMの初差は48 kHzの出力標本番号4,057、全発話の最大差は0.02538だった。通常CLIのPCMは内部観測器と両条件で全116,132標本が一致し、シマー0.042の対照は第34版のドリフト0のPCMとMFA境界を再現した。

再整列では語8区間と音素25区間すべてが対照と一致した。 `again` の /ɛ/–/n/ は両条件で2.030秒、旧比較では2.050秒だった。90%窓の開始標本は24,077のままで、旧比較の24,293を含む5窓はいずれも旧位置まで動かなかった。固定窓のF2差は最大1.30 Hzで10%窓に現れた。90%窓では−0.60 Hzだった。5条件25窓の開始標本と欠測は固定Rustと独立LPCで一致し、採択値の差は最大3.64×10⁻¹² Hzだった。[測定要約](../runs/tsp-again-amplitude-shimmer-mfa-20261123-a/summary.json)・[窓別F2](../runs/tsp-again-amplitude-shimmer-mfa-20261123-a/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_again_initial_tip_mfa.py tsp-again-amplitude-shimmer-mfa-new \
  --case cases/tsp-again-amplitude-shimmer-mfa.json
```

研究ワークスペースと `/tmp` から各10判定と上流13試験に通過した。各30出力のうち、4実行ログを除く26出力がバイト一致した。ドリフト比較の回帰でも、各31出力のうち4実行ログを除く27出力が一致した。波形、MFA区間、固定窓と再整列窓のF2、位相と振幅倍率をRTL9210B-CGに保存した。[再実行](../runs/tsp-again-amplitude-shimmer-mfa-20261123-repeat/manifest.json)・[ドリフト比較の回帰](../runs/tsp-again-pitch-drift-mfa-20261123-after-shimmer/manifest.json)
