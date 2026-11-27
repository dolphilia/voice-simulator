# Web MIDIで鳴らすアメリカアリゲーターのWater dance

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの `noteOn` が `creatureKeyHz` で鍵盤を12〜120 Hzの声門音高に合わせる。3オクターブ下げたあと、下限を割るMIDI 36・41を1オクターブ上げるため、対応は16.3516・21.8268 Hz。音高とコールIDは `AudioEngine`、Workletの `call` とWASMを経て `CreatureVoice::play_call` に届く。基準18 Hzに対する倍率が音高ロールに掛かる。離鍵で手動呼気が0になっても、コールの呼気は進む。[鍵盤の変換と呼気](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L100)・[押下の処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[コール開始](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

Water danceは口の目標を0で保ち、ゲートを1で1.6秒保って1.7秒で0へ下げる。粗さの目標はゲート保持中から0→0.75へ線形に上がる。最後の制御点から50 msを超えると、音高・口・粗さの目標が演奏者の値へ戻る。64出力フレームごとに音高を対数空間、口や粗さを線形空間で平滑化する。再発音でコールの時計と目標を先頭に戻す際、呼気の平滑値、声門位相、気道の伝搬状態を引き継ぐ。肺圧は呼気圧×980.665×平滑ゲート dyn/cm²、口先目標は0.05＋12×口 cm²。内部96 kHzで声門差圧を反映した開口を求めてから気道を更新する。[制御点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L117)・[制御の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[肺圧と気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)

声門位相は内部サンプルごとに「瞬時F0÷内部レート÷周期長倍率」だけ進む。位相が1を越えると、粗さを含むロジスティック写像と乱数から次周期の倍率を更新する。壁面・口端・鼻端の体積速度（cm³/s）は位相を保って足し、内部レートを掛けた一階差分（cm³/s²）を出力する。差分の周波数利得は2fs·|sin(πf/fs)|で、低域を小さくする。48 kHzへ間引いた後の12 HzのDC除去も低域を減衰させ、最後に振幅制限と単精度化を行う。[声門周期の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L181)・[放射の差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1146)・[出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L365)

固定上流のゴールデン試験では48 kHz・89,760フレームの単発Water danceをTypeScript版の波形、包絡とテレメトリに照合する。実時間試験は制御点の解決と発音・編集・停止・観測時の割り当てを検査する。ABI試験はWorkletからのコール選択と観測の配送を確認する。[音響試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・3.25秒でMIDI 36と、約870 ms後に41を押す。各離鍵後25〜100 msも発声が続き、再発音で粗さの目標が約0.38から0へ戻り、声門位相は連続すると予測する。各押下後280〜780 msで、位相の巻き戻り間隔とHann窓のピークを別々に測る。声門の周期周波数と各流量の低域が20 Hzの上下へ移り、PCMのピークは第2倍音付近に出ると予測する。固定Rustの同一時刻の全内部系列に加え、流量の加算からPCMまでを独立計算して、低域に対する高い帯域の比がどの段で増えるか調べる。[登録条件](../cases/worklet-midi-alligator-dance.json)・[固定時刻での低域と放射の比較](worklet-alligator-dance.md)

## 実装と比較

研究版と固定上流の通常画面でWater danceを選び、同じ仮想MIDIを送る。研究版が採用したフレームをCLIに渡し、固定Rustへは同じフレームと上流の通常画面が送った周波数を渡す。低域の分析は共通のアリゲーターMIDI計測に追加し、既存のWater dance用Hann窓の計算を各押下後に使う。位相の巻き戻り間の平均を周期周波数へ変換し、連続した内部系列で測る。壁面・口端・鼻端の和から時間差分を取り、全区間で間引き・DC除去・リミッターを独立に計算する。画面から保存したWAVは加工前のPCMを含む。[研究版のMIDI入口](../crates/vocal-core/src/airway/alligator.rs#L262)・[共通計測](../tools/measure_worklet_midi_alligator_call.py)・[低域の計測](../tools/measure_worklet_midi_alligator_dance.py)

## 検証結果

研究ディレクトリと`/tmp`からの実行は、いずれも95項目に合格した。48 kHzの156,000フレームはブラウザとCLIでビット一致し、2,438時点の55観測列は差0。固定上流の通常画面から、MIDI 36で16.3516 Hz、41で21.8268 Hzがコールに渡った。正式実行の採用フレームは6,784、24,704、48,512、67,456だった。[実行結果と入力時刻](../runs/worklet-midi-alligator-dance-20261121-final/summary.json)・[初回結果](../runs/worklet-midi-alligator-dance-20261121-a/summary.json)

再発音で音高目標は16.3516→21.8268 Hz、粗さ目標は0.38294→0、平滑粗さは0.36118→0.35167になった。平滑呼気は約1を保ち、声門位相は0.000168周期進んだ。離鍵後25〜100 msのPCM RMSは0.04104・0.05874。2回目の押下から1,750.67 msでコールの所有が終わり、音高・口・粗さの目標が手動値に戻った。[再発音・離鍵・自然終了](../runs/worklet-midi-alligator-dance-20261121-final/summary.json)

各押下後280〜780 msの実測周期周波数は、7周期と9周期から求めた。周波数ビン幅は2 Hzで、以下のピークビンは候補と固定上流で全て一致した。全区間の声門位相から復元した67周期の周期長倍率は、独立の写像・乱数計算と最大2.22×10⁻¹⁶の差で一致した。[周期とスペクトルの計測](../runs/worklet-midi-alligator-dance-20261121-final/summary.json)

| MIDI | 目標 | 位相から測った周波数 | 声門面積・圧力・各流量のピーク | PCMのピーク |
| --- | ---: | ---: | ---: | ---: |
| 36 | 16.35 Hz | 16.09 Hz | 16 Hz | 32 Hz |
| 41 | 21.83 Hz | 21.46 Hz | 22 Hz | 44 Hz |

合計した体積流量は16・22 Hzで最大だった。時間差分を取った段階で32・44 Hzへ移り、DC除去で高い帯域の比がさらに増えた。25〜80 Hzと12〜25 HzのRMS比は、MIDI 36で0.592→1.284→1.514、41で0.600→1.251→1.384。流量の和から求めた時間差分は実測放射と最大2.33×10⁻¹⁰ cm³/s²の差で、独立に再構成したPCMは全フレームで候補とビット一致した。[放射・間引き・DC除去の独立計算](../runs/worklet-midi-alligator-dance-20261121-final/summary.json)

固定Rustとの差は初回押下の次の内部サンプル13,569で、肺流量・口端流量・総放射に最初に現れた。次のサンプルで気管入口圧と壁の流量に差が出た。肺圧は一致し、最初の差を作る演算は未特定。正式実行のPCMは10フレームで最大3.73×10⁻⁹、初回は5フレームで最大2.33×10⁻¹⁰の差だった。[系列ごとの最初の差と許容差](../runs/worklet-midi-alligator-dance-20261121-final/summary.json)・[初回結果](../runs/worklet-midi-alligator-dance-20261121-a/summary.json)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。正式実行は全サンプルを判定した後、CSV2本を328.1 MBから235.2 MBへ絞り、各312,000内部サンプルを作業用ディスクRTL9210B-CGに保存した。物理MIDIと許可画面は未検証。[環境・コマンド・保存先](../runs/worklet-midi-alligator-dance-20261121-final/manifest.json)・[候補の保存系列](../runs/worklet-midi-alligator-dance-20261121-final/artifacts/cli.retained.csv)・[上流の保存系列](../runs/worklet-midi-alligator-dance-20261121-final/artifacts/upstream.retained.csv)

正式実行の成果17ファイルのSHA-256を照合した。固定時刻のWater dance回帰は288項目、共通計測を使うHissのMIDI回帰は89項目、`cargo test --locked --workspace`は40件に合格した。128フレーム量子の処理時間は両採取で中央値・p95・p99が2 ms。各1,219量子のうち2量子が2.67 msの予算を超え、最大は初回5 ms、正式実行3 msだった。計時は `Date.now` の1 ms刻みで、採取した音声時計に欠落はなかった。[固定時刻の回帰](../runs/worklet-midi-alligator-dance-20261121-fixed-regression/summary.json)・[HissのMIDI回帰](../runs/worklet-midi-alligator-dance-20261121-hiss-regression/summary.json)・[処理時間の記録](../runs/worklet-midi-alligator-dance-20261121-final/artifacts/midi-alligator.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 \
  ../../.venv/bin/python tools/measure_worklet_midi_alligator_dance.py worklet-midi-alligator-dance-local-1
```
