# Web MIDIによる手動発声の音高切り替え

## 固定上流の読解

比較対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`Keys.MidiButton` が `setMidi` を呼び、`connectMidi` が最初の押下と最後の離鍵を `store.noteOn`・`noteOff` へ渡す。手動モードは最後に押された保持キーを使い、音高目標は \(440\cdot2^{(n-69)/12}\) Hz。保持中の最新キーを離すと以前の保持キーに戻る。呼気目標は保持中に1、全解放で0。手動発声ではベロシティを呼気倍率に使わない。`AudioEngine.setSource` は更新をフレームにまとめてWorkletへ送り、Workletは `engine_set_source` と `engine_set_gate` を呼ぶ。実画面の採用時刻はメインスレッドと音声スレッドの境界に依存するため、合成器の差の比較は研究版の採用フレームへ揃える。[ポートと所有](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[保持音の選択](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[メッセージのまとめ方](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L389)・[Workletの適用](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L121)

`HumanVoice::set_source` は音源設定を更新する。スコアのない `control` では調音位置と接触を更新した後、呼気ゲートを立ち上げ25 ms・減衰70 msで追従させ、肺圧の更新幅を決める。続いて平滑音高 \(f\) を、目標 \(F\) に対し \(f(F/f)^{1-e^{-\Delta t/0.06}}\) に更新する。48 kHzでは制御の刻み \(\Delta t\) は64/48,000秒で、内部96 kHzの128サンプルにわたり同じ平滑音高を使う。`ParametricGlottis::next` は圧力差を平滑化し、声門の有声度・位相を進める。比較用の設定ではドリフト、ビブラート、ジッタ、シマーを0にするので、各内部サンプルで位相が \(f/96000\) 周期進み、1を超えると1周期を差し引く。音高を変えても位相は連続する。声門開口はcm²、流量はcm³/s、圧力はdyn/cm²。気道を1サンプル進めた総放射流量の時間微分を、間引き、DC除去、リミッターに通してf32 PCMを返す。[音源設定と合成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L305)・[制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L458)・[発振器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)

上流の `tests/live-control.test.ts` はポート・チャンネルの重複所有、抜線、遅い許可を検査する。`engine::output_does_not_depend_on_the_host_block_size` は歌唱スコアの音高指定を含む2秒を複数のホストブロックで照合する。このケースでは、手動演奏時の持ち替えと前の保持音への復帰を、固定上流の押下経路と実際の音源に分けて測る。従来の候補PCMのビット比較を再利用する。[所有テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L65)・[ホストブロックテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)・[既存の手動MIDI計測](worklet-midi-voice.md)

## 事前登録

男性の基準 /i/、初期110 Hz、出力48 kHz。0.14秒にMIDI 45を押し、0.46秒に57を重ね、0.78秒に57を離し、1.10秒に45を離す。1.60秒に手動で停止を要求し、既存の0.80秒の停止後区間も採取する。ブラウザで採用された音高は110→220→110 Hz、呼気は最後の離鍵までは1と予測した。音高だけ110 Hzに固定した候補対照と比べると、高音の採用フレームで声門の音高と位相が最初に変わり、その後128フレーム以内にPCM差が \(10^{-6}\) を超えると予測する。固定上流との許容差は同じ母音での既存の判定を使う。[入力・観測点・判定](../cases/worklet-midi-voice-pitch.json)

## 実装と再実行

研究版の「MIDI鍵盤の発声」と固定上流の「Play」をChromiumで開き、仮想ポートから同じ4イベントを送った。上流の画面では保持一覧、音高目標、呼気の指示を観測し、研究版では音声スレッドの採用フレーム、加工前PCM、CLIで再生できるケースを保存した。画面ごとに時計が独立しているため、音波形を比較する固定Rustプローブは、研究版の出力フレームを64で割った制御時刻を受け取る。

既存の調音プローブの発声モードに `f0_hz` を追加した。固定上流の `HumanVoice::set_source` を使い、更新のたびに比較ケースのジッタとシマーを0に保つ。出力の末尾内部サンプルで上流を観測し、候補の内部全サンプルから対応点を選んだ。候補のPCMはブラウザとRust CLIで、上流のPCMは1フレームずつの観測付きレンダーと77フレームまでの音声専用レンダーで照合した。声門位相は折り返しを除いた差分を、独立計算の平滑F0を内部レートで割った値と比較した。候補の放射から間引き、DC除去、制限を経たPCMも独立に再構成した。[計測コード](../tools/measure_worklet_midi_pitch.py)・[上流プローブ](../tools/upstream_articulation_probe.rs)

初回は候補のWAV・CSVと両画面のMIDI状態を保存した後、PCM出力CSVの読み込みで停止した。共通関数の戻り値がすでに列名を持つ辞書だったため、不要な転置を除いた。独立計算側も音高の比較はHzのままにし、位相差分の計算だけで内部レートによる除算を行うよう整理した。ケースと判定閾値は第1版から維持した。[停止時の記録と採取出力](../runs/worklet-midi-voice-pitch-20261121-a/failure.json)

macOS 15.6.1 arm64、Rust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4、NumPy 2.4.4を使用した。入力は仮想MIDIポートA。出力48 kHz、内部96 kHz、制御64出力フレーム、描画128フレーム。採用時刻の変動を含めた全フレームを比較し、保存対象の内部系列は列を選んで全行を残す。作業時の最大見積もりは1 GiBで、RTL9210B-CGの空き888 GiBと書き込み可否を確認した。

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_worklet_midi_pitch.py worklet-midi-voice-pitch-local-1
```

## 結果

両方の画面で保持音は45→57→45→全解放、音高目標は110→220→110→110 Hz、呼気目標は1→1→1→0だった。正式実行の採用時刻は出力14,848、30,208、45,568、60,928フレーム。220 Hzを指示した最初の更新では声門F0は110.000→111.689 Hz、保持中の110 Hzに戻った最初の更新では219.265→215.966 Hzだった。声門位相を折り返して求めた増分は独立計算と最大1.18×10⁻¹⁶周期差。候補と上流の平滑F0の独立式との差は最大6.26×10⁻¹³ Hz、呼気差は2.23×10⁻¹⁶だった。[押下・離鍵と制御の判定](../runs/worklet-midi-voice-pitch-20261121-final/summary.json)

110 Hzに固定した候補対照では、持ち替え前のPCMはビット一致し、呼気と調音は全区間で一致した。持ち替えが採用された内部サンプル60,416で、声門F0、位相、面積、流量が同時に分岐した。最初の総放射差は内部サンプル60,417。出力PCMのビット差は30,220フレームからあり、差が \(10^{-6}\) を超えたのは30,225フレームだった。採用から17フレーム（約0.354 ms）後に当たる。[音高だけを固定したケース](../runs/worklet-midi-voice-pitch-20261121-final/artifacts/constant-pitch-case.json)・[対照の声門・流量系列](../runs/worklet-midi-voice-pitch-20261121-final/artifacts/constant-pitch-state.retained.csv)

ブラウザとCLIは正式実行の124,416 PCMフレームがビット一致し、972時点の6内部系列も一致した。放射から独立に再構成したPCMは値がすべて一致した。固定上流とのPCM最大差は \(2.18\times10^{-11}\)。ビット差は13,082点あり、最初は押下前の出力0フレームだった。上流の最初の観測点である内部サンプル1では、口腔断面で \(1.11\times10^{-16}\) cm²の差が見え、咽頭側の圧力と口端流量にも差があった。今回記録した上流系列の間隔は2内部サンプルで、初期化のどの演算が先に分岐したかは未特定。固定上流の2通りのホストブロックではPCMがビット一致した。[上流の内部観測](../runs/worklet-midi-voice-pitch-20261121-final/artifacts/upstream-trace.retained.csv)・[数値差](../runs/worklet-midi-voice-pitch-20261121-final/summary.json)

作業ツリーと`/tmp`の各13項目、従来のMIDI所有回帰16項目、可動母音26項目、`cargo test --locked --workspace` 40件が合格した。正式実行はChromium 156.0.8078.4で、起動直後32量子を除いた940量子はp95・p99・最大が2 ms。1 ms刻みのタイマーで約2.67 msを超えた量子は無かった。物理MIDI機器とOS・ブラウザの許可画面は未照合。[作業ツリーでの計測](../runs/worklet-midi-voice-pitch-20261121-b/manifest.json)・[従来のMIDI回帰](../runs/worklet-midi-voice-pitch-20261121-midi-regression/summary.json)・[可動母音の回帰](../runs/worklet-midi-voice-pitch-20261121-motion-regression/summary.json)

正式実行の内部系列CSV3本は全行で判定した後、検証に用いた主要列を残し、合計237.9 MBから130.5 MBに縮めた。RTL9210B-CGの実体を、候補・音高固定対照の各248,832行と上流124,416行の座標、25成果物のSHA-256で照合した。[正式の実行と保存先](../runs/worklet-midi-voice-pitch-20261121-final/manifest.json)
