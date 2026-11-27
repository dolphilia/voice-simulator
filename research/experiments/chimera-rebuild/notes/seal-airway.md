# ウェッデルアザラシの気道と声門

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。手動制御を受ける `CreatureVoice::render` から、内部ステップの `Seal::sample`、共通の `step_glottis` と `AirwayNetwork::step` を追う。今回の出力は間引き前の内部状態と放射。既存の上流試験は持続、停止、初期パラメータ、コールの加工後PCMとテレメトリを照合する。[上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[サンプルループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[種ごとの計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L27)・[上流の波形と時間分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)

## 構造と更新順

肺は長さ1 cm・面積100 cm²の固定圧力節点。面積4 cm²の肺ポートを介して、長さ24 cm・面積4 cm²の気管に接続する。気管端と咽頭の間には長さ0.4 cm、幅1.8 cmのスリット粘性を持つ可動声門ポートがある。咽頭11 cmから口腔12 cmへは直結し、咽頭終端から鼻腔12 cmへの軟口蓋ポートは面積0。口端と鼻端に放射負荷があり、咽頭・口腔の壁流量も0.6倍で放射に足される。咽頭を3 cm²とし、口腔末端のセル中心 `u > 0.8` に `0.3 + 4 × mouth` cm²を与える。これらの断面は初期制御で確定し、初期化だけによる体積流を出さない。気管は `floor(24 / ((c/fs/0.93) × 1.6))` セルを3〜60に制限する。[共通の気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L51)・[セル数と肺の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L8)・[断面と声門の指定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)

制御境界で固定肺圧を更新する。各内部サンプルでは、直前の気管端圧から咽頭入口圧を引いた `Δp`（dyn/cm²）を声門モデルに渡す。声門は `Δp` を低域通過させて振動の有声度に反映し、別に平滑化する固定の隙間0.01 cm²を振動成分に足す。出力面積をポートに反映し、枝の慣性・粘性・二次損失から流量（cm³/s）を更新する。枝の更新後に各節点の圧力が進み、次のサンプルの声門差圧になる。声門の乱流は直前の枝面積と流量から求め、順流では咽頭の2本目の枝、逆流では気管の最後の枝に圧力を加える。出力となる総放射流量の差分は cm³/s²。周期、F0ドリフト、乱流の上流既定シードは順に777、4242、12345。[声門モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L111)・[圧差と乱流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L90)・[気道の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)

## 事前の予測

ゼロ状態の初回加圧では、肺ポートの二次損失係数は0で、`U = P / (fs·L + R)`。慣性 `L` には両端の半セルを、抵抗 `R` には円形管の粘性と `ρc/(2A)` を含める。同じステップに気管入口へ `Δp = U/(fs·C)` が現れ、気管端に達するまで声門流量はゼロのはず。気管のセル数だけ内部サンプルを進めると、声門が初めて非ゼロの圧差を読み、同じサンプルで流量が生じると予測する。44.1 kHzの開始指示73は出力フレーム128、内部サンプル256から反映され、その分だけ伝搬の起点が遅れる。

無呼気では声門の隙間が `0.01 × (1 − exp(−t/0.004))` cm²へ立ち上がり、圧力・流量・放射は常に0。標準の18 Hz、デューティ比0.55では最初の休止に入る区間の肺圧が深さ0より低いため、同区間の声門流量のRMSも深さ0より低くなると予測する。判定対象は `[3000,4000)` の内部サンプル。口端が狭い条件では形と音源の指定をそろえて上流と照合する。[ケース・観測区間・許容差](../cases/seal-airway.json)

## 実装と実測

既存の `SealBreath`、`Glottis`、`AirwayNetwork` を組み合わせた。上流プローブはレンダーを包み、実際の `Seal::sample` の直前に入力差圧、直後に面積・枝流量・節点圧・放射を読む。非公開の声門F0と有声度は、同じ差圧と初期制御を別の上流 `ParametricGlottis` に渡して測った。この声門モデルが出した面積と実レンダーの声門ポートの面積は全行で一致した。[再実装](../crates/vocal-core/src/airway/seal.rs)・[上流比較プローブ](../tools/upstream_seal_airway_probe.rs)・[実行結果](../runs/seal-airway-20261120-a/summary.json)・[上流ライセンス](../LICENSE-CHIMERA)

48 kHzの標準条件は内部96 kHzで気管38セル。最初の固定肺圧1,099.09 dyn/cm²から、肺ポート流量26.45579 cm³/s、気管入口圧152.33609 dyn/cm²が生じた。独立計算で `P/(fs·L+R)` と入口のコンプライアンスを使うと、丸め誤差の範囲で同じ値になった。上流と候補で、気管端に圧力が現れる最初の内部サンプルは37、差圧が声門に渡り、同じステップで流量と咽頭入口圧が生じるのは38だった。ここでいう最初の時刻は数値が厳密にゼロを離れた時点。比較条件の44.1 kHzでは、内部サンプル256で加圧し、気管端が290、声門流量が291で応答した。[伝搬時刻と独立計算](../runs/seal-airway-20261120-a/summary.json)

標準条件では総放射流量の差分がサンプル39から非ゼロになった。この時点の信号源は、伝搬経路と放射の式から、咽頭の入口側の壁運動と判断できる。鼻腔は閉じた軟口蓋を通る流量と鼻端の放射が0で、口端まで圧力が伝わるには咽頭・口腔の残りのセルを経る必要がある。次の測定では壁面と口端の放射を個別に保存し、この先行成分が最終PCMにどの程度現れるかを調べる。[ネットワークの壁と放射の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1048)・[放射の最初の観測点](../runs/seal-airway-20261120-a/summary.json)

96 kHzの無呼気では、声門面積の独立式との差は最大 `2.60×10⁻¹⁷ cm²` で、圧力・流量・有声度・放射は全て0だった。標準パルスの休止区間では、平均肺圧3,913.51 dyn/cm²、声門流量RMS 47.86 cm³/s。パルス深さ0の同時刻ではそれぞれ9,783.77 dyn/cm²、105.99 cm³/sだった。[無呼気とパルス深さ0の比較](../runs/seal-airway-20261120-a/summary.json)

標準条件で最初の数値差はサンプル2の肺ポート流量だった。保存した直前の流量と圧力から再計算すると、慣性を時間間隔で割ってから流量を掛ける候補の式は58.14967186749952 cm³/s、慣性と流量の積を保持してから時間間隔の逆数を掛ける上流の式は58.14967186749953 cm³/sとなり、各々の観測値に一致した。全27,648内部サンプルでは声門流量の上流との差は最大 `9.09×10⁻¹³ cm³/s`、総放射流量の差分は最大 `6.55×10⁻⁸ cm³/s²`。159項目を通過した。[候補の枝更新](../crates/vocal-core/src/airway/network.rs#L187)・[上流の運動量更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[差の最初の位置と最大値](../runs/seal-airway-20261120-a/summary.json)
