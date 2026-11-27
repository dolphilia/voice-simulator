# Web MIDIによるアメリカアリゲーターのBellow

## 固定上流の読解と事前登録

Bestiaryの「What the keys play」でBellowを選ぶと、`noteOn` は保持一覧を更新し、Pitchの12〜120 Hzへ鍵盤を割り当て、`playCall` へIDと周波数Hzを渡す。UIの`AudioEngine.playCall`からWorkletを介してWASMへ届く。振幅は既定の1で、離鍵は保持一覧と手動呼気だけを更新する。Breatheがオフなら手動呼気は0のままで、自動の呼気包絡が進む。上流のABIテストがコールIDの受け渡し、ゴールデン試験が移調済みコールと描画分割、実時間テストがコール切り替え中の割り当てを検査する。[鍵盤の音域と分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[ABI](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[ゴールデン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[実時間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)

`CreatureVoice::play_call` は前のコールが所有する目標を演奏者の値へ戻し、現在の制御時計を新しい開始時刻にする。Bellowでは、鍵盤周波数÷28 Hzを音高の倍率にする。発声の目標は0〜1.6秒で音高30→24 Hz、無次元のchaosが0.55→0.95へ線形に動き、口開度0.02・hiss 0を維持する。呼気目標は0〜150 msで0→1、1.6秒まで1、2秒までに0へ下がる。最後の点から50 msを超える制御更新で、音高・chaos・口・hissの目標を演奏者の値に返す。[Bellowの制御点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L102)・[コールの所有と評価](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[Bellowの単独比較](alligator-bellow.md)

制御は64出力フレームごとにコールの評価、音高の対数平滑化、chaosなど各値の平滑化、手動と自動の大きい方の呼気の平滑化を行う。音高とchaosは50 ms、呼気は上昇12 ms・減衰60 msの時定数を使う。再発音は包絡の時刻を戻し、平滑化値、声門の位相、気道の状態を引き継ぐ。アリゲーターは呼気と水柱cm指定の圧力から肺圧をdyn/cm²へ換算し、音高とchaosを声門へ渡す。48 kHzでは1出力フレームあたり2回、気管末端と咽頭入口の差圧から面積（cm²）を更新し、気道と壁面・口端・鼻端の放射を求める。[上流の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[肺圧と声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)

48 kHzで60を押し、220 ms後に離す。最初の開始から640 ms後に67で再発音し、190 ms後に離す。最初の音高目標は約35.04 Hzと52.50 Hzになると予測した。2回目の押下で呼気の目標は0へ戻り、実際の呼気は1付近から滑らかに減衰し始める。各離鍵から25〜100 msで発声が続くこと、自然終了から120〜300 msで呼気とPCMが減衰することを測る。同じ時刻の固定Rustの内部状態、独立の補間と平滑式、放射からのPCMを照合する。[登録条件](../cases/worklet-midi-alligator-call.json)

## 実装と計測

研究版のMIDIパネルはBellow、Growl、Hiss、Water danceと持続音を選べる。コールでは押下と離鍵を `alligator_voice.events[].midi_call` にID・音番号・押下状態とともに書き出す。CLIとAudioWorkletは `AlligatorVoice::midi_call` を共有し、鍵盤写像から得た周波数で既存の `play_call` を呼ぶ。離鍵の入力は記録に残り、物理状態の更新からは独立する。仮想MIDI比較では固定上流の通常の画面を通して、Rustへ届くコールのIDと音高を拾う。固定Rustのレンダーへはその音高と研究版が採用したフレームを渡し、固定上流が行う2回のコール発火を同じ時刻で再現する。[研究版のMIDIパネル](../../../../web/prototypes/chimera-research/src/main.tsx)・[共有の発音処理](../crates/vocal-core/src/airway/alligator.rs)・[CLIのイベント](../crates/vocal-cli/src/alligator_case.rs)・[比較の入口](../tools/measure_worklet_midi_alligator_call.py)

## 検証結果

正式計測ではChromium 156.0.8078.4、48 kHz・3.40秒で75項目すべてに合格した。実時間Workletと109フレーム分割のCLIのWAV 163,200フレームはビット一致し、2,550時点の55観測列は差0だった。独立の制御計算との差は音高目標で最大3.41×10⁻¹³ Hzで、独立に放射を間引き・DC除去・振幅制限したPCMも一致した。声門位相から復元した129周期の周期長倍率も、乱数とchaosを使う独立計算に対して最大差2.22×10⁻¹⁶だった。[正式結果](../runs/worklet-midi-alligator-call-20261121-retained/summary.json)

開始目標は60で35.0391 Hz、67で52.4994 Hz。640 ms後の再発音で、呼気目標は1→0、観測された呼気は1→0.9780になり、平滑音高は32.46→32.87 Hzへ進んだ。声門の位相は0.89022→0.89055周期へ進んだ。各離鍵後25〜100 msには呼気が0.9996以上で、声門の最大面積は1.47と1.33 cm²、PCMのRMSは0.116と0.137だった。第2回の開始から98,432出力フレーム後に自然終了し、演奏者の音高28 Hz・chaos 0.75へ目標を返した。[採用境界・離鍵後・自然終了](../runs/worklet-midi-alligator-call-20261121-retained/summary.json)

固定RustとのPCM最大差は5.82×10⁻¹¹で、ビットが異なるのは4サンプルだった。肺圧は全区間で一致し、観測した系列で最初の差は呼気上昇から6内部サンプル後の気管入口圧に出た。正式実行の座標では14,982。40内部サンプル後に気管末端、続いて声門の駆動差圧・流量と壁面放射へ差が現れた。気管入口圧の最大差は1.82×10⁻¹⁰ dyn/cm²、放射の時間微分の最大差は3.71×10⁻⁷ cm³/s²。枝の運動量項には、慣性と流量を掛けてから逆刻みを掛ける上流と、慣性を刻みで割ってから流量を掛ける研究版の評価順の違いがある。入口圧を最初に変えた演算については、入口に接続する枝と壁の流量を個別に採取して検証する余地がある。[上流の枝と節点の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1025)・[研究版の枝の更新](../crates/vocal-core/src/airway/network.rs#L189)・[系列ごとの差](../runs/worklet-midi-alligator-call-20261121-retained/summary.json)

初回は自然終了120 ms後の呼気に0.002以下を求め、実測0.00862で不合格だった。末尾では呼気目標が400 msの線形下降を経るため、独立計算でも所有終了時点の実際の呼気は約0.06367ある。第2版では120〜300 msを0.01以下、220〜300 msを当初の0.002以下とし、専用の判定を加えた。正式計測の220 ms後は0.00163。第3版では採用時刻の違いを含めて離鍵と終了の窓を保持し、気管入口と末端の圧力列を保存した。初回の判定と全時系列、第2版の合格結果を保存している。[第1版の判定](../runs/worklet-midi-alligator-call-20261121-a/summary.json)・[第2版の判定](../runs/worklet-midi-alligator-call-20261121-final/summary.json)・[改訂条件](../cases/worklet-midi-alligator-call.json)

別ディレクトリから再計測し、高密度CSV2本を全サンプルの判定後に317.5 MBから141.1 MBに抜粋してRTL9210B-CGに保存した。両方の抜粋に採用境界・離鍵後・自然終了後の観測窓が入り、成果17ファイルのサイズとSHA-256も照合した。既存Bellowの234項目、アリゲーターの持続音MIDI 10項目、Rust40件を再確認した。Rust 1.94.1・Python 3.14.4・NumPy 2.4.4・SciPy 1.17.1を使用した。物理MIDIと、Growl・Hiss・Water dance個別のMIDI比較は残る。[環境・実行・出力](../runs/worklet-midi-alligator-call-20261121-retained/manifest.json)・[Bellowの回帰](../runs/worklet-midi-alligator-call-20261121-bellow-regression/summary.json)・[持続音MIDIの回帰](../runs/worklet-midi-alligator-call-20261121-held-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=872415232 \
  ../../.venv/bin/python tools/measure_worklet_midi_alligator_call.py worklet-midi-alligator-call-local-1
```
