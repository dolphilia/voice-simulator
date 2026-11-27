# Web MIDIによるアフリカゾウの持続音

## 固定上流の読解と事前登録

Bestiaryの`KeysMode`でHeld voiceを選ぶと、`noteOn`は`Elephant::def`で音高の役割を持つ`pitch`へ鍵盤を割り当てる。中央値に当たる幾何平均と中央のドの比をオクターブへ丸め、音域8〜45 Hzから外れた音を倍または半分にする。MIDI 60、67は4オクターブ下の約16.35、24.50 Hz、0は下限を越えるまで倍にして約8.18 Hz。押下順の最新音を使い、解放時は以前の保持音に戻る。全解放では音高目標を保ち、手動の呼気目標を0にする。`lipPitch`はトランペット側の弁の固有周波数で、この持続音のMIDI音高の割り当てには使われない。[Bestiaryの鍵盤モード](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L78)・[MIDIの計算と振り分け](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L100)・[音域の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L118)

`setCParam`から`AudioEngine.setCreatureParams`を経由してWorkletに目標が届く。`CreatureVoice::control`は64出力フレームごとに、対数音高を50 ms、無次元の呼気ゲートを上昇12 ms・減衰60 msの時定数で更新する。時定数をτ、制御刻みをΔtとすると、目標へ進む比率は 1 − exp(−Δt/τ)。`Elephant::control`は肺圧を水柱cm×980.665×呼気ゲートとしてdyn/cm²へ換算し、声門へ更新後のHzと発声条件を渡す。つづく各サンプルでは、気管末端と咽頭入口の差圧で声門を更新し、鼻腔と長い鼻の境界の弁を決めてから気道を進める。初期モード0では弁を4.5 cm²に固定し、鼻腔入口の開口は6.1 cm²、口先は0.05 cm²。口・鼻先・壁面の体積流量の時間微分から、内部と出力が同じ48 kHzでDC除去と振幅制限を経たf32のPCMを得る。[制御時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[肺圧・鼻の弁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)・[声門と気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)

固定版のABI試験でBestiaryのパラメータとテレメトリの受け渡し、ゴールデン試験で発声中のPCM・状態・描画分割を検査する。研究版の既存ケースでは、呼気開始から気管末端、声門、鼻腔末端、弁、鼻先に変化が伝わる順を確認済み。今回は同じ初期姿勢でMIDIの60→67→60→全解放→0→全解放を使う。採用後250〜440 msで音高、声門の開閉と周期、鼻先・口端の流量を、解放後330〜400 msで呼気とPCMを測る。鼻先の流量RMSが口端を上回り、0でもこの窓で位相が少なくとも一周分の境界を越えると予測した。[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[既存の固定発声](worklet-elephant-fixed-voice.md)・[登録条件](../cases/worklet-midi-elephant.json)

## 実装と計測

「MIDIでアフリカゾウを演奏」は共通の鍵盤入力で最新の保持音を受け取り、`ElephantVoice::select_midi_note`が既存の音高と呼気目標へつなぐ。Workletの量子先頭で採用した入力を `elephant_voice.events[].held_midi.note` として出力する。CLIはこれを読み、同じRustの音源を109フレーム分割で動かす。固定上流でも通常の操作で鍵盤を押し、入力で選ばれた目標を研究版の採用時刻にそろえて、固定RustのPCMと圧力・声門・弁の系列を取得する。補間と平滑化は音高を対数で扱う計算で、PCMは採取した放射系列を入力にした別の計算で確認する。[研究版のMIDIパネル](../../../../web/prototypes/chimera-research/src/main.tsx)・[研究版の音源](../crates/vocal-core/src/airway/elephant.rs)・[固定版の測定入口](../tools/upstream_elephant_probe.rs)・[計測と判定の入口](../tools/measure_worklet_midi_elephant.py)

## 検証結果

48 kHz・3.55秒の仮想MIDIで、正式実行の14項目すべてに合格した。実時間Workletと109フレーム分割のCLIは170,400フレームのWAVがビット一致し、2,663時点の46観測列も差0だった。独立式との差は平滑音高で最大7.82×10⁻¹⁴ Hz、肺圧で1.82×10⁻¹² dyn/cm²。放射から独立に求めたPCMも全サンプルが一致した。[正式結果](../runs/worklet-midi-elephant-20261121-lung/summary.json)

目標音高は60、67、0の順に16.3516、24.4997、8.1758 Hz。キー0の測定窓では瞬時F0の中央値が8.1538 Hz、声門の最大開口が1.845 cm²で、位相の折り返しを1回観測した。鼻の弁は全区間4.5 cm²、弁を振動させる駆動差圧は0で、同じ窓の鼻先流量RMSは1,127.49 cm³/s、口端は182.60 cm³/sだった。最初の呼気上昇から気管末端へ34フレーム、声門流量へ35フレーム、鼻腔末端へ82フレーム、弁の流量へ83フレーム、鼻先の放射へ230フレームで変化が届いた。全解放の330〜400 ms後の呼気は最大0.00404、PCMのRMSは直前の保持音窓の0.089%以下になった。[測定窓と伝搬時刻](../runs/worklet-midi-elephant-20261121-lung/summary.json)

固定RustとのPCM最大差は9.31×10⁻¹⁰で、20サンプルのビットが異なった。肺圧は一致し、最初の微差は呼気上昇の1フレーム後の肺から気管へ入る流量に現れた。肺ポートを線形とし、最初に流れた体積から気管入口の圧力を求めると、2回目の更新では差圧に前の運動量の項を足して流量を解ける。固定上流の `(慣性 × 前回流量) × 刻みの逆数` と研究版の `(慣性 ÷ 刻み) × 前回流量` を独立計算で評価したところ、上流の330.226192814138と研究版の330.2261928141381 cm³/sを再現した。その後は気管末端、声門流量、壁面放射の順に微差が現れた。[独立式と採取値](../runs/worklet-midi-elephant-20261121-lung/summary.json)・[固定版の肺ポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L50)・[固定版の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L189)

最初の起動 `worklet-midi-elephant-20261121-a` はWAV読み込み関数のインポート元を取り違え、計測の開始とマニフェスト作成より前に停止した。インポートを修正した第1版は作業ツリーと別ディレクトリの両方で13項目が合格した。第2版は同じ条件に肺ポートの2サンプルの独立照合を加えた。固定発声の回帰80項目とRust40件も合格した。[第1版の計測](../runs/worklet-midi-elephant-20261121-b/summary.json)・[第1版の別ディレクトリからの再実行](../runs/worklet-midi-elephant-20261121-final/summary.json)・[固定発声の回帰](../runs/worklet-midi-elephant-20261121-fixed-regression/summary.json)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で計測した。高密度CSV2本は全点で比較後、必要な区間と列を172.5 MBから103.5 MBに絞ってRTL9210B-CGへ保存した。肺ポートに最初の微差が出た区間と、すべての測定窓が両方の抜粋に入り、成果16ファイルのSHA-256を照合した。物理MIDI機器とゾウのコールMIDIは未検証。[実行コマンドと成果のマニフェスト](../runs/worklet-midi-elephant-20261121-lung/manifest.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=671088640 \
  ../../.venv/bin/python tools/measure_worklet_midi_elephant.py worklet-midi-elephant-local-1
```
