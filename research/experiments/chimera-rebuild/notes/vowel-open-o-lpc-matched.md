# 連続母音列と固定発声の /ɔ/ に同じLPC条件を適用する

基準の旧表示は、連続母音列の第1LPCピークが571 Hz、単独の固定発声が619.81 Hz。両方の保存済み48 kHz・float32波形を通常の入口から再描画し、2条件の波形を固定した。発声開始後0.300秒・0.375秒、窓長32 ms・100 ms、分析レート12 kHz・16 kHz、整数区間の平均・ポリフェーズFIR、LPC 12次・18次を全組合せで適用した。各波形の32条件と、固定側の旧条件（0.400秒開始）1件を測定した。揃えた窓は、連続母音列の呼気停止指示0.480秒より前に収めた。 [事前登録](../cases/vowel-open-o-lpc-matched.json)・[基準の母音比較](ten-vowel-benchmark.md#結果)

## 波形の入口から根の選別まで

固定上流の `render::vowels` は成人男性の較正済み姿勢を0.6秒周期で順に設定し、舌先の自由追従を有効にする。音高の設定は110 Hz。128出力フレームずつ描画し、句ごとの相対時刻0.480秒以降は呼気を止める。/ɔ/ は6番目で、開始はフレーム144,000。旧表示の窓は158,400から1,536フレームを取り、4標本を平均して384点の12 kHz入力にする。固定発声の研究CLIは較正された舌先座標を指定したまま一つの母音を描画し、旧測定は19,200から4,800フレームを16 kHz・18次で評価する。 [上流の通常レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L829)・[上流の姿勢指定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L298)・[研究版の固定発声ケース](../cases/vowel-voice-open-o.json)

LPCの入力は間引き後の振幅系列。上流の `estimate_formants` は前回標本との差をプリエンファシス係数0.97で作り、Hamming窓を掛ける。自己相関のラグ `k` には幅40 Hzに対応する `exp(-0.5 (2π·40·k / fs)^2)` を掛ける。Levinson–Durbinで予測係数を更新し、同じ多項式の根をDurand–Kernerで求める。正の虚部の根で、偏角から周波数 `arg(z)·fs/(2π)`、絶対値から帯域幅 `-ln(|z|)·fs/π` をHzで得る。周波数90 Hz以上、帯域幅600 Hz以下の根を周波数順に返す。独立計算はToeplitz連立方程式とNumPyの多項式根探索を使い、両方のナイキスト境界の実根を集計上区別した。上流のゴールデン試験では自己相関、係数、根、包絡、選別後のピークを比較する。 [上流のLPC](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[独立計算](../tools/measure_vowel_voice.py#L53)

## 観測結果

連続母音列の288,000フレームと固定発声の32,768フレームを、保存済みのPCMとビット照合した。全65窓でYINの推定は109.75〜110.28 Hz。公開LPCと独立計算の周波数・帯域幅の差は最大8.58×10⁻¹⁰ Hzで、採択された根を上流の全根から再現した。旧条件の連続側の最初の3ピークの表示571・932・2,425 Hzと固定側のLPC入力・全ピークも再現した。 [比較結果と全条件](../runs/vowel-open-o-lpc-matched-20261124-repeat/summary.json)

| 共通の開始 | 長さ・間引き・LPC次数 | 連続母音列の第1ピーク | 固定発声の第1ピーク | 固定−連続 |
| --- | --- | ---: | ---: | ---: |
| 0.300秒 | 32 ms・12 kHzの4点平均・12次 | 570.74 Hz | 602.23 Hz | +31.49 Hz |
| 0.300秒 | 100 ms・16 kHzのポリフェーズFIR・18次 | 620.01 Hz | 619.81 Hz | −0.20 Hz |
| 0.375秒 | 32 ms・12 kHzの4点平均・12次 | 571.58 Hz | 585.60 Hz | +14.02 Hz |
| 0.375秒 | 100 ms・16 kHzのポリフェーズFIR・18次 | 621.08 Hz | 619.94 Hz | −1.14 Hz |

0.300秒の4値から、分析設定を先に交換する経路と波形を先に交換する経路を計算した。波形を交換した差の平均は+15.6433 Hz、分析設定を交換した差の平均は+33.4244 Hz。固定側だけ開始を旧条件の0.400秒に戻す効果+0.000068 Hzを加えると、未丸めの旧条件差+49.0678 Hzを再現した。波形差が同じ設定でも10 Hz以上残るという予測と、旧差の半分以上を波形交換で説明できるという予測は不成立。同じ波形で分析設定を替えると第1ピークが動くという予測は成立した。交換の効果は登録した2分析条件と開始時刻に依存する。 [比較の計算](../runs/vowel-open-o-lpc-matched-20261124-repeat/summary.json)

有声窓のすべてに公開ピークが3つ以上あるとした初回の集計条件は1件で不合格だった。連続母音列の0.375秒から100 ms、16 kHzの3点平均、LPC 12次では、約2,255 Hzの根の帯域幅が約1,109 Hzで、600 Hzの上限を越えた。公開ピークは732.38 Hzと4,460.37 Hzの2つだった。同じLPC入力で次数を18にすると8ピークが採択され、第1ピークは619.47 Hzとなった。旧条件の3値の再現と全条件の第1ピーク・根選別の照合を分け、初回の不合格を保存した。 [初回の集計](../runs/vowel-open-o-lpc-matched-20261124-registered/summary.json)・[上流の全根](../runs/vowel-open-o-lpc-matched-20261124-repeat/artifacts/upstream-analysis.json)

次はこの窓と間引きを固定し、LPC 12〜18次について、約600〜750 Hzと2.3〜2.5 kHzの根・帯域幅・採択の変化を照合する。

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使用した。事前登録のSHA-256は `034d4bea310a65ae9959c7d9164a144b8a0f94351b8d89ef988dece261886067`。既存ビルドを使う条件で実行ごとに512 MiBを見積もり、空き約331 GiBとUUIDを確認したRTL9210B-CGに出力した。修正後、研究ワークスペースと `/tmp` から各11判定を通過した。 [修正後の初回](../runs/vowel-open-o-lpc-matched-20261124-verified/manifest.json)・[別ディレクトリからの再実行](../runs/vowel-open-o-lpc-matched-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_vowel_open_o_lpc_matched.py vowel-open-o-lpc-matched-new
```
