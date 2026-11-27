# 初期舌先だけを戻したときの again の境界

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。確認用 `FK61_01` 「A plea for funds seems to come again.」で、設定を揃えた研究版と、同じ設定で舌先の初期座標2つだけを旧値へ戻した版を描画する。旧比較で `again` の /ɛ/ の終了境界は20 ms、90%窓の開始は216標本違ったため、この境界に絞って初期化の寄与を測る。

| 参照した処理 | 入力・状態・出力 |
| --- | --- |
| `crates/chimera-cli/src/compare/tsp.rs` の `say_all`、`crates/chimera-cli/src/render.rs` の `say` | 発話本文と体型から単語を音素へ変換し、50 ms後を起点としたジェスチャーを予約する。計画音素の秒区間と48 kHzの無加工PCMを得る。TSPの整列時に使う境界は、この計画音素の秒区間と区別する。 |
| `crates/chimera/src/anatomy/human.rs` の `rest_tip`、`crates/chimera/src/control/articulators.rs` の `ArticulatorBank::new`、`step` | cm単位の顎と舌体から休止舌先を求める。下顎の支点 `(-2.5, 10.5)` cmのまわりに舌先基準点を `−jaw / 9.84` rad回し、舌体の中立位置からの差をxへ0.30、yへ0.35倍加える。速度0から開始する。制御更新で目標を休止位置とスコアの重みから決め、`a = ω²(T − x) − 2ωv` を使い速度、位置の順で積分する。 |
| `crates/chimera/src/voice/human_voice.rs` の `control`、`render` | 発声制御区間ごとに舌先などの調音を進め、声道各セルの断面を更新する。音響の内部標本ごとに声門の実面積と圧力・流量を進め、放射を間引き・DC除去・振幅制限してPCMへ出す。 |
| `crates/chimera-cli/src/compare/tsp.rs` の `align_synth` と `over_noise_floor`、`a_render_is_aligned_over_a_noise_floor_like_the_recordings` | 同じ辞書、本文、雑音種でPCM16を作り、MFAの語・音素の始端と終端を秒で読む。上流試験は無音区間に載せた雑音床が目標の±0.5 dBで反復一致することを検査する。 |
| `crates/chimera/tests/golden_voice.rs` の `voice_matches_typescript`、`crates/chimera/tests/apical.rs` の `the_tip_barely_moves_from_the_consonant_into_the_vowel` | 前者は固定上流のPCM照合、後者は既定の舌先制御を使う歌唱で子音と母音の舌先位置を測る。今回の英語の初期値介入は新しい条件として別に評価する。 |
| 研究版 `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run`、`render`、`render_tract_profile` | 入力姿勢から発話器を作り、通常の `render-pcm` で波形を、`render` で指定フレーム完了直後の調音姿勢を採る。MFAの音素境界は `/ɛ/–/n/` の終端と始端、LPCは25 ms、12 kHz、次数12で観測する。 |

旧設定への介入で、最初の50 msに既報と同程度の波形差が現れると予測する。対象境界まで約2秒あるため、舌先座標はそこで1×10⁻⁶ cm以内に収まり、開始位置の216標本差は再現しないと予測する。F2は各条件固有の境界を使った窓のほか、基準と同じ境界を固定した窓でも測り、波形の差と窓開始の差を見分ける。全条件と合否は [ケース定義](../cases/tsp-again-initial-tip-mfa.json) に置いた。

## 実測

初期舌先を `(6.2414, 6.8105)` cmから旧値 `(6.45, 7.30)` cmに戻すと、最初の出力標本から波形が分岐した。最初の50 msの最大PCM差は0.0018885。調音姿勢の最大軸差は最初の制御更新後に0.48373 cm、50 msの時点で0.04120 cmだった。対象母音の開始約1.92秒と終了約2.04秒で採った舌先座標は完全一致し、1.90〜2.10秒の無加工PCMも9,600標本すべて一致した。MFAへ渡す全発話のPCM16では標本番号13から差が出て、4,773標本が異なった。最大差は62刻みだった。

| 条件 | /ɛ/ の終了境界 | 90%窓の開始標本（12 kHz） | F2 |
| --- | ---: | ---: | ---: |
| 設定を揃えた研究版 | 2.040秒 | 24,185 | 2,034.56 Hz |
| 初期舌先だけを戻して再整列 | 2.040秒 | 24,185 | 2,034.56 Hz |
| 設定を揃えた研究版のPCMに旧MFA境界を使用 | 2.060秒 | 24,401 | 2,144.09 Hz |

初期舌先だけを戻した条件ではMFAを再実行しても、基準と語・音素の区間がすべて一致した。90%窓のF2差109.53 Hzは旧境界を同じPCMへ適用すると現れた。旧比較には体型別出力ゲインと発声の揺らぎの設定差もあった。次に寄与を切り分ける場合は、同じ発話で周期長ジッターだけを旧設定に戻す条件を登録する。

窓中心は0.10、0.35、0.50、0.65、0.90。前回のケース定義にある0.25、0.75は誤記で、前回の実出力は0.35、0.65を使っていた。今回の判定では登録値と元のレポートを数値で照合した。5条件25窓の開始位置と欠測判定は一致し、固定Rustと独立計算のF1・F2採択値の最大差は4.09×10⁻¹² Hzだった。[前回の記録と訂正](tsp-matched-speech-mfa.md#実行と保存)・[25窓の比較](../runs/tsp-again-initial-tip-mfa-20261123-a/artifacts/window-comparisons.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、MFA 3.4.3。音響モデル、発音辞書、雑音床は第30版と同じ条件を使い、通常の研究CLIで計画・波形と調音姿勢を採った。上流は通常の `render text` で再描画し、LPCは固定版の観測入口と独立計算で照合した。研究ワークスペースから次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_again_initial_tip_mfa.py tsp-again-initial-tip-mfa-new
```

研究ワークスペースと `/tmp` からそれぞれ計測8判定・上流11試験に通過した。各28出力のうち、3つの実行ログを除く25出力がバイト一致した。RTL9210B-CGに条件別のケース、波形、調音姿勢、整列結果、LPC窓ごとの結果と試験ログを保存した。[初回のマニフェスト](../runs/tsp-again-initial-tip-mfa-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/tsp-again-initial-tip-mfa-20261123-repeat/manifest.json)
