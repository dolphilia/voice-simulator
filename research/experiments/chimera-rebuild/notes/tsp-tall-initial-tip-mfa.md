# 初期舌先だけを戻したときの tall の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。確認用の女性発話 `FK61_02` 「He lent his coat to the tall gaunt stranger.」の旧ゲイン比較を引き継ぐ。 `tall` の /ɔ/–/l/ 境界は1.650秒、旧研究版は1.680秒で、両者の整列用PCM16は先頭約251 msだけ異なる。出力ゲインは `5.5×10⁻⁷`、ドリフト、周期長ジッター、振幅シマーは0に固定し、初期舌先を `(6.241412821929657, 6.810460479056529)` cmから旧版の `(6.45, 7.30)` cmへ移す。旧版の入力JSONでは揺らぎの指定が省略されており、当時の `FixedVoice::new` は3係数を0で初期化している。[出力ゲインの比較](tsp-tall-output-gain-mfa.md)・[ケースの事前登録](../cases/tsp-tall-initial-tip-mfa.json)・[旧研究版の初期化](../runs/tsp-active-duration-original-20261121-repeat/artifacts/source/research/experiments/chimera-rebuild/crates/vocal-core/src/voice.rs)

| 読んだファイルと関数 | 入力・状態・出力 |
| --- | --- |
| 上流 `crates/chimera-cli/src/compare/tsp.rs` の `say_all`、同 `render.rs` の `say` | テキストと体型から音素を選び、開始0.05秒のジェスチャーを予約して48 kHzの浮動小数点PCMを出す。音素の計画区間とMFAが推定する区間を別々に記録する。 |
| 上流 `crates/chimera/src/anatomy/human.rs` の `rest_tip`、同 `control/articulators.rs` の `ArticulatorBank::new` と `step` | 舌先は顎の支点 `(−2.5, 10.5)` cmの周囲に `(6.45, 7.35)` cmを `−jaw/9.84` rad回転させ、舌体変位を横0.30倍、縦0.35倍加えた位置から始まる。位置はcm、速度はcm/sで初速0。各制御更新で同じ休止目標とジェスチャーを合成し、速度、位置の順で進める。舌先の自然周波数は13 Hz。 |
| 上流 `crates/chimera/src/voice/human_voice.rs` の `HumanVoice::new`、`control`、`render` | 出力64標本ごとに調音位置と声道面積を更新し、96 kHzで声門と圧力・流量を進め、放射を間引いて48 kHz PCMを作る。 |
| 上流 `compare/tsp.rs` の `over_noise_floor`、`align_synth` と `a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 20 ms窓の平均二乗の95パーセンタイルから雑音の振幅を作り、固定シードの系列を足してPCM16へ量子化する。MFAには各発話を別話者として渡す。試験は無音部の雑音床を±0.5 dBで照合し反復一致を検査する。 |
| 上流 `crates/chimera/tests/golden_voice.rs` の `voice_matches_typescript`、同 `apical.rs` の `the_tip_barely_moves_from_the_consonant_into_the_vowel`、同 `golden_analysis.rs` | 固定PCM、歌唱の舌先制御、LPC公開極の基準を照合する。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `render` と `render_tract_profile`、`crates/vocal-core/src/articulators.rs` の `ArticulatorBank::step` | 通常CLIの `inspect`、`render-pcm`、`render` で計画、無加工PCMと指定フレーム完了時の舌先を採る。姿勢の観測点は接触処理後に置く。 |

同一の目標と速度倍率で進む最初の10 msは、2条件の変位差に対する `Δv′ = (1 − 2ω dt) Δv − ω² dt Δx`、`Δx′ = Δx + dt Δv′` を独立に計算する。 `ω = 2π × 13` rad/s、`dt = 64/48000` 秒。確認するのは固定制御周期ごとの差で、音響PCMの時刻ではない。冒頭50 msでは波形が変わり、`tall` 周辺では舌先が1×10⁻⁶ cm以内に揃うと予測した。旧版と同じ舌先・出力ゲイン・音源設定なら、旧PCM16と全区間を再現し、`tall` の境界は1.680秒に戻ると予測した。

## 実測

発話計画と144,727標本の長さは共通だった。最初の制御更新直後に舌先の座標差は最大0.483733 cm、50 ms時点で0.041195 cmだった。冒頭8観測の最大計算誤差は9.99×10⁻¹⁶ cm。最初の音声標本で差が出て、先頭50 msの最大PCM差は0.00215830だった。1.50〜1.75秒の舌先観測4点と、無加工PCM12,000標本は対照と一致した。

旧舌先条件は旧研究版の無加工float32 PCMと整列用PCM16を各144,727標本、語9区間、音素30区間すべて再現した。対照との整列用PCM16の差4,679標本は番号16〜12,071の範囲にあり、最も遅い差の約1.43秒後に `tall` の終了境界が30 ms動いた。固定上流の無加工PCMは基準アーカイブとビット一致した。固定上流と介入後の波形にはゲインと音源変動の設定差があるため、この比較は旧研究版の再現を判定する。[一次出力と判定](../runs/tsp-tall-initial-tip-mfa-20261123-a/summary.json)

| 条件 | `tall` の /ɔ/ 終端 | 90%窓の開始（12 kHz） | 90%窓のF2 |
| --- | ---: | ---: | ---: |
| 休止舌先 | 1.650秒 | 19,505 | 1,270.70 Hz |
| 旧舌先・休止舌先の窓を適用 | 1.680秒 | 19,505 | 1,270.70 Hz |
| 旧舌先・再整列した窓を適用 | 1.680秒 | 19,829 | 1,528.49 Hz |
| 保存した旧研究版 | 1.680秒 | 19,829 | 1,528.49 Hz |

最初の差は初期の調音位置にあり、評価区間の波形は同じだった。5つの窓を固定する場合はF2がすべて一致した。再整列した90%窓ではF2が257.79 Hz上がった。25窓で固定上流のLPCと独立計算のF1・F2採択値の最大差は1.87×10⁻¹⁰ Hzだった。次の最小対照は、PCM16の冒頭50 msだけを旧舌先条件から移したテープで再整列し、1.680秒を再現できるかを調べること。全発話の局所波形は既知なので、音源を描画し直さずにMFAの入力範囲を操作できる。[窓別LPC](../runs/tsp-tall-initial-tip-mfa-20261123-a/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。既存の辞書・音響モデルと固定シードを使用した。次のコマンドを研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_tall_initial_tip_mfa.py tsp-tall-initial-tip-mfa-new
```

研究ワークスペースと `/tmp` から各9判定と上流11試験に通過した。各28出力のうち経過時間を含む3ログを除く25出力がバイト一致した。LPC窓の集計を共用した第38版のゲイン比較を再実行し、既存24出力中の計時・ビルドログ4件を除く20出力も一致した。ケース、姿勢、無加工PCM、MFA入力と区間、LPC窓をRTL9210B-CGに保存した。[初回](../runs/tsp-tall-initial-tip-mfa-20261123-a/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-tall-initial-tip-mfa-20261123-repeat/manifest.json)・[出力ゲインの回帰](../runs/tsp-tall-output-gain-mfa-20261123-tip-regression/manifest.json)
