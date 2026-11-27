# 同じ文の男性体型MK61_02で丸め前とPCMの誤差を照合する

女性体型FK61_02と同じ文を用いる確認用発話MK61_02を選んだ。保存済みの通常レンダーでは、男性設定の最大PCM差は女性設定の8分の1だった。全発話の変換前の誤差とPCMの誤差を照合し、この比が丸め前の誤差にも現れるかを測る。設定は両方とも内部96 kHz、出力48 kHz。男性側の発話基準F0は112 Hz、ゲインは5.5×10⁻⁷で、女性側は205 Hz、4.8125×10⁻⁷。発話条件ごとの比較として扱う。 [男性側の入力](../runs/tsp-held-out-matched-speech-20261123-repeat/artifacts/MK61_02/matched-case.json)・[女性側の比較](tsp-fk61-02-full-pcm-rounding.md)

## 通常経路と観測点

固定上流の `render text` は体型名を `say` に渡し、`text_f0` で発話計画の基準F0を決める。`HumanVoice::render` は壁・口・鼻の放射体積速度の和から時間差分を作り、49タップのFIRで48 kHzへ間引く。研究版の `render-pcm` と観測器には同じ体型の設定を渡す。放射時系列の単位は合算前後が cm³/s、時間差分後が cm³/s²。 [上流の発話計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L169)・[気道の放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1143)・[上流のFIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[研究CLI](../crates/vocal-cli/src/main.rs#L452)

ゲイン適用後の値 `x` と前フレームの入力・DC状態から `x − x_prev + c*y_prev` を求める。包絡とピーク保持時間を更新し、リミッターの閾値を確認する。作動しない範囲ではDC除去後の `f64` を `f32` に丸めた値がPCMになる。上流のエンジン試験は出力レートを変えた発声の有限性と振幅を、研究版の一様管試験は壁放射の重みと伝搬の状態を検査する。 [上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L397)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L104)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)・[研究版の試験](../crates/vocal-core/tests/uniform_tube.rs#L32)

## 事前に決めた条件

全144,727フレームを既存のMK61_02の合成PCMに照合し、初差9333、最大差82703、差のある1,254フレームを再現する。丸め前とPCMの最大差は異なる位置にあり、82703の隣接PCMは中点をまたぐと予測した。複数ULP差の95%以上は振幅10⁻⁶以下で、放射および変換前の初差はPCMの初差より早いとした。同文の女性設定に対する、変換前の版間RMS差の男性／女性比は0.5〜2と予測した。 [ケース定義](../cases/tsp-mk61-02-full-pcm-rounding.json)

## 実測

上流・研究版それぞれで、通常CLI、観測版、保存済みPCMが全144,727フレーム一致した。放射からPCMまでを内部289,454標本で再計算した。包絡の最大は約0.361で、リミッターは作動しなかった。声門流量の初差は内部4879、壁の放射流量と合算後の放射差分の初差は4880だった。口と鼻の初差は4912と40735。FIRと変換前の初差はフレーム2440で、PCMの初差9333より約0.144秒早かった。 [全観測点と再計算](../runs/tsp-mk61-02-full-pcm-rounding-20261124-registered/summary.json)

| 版間差の指標 | FK61_02・女性設定 | MK61_02・男性設定 | 男性／女性 |
| --- | ---: | ---: | ---: |
| 変換前の最大絶対差 | 9.021×10⁻¹⁴ | 1.569×10⁻¹³ | 1.740 |
| 変換前のRMS差 | 8.156×10⁻¹⁵ | 1.293×10⁻¹⁴ | 1.585 |
| PCMの最大絶対差 | 1.863×10⁻⁹ | 2.328×10⁻¹⁰ | 0.125 |
| PCMのRMS差 | 4.896×10⁻¹² | 6.136×10⁻¹³ | 0.1253 |
| 最大PCM差の1フレームを除いたRMS差 | 1.541×10⁻¹⁴ | 4.406×10⁻¹⁴ | 2.859 |

男性設定で変換前の差が最大の8620ではPCMが一致した。PCMの最大差82703は、保存済みの音素時刻で /ɫ/ の区間にある。隣接PCM値の中点から上流は−2.531×10⁻¹⁵、研究版は+2.550×10⁻¹⁵で、変換後に1 ULPの差が出た。82703は全PCM差の二乗和の99.48%を占めた。 [差の位置と中点](../runs/tsp-mk61-02-full-pcm-rounding-20261124-registered/summary.json)・[音素時刻](../runs/tsp-held-out-matched-speech-20261123-repeat/summary.json)

PCM差がある1,254フレームのうち1,187フレームが1 ULP、67フレームが複数ULPだった。複数ULPの全フレームで両版のPCM振幅は10⁻⁶以下で、その最大は1.291×10⁻⁷だった。最大のULP距離は5。事前に決めた五つの予測はすべて成立した。次は同じ評価方法を確認用12発話に適用し、丸め前とPCMの誤差による発話間の順位、および複数ULP差の振幅分布を集計する。 [振幅別の集計](../runs/tsp-mk61-02-full-pcm-rounding-20261124-registered/summary.json)・[確認用12発話](../runs/tsp-held-out-matched-speech-20261123-repeat/summary.json)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。上流のエンジン試験6件、研究版の一様管試験3件と計測の4判定に通過した。共通化後の集計でFK61_02も再計算し、保存済みの要約と一致した。採取と一時ビルドにはRTL9210B-CGを使用した。 [初回マニフェスト](../runs/tsp-mk61-02-full-pcm-rounding-20261124-registered/manifest.json)

`/tmp` から絶対パスで同じコマンドを実行した。観測系列、PCMのハッシュ記録、要約の3出力が初回とバイト一致した。 [再実行のマニフェスト](../runs/tsp-mk61-02-full-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_mk61_02_full_pcm_rounding.py tsp-mk61-02-full-pcm-rounding-new
```
