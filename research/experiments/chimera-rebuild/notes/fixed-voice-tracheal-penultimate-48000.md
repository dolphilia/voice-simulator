# 固定 /i/ の気管の最後から2番目の節点と直列枝

## 読解と事前の予測

固定上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は肺圧と声門面積を先に設定してから気道を1内部点だけ進める。[`HumanAirway::new`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L106) では、気管を円筒の一様断面として分割する。今回は末端の一つ手前の節点を挟む、肺側から入る枝と声門側へ出る枝の2本を調べる。正の流量は肺から声門に向かう。

上流の [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L955) と研究版の [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) は、枝の左右に残る更新前の圧力と、枝自身の前回流量を使う。枝の慣性 `L` は隣り合う半セルの `ρℓ/A` の和で、単位は g/cm⁴。線形係数は `L/dt + R`、駆動圧は `p_left − p_right + p_noise + M/dt`。ここで `R` は粘性抵抗、`M` は前回から引き継ぐ流量×慣性。上流は線形項を `L×Fs`、運動量を `M×Fs` として計算する。研究版のこの直列枝では `L/dt` と `(L_carry/dt)×U_prev` を使う。損失係数 `K` は枝が出入りする断面差から作り、駆動圧の符号で選ぶ。一様断面では `K=0` になると予想する。その条件で流量は駆動圧を線形係数で割った値となる。

枝をすべて更新し、壁流出を引いてから節点を更新する。内部点 `n` の節点更新は、次の点 `n+1` の枝から参照される。上流の [`steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92) は狭窄における定常圧力差、[`sealed_cavity_compression_follows_the_linearised_adiabatic_law`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56) は節点での圧縮を検証する。今回の独立計算では、静的な気管の2本の枝とその間の節点を同じ内部番号で照合する。

先行実験で、末端に向かう枝が8,214点目に読む圧力には差があり、流量の初差は8,215点目だった。そこで一つ手前の節点の更新後圧力の初差を8,213点目と予測した。最初の圧力差を作る項は肺側からの流入、末端への流量差では駆動圧・持ち越し運動量・線形係数の寄与を個別に見る。区間と判定条件を[ケース定義](../cases/fixed-voice-tracheal-penultimate-48000.json)に固定した。

## 最初の流量差は枝が読む肺側の圧力から生じる

先行のゲート入力と固定姿勢で、4,120出力フレームのうち内部8,188〜8,239点目を詳しく採取した。研究版は先行実験と同じ隔離ソースおよび変更差分を復元し、固定上流も別ディレクトリに展開した。追加の計測では、気管直列枝の更新値と、両枝に接続する節点の圧力更新を記録する。両版の描画、末端の収支、声門枝の記録は、観測を追加する前の保存値と照合した。

| 内部サンプル | 最初に分かれた観測点 | 局所計算による確認 |
| ---: | --- | --- |
| 8,213 | 肺側から入る枝が読む圧力と、枝の流量 | 肺側の圧力を `0.022261349757830905` から上流の `0.022261349757830902` dyn/cm² に置き換えると、流入が上流の `0.0007920371119121286` cm³/s に一致した |
| 8,213 | 末端の一つ手前の節点の更新後圧力 | 流入の置換だけで、圧力が `0.007093779608658107` から上流の `0.007093779608658105` dyn/cm² に一致した |
| 8,214 | 末端へ出る枝の駆動圧 | 肺側の圧力と持ち越し圧が分かれ、駆動圧は `0.009871063211213643` と `0.009871063211213641` dyn/cm²。除算後はいずれも `0.0002441731379636106` cm³/s |
| 8,215 | 末端へ出る枝の流量 | 肺側の圧力を置き換えると、流量が `0.0006163834630005989` から上流の `0.0006163834630005988` cm³/s に一致した |

両直列枝とも、慣性から換算した値 `40.40861538461539` と、抵抗を加えた線形係数 `40.4264911920194` は52点を通じて両版で一致した。抵抗自体には丸め差があり、持ち越し圧にも8,205点目から差が見えた。初めて流量が分かれる点では、これらの項の置換によって流量は変わらず、肺側からの圧力の置換で上流値を復元できた。損失係数は両向きともゼロだった。[初差、係数と置換結果](../runs/fixed-voice-tracheal-penultimate-48000-a/summary.json)

次の採取では、同じゲート入力で肺ポートから気管末端までを一度に観測する。肺境界圧、気管各セルの前後圧力、各直列枝の流量を同じ内部番号でそろえ、8,213点目の流入が読む圧力差をさらに肺側へ追う。抵抗差と運動量の丸め差が実際に枝の出力へ現れる点も同じ採取で区別できる。

## 実行と検証

```bash
# 研究ワークスペースで初回を実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_tracheal_penultimate.py fixed-voice-tracheal-penultimate-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_tracheal_penultimate.py" \
  fixed-voice-tracheal-penultimate-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各実行の8判定と固定上流の12試験が通過した。各実行の節点104点と枝208点について、有理数と十進数で更新を再計算した。観測CSV、固定上流PCM、計測差分など13出力がバイト一致した。上流プローブの実行ファイルは再ビルド間でハッシュが異なり、判定と計測値を含む要約のその他の項は一致した。354入力と44出力をSHA-256で照合し、採取物4,903,689バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/fixed-voice-tracheal-penultimate-48000-a/manifest.json)・[再実行マニフェスト](../runs/fixed-voice-tracheal-penultimate-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-penultimate-48000.json)
