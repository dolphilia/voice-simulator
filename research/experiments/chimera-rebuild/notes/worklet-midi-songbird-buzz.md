# Web MIDIでのFinch buzzのパルス間隔

## 固定上流の読解

比較対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `connectMidi` から `store.noteOn` へ進み、BestiaryのFinch buzzを選んでいる間は `creatureKeyHz` の音高を `AudioEngine.playCall` へ渡す。基準はA4=440 Hz。鳴禽の400〜9,000 Hzに合わせて3オクターブ上へ移るので、MIDI 60・67は2,093・3,136 Hzになる。Workletの `call` がWASMの `engine_play_call` を呼び、Rustの `CreatureVoice::play_call` が呼気倍率1と鍵盤音高／1,200 Hzを携えてコール時計を始める。`noteOff` は保持キーを解放する。コールモードでは手動呼気が0のまま進み、包絡の終点に達するまでコールが有効になる。[MIDI](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[押下と離鍵](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)

`songbird::def` の `buzz_keys` は最初のキーで呼気0、基準音高1,200 Hz、左右の配分0.5、駆動0.95、張力0.15、音程差0.5半音、口腔食道腔の追従を混ぜる比率0.1を設定する。呼気の目標値は \(i=0…7\) に対して \(0.02+0.07i\) 秒で1、\(0.06+0.07i\) 秒で0.35。末尾キー0.60秒で0になる。`CreatureVoice::eval_call` は各項目の前後のキーを読み、曲線指定が無い区間は線形補間する。呼気目標は無次元で、倍率1を適用した自動呼気と0の手動呼気の最大値を使う。音高の補間・平滑化は対数空間で、時定数は8 ms。呼気の一次遅れは増加時4 ms、減少時12 msで、64出力フレームごとに係数 \(1-\exp(-\Delta t/\tau)\) で更新する。再発音では次の制御で呼気目標が0に戻る。平滑値と発音器は直前までの状態から進む。最後のキーから50 msを過ぎた制御で、所有していた目標を演奏者の値へ戻す。[キー列](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L149)・[包絡と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

`Songbird::control` は平滑呼気と気嚢の設定圧を掛け、kPaからdyn/cm²へ10,000倍して気嚢圧を設定する。左右の筋ゲートは配分0.5なら両方1。右の音高は左の \(2^{0.5/12}\) 倍が目標となる。各内部サンプルで `SyrinxLabia::next` が駆動と張力を係数に変換し、二変数の振動を4次Runge–Kuttaで進める。変位を周期表の最小・最大で正規化し、その二乗と左右の筋ゲートの平滑値で開口を求める。開口×0.03 cm²を左右の枝に適用して気道を更新する。放射流量の時間微分はcm³/s²で、間引き・DC除去・振幅制限を通した出力は無次元のf32 PCM。[気嚢から気道まで](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[鳴管弁の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs#L112)

上流の `creatures_match_typescript` は48 kHzの `songbird-call-buzz` で全37千弱フレームの音と包絡、途中のテレメトリを照合する。`defs_serialise_like_typescript` はキー列を含む定義、`warm_creature_voice_does_not_allocate` と `every_call_key_resolves` は全コールを含む割り当てと名前解決を検査する。WorkletのABIテストは各動物の最初のコールの識別子と観測列を照合する。今回の比較は通常のWeb MIDIを入口とし、離鍵と再発音を検査する。[ゴールデンテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[実時間テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)・[WorkletのABIテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

## 事前登録

48 kHz、内部192 kHz、2音で1.65秒。MIDI 60を0.14秒、67を0.585秒に押し、0.36・0.84秒に離す。判定では実際の採用フレームを起点にして、64フレームごとの制御を読む。初回では0から1に向かう区間を読むので呼気目標0.75に達するのは \(0.02\times0.75=0.015\) 秒。第2パルスの交差は \(0.06+0.03(0.75-0.35)/(1-0.35)\) 秒で、初回の間隔は約63.46 msになる。後続6間隔は70 ms。第2音で8回の上向き交差を予測し、第1音は再発音前までの交差を数える。平滑呼気は第2音で目標の交差から64〜320フレーム後に同じレベルへ達すると予測する。左右の流量とPCMを両離鍵後25〜160 msで測り、次の押下で音高・呼気の平滑状態が連続するかを一更新の式で確かめる。固定時刻の96 kHz・呼気倍率0.8の計測も回帰で再実行する。[閾値と観測点](../cases/worklet-midi-songbird-buzz.json)・[固定時刻の比較](worklet-songbird-buzz.md)

## 実装と再実行

研究版の「MIDIで鳴禽を演奏」でFinch buzzを選び、仮想Web MIDIのポートから候補と固定上流の通常画面へ同じ操作を送った。研究版はAudioWorkletとWASMから `SongbirdVoice::midi_call` を呼ぶ。出力したケースの採用フレームを使い、Rust CLIは113フレーム単位で再生する。固定Rustは同じ採用時刻に、上流画面が発行した音高を持つ押下を再生する。上流と候補の実時間画面は個別に実行した。

比較器は固定時刻の実験にある有理数の交差時刻計算を使う。開始から再発音または終了までを2窓に分け、先に線形キーから目標の交差、次に独立した平滑化から呼気の交差を算出した。左右の配分・駆動・張力・音程差・純度も目標と平滑値を別に検査し、固定Rustと放射・間引き・DC除去それぞれの最初の差を記録した。[Web MIDIの計測器](../tools/measure_worklet_midi_songbird_buzz.py)・[独立した交差計算](../tools/measure_worklet_songbird_buzz.py)・[コールを受ける合成器](../crates/vocal-core/src/songbird_voice.rs#L121)

macOS 15.6.1 arm64、Rust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4、NumPy 2.4.4を使用した。48 kHz、1.65秒、79,200出力フレーム。Workletの描画量子は128フレームで、64フレームごとの区間末尾を記録した。UUIDと書き込み可否を確認した作業用RTL9210B-CGに出力し、基準のCSVとビルドを含む容量見積もりとして512 MiBを指定した。

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_songbird_buzz.py worklet-midi-songbird-buzz-local-1
```

## 結果

正式実行では8,320・29,568フレームで押し、18,816・41,856で離した。先頭の音高目標は2,093.005・3,135.963 Hz。左右の配分0.5、駆動0.95、張力0.15、左右の音程差0.5半音、純度0.1の目標を両押下時に確認した。再発音で呼気目標は0.978333→0、平滑呼気は0.941683→0.842655、平滑音高は2,093.005→2,227.040 Hz。直前までの平滑値からの一更新に一致した。第2音の終了は60,800フレーム。評価に使う時計は前の制御で0.649333秒、終了時に0.650667秒だった。[採用時刻と内部状態](../runs/worklet-midi-songbird-buzz-20261121-final/summary.json)

両実行で目標0.75の交差は第1音7回、第2音8回。独立計算を64フレーム格子に切り上げた全15位置に一致した。両音の初回間隔は3,008フレーム（62.667 ms）、後続は3,392と3,328フレーム（70.667と69.333 ms）が交互に現れた。目標の交差に対する平滑呼気の遅れは128と192フレーム（2.667と4 ms）が交互に現れた。平滑呼気の交差位置も独立計算と一致した。[交差と平滑化](../runs/worklet-midi-songbird-buzz-20261121-final/summary.json)

離鍵後25〜160 msの窓には両音とも2回の上向き交差があり、左・右の流量RMSは第1音が15.113・15.142 cm³/s、第2音が7.651・7.238 cm³/s。対応するPCMのRMSは0.32715・0.08967だった。開口×0.03 cm²とポート面積の差は、左右とも全フレームで0。[両離鍵窓と鳴管の時系列](../runs/worklet-midi-songbird-buzz-20261121-final/artifacts/cli.retained.csv)

候補のブラウザとCLIは79,200 PCMフレームがビット一致し、1,238時点の23列で差は0。放射から独立に再構成したPCMも一致した。固定Rustとの最初の差は押下6内部サンプル後の総放射で、候補が−0.03329702717173142、上流が−0.03329702717173143 cm³/s²。この時点の呼気と気嚢圧は0で、呼気目標に正値が出るのは押下64出力フレーム後だった。左右流量で最初に差が見えたのは押下5出力フレーム後で、開口、気嚢圧、音高は全フレームで一致した。固定Rustとの差がPCMに現れたのは両実行とも減衰中の1点で、正式実行ではフレーム77,443の絶対差が \(1.32\times10^{-23}\)。上流との差を生む総放射より前の演算と、物理MIDI・許可画面は未検証。[合成段ごとの比較](../runs/worklet-midi-songbird-buzz-20261121-final/summary.json)

作業ツリーと `/tmp` から各19項目、96 kHzの固定時刻の回帰20項目、`cargo test --locked --workspace` 40件が合格した。Chromium 156.0.8078.4の採取量子は619。最初の8量子を除くp95は1 ms、p99は2 ms。1 ms刻みの計時で最大3 msを記録し、予算2.67 msを5件が超えた。採取フレームの欠落は0だった。正式実行はCSV2本を全79,200行で判定した後、合計74.4 MBから69.8 MBに絞ってRTL9210B-CGに保存した。[初回](../runs/worklet-midi-songbird-buzz-20261121-a/manifest.json)・[正式実行と保存先](../runs/worklet-midi-songbird-buzz-20261121-final/manifest.json)・[固定時刻の回帰](../runs/worklet-midi-songbird-buzz-20261121-fixed-regression/summary.json)

Chirp cascadeの回帰の初回は、共通の計測器から固定Rustの内部系列を追加で渡した際、Chirp側の関数がその引数を受け取れず、全判定を作成する前に停止した。採取済みのWAVとCSVを失敗記録に保存した。Chirp側が拡張用の引数を受け取れるよう修正し、新しい実行IDで再計測した。[回帰の停止記録](../runs/worklet-midi-songbird-buzz-20261121-chirps-regression/manifest.json)

修正後のChirp cascadeの回帰20項目はすべて合格した。Finch buzzの正式実行の15成果物とCSV各79,200行をマニフェストに照合した。[Chirpsの回帰結果](../runs/worklet-midi-songbird-buzz-20261121-chirps-regression-rerun/summary.json)
