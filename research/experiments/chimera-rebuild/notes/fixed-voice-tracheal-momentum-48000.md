# 気管の最初の直列枝の持ち越し運動量を揃える

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は内部点ごとに肺圧と声門開口を更新し、[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029) を呼ぶ。上流の気道は前回流量 `U_prev`（cm³/s）、前回慣性 `L_prev`（g/cm⁴）、前回運動量 `M_prev=L_prev×U_prev` を枝ごとに保持する。慣性が減ると、今回の慣性と前回流量から運動量を作り直す。気管の直列枝では断面が静的なので `L` と `L_prev` は等しい。上流は動圧に加える持ち越し項を `(L×U_prev)×Fs` で計算する。`Fs` は内部サンプルレートで、この積の単位は dyn/cm²。

研究版の [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) は同じ持ち越しを `(L/dt)×U_prev` と書く。有限精度では慣性を時間換算する位置で丸めが異なる。今回の試行では、[`HumanAirway::with_tract`](../crates/vocal-core/src/airway/human.rs#L80) が持つ気管の枝範囲を使い、構築時に最初の直列枝を一つ選ぶ。既存の声門枝の実験設定も引き継ぐ。対象の枝では持ち越し項だけを変更し、枝の線形係数 `L/dt + R` と弾性壁や節点の更新は対照と同じ式を使う。流量の更新後、節点では流入と流出から次の圧力を求める。したがって枝の差は同じ内部点で接続先の圧力に現れうる。

上流の [`output_does_not_depend_on_the_host_block_size`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78) を読み、通常の研究版CLIでもホスト側の分割を128と77にした場合のPCMを比較する。[先行の気管全域比較](fixed-voice-tracheal-onset-48000.md#最初の差は気管の最初の直列枝で生じる)で見つけた8,196点目の差が連続更新でも解消し、それ以前の観測値が保たれると予測した。開始・停止を含む全PCMについては、既存の絶対許容差で判定し、ビット差の数と位置も別に記録する。[事前登録](../cases/fixed-voice-tracheal-momentum-48000.json)

## 連続描画での圧力とPCMの変化

固定 `/i/` の出力48 kHz・内部96 kHz、ゲート開放4,096フレーム目の条件を用いた。先行の候補ソースと計測差分を隔離ディレクトリに復元し、対照の内部CSV、観測出力、PCMを保存済みの出力とバイト照合した。同じ隔離ソースで、肺側から最初の直列枝だけに持ち越し項の新しい計算順を適用した。

8,195点目まで気管の全13枝・13セルの流量と圧力は対照と一致した。8,196点目の枝1の流量は上流の `0.1445155836617482` cm³/s、セル1の圧力は `1.409117402697833` dyn/cm² に一致した。慣性と抵抗を足した線形係数も対照と一致した。今回の変更で、気管全域の次の初差は8,198点目の枝2に移った。その枝の持ち越し圧を `2.068679249381922` から上流の `2.0686792493819217` dyn/cm² に替えると、流量が上流の `0.1043749118920781` cm³/s に一致した。同じ流量をセル1の流出へ反映した検算では、セル1の圧力差も解消した。末端セル12の圧力の初差は対照の8,216から変更版の8,211点目へ移った。[内部系列と置換の判定](../runs/fixed-voice-tracheal-momentum-48000-a/summary.json)

| 固定上流とのPCM比較 | 対照 | 枝1の換算を変更 |
| --- | ---: | ---: |
| 最初のビット差が出た出力フレーム | 4,802 | 62,275 |
| ゲート開放中に差が出たフレーム | 1 | 0 |
| ゲートを閉じた後に差が出たフレーム | 12 | 10 |
| 最大絶対差 | 1.8189894×10⁻¹² | 1.1368684×10⁻¹³ |

ゲートを閉じるのは54,656フレーム目。両版で128・77のブロック分割は全93,056フレームでビット一致した。変更版と対照のPCMは9フレームで異なり、最大差は `1.8189894×10⁻¹²` だった。上流・対照に対して登録した絶対許容差 `5×10⁻⁷` 以内だった。[PCMの判定と各差の位置](../runs/fixed-voice-tracheal-momentum-48000-a/summary.json)

次は一様断面の気管に限り、全12本の直列枝で同じ運動量換算を試す。肺・声門ポートの設定は今回の対照と揃え、全域の圧力・流量の次の初差と、ゲート停止後のPCMを個別に比較する。

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_tracheal_momentum.py fixed-voice-tracheal-momentum-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_tracheal_momentum.py" \
  fixed-voice-tracheal-momentum-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各9判定と固定上流の各9試験に合格した。各実行につき対照と変更版の節点1,352点および枝1,352点を有理数と十進数で独立に再計算した。WAVの生PCMから3組の比較を再計算し、再実行間で観測、WAV、差分の15出力とビルドのハッシュが一致した。356入力・44出力をハッシュ照合し、採取物13,299,100バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/fixed-voice-tracheal-momentum-48000-a/manifest.json)・[再実行マニフェスト](../runs/fixed-voice-tracheal-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-momentum-48000.json)

圧力置換の要約に出る互換フィールド `glottal_outflow` は、この比較のセル1では枝2への流出を指す。同じ行の `trachea_outflow` と同値で、元の気管セルCSVでは `trachea_outflow` を使用する。
