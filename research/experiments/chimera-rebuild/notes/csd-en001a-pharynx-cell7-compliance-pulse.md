# CSDの咽頭セル7で標本0の圧力差を口端まで追う

`en001a` の先頭2句を48 kHzで出力する。96 kHzの標本0で咽頭セル7（節点20）のコンプライアンスだけを、同じ版の初期面積交換時に採った値へ置き換える。比較は両版それぞれの通常、初期面積交換、コンプライアンス一値交換の3条件で行う。 [事前登録](../cases/csd-en001a-pharynx-cell7-compliance-pulse.json)・[先行実験の128標本](csd-en001a-pharynx-cell7-first-block.md)

## 呼び出しと更新順

上流の `HumanVoice::render` は内部標本ごとに発声制御と声門を更新し、`AirwayNetwork::step` の放射差分を間引き器に渡す。気道は形状ランプと体積源、乱流と枝の流量、壁の流量、節点圧力の順に更新する。開いた非放射節点の圧力（dyn/cm²）は、更新前圧力に `(dt/C) × 正味流入` を足す。時刻幅 `dt` は秒、コンプライアンス `C` はcm⁵/dyn、正味流入はcm³/s。交換点はこの一式が受け取る `C` で、セル形状や枝係数を求める処理の後にある。密閉空洞試験では、体積を押し縮めたときの圧力を線形断熱式と比較している。 [レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の圧力更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1110)・[密閉空洞試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L55)

