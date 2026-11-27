# 周期長ジッターだけを戻したときの again の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。確認用 `FK61_01` 「A plea for funds seems to come again.」の体型、初期舌先、出力ゲイン、ドリフト5セントとシマー0.042を揃え、周期長ジッターだけを0.00455から旧研究版の既定値0へ戻す。[初期舌先だけを戻した比較](tsp-again-initial-tip-mfa.md)

| 参照した処理 | 入力・状態・出力 |
| --- | --- |
| `crates/chimera-cli/src/render.rs` の `say`、`crates/chimera/src/voice/human_voice.rs` の `apply_source` と `render` | 本文と女性体型から基準F0 205 Hzと調音・呼気の計画を作る。既定roughness 0.1に対してジッターを `0.0021 + 0.0245 × 0.1`、シマーを `0.02 + 0.22 × 0.1` とする。音響更新では気道圧差（dyn/cm²）を声門モデルに渡し、面積（cm²）、声門流量と口端放射を経て48 kHzのPCMを得る。 |
| `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::new` と `next`、`crates/chimera/src/math.rs` の `Rng::gauss` | 初期位相0、周期と振幅の倍率1、乱数種777。96 kHzの各内部標本でドリフトとビブラートを含む瞬時F0を求め、現在の周期倍率で `F0 / 96000` を割って位相に足す。位相が1を超えると周回し、乱数から周期倍率 `clamp(1 + jitter × g₁, 0.55, 1.8)`、振幅倍率 `max(0.12, 1 + shimmer × g₂)` の順で更新する。新しい周期倍率は次の標本から使う。ジッター0でも周期ごとの乱数の消費順は同じ。両条件で倍周期化とカオスは0。 |
| `crates/chimera/tests/voice_source.rs`、`golden_voice.rs`、`golden_analysis.rs` | 声門閉鎖と音源の高域成分、固定発話PCMとブロック分割、公開LPC極をそれぞれ検査する。今回の周期境界は実測F0を使った独立計算と照合する。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run` と `render`、`crates/vocal-core/src/glottis.rs` の `Glottis::step` | `source_variation.period_jitter` を通常のCLIから声門モデルへ渡す。未指定時は0。内部観測器でF0、位相、振幅倍率、声門面積、圧差、流量、放射を保存し、同じ設定の通常PCMと照合する。 |
| 固定上流 `compare/tsp.rs` の `align_synth` と `over_noise_floor` | 前回と同じ辞書、雑音床、PCM16変換でMFAを実行し、/ɛ/–/n/ の境界を得る。同じPCMに基準境界と再整列境界を用いることで、F2への窓位置の寄与を観測する。 |

位相の最初の差は初回周期境界の次の内部標本に出ると予測する。声門周期の違いは `again` 付近まで残り、窓を固定したF2は少なくとも1窓で1 Hz以上変わると予測する。MFAで再整列した /ɛ/–/n/ の境界差は10 ms以内を見込む。[事前登録](../cases/tsp-again-period-jitter-mfa.json)

## 実測

最初の周期境界は96 kHzの標本番号830で、位相は次の831から分かれた。501周期の境界と振幅倍率を独立計算で両条件とも完全に再現した。瞬時F0と周期番号で揃えた振幅倍率には差がなく、周期境界の最大時刻差は65標本（約0.68 ms）だった。

声門面積と声門流量の初差は8,083内部標本、声門圧差と放射流量の時間差分は8,084内部標本だった。48 kHzの通常PCMは標本番号4,059から分かれ、最初の50 msは一致した。 `again` の境界を含む1.90〜2.10秒では、無加工PCMの9,600標本すべてに差が出た。

MFA入力のPCM16では、無加工PCMより早い標本番号4で28と29に分かれた。雑音の乱数列と相対床は同じだが、前処理は発話全体の20 ms平均二乗の95パーセンタイルから雑音の最大振幅を決める。その振幅がジッター0で0.08719%増えた。両版の無加工PCM、xorshift32の先頭5値、各発話の雑音振幅を使い、最初の5標本の整数値を再計算して確認した。MFA 3.4.3で再整列すると、語・音素の全区間が一致した。 /ɛ/–/n/ 境界は両条件とも2.040秒だった。

| 母音内の窓中心 | 0.00455のF2 | 0のF2 | 差 |
| --- | ---: | ---: | ---: |
| 10% | 2,082.10 Hz | 2,083.89 Hz | +1.79 Hz |
| 35% | 2,022.39 Hz | 2,025.05 Hz | +2.66 Hz |
| 50% | 2,066.40 Hz | 2,062.55 Hz | −3.86 Hz |
| 65% | 2,041.66 Hz | 2,037.77 Hz | −3.89 Hz |
| 90% | 2,034.56 Hz | 2,035.27 Hz | +0.72 Hz |

90%窓は両条件とも12 kHzの標本番号24,185から始まった。基準PCMへの旧境界の適用では24,401から始まり、F2差は109.53 Hzだった。5条件25窓の窓開始と欠測は固定Rustと独立計算で一致し、採択値の最大差は4.09×10⁻¹² Hzだった。[計測要約](../runs/tsp-again-period-jitter-mfa-20261123-a/summary.json)・[窓別結果](../runs/tsp-again-period-jitter-mfa-20261123-a/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。研究ワークスペースから次のように実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_again_initial_tip_mfa.py tsp-again-period-jitter-mfa-new \
  --case cases/tsp-again-period-jitter-mfa.json
```

研究ワークスペースと `/tmp` から各10判定・上流13試験に通過した。各30出力のうち計時などを含む3実行ログを除いた27出力がバイト一致した。波形、MFA入力・境界、固定Rustと独立LPCの結果、瞬時F0・位相・振幅倍率をRTL9210B-CGに保存した。前回の初期舌先比較も更新後のCLIから再実行し、主要25出力が一致した。[周期長ジッターの再実行](../runs/tsp-again-period-jitter-mfa-20261123-repeat/manifest.json)・[初期舌先の回帰](../runs/tsp-again-initial-tip-mfa-20261123-after-jitter/manifest.json)
