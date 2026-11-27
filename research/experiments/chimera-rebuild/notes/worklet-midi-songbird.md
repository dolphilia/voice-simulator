# Web MIDIによる鳴禽の持続音

## 固定上流の読解

Bestiary の `KeysMode` で「Held voice」を選ぶと、`connectMidi` が入力ポートごとの押下・解放をストアに渡す。`noteOn` は音番号の保持順を更新し、種のパラメータから役割が `pitch` の項目を選んで目標F0を設定する。押下速度はこの持続音の経路では音量に使われず、呼気目標は保持中1、最後の解放で0になる。上に重ねたキーを離したときは、残っているうち最も後から押したキーの音高に戻す。最後のキーを離しても目標F0が残る。`AudioEngine.setCreatureParams` の音高更新とゲート指示はWorkletへ届き、固定Rust版の `CreatureVoice::set_params` と `set_gate` で目標になる。[MIDI入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[Bestiaryの入力選択](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L79)・[ストア](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[ブラウザの送信](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L291)・[固定Rust版の目標更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)

`creatureKeyHz` はMIDI音番号 `n` を `440 × 2^((n−69)/12)` Hzに変換する。種の音域下端 `L` と上端 `H` の幾何平均と、中央のドの周波数との比を2を底とする対数にし、最も近い整数オクターブ分だけ鍵盤全体を移す。移した音が上端を超えれば半分にし、下端を割れば倍にする。鳴禽の左鳴管は400〜9,000 Hzなので移動幅は+3オクターブ。右鳴管は左の音高に `2^(interval_semitones/12)` を掛け、既定値では+7半音。独立計算では同じ操作を半音の尺度で計算した。[音域への写像](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L95)・[鳴禽のパラメータ範囲と左右の鳴管](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)

48 kHz出力では128フレームの描画量子に対し、音源の制御は出力64フレームごと、内部刻みは192 kHz。`CreatureVoice::control` はその時点の目標を読み、左のF0を対数上で時定数8 ms、呼気を線形上で上昇4 ms、下降12 msで更新する。続いて気嚢圧と左右の鳴管を設定し、内部サンプルごとに左右の開口比から断面積を設定して、気道の圧力・流量と放射を進める。固定版の既存ABIテストは全種の管・音源・パラメータ項目をWorkletで確認する。今回は加えて実ブラウザの鍵盤経路と、左右の鳴管ポートの流量を照合した。[制御とレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[ブラウザのABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

## 事前登録と実装

60と67を重ねて60へ戻してから全解放し、続いて0、127で音域の上下から折り返す。60 → 67 → 60は約2,093 → 3,136 → 2,093 Hzと予測した。音高の指示が変わった直後と安定窓、最終解放後160〜240 msを比較する。定常窓で左右の流量RMSを検査し、60の音高を固定した対照で呼気と気嚢圧を一致させたまま、鳴管流量とPCMが変わるか調べる。[ケース・測定窓・事前の判定条件](../cases/worklet-midi-songbird.json)

研究版の「MIDIで鳴禽を演奏」で「持続音」を選ぶと、既存のMIDI所有管理を使い、変化した最新の保持音または全解放を既存の動物AudioWorkletへ渡す。Workletは次の描画量子の先頭で適用した順番、出力フレーム、AudioContextフレームを保存する。Rustの `SongbirdVoice::select_midi_note` は音域の上下限を鳴禽の制御値検査と共有する。書き出した `songbird_voice.events[].held_midi.note` をWASMとCLIで同じRustの処理に渡す。同じフレームの鍵盤操作は入力順で適用されるため、同じ量子に押下と解放が届いても、最後に押した音高を保持して呼気を閉じる。[画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[量子での適用](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[RustのMIDI入力](../crates/vocal-core/src/songbird_voice.rs)・[CLIの再実行](../crates/vocal-cli/src/songbird_voice_case.rs)

固定ブラウザで受けた音高の設定値を候補の採用フレームに置き、固定版のネイティブ `CreatureVoice` を描画する。別に進める観測用気道は同じ制御値で描画し、左右の気管支の末端と気管の先頭を結ぶ枝から断面積と体積流量を読む。比較するPCMは固定版の公開レンダーから採取する。ブラウザの公開テレメトリは、別の起動時刻に対して安定窓の音高と呼気を比較する。[ブラウザ実行](../../../../web/prototypes/chimera-research/tools/capture-midi-songbird.mjs)・[固定版のネイティブ観測](../tools/upstream_songbird_voice_probe.rs)

## 検証結果

登録した17項目が合格した。左鳴管の目標は60が2,093.00 Hz、67が3,135.96 Hz、0が523.25 Hz、127が6,271.93 Hz。60 → 67 → 60と戻る間の定常窓では、呼気ゲートは0.999以上を保った。全解放後のPCMのRMSは直前の定常区間比で最大9.43×10⁻⁷だった。音高を60に固定した対照では呼気と気嚢圧が全フレームで一致し、持ち替え区間のPCM差のRMSは0.202だった。[正式計測の全判定](../runs/worklet-midi-songbird-20261121-rev2/summary.json)

48 kHzの加工前WAV 144,000フレームが、113フレーム単位で描画したCLIとビット一致した。同じ採用フレームから描画した固定上流もPCMの最大サンプル差は0。候補WorkletとCLIの2,250点では、比較した11系列すべての差が0だった。固定上流と比較した流量には、左ポートがフレーム10,114、右ポートが10,115から微差が観測された。左の最大差は2.98×10⁻¹³ cm³/s、右は2.13×10⁻¹³ cm³/s。開口比・実断面積・気嚢圧・音高には差がなかった。流量の内部刻みで初めて差が生じる演算は未特定。採用間隔と登録値との差は最大2.67 msだった。[系列差と採用フレーム](../runs/worklet-midi-songbird-20261121-rev2/summary.json)

登録条件の初回試行は、固定ブラウザの鳴禽ボタンのアクセシブル名に学名も含まれ、厳密なラベル検索がタイムアウトした。検索を学名を含むラベルに修正し、14項目が合格した。同じフレームで押下と解放を行う追加対照では、当初の無音という予測だけが外れた。入力順どおり音高目標は523.25 Hzに変わり、呼気ゲートと気嚢圧は0のまま、フレーム129から短いPCMが現れた。[初回の失敗](../runs/worklet-midi-songbird-20261121-a/manifest.json)・[初回の比較成立](../runs/worklet-midi-songbird-20261121-b/summary.json)・[判定改訂前の結果](../runs/worklet-midi-songbird-20261121-final/summary.json)

第2版で、同じ音高操作を固定上流に渡し、候補には口腔食道腔の音高追従を0にした対照も加えた。通常の追従条件は候補と固定上流ともPCMピーク0.07390、開始フレーム129で、サンプル差は0。追従を0にしたときは全PCMが0だった。音高 f に追従する容積の成分は f⁻² に比例する。気道は形状補間で生じる −dV/dt を節点の流量源として扱うため、気嚢圧を供給しなくても口腔食道腔の容積変化が音を作る。ゲートが閉じているときだけ追従を遅らせる案は、通常の持続音の立ち上がりとこの短い過渡を別々に比べる改善候補として残した。[同一フレームの結果と対照](../runs/worklet-midi-songbird-20261121-rev2/summary.json)・[上流の容積流量源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L834)

持続音と停止の回帰25項目、既存の `flute` コールの回帰18項目、Rustの40件が通過した。高密度CSV3本は全フレームの判定後に180.3 MBから37.4 MBへ抜粋し、RTL9210B-CGに置いた。元CSVのハッシュ、実行コマンド、環境、WAVと再実行ケースはマニフェストから確認できる。実機の操作と許可画面、鍵盤からコールを開始する判断、他の動物への適用は後続の条件に残る。[正式マニフェスト](../runs/worklet-midi-songbird-20261121-rev2/manifest.json)・[持続音の回帰](../runs/worklet-midi-songbird-20261121-sustain-regression/summary.json)・[コールの回帰](../runs/worklet-midi-songbird-20261121-flute-regression/summary.json)・[次の登録条件](../cases/worklet-midi-songbird-call.json)

研究ディレクトリで仮想環境を有効にして次のコマンドを実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  python3 tools/measure_worklet_midi_songbird.py worklet-midi-songbird-local-1
```
