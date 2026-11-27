# 音源をそろえた4発話のMFA再整列

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。比較CLIの `compare::tsp::run` は合成発話を用意し、同じ無加工波形から、整列用PCM16と比較用信号を作る。対象は整列用PCM16から語・音素境界が決まる経路で、合成器やフォルマント推定器への変更はない。

| 参照元 | 入力と出力 |
| --- | --- |
| `crates/chimera-cli/src/compare/tsp.rs` の `align_synth` | 発話ごとの無加工モノラル波形と本文から、G2Pの音素辞書、ラベル、PCM16を用意する。発話をそれぞれ別話者のフォルダに置き、MFAが返すJSONから無音ラベルを除いた音素の開始・終了秒を得る。 |
| 同モジュールの `over_noise_floor`、`mean_square`、`percentile` | 48 kHzの入力を20 msの完全な窓に分け、平均二乗の95パーセンタイルから目標雑音電力を求める。乱数状態は発話ごとに `0x2545f491` に戻し、xorshift32のシフト13、17、5を適用して一様値を得る。差分の観測点は無加工float32、雑音加算後のfloat32、PCM16の順とする。 |
| `crates/chimera-cli/src/wav.rs` の `write` と `crates/chimera/src/math.rs` の `js_round` | 雑音加算結果を `[-1, 1]` に収め、32767倍し、半端が0.5の場合は大きい整数へ丸め、符号付き16ビットで保存する。 |
| `tools/tsp/mfa.yaml` と `a_render_is_aligned_over_a_noise_floor_like_the_recordings` | MFAのditherと話者適応を無効にする。固定上流の試験は、後半を無音にした正弦波の床が登録値の±0.5 dBに入り、雑音付加の再実行も一致することを確かめている。 |
| `tools/measure_tsp_phone_boundaries.py` の `alignment_wav`、`versions`、`mfa_run`、`tiers` | 研究側で雑音付加と量子化を実行し、既存のMFA 3.4.3と英語音響モデルで整列する。固定上流のRust関数に同じ無加工PCMを渡し、整列前の変換を標本単位で照合する。 |
| `tools/measure_tsp_stressed_vowel_formants.py` の `window`、`write_f2_candidates` | 音素境界を `a, b` 秒、中心の相対位置を `q` としたとき、12 kHzでの窓開始は `int(12000 × (a + q × (b − a))) − 150`。前回のF2候補レポートから実際に使用された窓を復元する。 |

雑音の最大振幅は `sqrt(3 × p95 × 10^(−47/10))`。両版の音源条件をそろえたPCMの差は前回最大1.86×10⁻⁹だったので、量子化で消えるか、丸めの境界にある標本で1刻みになると予測する。MFAに入る波形と辞書をそろえれば4組とも音素境界が一致し、以前の開始位置差15窓、最大216標本が解消すると予測する。対象は確認用の2文、男女各2発話。合否と入力のマニフェストは [事前登録](../cases/tsp-matched-speech-mfa.json) に記録した。

## 測定結果

| 発話 | 標本数 | 差のある無加工float32標本 | 雑音加算後のfloat32 | 量子化後のPCM16 | 一致した語／音素の区間数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `FK61_01` | 116,132 | 2,257 | 8 | 0 | 8／25 |
| `MK61_01` | 116,132 | 1,357 | 5 | 0 | 8／25 |
| `FK61_02` | 144,727 | 1,992 | 4 | 0 | 9／30 |
| `MK61_02` | 144,727 | 1,254 | 6 | 0 | 9／30 |

固定Rustと研究側の変換は、全8入力で量子化後の標本が一致した。雑音床は−47.00425〜−46.99696 dB、クリップ0件。上流4発話は保存済みのMFA入力と境界を再現した。研究版の旧入力に対しては、全4発話で音素境界が変わり、最大の境界差は `FK61_02` の50 msだった。

`FK61_01` の `again` の /ɛ/ では、旧研究版の終了境界2.060 sが2.040 sになった。90%窓の開始は、上流の24,185標本に対して旧研究版では24,401標本だった。再計測では両版とも24,185標本となった。共通60窓が前回の固定上流窓と一致したため、再整列後に使う窓には、[前回の共通窓でのF2照合](tsp-matched-speech-formants.md)を適用できる。実録音の再整列とF2候補への人手注釈はこの試験の対象外とした。

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1、MFA 3.4.3、英語音響モデル `english_us_arpa v3.0.0`、1ジョブで計測した。版指定と辞書・モデルのハッシュは保存済みケースを引き継ぎ、MFAの実行コマンドと依存環境一覧をマニフェストと成果物に記録した。新たな録音の取得は行っていない。研究ワークスペースからの計測コマンドを示す。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_matched_speech_mfa.py tsp-matched-speech-mfa-20261123-a
```

RTL9210B-CGの実体には整列用8本のPCM16、ラベル、辞書、MFAの語・音素区間JSON、窓ごとの開始位置を保存した。無加工PCMは既存のNPZを参照し、固定上流のビルドと変換の中間WAVは作業領域でのみ生成した。[初回のマニフェスト](../runs/tsp-matched-speech-mfa-20261123-a/manifest.json)・[再実行の要約](../runs/tsp-matched-speech-mfa-20261123-repeat/summary.json)・[窓ごとの比較](../runs/tsp-matched-speech-mfa-20261123-repeat/artifacts/window-comparisons.json)

研究ワークスペースと `/tmp` から計4判定・固定上流6試験をそれぞれ通過した。各32出力のうち、PCM16・MFA出力・窓別比較と要約を含む30出力がバイト一致した。残る2出力は計時を含む実行ログだった。[再実行のマニフェスト](../runs/tsp-matched-speech-mfa-20261123-repeat/manifest.json)

第31版で確認した訂正。第30版のケース定義に窓中心を0.25、0.75と記した箇所は、それぞれ0.35、0.65が正しい。計測は第29版が保存した候補レポートの中心0.10、0.35、0.50、0.65、0.90を読み込んでいた。窓別成果物と照合し、60窓の集計結果は変わらない。事前登録時の記述はマニフェストに残した。[実際の窓](../runs/tsp-matched-speech-mfa-20261123-repeat/artifacts/window-comparisons.json)・[窓中心を数値で照合するケース](../cases/tsp-again-initial-tip-mfa.json)
