# ウェッデルアザラシの持続音と停止のPCM

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流CLIの `render creature seal` は初期値から1.2秒発声させ、ゲート0で0.4秒をレンダーしてからコールを始める。今回は手動ゲートによる持続と停止を比較する。上流の `golden_creatures` は持続・停止を含むPCMとテレメトリを照合し、1・77・4096フレームの分割でも128フレームと同じ出力を要求する。`creature_realtime` は初期化とウォームアップ後のレンダーの割り当てを検査する。[CLIのレンダー順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形と分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 内部放射からPCMまで

`Seal::sample` は声門の開口を更新して気道を進める。気道各部の壁から放射される流量と、口端・鼻端の放射流量（cm³/s）の和を取り、前回値との差に内部レートを掛ける。咽頭・口腔の壁流量には放射係数0.6を掛ける。軟口蓋は閉じている。内部放射の出力は cm³/s²。各出力フレームにつき、60 kHz以下は2内部サンプル、60 kHz超は1内部サンプルを進める。ゲート目標はイベント以降の64出力フレーム境界で読まれ、立ち上がり6 ms・解除30 msで平滑化される。[声門と気道](seal-airway.md)・[放射係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L27)・[総放射流量の差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)・[内部レートと制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)

間引き率2では、正規化した49タップのKaiser窓付きsinc（内部レートに対する遮断周波数0.23、β=8.5）をゼロ初期化した履歴に畳み込み、内部サンプル1、3、5、…で値を取る。率1の係数は1。間引き後に固定ゲイン `6.4×10⁻⁸ × level` を掛け、`y[n] = x[n] − x[n−1] + exp(-2π·12/fs_out)·y[n−1]` でDC成分を除く。絶対値が0.7を超えると、絶対値を `0.7 + 0.3·tanh((|y|−0.7)/0.3)` に置き換えて符号を戻す。最後に単精度へ変換する。履歴と制御カウンターはホストの呼び出しをまたいで保持する。[間引きフィルタ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L48)・[ゲインと出力処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L47)・[DC除去・飽和](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L395)

## 事前の予測

48 kHz出力の標準条件では、内部サンプル38で初めて咽頭入口の圧力が変化する。壁の速度は次のサンプル39で変わり、初期ゼロ状態の口端の放射流量は咽頭28セルと口腔30セルを伝わったサンプル95で初めて非ゼロになると予測する。FIRの最初の係数が非ゼロなので、内部サンプル39を含む出力フレーム19からPCMがゼロを離れる。これは初めて非ゼロになる時刻で、聴取上の遅延やFIRの群遅延とは測り方が異なる。44.1 kHzでは開始指示73がフレーム128、内部サンプル256で適用され、同じ伝搬順を予測する。96 kHzでは間引きを経由しても放射の内部番号とPCMの番号が一致する。

128・77フレームの分割でWAVと観測CSVのハッシュが一致すること、無呼気は全区間ゼロ、増幅条件は0.7以上のサンプルの一部が抑えられることを事前条件にした。各内部サンプルで壁・口・鼻の流量を別々に取り、その和の差分が総放射を説明するかを調べる。独立計算ではSciPyのFIR設計と差分フィルタで保存済みの放射からPCMを再計算する。尾部は最後の20 msのRMSと停止前の窓を比べる。[ケースと判定条件](../cases/seal-sustain-pcm.json)

## 実装と実測

`SealVoice` は `SealBreath`、`SealAirway` と既存の `Decimator` をつなぎ、上流と同じ12 HzのDC除去と飽和を適用する。上流プローブは `CreatureVoice::render` を実行し、気道から実際に返った内部放射、壁・口端・鼻端の流量、出力PCMを同時に取る。別の計算として、壁・口端・鼻端から総放射を再構成し、SciPyで設計したFIRと差分フィルタからPCMを再計算した。[再実装](../crates/vocal-core/src/seal_voice.rs)・[上流プローブ](../tools/upstream_seal_voice_probe.rs)・[独立計算](../tools/measure_seal_sustain_pcm.py)

44.1・48・96 kHzの5条件、計194,089出力フレームで、128・77フレーム分割のWAVとCSVは全件一致した。48 kHzでは、演奏値を固定した発声の1.2秒と、ゲートを0に戻した後の0.4秒の全76,800フレームが、上流CLIのWAVおよびプローブとビット一致した。標準と遅延44.1 kHz条件の最大ピークはそれぞれ0.401、0.388。無呼気の1,024フレームは全区間ゼロだった。最後の20 msのRMSは各発声条件で持続時の `1.97×10⁻⁸` 以下だった。[実測値と判定](../runs/seal-sustain-20261120-repeat/summary.json)

| 出力条件 | 立ち上がり・停止の制御フレーム | 最初の壁放射（内部） | 最初の口端放射（内部） | 最初の非ゼロPCM（出力） |
| --- | --- | ---: | ---: | ---: |
| 48 kHzの上流CLIと同じ条件 | 0・57,600 | 39 | 95 | 19 |
| 遅延開始の44.1 kHz | 128・9,984 | 292 | 343 | 146 |
| 遅延開始の96 kHz | 192・16,064 | 231 | 287 | 231 |

48 kHzでは壁の放射が口端より56内部サンプル（約0.583 ms）先行し、総放射の差分は最初の壁の変化から現れた。3レートすべてで、鼻端放射は0だった。増幅条件ではDC除去後の絶対値が0.7を超えた2,613フレームに飽和がかかり、ピークは4.09519から単精度PCMの1.0に収まった。[放射の始点と出力レベルの比較](../runs/seal-sustain-20261120-repeat/summary.json)

上流との差は、総放射で最大 `1.09×10⁻⁷ cm³/s²`、PCMでは96 kHzの減衰中に20フレーム（最大 `7.11×10⁻¹⁵`）と増幅条件の減衰中に1フレーム（`4.44×10⁻¹⁶`）だった。96 kHz条件では放射の最初の数値差は内部サンプル231、最初のPCM差はフレーム31,980。候補と上流それぞれの放射を独立計算に入れると、DC除去後の絶対値が単精度の丸め境界を挟み、実測と同じ隣接2値になった。増幅条件のフレーム26,525も、各々の放射を使う独立計算で隣接2値を再現した。[気道での丸め差](seal-airway.md#実装と実測)・[出力の比較](../runs/seal-sustain-20261120-repeat/summary.json)

研究ディレクトリと `/tmp` からの実行で各163項目を通過し、要約・入力ケース・観測CSV・WAVが一致した。既存の気道の回帰159項目も通過した。次は下行コール `trill` のキー補間と演奏値の引き継ぎをPCMまで照合する。[初回の条件とツールチェーン](../runs/seal-sustain-20261120-a/manifest.json)・[再実行の記録](../runs/seal-sustain-20261120-repeat/manifest.json)・[気道の回帰](../runs/seal-airway-pcm-regression-20261120/manifest.json)
