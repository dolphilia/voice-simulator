# Web MIDIによるウェッデルアザラシの持続音

## 固定上流の読解と事前登録

固定上流のBestiaryで Weddell seal と Held voice を選ぶと、MIDIの `noteOn` と `noteOff` は保持順を更新し、最後に押されているキーを発声の音高と呼気へ渡す。全解放では保持音が空になり、呼気目標が0になる。音高の設定値は残る。音高役割のパラメータは `seal::def` の `pitch` で、範囲は40〜6,000 Hz、既定値は900 Hz。鍵盤の全体を、中央のドが音域の幾何平均に近づく整数オクターブだけ動かす。音域外の周波数は2倍・半分を繰り返す。アザラシでは+1オクターブになり、60と67は523.251 Hzと783.991 Hz。127は6,000 Hzを下回るまで折り返して3,135.963 Hzになる。[固定版の鍵盤と呼気](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L95)・[保持順の更新](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[アザラシの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L87)

`CreatureVoice::control` は出力64フレームごとに音高を対数上で時定数10 ms、呼気を上昇6 ms・減衰30 msで平滑化する。続く `Seal::control` は呼気パルスの位相を回し、半正弦の包絡を作る。肺圧は水柱cmの設定値に980.665、平滑化した呼気、パルスのゲインを掛けた dyn/cm²。出力の前に1回無呼気の制御が実行されるため、フレーム0のパルス位相までに2刻み進む。さらに声門へ平滑化した音高を渡し、圧力差から内部サンプルごとの開口と流量を更新する。出力48 kHzでは気道は96 kHzで進み、放射流量の時間微分を2倍間引きし、DC除去とリミッタを経て f32 PCM を得る。固定版のABI試験は実際のWorkletへ動物を切り替え、テレメトリの管・音源・パラメータを確認する。[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[肺圧と声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[声門と気道の結合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[先行する持続音の測定](worklet-seal-sustain.md)

登録ケースは60→67→60→全解放、続いて127→全解放。押下・持ち替えから100〜240 msで音高・呼気・声門・PCMを観測し、全解放から250〜330 msで減衰を測る。60へ戻る区間も呼気が0.999以上を保ち、全解放後の窓で0.00035以下になると予測した。固定上流のブラウザで保持音・設定値・テレメトリを観測し、候補が採用したフレームへ同じ設定を置いた固定RustのPCM・内部系列を比較する。独立計算は半音単位の音域への写像、音高と呼気の平滑化、肺圧のパルス、放射系列からPCMまでを別々に照合する。[時刻と判定基準](../cases/worklet-midi-seal.json)

## 実装と比較方法

「MIDIでウェッデルアザラシを演奏」は鳴禽と同じMIDIポートの所有管理を使う。Workletは描画量子の先頭で採用した音番号と2つのフレーム時計を保存する。鳴禽で使っていた鍵盤写像を共有Rust関数に移し、アザラシは範囲40〜6,000 Hzを渡して音高目標と演奏者の呼気を更新する。ブラウザまたはCLIで `seal_voice.events[].held_midi.note` を渡すと、`SealVoice::select_midi_note` が実行される。Workletは128フレームの描画量子の中で、CLIは指定した分割幅で、同じ声門・気道の状態を進める。[共通の鍵盤写像](../crates/vocal-core/src/creature_midi.rs)・[アザラシの音源](../crates/vocal-core/src/seal_voice.rs)・[CLIの適用順序](../crates/vocal-cli/src/seal_voice_case.rs)・[ブラウザの操作](../../../../web/prototypes/chimera-research/src/main.tsx)

固定版ネイティブの観測器は、実際の気道の声門枝から開口、壁面と口端・鼻端から放射を読む。位相と瞬時F0は、同じ差圧とパラメータを入れた観測用声門から取得し、その面積が実際の声門枝と一致することも検査する。上流PCMは `CreatureVoice::render` の出力を使う。[固定上流の観測器](../tools/upstream_seal_voice_probe.rs)・[ブラウザの比較手順](../../../../web/prototypes/chimera-research/tools/capture-midi-songbird.mjs)・[計測入口](../tools/measure_worklet_midi_seal.py)

## 検証結果

別の作業ディレクトリから再実行し、登録11項目が合格した。48 kHzのWAV 139,200フレームが、109フレーム分割のCLIとビット一致した。同じ採用フレームから固定版を描画したPCM、および候補の内部放射から独立計算したPCMもサンプル差が0。WorkletとCLIの2,175観測点では、比較した21系列がすべて差0だった。登録したキー間隔と採用間隔との差は最大4 ms。[正式試行の結果](../runs/worklet-midi-seal-20261121-final/summary.json)

持ち替えて60へ戻るまで呼気は継続した。60→67→60の平滑化音高の中央値は約523.25→783.99→523.25 Hzで、127は約3,135.96 Hz。持続音での声門開口の最大は約0.246〜0.248 cm²。全解放後の窓では、呼気ゲートの最大が0.000235、開口の最大が0.010 cm²で、PCMのRMSは直前の持続音の最大1.74×10⁻⁷倍だった。同じように呼気が開いていた67と60への復帰の窓でも、PCMのRMSは0.0475と0.104だった。異なる窓の呼気パルス位相を揃える比較を改善候補に残した。[音高・声門・呼気の測定値](../runs/worklet-midi-seal-20261121-final/summary.json)

初回は独立計算の肺圧が最大804.10 dyn/cm²ずれ、最初の押下で呼気が立ち上がるフレーム6,656から差が出た。独立計算が出力前の無呼気制御を1回省いていたため、半正弦の位相が1制御周期ずれていた。位相を出力前の値で初期化して再実行し、肺圧の最大差は1.82×10⁻¹² dyn/cm²になった。登録した許容値は変えていない。気道の候補と上流では最初の押下から19出力フレーム後に壁面放射の系列で最初の微差が出た。放射の時間微分の最大差は9.78×10⁻⁸ cm³/s²で、差が生じる内部演算は未特定。[初回の失敗と差](../runs/worklet-midi-seal-20261121-a/summary.json)・[修正後の全差分](../runs/worklet-midi-seal-20261121-final/summary.json)

鳴禽のMIDI回帰17項目、アザラシのコール `zap` の回帰72項目、Rust40件が通過した。全フレームで判定したCSV2本は120.5 MBから34.1 MBに抜粋し、WAV・再実行ケースとともにRTL9210B-CGに保存した。環境・実行コマンドと元CSVのハッシュはマニフェストにある。物理機器と許可画面、アザラシのコールを鍵盤から開始する条件が残る。[正式マニフェスト](../runs/worklet-midi-seal-20261121-final/manifest.json)・[鳴禽の回帰](../runs/worklet-midi-seal-20261121-songbird-regression/summary.json)・[zapの回帰](../runs/worklet-midi-seal-20261121-zap-regression/summary.json)・[次の登録条件](../cases/worklet-midi-seal-call.json)

研究ディレクトリで仮想環境を有効にして再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  python3 tools/measure_worklet_midi_seal.py worklet-midi-seal-local-1
```