研究版も `FixedVoice::step_source` から形状更新、枝、壁、節点へ進む。通常の圧力更新式は同じ。枝はその標本の節点更新より前の圧力を読むので、標本0の差は隣の節点へ早くても標本1に伝わる。両版の区間20→43は咽頭から口腔への直列経路で、口端までに23本の枝を経る。壁面は各節点の局所圧力を読むため、壁放射の合計への影響は口端への到達を待たない。 [研究版の声門と気道](../crates/vocal-core/src/voice.rs#L213)・[研究版の圧力更新](../crates/vocal-core/src/airway/network.rs#L770)・[上流の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L150)・[口端の同定](csd-en001a-first-lip-load.md)

壁・口・鼻の体積速度（cm³/s）を加え、前回合計との差を時刻幅で割って放射差分（cm³/s²）を得る。上流では最初の制御更新以降、制御境界で微小な前回値をゼロにする。放射差分をFIRと2対1の間引き、出力ゲイン、DC除去へ渡し、出力制限の発動条件を確認してfloat32変換を検算する。 [先行の出力段の独立計算](../tools/measure_csd_en001a_two_phrase_pcm_rounding.py#L203)・[ホストのブロックに依存しない出力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L77)

## 一値交換で観測した差

両版とも標本0で節点20だけの圧力を初期面積交換と同じ値にできた。正味流入は同じで、コンプライアンスが減る上流では圧力差が −4.235×10⁻²² dyn/cm²、増える研究版では +4.235×10⁻²² dyn/cm² だった。数値は各版の一値交換から通常を引いた差。標本番号は0始まり。 [採取と検算の要約](../runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-registered/summary.json)

| 最初に差が現れた観測点 | 上流 | 研究版 |
| --- | ---: | ---: |
| 節点20の圧力（内部標本） | 0 | 0 |
| 壁放射の合計（内部標本） | 全点一致 | 86 |
| 口端の圧力（内部標本） | 先頭128標本で一致 | 99 |
| 口端流量・放射差分（内部標本） | 全点一致 | 100 |
| float32変換の直前（出力フレーム） | 全点一致 | 54 |
| PCM（出力フレーム） | 全点でビット一致 | 26,133 |

上流は標本1の節点21まで差が届き、採取した全71節点の圧力は標本2〜127で一致した。壁・口・鼻の放射も全403,200標本で一致し、壁放射が口端流量に先行するという予測を上流では確認できなかった。研究版も標本2では全71節点の圧力が一致したが、標本3で節点20と21に差が再び現れた。前回の3節点モデルに、外側の枝の通常流量と標本0のコンプライアンスだけを与え直すと、上流は全128標本、研究版は標本0〜4の3節点圧力を再現した。研究版で最初に再現できなくなる標本は5。 [3節点モデル](../tools/measure_csd_en001a_pharynx_cell7_first_block.py#L94)

研究版のPCM差は22,334フレームに出た。最大差は最初の相違フレーム26,133の1.654×10⁻²⁴で、このフレームの通常PCMは −1.742×10⁻¹⁷、交換後は隣のfloat32値だった。初期面積交換との差はなお89,603フレームあった。上流は一値交換後も通常と全PCMがビット一致し、初期面積交換との差8,688フレームがすべて残った。 [全区間の差と測定した判定](../runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-registered/summary.json)

## 標本3で圧力差が戻る理由の検算

局所モデルで標本2の更新後、研究版の内側枝19→20と20→21の流量差をそれぞれ −1.059×10⁻²²、+2.118×10⁻²² cm³/s と計算した。この2値だけを標本3の通常入力の前回枝流量に渡すと、節点19〜21の実測圧力差を再現した。節点20は −6.776×10⁻²¹、節点21は +6.776×10⁻²¹ dyn/cm²。標本2の壁速度・変位だけを渡した場合、標本3の圧力は通常入力と一致した。次は実際の枝履歴を採って、この局所モデルの予測と照合する。

研究ワークスペースからの検算では、保存済みの通常描画を初期値にし、標本2までの局所モデルが返した枝流量・壁運動を標本3に個別に渡す。結果の配列順は節点19、20、21。

```bash
PYTHONPATH=tools ../../.venv/bin/python - <<'PY'
from pathlib import Path
import numpy as np
import measure_csd_en001a_pharynx_cell7_compliance_pulse as pulse

study = pulse.tsp.read(pulse.CASE)
base, _, case, _, _ = pulse.study_inputs(study)
run = Path('runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-repeat')
summary = pulse.tsp.read(run / 'summary.json')
rows, _ = pulse.block.read_events(
    base[0] / 'artifacts/candidate_native-block.csv', case['measurement'], False)
compliance = list(rows[0]['compliance'])
compliance[1] = summary['sides']['candidate']['sample_zero']['compliance_only']['used_c']
state = pulse.block.simulate([rows[0] | {'compliance': compliance}, *rows[1:3]], 96000, False)[2]
ordinary = rows[3]
branches = ordinary['branches'].copy()
for i, flow in enumerate(state['inner'], 1):
    before = branches[i]
    branches[i] = before | {'previous_flow': flow, 'previous_momentum': before['previous_inertance'] * flow}
walls = [base | {'previous_velocity': trial['wall']['velocity'],
                 'previous_displacement': trial['wall']['displacement']}
         for base, trial in zip(ordinary['walls'], state['rows'], strict=True)]
with np.load(run / 'artifacts/network.npz', allow_pickle=False) as measured:
    native = measured['candidate_native_pressure'][3, 19:22]
    observed = measured['candidate_compliance_only_pressure'][3, 19:22]
for label, replacement in [('枝履歴', {'branches': branches}), ('壁履歴', {'walls': walls})]:
    solved = pulse.block.simulate([ordinary | replacement], 96000, False)
    predicted = np.array([node['pressure'] for node in solved[0]['rows']])
    print(label, predicted - native, np.array_equal(predicted, observed))
PY
```

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。事前登録のSHA-256は `878511713c71002ec061ba3fe1115e51114c17af3bfb2a721aa28defe07f5c3f`。各版の3条件で全歌唱計画、各403,200内部標本の放射合算・差分と201,600 PCMフレームを照合した。通常と初期面積交換については第1制御ブロックの圧力系列、短区間の形状、PCMにも一致した。上流の幾何・気道の7試験、研究版の再標本化の1試験を実行した。計測用の一時ビルドと検証済みの採取物はRTL9210B-CGに置いた。 [初回のマニフェスト](../runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_csd_en001a_pharynx_cell7_compliance_pulse.py csd-pharynx-compliance-pulse-new
```
