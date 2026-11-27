# 混合体型の初期舌先と無発声時の流量

女性係数0.4・子ども係数0.3の声部では、上流のドリフト・ジッター・シマーを0にそろえた後も、無発声時の声門流量に差が残った。先行実行では、差が `10⁻⁶ cm³/s` を初めて超えたのが25出力サンプル目だった。同じ譜面、同じ音源・体型・出力ゲインを使い、研究版ケースの `song_voice.posture.tongue_tip_cm` だけを休止位置へ変更する。[事前登録](../cases/duet-mixed-initial-tip.json)・[先行する声門乱流の実測](duet-mixed-glottal-noise-origin.md#実測)

## 読解と観測方法

- 上流CLIの歌唱入口は `plan_song` のジェスチャーを `HumanVoice` に登録する。固定上流では混合体型を先行と同じ観測器から指定する。`HumanVoice::new` は `ArticulatorBank::new` が得た自由舌先の休止座標で気道形状を初期化し、`snap_to_targets` で断面積・体積などの初期値を確定する。研究版の `run_song` はケースの座標を調音器に渡し、`ArticulatedVoice::for_tract` がその座標で気道を作る。最初の制御更新は出力サンプル1の前にあり、初期位置と休止位置に差があれば、位置と速度がここから変わる。上流の `geometry_continuity` は休止舌先を含む姿勢移動中の断面積を、`body_mix` は体型補間と混合体型の描画を、`engine` はブロック分割や無発声時の安定性を検査する。[上流の歌唱CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[上流の調音器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L79)・[研究版の描画入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L260)・[研究版の気道初期化](../crates/vocal-core/src/voice.rs#L317)・[上流の形状試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L119)・[体型の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)・[描画の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)
- `rest_tip` の計算は解剖の基準座標で行う。同じ顎0.6 cmと舌体 `[2.9, 6.85] cm` から、`[-2.5, 10.5] cm` を中心に基準舌先 `[6.45, 7.35] cm` を `−0.6/9.84 rad` 回す。この姿勢では舌体の補正は0。体型係数を掛けるのは座標を実際の気道形状に写す段で、休止位置の計算には入らない。制御周期は64出力サンプル、角周波数は `2π×13 rad/s`。位置が `x`、目標が `T`、速度が `v` のとき、加速度 `ω²(T−x)−2ωv` を求め、速度を先に更新してから位置を進める。保存した位置・目標・速度を独立した差分式と照合する。[上流の休止座標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L454)・[上流の体型補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L325)・[研究版の調音更新](../crates/vocal-core/src/articulators.rs#L314)
- 声道の断面積（cm²）は制御ブロックごとに端点間を128内部サンプルで補間する。セルの体積 `V`（cm³）の変化は流量源 `−ΔV/Δt`（cm³/s）になり、狭窄部での配分と平滑化を経て圧力・流量の更新に入る。描画前をサンプル0とし、以後は2回目の内部更新後を採取する。唇端・咽頭先頭の断面積、声門枝流量、放射流量の時間微分（cm³/s²）、PCMを比較する。ゲートも乱流振幅も0の区間で、舌先を休止位置から始めると断面積の既定値との差と放射の過渡が消えると予測した。[上流の断面積の補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L686)・[研究版の可動壁](../crates/vocal-core/src/airway/network/geometry.rs#L113)

## 再現

既存の子ども声部用計測CLIに、混合体型の保存ケースを選ぶ指定を加えた。上流と変更前の研究版は、先行実行のPCM全97,920フレームと観測の先頭512行、ジェスチャー計画に照合する。研究版の2条件では通常の `render-pcm-tele` と観測用レンダーのPCMを照合する。[計測CLI](../tools/measure_duet_child_initial_tip.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_child_initial_tip.py --case mixed duet-mixed-initial-tip-new
```

最初の2試行は保存入力の照合中、描画を始める前に停止した。混合体型の先行実行は計画を `candidate.gestures.json` として保存していたが、計測CLIは子ども声部の `candidate-gestures.json` を探していた。接尾辞をケースから指定する修正の初回は、その参照がCLI入口のスコープ外にあり `NameError` になった。配置を修正して再実行した。いずれも観測条件・許容差は同じで、停止時点では実行ディレクトリが作成されていなかった。

子ども声部の回帰では、研究版の `"child"` と上流の `{"female": 0, "child": 1}` を入力検査が直接比較し、同じ体型を不一致と判定した。他の10判定と3予測は通過し、採取データは以前と一致した。名前を体型係数に展開してから比較するよう修正した。[修正前の回帰結果](../runs/duet-child-initial-tip-20261122-mixed-regression/summary.json)

## 実測

固定上流の初期舌先と独立計算は、どちらも基準座標 `[6.241412821929657, 6.810460479056529] cm` だった。研究版の元のケース `[6.45, 7.30] cm` からは最初の制御更新で `[6.44752593262018, 7.2941935368649995] cm` に移った。8制御周期の位置・目標・速度は独立計算と一致し、唇端と咽頭先頭の断面積は8ブロックそれぞれで端点の線形補間と一致した。[各時刻の計測結果](../runs/duet-mixed-initial-tip-20261122-c/summary.json)

| 描画前と最初の512出力サンプル | 元の舌先と上流の最大絶対差 | 休止位置から始めた研究版と上流の最大絶対差 |
| --- | ---: | ---: |
| 唇端の断面積（cm²） | 0.000941049 | 2.22×10⁻¹⁶ |
| 咽頭先頭の断面積（cm²） | 0 | 0 |
| 声門流量（cm³/s） | 0.0102996 | 0 |
| 放射流量の時間微分（cm³/s²） | 5579.13 | 0 |
| PCM絶対値 | 0.00211795 | 0 |

元の姿勢では、描画前から唇端の断面積に差があり、放射とPCMはサンプル1で、声門流量はサンプル4で最初に差が出た。25サンプル目に閾値 `10⁻⁶ cm³/s` を超えたという先行結果は、乱流計算が参照した更新前の流量。今回は更新後も観測し、24サンプル目で `1.0564×10⁻⁶ cm³/s` だった。休止位置から始めると、両版の声門流量・放射・PCMが最初の512サンプルすべてで0になった。混合体型の咽頭先頭は元の姿勢でも一致した。子ども体型では同じ舌先変更に伴って咽頭先頭にも最大 `1.90×10⁻⁵ cm²` の差が生じており、離れたセルへの影響は体型で異なる。セルの区切りと断面の測り方がこの差にどれだけ関わるかは未分離。[元の姿勢からの時系列](../runs/duet-mixed-initial-tip-20261122-c/artifacts/case_tip-startup.csv)・[休止位置からの時系列](../runs/duet-mixed-initial-tip-20261122-c/artifacts/resting_tip-startup.csv)・[子ども声部の測定](duet-child-initial-tip.md#実測)

混合体型の長さの比は `0.42×1 + 0.28×0.9 + 0.30×0.74 = 0.894` で、上流では出力係数0.875が適用される。全97,920フレームで休止舌先をそろえたPCMの最大絶対差は0.08469647。保存した研究版PCMに係数0.875を後から掛ける予備計算では `5.22×10⁻⁸` に減った。上流と同じ段で係数を掛けたときのDC除去・包絡・PCMの一致は次の比較で測る。[研究版の保存PCM](../runs/duet-mixed-initial-tip-20261122-c/artifacts/resting_tip-pcm.f32le)・[上流の保存PCM](../runs/duet-mixed-initial-tip-20261122-c/artifacts/upstream-pcm.f32le)・[固定上流の体型係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L280)

後続の計測で係数0.875を描画時に掛けると、上流との全区間のPCM最大差は `1.46×10⁻¹¹` まで縮んだ。両版のピーク包絡は0.75以下だった。[混合体型の出力ゲインの実測](duet-mixed-output-gain.md#実測)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ディレクトリと `/private/tmp` から各11判定と5予測、固定上流15試験が通過した。下唇形状の既知の段差を検査する1試験は上流で除外設定。要約・時系列・PCMなど20出力がバイト一致し、複素数による休止座標と制御更新、全8ブロックの面積補間、PCMも保存ファイルから別に照合した。子ども声部の回帰では11判定と3予測が通過し、子ども声部の以前の要約の全項目および数値を記録した19出力が一致した。失敗した回帰を含む5実行の730入力・130出力をサイズとSHA-256で照合し、採取物105,045,440バイトをRTL9210B-CGに保存した。[最終実行](../runs/duet-mixed-initial-tip-20261122-final/manifest.json)・[再実行](../runs/duet-mixed-initial-tip-20261122-repeat/manifest.json)・[子ども声部の回帰](../runs/duet-child-initial-tip-20261122-mixed-regression-final/manifest.json)
