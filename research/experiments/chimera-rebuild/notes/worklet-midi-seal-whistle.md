# Web MIDIで鳴らすウェッデルアザラシのU whistle

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。通常画面でU whistleを選ぶと、`noteOn` は鍵盤を声門音高の範囲40〜6,000 Hzに合わせる。MIDI 60・67は1オクターブ上の523.25・783.99 Hzになる。音高とコールIDが `AudioEngine`・Worklet・WASMを経て `CreatureVoice::play_call` に届き、時刻の原点と音高倍率を設定する。離鍵で手動呼気は0のまま、コールが呼気を出し続ける。[鍵盤の変換](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L100)・[押下と離鍵](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[再発音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

`eval_call` は音高のキーを0秒の1,700 Hzから0.45秒の620 Hz、0.95秒の1,500 Hzの順に指数補間し、音高ロールにだけ鍵盤のHz÷1,700を掛ける。呼気目標は1から1秒間かけて0に下がる。コールが所有する音高とパルス深さは、最後の制御点から50 msを超えると手動値へ戻る。深さの目標はコール中0.1。パルス周波数とデューティは手動設定を使う。[コールの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L116)・[経過時刻と補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

`control` は64出力フレームごとに音高を対数空間で平滑化し、時定数は10 ms。対数化した音高目標を X、平滑値を Y とすると、Y[n]＝rY[n−1]＋(1−r)X[n]、r＝exp(−Δt/10 ms)。連続近似では下降と上昇の対数傾きの絶対値 a・b から谷の遅れを10 ms×ln(1＋a/b)と求める。再発音も直前の平滑値を初期状態にする。制御は呼気と各パラメータを更新した後、`Seal::control` でパルス位相を進めて肺圧（dyn/cm²）を求める。内部96 kHzでは前の声門差圧を使って開口を更新し、気道の流量を進め、放射・間引き・DC除去を経て48 kHzのPCMを得る。[平滑化と内部サンプル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[アザラシの肺圧と声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[独立式と固定時刻の比較](worklet-seal-whistle.md)

上流の単発U whistle試験は48 kHz・56,160フレームをTypeScript基準のPCM・包絡・観測に照合する。実時間試験は全コールのキーと、発音・編集・停止・観測時の割り当てを検査し、ABI試験はWorklet経由の再生と観測を検証する。[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・2.4秒でMIDI 60を鳴らし、約740 ms後に67を押す。0.45秒のキーは制御境界の中間にある。上昇側の傾きが緩やかなので、目標の最小は後の境界、開始から21,632フレームと予測する。独立の対数IIRでは平滑値の最小は21,952フレームで、両者は6.667 ms離れる。目標の最小は約191.06・286.26 Hz、平滑値は約193.62・290.10 Hzと予測する。両離鍵後の発声、再発音の呼気と音高、最後の押下から約1.05秒後の手動目標への復帰も比較する。[登録条件](../cases/worklet-midi-seal-whistle.json)

## 実装と比較

既存のアザラシのMIDIパネルからU whistleを選び、研究版と固定上流の通常画面へ仮想MIDIを送る。研究版が採用したフレームと固定上流へ送られた周波数で、CLIと固定Rustの系列を取得する。保存した各押下前の平滑音高を初期値にして、固定時刻のWhistle検証で使った独立の対数IIRを適用する。二つの谷のフレームと音高、曲線全体の差、離鍵後のPCM・声門開口を出力する。[MIDI画面](../../../../web/prototypes/chimera-research/src/main.tsx#L1041)・[コール実装](../crates/vocal-core/src/seal_voice/call.rs#L126)・[MIDI計測](../tools/measure_worklet_midi_seal_whistle.py)・[対数IIRの独立計算](../tools/measure_worklet_seal_whistle.py#L21)

## 検証結果

研究ディレクトリと `/tmp` から実行し、各25項目に合格した。48 kHzの115,200フレームはブラウザとCLIでビット一致し、1,800時点の29観測列は差0だった。正式実行で採用したフレームは8,320、16,256、43,904、52,096で、最初の押下を基準にした入力時刻の最大差は5.33 msだった。[正式判定と採用時刻](../runs/worklet-midi-seal-whistle-20261121-final/summary.json)・[初回](../runs/worklet-midi-seal-whistle-20261121-a/summary.json)

| MIDI | 開始の音高目標 | 目標の谷 | 平滑値の谷 | 谷の間隔 |
| --- | ---: | ---: | ---: | ---: |
| 60 | 523.251 Hz | 191.058 Hz | 193.616 Hz | 6.667 ms |
| 67 | 783.991 Hz | 286.263 Hz | 290.096 Hz | 6.667 ms |

両音とも目標の谷は開始から21,632フレーム、平滑値の谷は21,952フレームで、対数IIRの計算と一致した。0.45秒の制御点から平滑値の谷までの7.333 msは、連続近似8.191 msとの差が0.858 msで、1制御間隔の1.333 ms以内だった。独立式との最大差は目標で5.67×10⁻¹¹ Hz、平滑値で5.43×10⁻¹¹ Hz。表の平滑値は声門へ渡す制御音高で、声門の瞬時F0も別の観測列で照合した。[谷の位置と独立式との差](../runs/worklet-midi-seal-whistle-20261121-final/summary.json)

離鍵後25〜100 msのPCM RMSは0.06753・0.08348だった。再発音で目標音高は783.99 Hzへ戻り、平滑音高は313.35→351.35 Hz、平滑呼気は0.28934→0.43095へ進んだ。第2音は開始0.95067秒から691.76 Hzの目標を保ち、1.05067秒で音高とパルス深さの手動目標へ戻った。パルス周波数とデューティの手動目標は全区間で一定だった。[離鍵・再発音・自然終了](../runs/worklet-midi-seal-whistle-20261121-final/summary.json)

固定Rustとの最初の微差は第1音の押下の39内部サンプル後、出力8,339の内部2サンプル目で壁面体積流量と総放射に現れた。肺圧と制御音高は全区間で一致した。最初の差を生んだ演算は未特定。正式実行のPCMは9フレームで最大1.39×10⁻¹⁷、初回は最大7.11×10⁻¹⁵異なった。候補の放射を独立の出力段に入れたPCMは候補とビット一致した。[系列ごとの差](../runs/worklet-midi-seal-whistle-20261121-final/summary.json)・[壁面と放射の保存系列](../runs/worklet-midi-seal-whistle-20261121-final/artifacts/cli.retained.csv)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。正式実行の128フレーム量子は900回で処理時間のp95・p99は1 ms、最大2 msだった。計時の刻みは1 msで、音声時計の欠落はなかった。全サンプルを判定した後、CSV2本を102.0 MBから69.0 MBに絞り、各115,200行をRTL9210B-CGに保存した。正式実行の成果15ファイルのSHA-256を照合した。物理MIDIと許可画面は未検証。[実行記録](../runs/worklet-midi-seal-whistle-20261121-final/manifest.json)・[処理時間と観測](../runs/worklet-midi-seal-whistle-20261121-final/artifacts/midi-seal.json)

固定時刻のWhistle回帰は101項目、共通計測を使うDescending trillのMIDI回帰は15項目、`cargo test --locked --workspace`は40件に合格した。[固定時刻の回帰](../runs/worklet-midi-seal-whistle-20261121-fixed-regression/summary.json)・[TrillのMIDI回帰](../runs/worklet-midi-seal-whistle-20261121-trill-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_seal_whistle.py worklet-midi-seal-whistle-local-1
```
