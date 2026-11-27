# CSDの調整曲 en001a の採取を先頭2句から全曲へ広げる

`en001a` の先頭2句を4.2秒に区切った採取では、丸め前とPCMの最大差が共に20,363フレームだった。全曲の通常出力は、研究版の保存済み音響評価で使った50句・86音符・64.8秒を採用する。固定上流の通常設定の出力は歌唱計画検証の公式波形へ、研究版の通常出力は音響評価の研究版の波形・譜面計画へ照合する。同設定の比較は女性体型、出力48 kHz、内部96 kHz、初期姿勢と声源を揃える。 [事前登録](../cases/csd-en001a-full-pcm-rounding.json)・[先頭2句の測定](csd-en001a-two-phrase-pcm-rounding.md)・[全曲の音響評価](csd-acoustic-f0-en001a.md)

## 呼び出しと独立計算

上流CLIの `compare_song` はCSVと録音を読み、録音の標本数とサンプルレートから描画長を決める。`render_notes` は句を語尾の印で分け、60 BPMの `plan_song` に、開始時刻と隣接音符の秒差を渡す。最後の音符の長さには実際の終了秒との差を使う。全句のジェスチャーを一つのスケジューラへ時刻順に登録してから、128出力フレームずつの `HumanVoice::render` を呼ぶ。ジェスチャーの `rampIn` は目標到達時刻より前の準備を表す。保存された全曲計画では第3句は4.1813秒からで、4.0723秒から準備に入る子音がある。短い採取の4.2秒までに、第3句を含めた描画とのPCM差が現れると予測した。 [公式の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[譜面の変換と予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L259)・[保存済みの全曲計画](../runs/csd-acoustic-f0-en001a-20261121-final/artifacts/candidate-inspect.json)

内部時刻では、圧力境界と声門面積を更新して気道を1標本進める。口・鼻・壁の放射体積速度を合計し、前回の値との差を内部時刻幅で割った値（cm³/s²）をFIRに渡す。FIRは最古の入力から加算し、2内部標本ごとに出力する。ゲイン適用後の値を `x`、DC除去後を `y` とすると、更新式は `y[n] = x[n] - x[n-1] + a*y[n-1]`。包絡は絶対振幅が上回ると更新し、保持時間の間は維持し、それを過ぎると減衰する。包絡が0.75を超えたときは `0.75 / 包絡` を掛け、絶対振幅が0.85を超えたときはソフトクリップを通してからfloat32へ変換する。研究版の `OutputStage::push` も同じ順序を取る。微小な状態を制御境界でゼロにする上流の処理を独立計算にも含めた。 [上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流のFIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)

`fast_runs_land_on_the_beat` は速い譜面の母音の開始が拍と一致し、母音の持続が確保されることを確認する。`a_sung_phrase_ending_on_a_vowel_is_let_go_gradually` は母音終端の前から声帯を開き、呼気が終端まで続くことを確認する。`assert_no_denormal_states` は発声停止や姿勢変更後の微小な状態の処理を検査する。研究版のCLIを計装した実行は、同じ譜面を未計装の `inspect`・`render-pcm` からも実行して照合する。 [上流の開始時刻試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L29)・[上流の句末試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L48)・[上流の微小履歴試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L68)・[採取の入口](../tools/measure_csd_en001a_two_phrase_pcm_rounding.py#L120)

## 全曲の測定結果

固定上流の通常PCMは公式の保存波形と、研究版の通常PCM・譜面計画は音響評価の保存出力と一致した。観測を加えた両版は未計装の描画・計画を再現した。両版それぞれの6,220,800内部標本と3,110,400出力フレームで、放射からPCMまでの独立計算が一致した。最初の両版間の差は内部標本0の口端流量にあり、同じ標本で放射の合計と時間差分も分かれた。 [全曲の要約](../runs/csd-en001a-full-pcm-rounding-20261124-registered/summary.json)

| 区間（0起点・終端を含まない） | 丸め前の最大絶対差（フレーム） | PCM最大絶対差（フレーム） | 1 ULPの数 | 複数ULPの数 | 利得抑制の作動数（各版） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 第1拍前 [0, 115,200) | 1.413×10⁻¹¹（20,363） | 1.413×10⁻¹¹（20,363） | 986 | 101,441 | 0 |
| 譜面区間 [115,200, 3,066,302) | 1.257×10⁻¹³（2,134,694） | 2.328×10⁻¹⁰（2,646,585） | 25,598 | 446,432 | 400,936 |
| 譜面終端以降 [3,066,302, 3,110,400) | 6.059×10⁻¹⁴（3,066,494） | 7.276×10⁻¹²（3,069,960） | 1,649 | 29,716 | 0 |

PCM最大差は55.1371875秒に1回だけ現れた。第45句の譜面終端は54.2812秒、第46句の拍は55.2秒。先行する調音ジェスチャーが有効な区間にあり、その時点でピーク包絡は両版とも約0.0224だった。利得抑制を掛けずに丸め段へ入った2値は2.759×10⁻¹⁵離れ、float32の中点−0.002007898292504251を挟んだ。PCMでは1 ULPの差となり、このフレームだけで全曲PCMの二乗誤差の80.93%を占めた。複数ULP差の577,589フレームはすべて両版のPCM振幅が10⁻⁶以下だった。利得抑制が作動した集合は両版で一致し、作動中にPCMが分かれたのは6フレームだった。 [最大差の中点と包絡](../runs/csd-en001a-full-pcm-rounding-20261124-registered/summary.json)・[第46句の計画](../runs/csd-en001a-full-pcm-rounding-20261124-registered/artifacts/upstream-plan.json)

同じ版で全曲と先頭2句の計画を照合した。第3句の先頭の /d/ の準備は4.0723秒。そこから先の最初の64出力フレームごとの制御境界は `ceil(4.0723 × 48000 / 64) × 64 = 195520` で、内部標本391,040に対応する。NPZの `source` と `output` を64ビット、`pcm` を32ビットの整数表現で、短い採取の長さまで比較した。両版とも内部標本391,040で声門流量、口端と壁の放射体積速度、放射合計と差分が分かれた。出力195,520でFIRとDC除去後の値、PCMに差が現れた。短い採取の末尾まで残る6,080出力フレームはすべて異なった。 [全曲の観測](../runs/csd-en001a-full-pcm-rounding-20261124-registered/artifacts/output-trace.npz)・[先頭2句の観測](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/artifacts/output-trace.npz)・[上流の制御間隔](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L237)

同じ版どうしの冒頭は `en005a`・`en035a` と111,872フレーム、`en012a` と76,672フレーム一致した。4曲の丸め前最大差はすべて共通の20,363フレームにあった。8つの予測はいずれも成立した。 [4曲の区間別の比較](../runs/csd-en001a-full-pcm-rounding-20261124-registered/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用する。事前登録のSHA-256は `79fb77cb3dcaa9c9ba2d859207b0d26f8ea1ff621451012aca0cea773d366e5c`。出力フレーム数を `en012a` と比較し、圧縮観測を約1.1 GiBと見積もった。圧縮前のデータ、一時CSV、隔離ビルドを含む見積もりは1実行あたり10 GiB。開始時の空き332 GiBとUUIDを照合し、作業用ディスクRTL9210B-CGに直接保存する。公式上流の波形と研究版のケースを別々のマニフェストに固定し、それぞれに登録した出力のSHA-256を確認する。 [全曲計測の入口](../tools/measure_csd_en035a_full_pcm_rounding.py)・[固定上流の保存出力](../runs/csd-song-planning-20261121-final/manifest.json)・[研究版の保存出力](../runs/csd-acoustic-f0-en001a-20261121-final/manifest.json)

研究ワークスペースと `/tmp` からの2実行は、それぞれ8判定に通過した。上流の歌唱・微小履歴16試験と研究版の一様管3試験も通過した。採取後、同じSHA-256の `output-trace.npz` 2件を同じ作業用ディスク上でハードリンクに統合した。各実体を別々に検証してからリンクを置き換え、両実行パスで同じinodeとSHA-256を再確認した。1,078,008,545バイトのファイル1件分が共用になり、ファイルの割当てで1,092,763,648バイト減った。2件のマニフェストに元の実行記録を残した。 [初回](../runs/csd-en001a-full-pcm-rounding-20261124-registered/manifest.json)・[別ディレクトリからの再実行](../runs/csd-en001a-full-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=10737418240 \
  ../../.venv/bin/python tools/measure_csd_en035a_full_pcm_rounding.py csd-en001a-full-pcm-new \
  --case cases/csd-en001a-full-pcm-rounding.json
```
