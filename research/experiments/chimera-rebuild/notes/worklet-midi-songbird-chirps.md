# Web MIDIでのChirp cascadeのキーの重なり

## 固定上流の読み方

比較対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryのコールを選ぶと、`src/ui/midi.ts` の `connectMidi` から `src/ui/store.ts` の `noteOn` を通る。`creatureKeyHz` は音域の幾何平均に近づくようMIDI 60のオクターブを選び、入力を鳴禽の400〜9,000 Hzに折り返す。60と67は3オクターブ上へ移る。押下は `AudioEngine.playCall` からWorkletの `call`、WASMの `engine_play_call`、Rustの `CreatureVoice::play_call` に届く。離鍵は保持キーと手動ゲートを更新する。コールモードのキーは手動ゲートを開けないため、離鍵後もコール時計が進む。[UI](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)

`songbird::def` 内の `chirp_keys` は `voices=0.15` と `drive=0.4` を指定し、添字 \(i=0…8\) の開始秒 \(s=i(0.14-0.008i)\) を順に作る。呼気目標は \(s, s+0.01, s+0.06, s+0.07\) 秒でそれぞれ0・1・1・0。最初の音高は \(7000-300i\) Hz、終点は \(2400-80i\) Hz。開始はステップ、終点へは正値どうしを指数補間する。音高目標は鍵盤周波数を4,500 Hzで割った比で移調され、鳴禽の音域に収まるよう制限される。呼気と左右の配分は無次元、音高はHz。[コールの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs)

`CallDef::resolve` は順序を保持して名前を添字に解決する。`CreatureVoice::eval_call` は項目ごとに途中のキーを飛ばしながら、最初に見つかる未来キーまで走査する。補間は直前に通ったキーとその未来キーで行い、曲線は後者の指定を使う。i=4の末尾0.502秒がi=5の開始0.500秒より先に登録される。登録順では0.492秒以降のゲートの下降を読み、時刻順ではi=5のステップ開始まで値1を保つ。0.61秒付近では、登録順でi=6の高さ1の区間を読み、時刻順ではi=8の開始から立ち上がる途中を読む。最後に登録されたキーの時刻は0.678秒で、そこから50 msを過ぎた制御更新で演奏者へ目標が戻る。[キー解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs)・[コール時計と評価](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs)

48 kHzでは内部192 kHzで、出力64フレームごとにコール目標を評価し、音高は対数空間で時定数8 ms、呼気は線形空間で上昇4 ms・下降12 msの一次追従を行う。1更新の残留率は `exp(-64 / (48000 × 時定数))`。再発音はコール時刻と発火フラグを初期化する。平滑値、左右の鳴管弁の変位・速度、気道、出力フィルタの状態は引き継ぐ。`Songbird::control` で平滑化した呼気ゲートと気嚢設定圧の積を取り、kPaからdyn/cm²へ10,000倍する。右の音高は左の音高の `2^(interval/12)` 倍。`Songbird::sample` は左右の `SyrinxLabia::next` を内部サンプルごとに進め、正規化開口に0.03 cm²を掛けてポートへ適用し、気道の伝搬を1回進める。開口はRK4で解く変位の正規化値を二乗し、左右別に平滑化した弁ゲートを掛ける。放射流量の時間微分はcm³/s²で、間引き・直流除去・制限を経て無次元のf32 PCMとなる。[気道との結合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs)・[鳴管弁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs)

