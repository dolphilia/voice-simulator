# seems の周期長ジッター

ドリフト0の固定上流と研究版で周期長のジッターだけを切り替える。1.1525〜1.1775秒の同じ /i/ を比較する。前回、上流の振動器へ通常条件の圧力差を再入力したときのLPC極の移動は−1.42×10⁻⁶ Hzで、ドリフト0の固定上流から研究版までの差は約5.95 Hzだった。[事前登録](../cases/tsp-seems-period-jitter.json)・[圧差の比較](tsp-seems-pressure-replay.md)

## 上流の読解

- `crates/chimera-cli/src/render.rs` の `say` は固定した辞書から発話計画を作り、男性条件で基準F0を112 Hz、発話計画の開始を0.05秒として `HumanVoice` に渡す。`crates/chimera/src/voice/human_voice.rs` の `apply_source` では既定roughness 0.1から周期長の係数 `0.0021 + 0.0245 × 0.1 = 0.00455`、振幅の係数 `0.02 + 0.22 × 0.1 = 0.042` を求める。両方とも無次元。`render` は96 kHzで圧差（dyn/cm²）を `ParametricGlottis::next` に渡し、返された声門面積（cm²）で声門枝を更新する。その後に気道を進め、放射差分から48 kHzのPCMを得る。
- `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::new` は位相0、周期倍率1、振幅倍率1、周期番号0、乱数種777から開始する。`next` は平滑化した有声度を更新し、位相に `(F0 / 96000) / 現在の周期倍率` を加える。位相が1をまたいだ標本では、位相から1を引いて周期番号を進め、次の増分で使う周期倍率を `clamp(1 + jitter × g₁, 0.55, 1.8)` とする。同じ標本で振幅倍率を `max(0.12, 1 + shimmer × g₂)` に更新する。このケースの倍周期化とカオスの係数は0。更新後の振幅倍率と新しい位相で面積パルスが決まり、その時刻の声門流量に伝わる。
- `crates/chimera/src/math.rs` の `Rng::next` はMulberry32で一様乱数を進める。`gauss` は4個の和から2を引き、1.7320508を掛ける。境界ごとに周期・振幅の順で別の4個を使う。係数を0にした条件もこの順で乱数を消費するので、周期番号で揃えた振幅は同じで、境界の時刻がずれれば同じ物理時刻の振幅が一時的に異なり得る。
- 上流の `voice_source.rs` は声帯の閉鎖形状と高域出力、`golden_voice.rs` は固定発話のPCMとブロック分割、`golden_analysis.rs` は公開LPC極を照合する。`math.rs` の内部試験は乱数の値域を確認する。今回は公開PCMと別に、実測F0を入力として各標本の位相・周期・振幅をPythonで再計算する。

研究版の `crates/vocal-cli/src/timing_case/speech_voice.rs` は `source_variation.period_jitter` を `ArticulatedVoice::set_period_jitter` へ渡せる。指定なしでは `crates/vocal-core/src/voice.rs` にあるジッター0、シマー0、ドリフト0で初期化する。`crates/vocal-core/src/glottis.rs` の `Glottis::step` では固定上流と同様に、境界に達する増分を旧周期倍率で計算し、面積に使う振幅を境界で更新する。

## 実測

固定上流は隔離コピーに計測パッチを当て、ドリフトを0にした2条件で周期長のジッターだけを変えた。研究版は同じケースの `source_variation.period_jitter` だけを変え、2条件とも通常のCLIでレンダーした。通常CLIの全116,132 PCMフレームは両版の観測付き基準と一致し、研究版のジッター追加条件も通常CLIと一致した。発話計画、既定条件の保存WAV、先行のドリフト0の窓を照合した。

| 版 | ジッター0の高域LPC極（Hz） | ジッター0.00455の高域LPC極（Hz） | ジッター追加での移動（Hz） |
| --- | ---: | ---: | ---: |
| 固定上流、シマー0.042 | 2,210.1451 | 2,206.5029 | −3.6422 |
| 研究版、シマー0 | 2,212.4485 | 2,208.8973 | −3.5512 |

ドリフト停止時に5.9455 Hzあった版間差は、両版のジッターを0に揃えると2.3033 Hzになった。25 ms窓で見た声門流量の1,950〜2,600 Hz内のパワー分布の全変動距離は、ジッター有無の間で固定上流0.11168、研究版0.10840だった。独立出力計算で先頭56,600フレームを再現した。FFTと直接フーリエ和の最大相対誤差は1.20×10⁻¹⁴、固定LPCと独立計算の最大誤差は1.01×10⁻¹¹ Hzだった。

両版のジッター有無で第871内部標本の周期境界まで位相が一致し、第872標本で初めて分かれた。対応する周期境界の時刻差は最大46標本（約0.48 ms）、円周上での位相差は最大0.05316周期だった。声門面積と流量は第8,081標本、圧差と有声度は第8,082標本から変化し、PCMは48 kHzの第4,060フレームから変わった。瞬時F0と周期番号で揃えた振幅倍率は各版内で一致した。

先頭113,200内部標本でPythonの独立計算と位相・境界・振幅倍率がすべて一致し、固定上流の周期倍率も一致した。さらにジッターの値を揃えた2組は、全観測標本で両版間の瞬時F0と位相が一致した。固定上流と研究版の振幅倍率の最大絶対差は0.11368。次はドリフトとジッターを0としたまま振幅のシマーだけを揃え、振幅倍率とLPC極の残差を照合する。計測7判定と登録した3仮説は成立した。[結果要約](../runs/tsp-seems-period-jitter-20261123-repeat/summary.json)

## 再実行

`research/experiments/chimera-rebuild` で別の実行IDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_seems_period_jitter.py tsp-seems-period-jitter-new
```

`cycle-traces.npz` に瞬時F0、位相、振幅倍率と上流の周期倍率を、`drift-windows.npz` と `drift-spectra.npz` に比較窓とスペクトルを保存した。ジッターを追加した研究版の入力、計画、固定上流のLPC、試験ログはマニフェストにある。比較のビルドと一時波形・計測成果はRTL9210B-CGを使用した。[初回](../runs/tsp-seems-period-jitter-20261123-a/manifest.json)・[再実行](../runs/tsp-seems-period-jitter-20261123-repeat/manifest.json)

実行環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。実験ディレクトリと `/tmp` で、要約、周期系列、観測窓、スペクトル、固定LPC、発話計画がバイト単位で一致した。上流4試験と研究版17試験は両方で通過した。先行の圧差再入力も共通化した観測器から再実行し、要約、圧差系列、観測窓、スペクトル、LPCが従来の保存出力とバイト一致した。[圧差ケースの再確認](../runs/tsp-seems-pressure-replay-20261123-recheck-after-jitter/manifest.json)
