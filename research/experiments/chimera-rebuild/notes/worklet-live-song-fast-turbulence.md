# 短い音符の歌唱で乱流係数だけを変える

240 BPM・各4分の1拍の `Pop Dee` で、同じスコア、体型、拍、先行音、分割事前描画を使う。比較する入力は乱流係数0と1。歌唱画面に「乱流係数」を追加し、プリセットを選ぶと短音は0、長音は1になる。ブラウザが保存した再実行ケースから実際に適用した値を照合する。[事前登録](../cases/worklet-live-song-fast-turbulence.json)・[短音の基準](worklet-live-song-fast-return-time.md)

## 乱流源から出力まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`singing.ts` から計画した歌唱をWorkletに予約する。`ChimeraProcessor.process()` が量子長を `engine_render()` に渡すと、Rustの `Engine::render()` が拍に合わせて状態を更新し、`HumanVoice::render()` が内部サンプルを進める。調音更新で `HumanAirway::commit()` が形状を反映し、`update_noise()` が声門、狭窄、歯の周囲の乱流源を登録する。上流の `affricates` は閉鎖後の摩擦の長さと有声区間への移行を音響で確かめる。短音の拍を検証する `sing_fast` と、ホストの分割で波形が変わらないことを検証する `engine` もこの比較の前提になる。[上流の歌唱画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[人の声道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)・[摩擦の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs)・[短音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)

`AirwayNetwork::step()` は枝の流量を更新する前に `compute_noise()` を呼ぶ。枝の開口面積 `A` をcm²、直前の流量 `U` をcm³/s、動粘性係数 `ν` をcm²/sとして、開いている枝のレイノルズ数を `2 × |U| ÷ (ν × √(πA))` で求める。1,800を越えたとき、超過分 `x = Re² − 1800²` を `x ÷ (1 + x ÷ (12000² − 1800²))` で飽和させる。乱流係数と `√(96000 ÷ 内部レート)` と源別のゲインを掛け、白色雑音を高域通過1段と低域通過2段に通した値に掛ける。流れが正なら下流へ加え、逆なら反対側の枝から引く。乱流係数0でも乱数とフィルタは更新する。[上流の音響網](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[物理定数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs)

再実装では、CLIの `run_song()` とWorkletの `prepareSongVoice()` が設定した係数をそれぞれの描画経路から `enable_turbulence()` に渡す。`Turbulence::step()` は同じ順に圧力源を求める。`retains_filter_state_when_gain_changes()` は源のゲインだけを2倍にすると、状態を保持したまま次の圧力が2倍になることを確認する。これらの圧力は声道の枝で観測し、声門面積と流量、放射の微分、間引き後のPCMを48 kHzの出力フレームに対応づける。[CLIの入り口](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[Workletの準備](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[分岐の乱流計算と試験](../crates/vocal-core/src/airway/network/turbulence.rs)

## 比較方法

係数0の基準を前回から参照する。係数1は同じケースの乱流係数だけを上書きした入力を保存し、CLIと固定上流の再描画、および通常のオフラインWorkletを照合する。実時間でも同じ係数のオフライン基準とPCMおよび観測を照合する。最初のビット差、差の振幅が10⁻⁶を超える最初の出力点、圧力・声門・放射に差の出た最初の出力点を別々に記録する。

Firefoxの分割事前描画は64フレームを3回、無音の第1・3・5量子に置く。機器の要求長256フレームと前後の先行音を照合し、構築要求の返却前から予定ホスト時刻までの差を測る。係数0と1を4組で交互に実行し、`係数1 − 係数0` の対応差を集計する。乱流による後の音の差と、歌唱開始前の返却時刻の差をそれぞれ検査する。[比較の入口](../tools/measure_worklet_live_song_turbulence.py)・[返却時間の判定範囲](worklet-live-song-cubeb-return-time.md#実測)

## 実測

係数1のオフラインWorkletはCLIと49,200フレームすべてがビット一致した。固定上流との差は最大9.31 × 10⁻¹⁰だった。係数0と1で拍は0.5秒と0.5625秒、音素と調音ジェスチャーの計画、観測の呼気ゲート、開大、声門F0は一致した。係数0の乱流圧は観測した6系列で全区間0。係数1では0.42〜0.66秒の観測範囲で最大98.38 dyn/cm²だった。[係数1のオフライン基準](../runs/worklet-song-voice-fast-20261121-turbulence-one/summary.json)

| 観測値 | 0始まりで初めて差が出た出力フレーム |
| --- | ---: |
| 声門乱流源の順方向の圧力 | 20,294 |
| 声門上圧・声門流量・放射の時間微分 | 20,295 |
| PCMのビット列 | 20,309 |
| PCMの絶対差が10⁻⁶を超えた点 | 20,380 |
| 声門面積 | 28,088 |

CLIと固定上流の両方で上の順序と最初のフレームが一致した。生CSVから求めた声門側の最初の乱流圧の差は約6.89 × 10⁻⁵ dyn/cm²だった。係数によるPCMの最大絶対差は両版で0.03961。Firefoxの前後17要求の先行音は全16試行で連続するフレーム印と一致し、歌唱PCMはそれぞれ同じ係数のCLI基準とバイト一致した。[初回](../runs/worklet-live-song-fast-turbulence-20261121-a/summary.json)・[別ディレクトリからの再実行](../runs/worklet-live-song-fast-turbulence-20261121-repeat/summary.json)

構築要求での返却時の残り時間の対応差の中央値は、初回が係数1で+0.193 ms、再実行が+0.632 msだった。対応差は−0.873〜+1.718 msで、絶対値0.5 ms未満という予測は再実行で外れた。差を分けると、予定時刻に対する入口の対応差は全組で絶対値0.010 ms未満だった。返却位置の差はほぼコールバックの処理時間差に対応し、ノード構築区間からも差が見えた。飛びは係数0で2回、係数1で1回で、固定した判定がいずれも検出した。名目周期による判定も同じ3回を検出した。最初の事前描画はPCMに乱流の差が現れるより前に済むため、この時間差が乱流係数によって生じたかは追加の対照が必要になる。

係数1のオフラインは16判定、実時間は各164判定、従来の長音は15判定を通過した。固定上流の摩擦試験と再実装のフィルタ状態の試験も通過した。実行記録の入力1,100件と出力308件を照合し、計測データ約320.19 MBをRTL9210B-CGで保存した。[長音の回帰確認](../runs/worklet-song-voice-20261121-turbulence-regression/manifest.json)・[上流の摩擦試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/upstream-frication-test-20261121.log)・[フィルタの試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/turbulence-gain-test-20261121.log)

次は同じ歌唱で、係数1を保ち、声門の乱流源のゲインだけを0にする対照を用意する。圧力の差が声門流量と放射に到達する順序や、最初のPCM差がどこまで移るかを確認する。

## 再現

研究ワークスペースから実行する。`<係数1の基準ID>` と `<実行ID>` には未使用の名前を指定する。

```bash
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=190000000 ../../.venv/bin/python \
  tools/measure_worklet_song.py <係数1の基準ID> --case cases/worklet-song-voice-fast.json --turbulence-scale 1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=180000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_turbulence.py <実行ID> <係数1の基準ID> --cubeb-output "$firefox"
```
