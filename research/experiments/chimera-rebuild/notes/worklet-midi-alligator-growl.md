# Web MIDIで鳴らすアメリカアリゲーターのGrowl

## 固定上流の読解と事前登録

BestiaryでGrowlを選ぶと、`noteOn`は音高ロールにある12〜120 Hzへ鍵盤を対応させ、`playCall`をWorkletとWASMへ送る。MIDI 60と67を3オクターブ下げると32.7032 Hzと48.9994 Hzになる。離鍵で変わるのは手動呼気で、コールの呼気はその時計で進む。再発音時の`CreatureVoice::play_call`は前のコールを置き換え、経過時間を0に戻す。平滑値と気道・声門の状態は引き継ぐ。[MIDIの受け渡し](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletのコール入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[コールの再開始](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

`eval_call`は経過時刻に応じて音高、粗さ、口を補間し、音高ロールにだけ鍵盤のHz÷45 Hzを掛ける。音高は500 msで45から38 Hzに下がり、呼気目標は600 msで1から0になる。粗さ0.7と口0.15を保持し、hissは演奏者の値0のまま進む。最後の制御点から50 msを超えると音高・粗さ・口の目標が演奏者の値へ復帰する。`control`は64出力フレームごとに自動呼気と手動呼気の大きい方に追従し、立ち上がり12 ms、下降60 msの時定数を切り替える。音高は対数、他の値は線形空間で平滑化する。[Growlの制御点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L109)・[補間と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

`Alligator::control`は肺圧を「呼気圧×980.665×平滑呼気」でdyn/cm²へ、口先と軟口蓋の目標断面をそれぞれ「0.05＋12×口」、「0.4＋1.6×鼻孔」でcm²へ換算する。気道断面は各制御区間内で補間される。各内部サンプルで声門両側の直前の圧力を読み、周期位相、声門面積、流量を更新してから気道を進め、口・鼻・壁からの放射を得る。48 kHz出力では内部2サンプルを進める。ゴールデン試験は既定シーケンスの音響量を、リアルタイム試験は発音中の割り当てを、ABI試験はコールの配送を検査する。[肺圧・声門・気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[声門の駆動と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[リアルタイム試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・1.65秒でMIDI 60、約360 ms後に67を押す。再発音直前の呼気目標を0.30〜0.50、再発音直後を1と予測する。平滑呼気は直前より大きく1未満で、肺圧も上がる。演奏者の口0.02に相当する約0.29 cm²から、コール中に口先実断面が1.80 cm²を超え、再発音でも同じ目標1.85 cm²へ近づくと予測する。各離鍵後25〜100 msで呼気0.5以上と発声を、自然終了後120〜250 msで呼気0.01以下と離鍵窓比2.5%以下のPCM RMSを求める。候補画面で実際に採用したタイミングでCLIと固定Rustのコールを再生し、音声と内部系列を比較する。固定版の音響比較に加え、制御曲線、肺圧、断面、出力段を独立に計算する。[観測点と合否基準](../cases/worklet-midi-alligator-growl.json)・[固定時刻での既存比較](worklet-alligator-growl.md)

## 実装と比較

既存パネルの「MIDIでアメリカアリゲーターを演奏」からGrowlを選び、候補と上流の通常画面へ仮想MIDIを送る。候補の採用フレームをCLIへ渡し、ブラウザが出力したWAVと内部観測を照合する。固定Rustへは同じフレームと上流画面が出した音高を渡す。Bellowの入力・音声時計・比較処理を共通にし、Growl固有の目標、口先の補間、声門位相を別に検査する。共通計測は基準実行に記録されたケース定義のハッシュを確認してから始める。[研究版のMIDI入口](../crates/vocal-core/src/airway/alligator.rs#L262)・[コールの実装](../crates/vocal-core/src/airway/alligator/call.rs#L37)・[共通計測](../tools/measure_worklet_midi_alligator_call.py)・[Growlの検査](../tools/measure_worklet_midi_alligator_growl.py)

## 検証結果

48 kHzの79,200フレームで76項目すべてに合格した。ブラウザと109フレーム分割のCLIはWAVがビット一致し、1,238時点の55観測列の差は0だった。上流画面からGrowlに届いたMIDI 60・67の音高は32.7032・48.9994 Hzだった。候補の採用フレームは10,368、17,024、27,776、34,944。初回押下を基準にした入力時刻の最大差は2.67 msだった。[正式判定・採用フレーム](../runs/worklet-midi-alligator-growl-20261121-final/summary.json)

再発音で呼気目標は0.39778→1、平滑呼気は0.49615→0.54914、肺圧は8,758.03→9,693.32 dyn/cm²になった。口は同じ1.85 cm²の目標に向かい、再発音前後の実断面は約1.848896 cm²だった。声門位相は0.000305周期進み、声門流量は1,478.85→1,475.70 cm³/sになった。各離鍵後のPCM RMSは0.11888・0.19699で、口と鼻からの流量も続いた。2回目の開始から650.67 msでコールの制御が終わり、その120〜250 ms後の平滑呼気は最大0.00575、PCM RMSは2回目の離鍵窓の0.00521%だった。[再発音・離鍵・自然終了の系列](../runs/worklet-midi-alligator-growl-20261121-final/summary.json)

固定Rustと肺圧・口先断面は全区間で一致した。最初の微差は最初の発音と同じ内部20,736の総放射に現れ、値は−7.727060126436751と−7.727060126436750 cm³/s²だった。肺流量は次の内部サンプル、口端流量と気管入口圧はその次、声門流量は47サンプル後に差が出た。総放射の最初の差を生む演算は未特定。正式実行のPCMは全フレームでビット一致し、初回は2フレームで最大1.82×10⁻¹²の差があった。候補の放射から独立に再計算したPCMは両実行で候補と一致し、独立計算した口先断面との差は最大1.44×10⁻¹⁴ cm²だった。[系列ごとの許容差と最初の差](../runs/worklet-midi-alligator-growl-20261121-final/summary.json)・[初回の比較](../runs/worklet-midi-alligator-growl-20261121-a/summary.json)

研究ディレクトリと`/tmp`の両方から実行した。macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使用した。正式実行では全サンプルで判定後、CSV2本を152.8 MBから86.7 MBへ絞り、各158,400サンプルを作業用ディスクRTL9210B-CGに保持した。成果17ファイルのSHA-256を照合した。物理MIDIは未検証。[コマンド・環境・保存場所](../runs/worklet-midi-alligator-growl-20261121-final/manifest.json)・[候補のCSV](../runs/worklet-midi-alligator-growl-20261121-final/artifacts/cli.retained.csv)・[上流のCSV](../runs/worklet-midi-alligator-growl-20261121-final/artifacts/upstream.retained.csv)

BellowのMIDI回帰は75項目、固定時刻のGrowl回帰は285項目に合格した。研究版の `cargo test --locked --workspace` は40件が合格した。[BellowのMIDI回帰](../runs/worklet-midi-alligator-growl-20261121-bellow-regression/summary.json)・[固定Growlの回帰](../runs/worklet-midi-alligator-growl-20261121-fixed-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_alligator_growl.py worklet-midi-alligator-growl-local-1
```
