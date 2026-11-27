# 放射流量微分の時間換算を上流と揃える

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L394) は気道を内部番号ごとに更新し、気道が返す放射流量の時間微分を間引き器へ送る。上流の [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053) は壁の放射寄与と口端・鼻端の放射流量を合計した後、前回合計との差 `ΔU`（cm³/s）に内部サンプルレート `Fs` を掛ける。微分 `ΔU×Fs` の単位は cm³/s²。その後、今回の合計を次の内部点のために保存する。[上流の微分と状態更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)

研究版の [`AirwayNetwork::step_with_prescribed_flow`](../crates/vocal-core/src/airway/network.rs#L791) は `ΔU/dt` を使う。`dt` は `1/Fs` を二進64ビットに丸めた値であり、96 kHzでこの丸めを含む除算と直接の乗算にはビット差が生じうる。隔離ビルドで、先行実験がすでに保持している内部サンプルレートを用いて最終の微分だけを計算し直す。壁の速度更新、放射負荷、流量の合算、前回合計の更新には対照と同じ式を使う。

上流の [`fdtd_impulse_response_agrees_with_frequency_domain_model`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68) は時間応答の放射スペクトルを周波数領域の予測と比較する。[`output_does_not_depend_on_the_host_block_size`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78) はホスト分割の違いに対する出力のビット一致を検査する。[咽頭壁面積の先行実験](fixed-voice-pharyngeal-wall-surface-48000.md#初期放射とpcmの比較)では、保存された流量の局所計算で8,206・8,213点目の微分差が消え、最初に残る差は8,220点目だった。今回もその時系列の順序を予測し、通常CLIで入力と分割を揃えて停止後まで描画する。[事前登録](../cases/fixed-voice-radiation-derivative-48000.json)

## 残った微分差は咽頭入口の圧力差から伝わる

咽頭入口の壁面積まで揃えた隔離ソースを復元した対照と、放射微分の時間換算だけを乗算に替えた版を比較した。固定 `/i/`、出力48 kHz・内部96 kHz、ゲート開放4,096・停止54,656出力フレーム目の条件を使った。採取した64内部点では、壁の状態と流量、口端・鼻端流量、今回と前回の流量の合計が対照の値とビット一致した。観測した放射微分のビット差は28点から22点に減り、予測した8,206・8,213点目は上流に一致した。変更版の最初の残差は内部8,220点目、フレーム末尾の最初の残差は8,221点目だった。[放射成分とPCMの比較](../runs/fixed-voice-radiation-derivative-48000-repeat/summary.json)

8,220点目では、咽頭入口の節点13からの壁流量だけを上流値にすると、放射流量微分が上流の `0.0007515525574101965` cm³/s² に一致した。節点13の壁面積・前回速度・前回変位は両版で一致した。今回の壁入力圧は研究版 `0.0013183272113715158`、上流 `0.0013183272113715156` dyn/cm² で、上流圧への置換だけで壁流量も再現した。壁が読むのは直前の節点更新の結果。8,219点目の保存済みの咽頭収支と照合すると、咽頭内へ向かう流出だけを `1.5797716149445316×10⁻⁵` から上流の `1.579771614944532×10⁻⁵` cm³/s に替えて入口圧を再現できた。[節点13の壁流量の検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-derivative-residual-48000.json)・[咽頭流出の置換](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-derivative-pharynx-48000.json)・[照合した固定上流の収支](../runs/fixed-voice-pharynx-onset-48000-repeat/manifest.json)

対照と変更版のPCMは全93,056フレームでビット一致した。ホスト分割128・77も各版で一致した。上流とのPCM差は、両版で停止後の15フレーム、最初は55,880フレーム目、最大絶対差は `5.8207661×10⁻¹¹` だった。次は8,219点目に咽頭内へ出る最初の直列枝の左右圧、持ち越し運動量、慣性・抵抗、損失を採り、流出差を作る項の置換を試す。

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_radiation_derivative.py fixed-voice-radiation-derivative-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_radiation_derivative.py" \
  fixed-voice-radiation-derivative-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各11判定と固定上流の各9試験に合格した。各実行の壁4,608点、微分128点を独立計算で照合し、WAVの生PCMでも差の数・位置・最大値を再計算した。要約、計測CSV、WAV、差分の14出力が再実行間でバイト一致した。402入力と40出力をハッシュ照合し、採取物19,868,364バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-radiation-derivative-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-derivative-48000.json)
