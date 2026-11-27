# 咽頭入口の壁面積だけを上流の演算順で求める

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L394) は声門の面積を設定し、気道が返す放射流量微分を間引き器に渡す。上流の [`AirwayNetwork::finalize`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L560) は管の周長補正係数 `q` から `q×2×√π` を事前計算する。[壁の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053) では現在の断面積 `A` とセル長 `dx` を使い、この係数に `√A` と `dx` を順に掛ける。`A` は cm²、`dx` は cm、壁面積は cm²。壁速度（cm/s）との積で壁流量（cm³/s）を求め、放射率を掛けて口端・鼻端の放射に加える。壁流量はそのセルが次に更新する圧力の体積収支にも入る。

研究版の [`Section::wall_surface`](../crates/vocal-core/src/airway/network.rs#L34) は `2×√(π×A)×dx×q` の順で同じ物理量を求める。[先行診断](fixed-voice-radiation-balance-48000.md#初差は咽頭入口の壁面積から放射へ伝わる) で初めて差が出たのは、上流・研究版とも絶対節点番号13の咽頭入口だった。今回の隔離ビルドでは、人間の声門ポートの下流側から対象セルを選び、そのセルの壁面積だけを上流順にする。壁速度の積分、口端・鼻端の負荷、微分の時間換算には対照の実装を使う。

上流の [`fdtd_impulse_response_agrees_with_frequency_domain_model`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68) は壁あり・なしの一様管で時間応答と周波数応答を比較する。今回は固定 `/i/` の初期放射で、8,206・8,207点目の壁流量和の一致を予測した。8,206点目には微分の時間換算の差が残り、8,207点目の微分は上流と一致することも先行の局所計算から予測した。[事前登録](../cases/fixed-voice-pharyngeal-wall-surface-48000.json)

## 初期放射とPCMの比較

声門抵抗まで揃えた隔離ソースと、先行の放射観測の差分を復元した。対象セルの壁面積だけを上流順にした版と対照を、同じゲート時刻と固定姿勢で通常CLIから描画した。対照の観測CSVとPCMは保存済みの値と一致した。対象を変えた版でも、観測した64内部点で他の壁の面積は対照と一致した。

| 観測点 | 対象セルの計算順を変えた結果 |
| --- | --- |
| 内部8,206点目 | 壁流量和が上流の `1.877746426367484×10⁻¹⁸` cm³/s に一致。微分は時間換算の丸めで1 ULP分かれ、上流と同じ `×Fs` を使う局所計算で一致 |
| 内部8,207点目 | 壁流量和と微分が上流に一致 |
| 内部8,208点目 | 残る最初の個別壁流量差は節点15。対象の咽頭入口は節点13 |
| 内部8,213点目 | フレーム末尾に現れる最初の微分差。今回と前回の合計流量は一致し、時間換算だけの置換で微分も一致 |
| 内部9,605点目 | 出力4,802フレーム目に対応。放射流量微分の上流との差が縮小し、このフレームのPCMは上流と一致 |

保存した64点の流量和を使い、微分を `差分×Fs` で計算する対照も十進計算で確認した。この局所計算では、上流との差が最初に残る点は8,220点目だった。その後の連続描画とPCMへの効果は、別の実験で確認する。[放射の比較結果](../runs/fixed-voice-pharyngeal-wall-surface-48000-repeat/summary.json)・[時間換算の検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-wall-surface-time-48000.json)

| 固定上流とのPCM比較 | 対照 | 咽頭入口の壁面積を変更 |
| --- | ---: | ---: |
| ビット差のあるフレーム | 17 | 15 |
| 最初に差が出た出力フレーム | 4,802 | 55,880 |
| ゲート停止後の差のあるフレーム | 16 | 15 |
| 最大絶対差 | `5.8207661×10⁻¹¹` | `5.8207661×10⁻¹¹` |

両版とも128・77の分割で全93,056フレームがビット一致し、登録許容差 `5×10⁻⁷` に収まった。変更版に残る15フレームの差はすべてゲートを閉じる54,656フレーム目より後だった。次はこの版を対照にして、放射流量微分の時間換算だけを上流順に揃える。

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharyngeal_wall_surface.py fixed-voice-pharyngeal-wall-surface-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_pharyngeal_wall_surface.py" \
  fixed-voice-pharyngeal-wall-surface-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各10判定と上流の各9試験が通過した。各実行の壁運動と流量4,608点、放射微分128点を独立計算で照合した。要約、計測CSV、WAV、差分など14出力が再実行間でバイト一致した。396入力と40出力をハッシュ照合し、採取物19,869,384バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-pharyngeal-wall-surface-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-wall-surface-48000.json)
