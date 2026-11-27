# Web MIDIで鳴らすウェッデルアザラシのChug

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。通常画面でChugを選ぶと、`noteOn` はMIDI 24・31を発声域40〜6,000 Hzに合わせ、1オクターブ上の65.406・97.999 Hzを `playCall` へ送る。WorkletとWASMから呼ばれる `CreatureVoice::play_call` は、基準90 Hzに対する音高倍率とコールの開始時刻を設定する。音高ロールだけに倍率が掛かる。離鍵で手動呼気は0のまま、コールの呼気は継続する。[鍵盤と呼気](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L100)・[押下の処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletのコール入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[経過時刻と音高倍率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

Chugは音高90 Hz、パルス周波数11 Hz、深さ1、デューティ0.35を目標にする。粗さは0.95秒で0.3から0.05へ線形に下がる。呼気目標は0.9秒まで1を保ち、0.95秒で0になる。最後の制御点から50 msを超えるとコールが所有した目標を手動値に戻す。再発音では目標曲線を先頭へ戻し、平滑値と呼気パルス・声門の状態を引き継ぐ。64出力フレームごとの更新で、音高とパルス周波数は対数空間、粗さ・深さ・デューティ・呼気は線形空間で追従する。粗さの平滑化時定数は50 ms。[Chugの制御点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L124)・[制御の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

`Seal::control` はパルス位相に平滑パルス周波数×制御間隔を加え、1周期に折り返す。位相がデューティ未満なら半正弦、区間外では0を使う。肺圧は呼気圧×980.665×平滑呼気×(1−深さ＋深さ×半正弦)でdyn/cm²に換算する。深さが1に近づくと、呼気ゲートが高いままデューティ外の肺圧が0へ近づく。声門位相は内部サンプルごとに「瞬時F0÷内部レート÷周期長倍率」だけ進む。周期境界で粗さの写像と乱数により次の周期長倍率と振幅を更新し、前の圧力差から得た開口で気道を進める。放射は内部96 kHzから48 kHzへ間引かれ、DC除去を経て単精度PCMとなる。[肺圧・声門・気道の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[声門の周期更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L181)・[固定時刻の実測](worklet-seal-chug.md)

固定上流には48 kHz・53,760フレームの単発Chugのゴールデン試験があり、TypeScript基準とPCM・包絡・観測を比較する。実時間試験は全コールの制御点と描画中の割り当てを、ABI試験はWorkletからの配送を検査する。[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・2秒でMIDI 24を押し、約480 ms後に31で再発音する。押下から150〜400 msを使い、呼気と声門の位相を別々に測る。両呼気は11 Hz付近、声門周期は鍵盤による周波数に近く、第2音で高くなると予測する。離鍵後25〜200 msには高い呼気ゲートとデューティ外の低い肺圧が共存すると予測する。再発音の位相、粗さと第2音終盤の周期長倍率を独立計算と照合する。[登録条件](../cases/worklet-midi-seal-chug.json)

## 実装と初回の再解析

研究版と固定上流の通常画面でChugを選び、仮想MIDIを入力する。研究版が採用したフレームと上流へ送られたHzから、CLI・固定Rustの系列を取得する。呼気パルスは出力フレームの位相、声門は各出力フレームに保存した内部2サンプルの位相から巻き戻りの間隔を求めた。声門周期倍率の比較には既存のChugの独立計算を使い、採取開始からの乱数列と粗さの写像を続ける。離鍵後の各窓は位相とデューティの大小で分けて肺圧の最大値を求めた。[MIDI入口](../crates/vocal-core/src/seal_voice.rs#L157)・[呼気パルス](../crates/vocal-core/src/seal_breath.rs#L112)・[MIDI計測](../tools/measure_worklet_midi_seal_chug.py)・[周期倍率の独立計算](../tools/measure_seal_chug.py#L23)

初回は、自然終了時の手動目標の検査に使う `target_pressure_cm_h2o` を計測器が読み込んでおらず、CLIと上流の出力取得後に停止した。肺圧の手動目標と平滑値を読み込むように修正した。保存済みの初回CLIデータを再解析すると、Chug固有の8判定はすべて合格し、周期周波数は呼気が両方10.9489 Hz、声門が64.1911・96.3687 Hzだった。ケース定義の版と閾値は維持し、初回のマニフェストと元のCSVを保持した。[初回のエラー・出力一覧](../runs/worklet-midi-seal-chug-20261121-a/manifest.json)

## 検証結果

修正後は研究ディレクトリと `/tmp` から実行し、各17項目に合格した。48 kHzの96,000フレームはブラウザとCLIでビット一致し、1,500時点の33観測列は差0。正式実行の採用フレームは8,960、18,176、32,000、43,008で、最初の押下を基準にした入力時刻の最大差は2.00 msだった。[正式結果](../runs/worklet-midi-seal-chug-20261121-final/summary.json)・[研究ディレクトリからの結果](../runs/worklet-midi-seal-chug-20261121-b/summary.json)

| MIDI | 音高目標 | 声門周期の周波数 | 呼気パルスの周波数 |
| --- | ---: | ---: | ---: |
| 24 | 65.406 Hz | 64.197 Hz | 11.029 Hz |
| 31 | 97.999 Hz | 96.369 Hz | 11.029 Hz |

押下後150〜400 msに収まった声門周期は15・23周期、呼気パルスは1・2周期だった。両離鍵後25〜200 msの平滑呼気ゲートは約1だった。肺圧の最大値はデューティ内で9,803.1・9,799.3 dyn/cm²、デューティ外で0.07486・7.62×10⁻¹² dyn/cm²。声門開口の最大値は約0.248・0.247 cm²、PCM RMSは0.00737・0.01249で発声が続いた。[周期と離鍵後の観測](../runs/worklet-midi-seal-chug-20261121-final/summary.json)

再発音で粗さ目標は0.17404→0.3、平滑粗さは0.18700→0.18997、音高の平滑値は65.406→68.792 Hzになった。呼気位相は0.78269→0.79736周期へ進み、直前の位相から求めた値に一致した。声門位相は0.000704周期進んだ。採取全体から復元した584周期の倍率は独立計算と最大2.22×10⁻¹⁶の差だった。第2音の150〜450 msと770〜900 msでは、周期倍率からジッター項を引いたRMSが0.02126→0.00708に下がった。第2音の開始1秒後の出力80,000で手動目標へ戻った。[再発音・周期倍率・自然終了](../runs/worklet-midi-seal-chug-20261121-final/summary.json)

固定Rustとの最初の微差は第1音の押下から39内部サンプル後の壁面体積流量と総放射に現れた。肺圧は全フレームで固定Rustと一致し、独立計算との差は最大4.06×10⁻⁹ dyn/cm²だった。PCMは固定Rustと3フレームで最大7.28×10⁻¹²異なった。最初の差を生んだ演算は未特定で、候補の放射から独立に再構成したPCMは候補とビット一致した。[系列の差](../runs/worklet-midi-seal-chug-20261121-final/summary.json)・[候補のCSV](../runs/worklet-midi-seal-chug-20261121-final/artifacts/cli.retained.csv)・[上流のCSV](../runs/worklet-midi-seal-chug-20261121-final/artifacts/upstream.retained.csv)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。正式実行の128フレーム量子は750回でp95は1 ms。計時は1 ms刻みで、2.67 msの予算を超えた量子は1回（3 ms）、音声時計に欠落はなかった。正式実行では全サンプルの判定後にCSV2本を93.1 MBから78.2 MBに絞り、各96,000行をRTL9210B-CGに保存した。成果15ファイルのSHA-256を照合した。固定時刻のChug回帰は88項目、`cargo test --locked --workspace`は40件が合格した。物理MIDIと許可画面は未検証。[実行記録](../runs/worklet-midi-seal-chug-20261121-final/manifest.json)・[処理時間](../runs/worklet-midi-seal-chug-20261121-final/artifacts/midi-seal.json)・[固定時刻の回帰](../runs/worklet-midi-seal-chug-20261121-fixed-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_seal_chug.py worklet-midi-seal-chug-local-1
```
