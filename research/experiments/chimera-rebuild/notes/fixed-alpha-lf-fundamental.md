# 固定 /ɑ/ で固定LFの声門流量の基本波だけを合わせる

元の通常発声と固定LFの比較では、固定LFの口端流量の交流RMSは2.85%低下した。保存波形の口端側で110 Hzの複素係数を通常発声に戻すと、計算上の低下は6.40%だった。今回は声門流量の110 Hzを合わせ、気道を通した口端と総放射を再計測した。 [事前登録](../cases/fixed-alpha-lf-fundamental.json)・[保存波形の電力収支](fixed-lf-radiation-harmonic-budget.md#観測結果)

## 上流の描画と固定入力の経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、肺圧を設定し、声門両側の圧差から声門面積を更新して `AirwayNetwork::step` を呼ぶ。そこで求めた枝流量には、圧差・前の運動量と、流向別の二次損失が入る。全枝の流量を節点の収支に加え、壁の運動、節点圧、口端・鼻端の放射を進める。放射の戻り値は、壁の放射寄与と開口の放射流量の和の後退差分であり、通常発声はその後に間引きと出力段を通る。上流の短い狭窄の試験は、狭窄が1セルと1/4セルを占める場合に定常流を測り、ベルヌーイ近似と15%以内で照合する。 [通常発声の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝の二次損失](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[節点圧と放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1110)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

固定姿勢プローブの `write_fixed_airway` は、閉じた声門枝を持つ固定 /ɑ/ の咽頭入口の外部注入流量を直接設定する。研究版は `vocal-cli render` から `render_fixed_airway` を呼び、同じ姿勢・注入サンプル列で気道を進める。入力前は定常流139.8857905134376 cm³/sを0.80秒与え、標本76,800から19,200標本の周期列を4回繰り返した。観測量は咽頭入口圧（dyn/cm²）、口端・壁などの体積流量（cm³/s）、総放射の差分（cm³/s²）。最初の128標本と最後の2ブロックを保存した。 [上流の固定姿勢プローブ](../tools/upstream_sagittal_probe.rs#L269)・[研究版CLIの入口](../crates/vocal-cli/src/main.rs#L371)・[研究版の周期入力](../crates/vocal-cli/src/geometry_case.rs#L569)

## 110 Hzだけの変更と独立計算

96 kHzの19,200標本は110 Hzの22周期にあたり、複素DFTの22番ビンに一致する。通常発声と固定LFの流量差を22番ビンに直接射影して複素係数の差 `ΔQ` を求め、固定LFの入力に `2 Re(ΔQ exp(2πi·22n/19200))` を足した。正負の周波数の係数を共役にすると実数の入力になる。FFTで全ビンを検査し、110 Hzが通常発声に一致し、平均流量とほかのビンが固定LFに一致することを照合した。入力の構成と合否判定は事前登録に従い、固定上流と研究版の通常の描画を共通の計測処理で呼び出した。 [入力の生成と照合](../tools/measure_fixed_alpha_lf_fundamental.py#L56)・[周期描画の呼び出し](../tools/measure_fixed_alpha_periodic_flow.py#L82)

最後の22周期では、110 Hz・660 Hz・770 Hzの直接DFTをFFTと照合し、交流成分の平均二乗は時系列の分散と片側スペクトルの電力和で別々に求めた。壁・口・鼻の放射流量を足した列から総放射を後退差分で再構成し、前ブロック末尾の1標本を窓先頭の差分に使った。定常点を線形化した節点方程式では入口の110 Hzの変化に対する口端の複素変化を予測した。口端側で基本波だけを置換した場合のRMSは、固定LFの交流平均二乗から基本波の電力を引き、通常発声の基本波の電力を足して求めた。 [流量と放射の計測](../tools/measure_fixed_alpha_lf_fundamental.py#L73)・[平均流での離散節点応答](../tools/measure_fixed_alpha_periodic_flow.py#L136)

切替の標本では枝の更新が前標本の節点圧を読むため、入力の差 `ΔU` が現れるのは咽頭入口の節点圧からと予測した。独立計算では、入口の有効コンプライアンスを `C`、標本周期を `Δt` とすると、その標本の圧力差は `ΔU·Δt/C` となる。口端への初着は、固定 /ɑ/ で咽頭入口から口端に至る35枝が基準になる。 [初期圧と伝搬段数の照合](fixed-alpha-periodic-flow.md)

## 実測

| 周期入力 | 口端流量の交流RMS（cm³/s） | 総放射の交流RMS（cm³/s²） |
| --- | ---: | ---: |
| 通常発声 | 149.9621 | 206,436.33 |
| 固定LF | 145.6830 | 141,187.80 |
| 固定LFの110 Hzを通常発声に合わせる | 140.3734 | 138,544.90 |

声門入力の基本波を合わせると、通常発声に対する口端流量のRMS低下は2.853%から6.394%になった。口端で基本波だけを直接置換する計算は6.399%で、再描画との差は0.00537パーセントポイント。再描画で固定LFから減った口端の交流平均二乗について、110 Hzの寄与は−1,519.05 (cm³/s)²、ほかのビンの合計は+0.202 (cm³/s)²だった。総放射のRMS低下は31.61%から32.89%に増えた。元の固定LFの5%判定は不合格のまま保存した。 [再描画の結果](../runs/fixed-alpha-lf-fundamental-20261124-repeat/summary.json)・[元の判定](../runs/fixed-lf-glottal-flow-20261121-b/summary.json)

全ビンの入力係数は目標とピーク相対1.80×10⁻¹⁶以内で一致した。口端の110 Hzの複素変化に対し、定常点の離散線形予測との差は0.0136%。入力係数が等しい660 Hzと770 Hzでも、口端の複素係数は比較元の固定LF比でそれぞれ0.0202%、0.0233%変化した。線形モデルの110 Hzへの応答だけではこれらの変化は生じない。どの枝がこの差を生んだかは、枝ごとの圧力損失を観測して確かめる。

咽頭入口圧は切替標本で590.4714 dyn/cm²変わり、入口のコンプライアンスから求めた値と一致した。最初の差は総放射で1標本後、咽頭と口腔の接続節点圧で17標本後、口端流量で35標本後に観測した。総放射に口端より早く現れる差は壁の寄与と同じ標本から始まった。両版の時系列はピーク相対2.03×10⁻¹⁴以内で一致し、通常発声と固定LFの再計測は以前の周期再入力の保存波形とビット一致した。 [各段の最初の差と時系列の比較](../runs/fixed-alpha-lf-fundamental-20261124-repeat/summary.json)

## 再実行と保存

研究ワークスペースから未使用の実行IDで指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_alpha_lf_fundamental.py fixed-alpha-lf-fundamental-local-01
```

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` から各22判定と固定上流の狭窄試験に通過した。要約と5成果がバイト一致し、圧縮観測12,997,422バイトを作業用RTL9210B-CG上で共有した。 [初回](../runs/fixed-alpha-lf-fundamental-20261124-registered/manifest.json)・[再実行](../runs/fixed-alpha-lf-fundamental-20261124-repeat/manifest.json)・[全体監査](../runs/plan-completion-v20-alpha-lf-fundamental-20261124/manifest.json)