上流の `every_call_key_resolves` は名前の解決を、`warm_creature_voice_does_not_allocate` は48・96 kHzで各コールと停止を含む割り当てを検査する。`creatures_match_typescript` は固定のシナリオから音・包絡・テレメトリを、`defs_serialise_like_typescript` はキー列を含む定義を照合する。ABIテストは最初のコールについてWorkletを経由した識別子・状態を照合する。今回は既存の44.1 kHzの固定時刻のキー順比較を、通常のWeb MIDIで移調と再発音を行う48 kHzケースへ広げる。[上流の実時間テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)・[比較テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[ABIテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[固定時刻の比較](worklet-songbird-chirps.md)

## 実装前の予測

MIDI 60・67を0.14・0.84秒に押し、0.30・1.03秒に離す。実際に採用されたフレームを起点にする。呼気目標の最初の差は23,680フレーム、音高目標の差は24,000または24,064フレームと予測する。0.61秒以上の最初の制御境界は相対フレーム29,312で、呼気目標は登録順で1、時刻順で2/3、音高目標は登録順のほうが250 Hz以上低い。全条件で並べ替えるのは対照用のキー列だけとし、出力比較では両方の目標を既存の手動入力で同一の合成器に通す。閾値、保存列、固定基準はケース第1版に登録した。[ケース定義](../cases/worklet-midi-songbird-chirps.json)

## 実装と再実行

研究版の「MIDIで鳴禽を演奏」でChirp cascadeを選び、仮想ポートから同じキー列を研究版と固定上流へ入力した。研究版では既存のAudioWorkletからWASMの `midi_call` を経由し、採用フレームを含むケースを書き出した。CLIはそのケースを113フレームずつ再生する。固定Rustプローブには押下のみを `play_call` として渡し、音高には上流の画面が送った値を使う。固定上流のコール定義は保存済み基準とSHA-256で照合した。固定上流の画面と研究版の画面は別々に実時間で動かし、Rust比較は研究版の採用フレームに揃えた。

計測器の `control_reference` はRustの評価関数を呼ばず、アーカイブのキー列から登録順と時刻順の目標を計算する。2本の目標を出力64フレームごとの手動ゲートとパラメータに変換して同じCLIへ入力した。同じ初期状態と採用時刻を両方に使い、合成器の係数には変更を加えていない。候補と固定上流の差とは別に、順序変更の差が最初に出る気嚢圧・開口・放射とPCMを記録する。[Web MIDIの計測器](../tools/measure_worklet_midi_songbird_chirps.py)・[制御目標の独立計算](../tools/measure_songbird_flute.py)・[目標系列の再生](../tools/measure_worklet_songbird_chirps.py)

macOS 15.6.1 arm64、Rust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4、NumPy 2.4.4を使用した。出力は48 kHz、2.20秒、105,600フレーム。Workletの量子は128フレーム、出力64フレームごとの末尾を記録した。RTL9210B-CGのUUID、書き込み状態、空き889 GiBを確認し、4本のCSV、WAV、ビルドログの同時使用を見込んで1 GiBを指定した。研究ワークスペースからの再実行は次のとおり。

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_worklet_midi_songbird_chirps.py worklet-midi-songbird-chirps-local-1
```

## 結果

正式実行の採用フレームは押下8,320、離鍵16,000、再押下41,856、離鍵51,072。先頭の音高目標は3,255.785・4,878.165 Hzだった。再発音の前後で平滑呼気は0.12650→0.11320、平滑音高は820.583→1,078.863 Hz。直前値からの1制御更新と一致した。離鍵後25〜200 msの左・右ポートの流量RMSは第1音で13.093・4.889 cm³/s、第2音で8.384・5.846 cm³/s。正規化開口×0.03 cm²は全フレームで両ポートの断面と一致した。第2音は押下から34,944フレーム（0.728秒）で終了し、演奏者の目標へ戻った。[実測結果](../runs/worklet-midi-songbird-chirps-20261121-final/summary.json)

| 観測値 | 第1音 | 第2音 |
| --- | ---: | ---: |
| 押下から呼気目標が初めて分岐するまで | 23,680フレーム | 23,680フレーム |
| 押下から音高目標が初めて分岐するまで | 24,064フレーム | 24,000フレーム |
| 経過0.610667秒の呼気目標（登録順／時刻順） | 1／0.666667 | 1／0.666667 |
| 同時刻の音高目標（登録順／時刻順） | 913.008／1,194.935 Hz | 1,367.966／1,790.380 Hz |

相対フレーム24,000は両回とも公称0.5秒。CSVの時計の差は第1音で0.49999999999999845秒、第2音で0.5000000000000175秒だった。0.500秒のステップの前側と後側に分かれるため、音高目標の差が出始める制御境界が一つずれた。[制御時計と目標の系列](../runs/worklet-midi-songbird-chirps-20261121-final/artifacts/cli.retained.csv)

二つの手動対照では、出力フレーム32,000で平滑ゲートと気嚢圧、内部サンプル128,028で総放射、出力フレーム32,007で間引きとDC除去が最初に分かれた。PCMのビット差は32,008、差が \(10^{-6}\) を超えたのは32,019で、最初の気嚢圧差から19フレーム（0.396 ms）後だった。左右の鳴管開口と平滑音高が分岐するのは32,384。キー順を変えたときのPCM最大絶対差は0.71716、登録順の手動対照と通常経路のPCM差は最大 \(1.49\times10^{-8}\) だった。[合成段ごとの比較](../runs/worklet-midi-songbird-chirps-20261121-final/summary.json)・[登録順の手動対照](../runs/worklet-midi-songbird-chirps-20261121-final/artifacts/declared-targets.retained.csv)・[時刻順の手動対照](../runs/worklet-midi-songbird-chirps-20261121-final/artifacts/chronological-targets.retained.csv)

WorkletとCLIは105,600 PCMフレームでビット一致し、1,650時点の17列で差は0。放射系列からの独立再構成もPCMではビット一致した。固定Rustとの最初の差は押下6内部サンプル後の総放射で、この時点で気嚢圧と左右の鳴管ポートの流量は0。右と左の流量で最初に差が見えるのは押下後5・6出力フレームで、開口、断面積、気嚢圧は一致する。PCMの差は減衰中のフレーム77,976の1点で \(8.88\times10^{-16}\)。総放射より前の演算は特定できていない。口腔食道腔の断面だけを固定する対照を次に試せる。[候補と固定Rustの総放射・ポート流量](../runs/worklet-midi-songbird-chirps-20261121-final/artifacts/upstream.retained.csv)・[差の判定](../runs/worklet-midi-songbird-chirps-20261121-final/summary.json)

研究ワークスペースと `/tmp` からの各実行は20項目に合格した。固定時刻の44.1 kHz回帰21項目、Canary trillのMIDI回帰17項目、`cargo test --locked --workspace` 40件も合格した。正式実行のChromium 156.0.8078.4では825量子を採取し、最初の8量子を除く処理時間はp95が1 ms、p99が2 ms、最大3 ms。1 ms刻みの計時で予算2.67 msを超えた量子を1件観測し、量子の欠落は0だった。物理MIDI機器と許可画面は未計測。[初回](../runs/worklet-midi-songbird-chirps-20261121-a/manifest.json)・[正式の実行と設定](../runs/worklet-midi-songbird-chirps-20261121-final/manifest.json)・[固定時刻の回帰](../runs/worklet-midi-songbird-chirps-20261121-fixed-regression/summary.json)・[Trillの回帰](../runs/worklet-midi-songbird-chirps-20261121-trill-regression/summary.json)

4本のCSVは全フレームで判定した後、調査用の列を残して合計160.0 MBから128.3 MBに減らした。各105,600行は全件保持し、RTL9210B-CG上の実体と正式実行の21成果物のSHA-256を照合した。[保存先と元CSVのハッシュ](../runs/worklet-midi-songbird-chirps-20261121-final/manifest.json)

後続の比較で、押鍵6内部サンプル後の最初の差を放射流量の時間差分に絞った。流量は同一で、刻みによる除算とレートによる乗算の丸めが末尾1ビットに現れた。音高追従を0にすると、初期の腔の圧力と放射は両版ともゼロだった。[押鍵直後の元出力と対照](songbird-chirps-onset-radiation.md)
