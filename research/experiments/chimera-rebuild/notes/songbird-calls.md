# 鳴禽の周期コールとコール切り替え

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。今回の機構は規則から作った鳴禽のキー列を、既存の `flute` と同じ制御更新・放射経路で再生する処理。[先行のキー補間](songbird-flute.md)・[事前登録](../cases/songbird-calls.json)

## キー生成と境界の読み方

上流の `render creature songbird` は持続・停止後に `flute`、`trill`、`chirps`、`buzz` を順に再生する。各コールの割り当て時間は末尾キー時刻に0.5秒を足した長さで、波形と発振器の状態はコール間で連続する。CLIの実際の出力と、`CreatureVoice::play_call_id` を直接呼んだ単独・途中切り替えを照合する。[CLIでの実行](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L793)・[コールの登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L190)

`trill` は1秒16周期、計18回。周期 `P=1/16` 秒の各開始時刻 `s` で呼気を0、音高を `3000×(1−0.35/2)` Hzへ切り替える。呼気は `s+0.08P` で1、`s+0.62P` まで維持、`s+0.75P` で0。音高は `s+0.62P` の `3000×(1+0.35/2)` Hzまで指数補間される。`chirps` は9回、開始時刻 `s=i(0.14−0.008i)` 秒。呼気の時刻は `s`、`s+0.01`、`s+0.06`、`s+0.07` 秒。音高は `7000−300i` Hzから `2400−80i` Hzへ指数補間する。`buzz` は8回、0.07秒ごとに呼気が0.02秒で1、0.06秒で0.35へ動き、全体の0.6秒で0。音高1,200 Hzのほか、駆動、張力、純度、右の音程差、左右混合比にも固定の指示を持つ。[生成式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L122)

`CallDef::resolve` はキーの宣言順を保つ。`eval_call` がパラメータ別に最初の未来キーで探索を止めるため、`chirps` の後半で区間が重なると、時刻順に整列したキー列と異なる値を読む。経過0.610秒直後では、先に宣言された `i=6` の呼気1の水平区間を読み、後から宣言された `i=8` の開始キーより先に評価が止まる。出力はコールの制御時計を基準にし、上流と同じ64出力フレーム周期で平滑化される。[キー解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L178)・[制御での探索](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

切り替えで `play_call` は先に旧コールを終え、旧コールが設定していた目標を最新の演奏値へ戻す。新コールの最初の評価は次の制御境界。呼気の平滑値、鳴管、気道、出力段の履歴を保つ。`buzz` が設定した張力・純度・音程差は `trill` のキーに現れないので、切り替えフレームで演奏値の目標を取り戻すと予測した。上流の波形試験には3種の単独、移調、別コールへの切り替えがあり、リアルタイム試験は再生や停止を含むレンダー中の割り当てを確認する。[切り替えの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[上流の波形検査](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 実装と実測

4コールはパラメータ付きのキー列を共有する。規則から生成する3列はRustの定数として組み立て、宣言順のまま評価した。コールの開始とレンダーにキー列の確保はない。計測器は固定上流が出力する4列の定義を読み、パラメータ別に補間し直す。CSVの `call_id` は、再生中のコールなし、`flute`、`trill`、`chirps`、`buzz` を順に0〜4で記録する。[キー列と評価](../crates/vocal-core/src/songbird_voice/call.rs)・[ライセンス](../LICENSE-CHIMERA)・[独立計算](../tools/measure_songbird_calls.py)

`trill` は48 kHzで0.5を上向きに超える呼気目標を18回観測した。周期は3,000出力フレーム相当で、観測した立ち上がり間隔は64フレームの制御格子上の2,944または3,008フレーム。最初の音高目標は2,475 Hzだった。`chirps` の44.1 kHzの条件では、経過0.610975秒に呼気目標1.0000、音高目標1,952.96 Hz。キーだけを時刻順に整列した独立計算では、同じ制御時刻で呼気目標0.7438、音高目標2,401.77 Hzになった。[周期・重なりの観測](../runs/songbird-calls-20261120-a/summary.json)

`buzz` の96 kHz条件は呼気倍率0.8、計測閾値0.6で、8つの立ち上がりを観測した。最初の間隔は6,080フレーム、続く6間隔は6,720フレーム。初回はすべての間隔を6,720フレームと仮定したため、周期の判定が不合格になった。閾値を呼気倍率で割ると0.75。線形補間から1回目の通過は0.015秒、2回目は `0.06+0.03×(0.75−0.35)/(1−0.35)` 秒になる。間隔の予測値は6,092.31フレームで、実測差12.31フレームは既定の64フレーム以内。第2版はこの立ち上がりの条件を追加し、音声、閾値、許容差を引き継いだ。[初回の判定](../runs/songbird-calls-20261120-a/summary.json)・[第2版の条件](../cases/songbird-calls-v2.json)

`buzz` から `trill` へ切り替えたフレーム9,601で、張力の目標は0.15から手動の0.65、純度は0.1から0.7、右の音程差は0.5から−4半音へ戻った。張力の平滑値は切り替え前の0.150012を保ち、最初の制御フレーム9,664で0.182258となった。同フレームで新しいコールの音高目標2,475 Hzを適用した。[切り替えの目標値と平滑値](../runs/songbird-calls-20261120-a/summary.json)

固定上流のCLIと、持続音の開始から4コールの末尾までの344,994フレームがビット一致した。全5条件の633,504フレームでは、`buzz` の96 kHz条件の減衰後に1フレームだけ `5.56×10⁻²²` のPCM差があった。目標、開口、呼気などを照合すると、この条件の差はまず内部放射のサンプル391で観測され、間引き・DC除去のフレーム195にも微小差が出た。PCMで差が残ったのはフレーム81,552で、値は両者とも約 `1.61×10⁻¹⁶`。許容差内で、全条件の内部放射の最大絶対差は `2.73×10⁻⁸ cm³/s²` だった。[固定上流との系列比較](../runs/songbird-calls-20261120-repeat/summary.json)

第2版は研究ディレクトリと `/tmp` で各452項目を通過した。WAV、CSV、キー定義、個別ケースと設定JSONの37ファイルは初回、改訂後、再実行で同一のハッシュになった。上流の動物音声・実時間試験は7件、既存の `flute` の回帰は346項目を通過した。[初回](../runs/songbird-calls-20261120-a/manifest.json)・[第2版](../runs/songbird-calls-20261120-b/manifest.json)・[再実行の条件とハッシュ](../runs/songbird-calls-20261120-repeat/manifest.json)・[fluteの回帰](../runs/songbird-calls-flute-regression-20261120/summary.json)

## くちばし入口まで揃えた実験版を全コールで比較する

固定上流の `render::creature` は `CreatureVoice::play_call_id` で鳴き声を開始し、`CreatureVoice::render` にPCMバッファを渡す。計測用の上流プローブもPCMは同じ公開レンダーから取得し、内部放射は同じ制御値を受ける観測用の気道で採取する。44.1 kHzの鳴禽は内部176.4 kHzで進み、64出力フレームごとに通過したキーを評価して音高・開口・呼気などを更新する。内部1サンプルごとに鳴管弁を更新して気道を解き、前回との放射流量の差へ内部レートを掛ける。放射後退差分の単位はcm³/s²。[上流の通常描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[コールの制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L337)・[観測用プローブ](../tools/upstream_songbird_voice_probe.rs#L159)

97タップのKaiser窓付きFIRが直近の内部標本を保持し、4点ごとに出力する。間引き値にレベルと鳴禽ゲイン `4.8×10⁻⁷` を掛けた値を `x[n]` とすると、DC除去は `y[n] = x[n] − x[n−1] + exp(−2π·12/fs)·y[n−1]`。前回の入力とフィルタ状態を保存し、出力の絶対値が0.7を超えると滑らかに制限してから正規化された `f32` PCMにする。固定上流の音響試験はTypeScriptの全描画・包絡・テレメトリを、実時間試験は描画中の割り当てを照合する。研究版の通常入口 `render-pcm` は `SongbirdVoice::render` に進み、4つの内部放射標本と各出力段を同じCSV行に記録する。[間引き実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L50)・[DC除去と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[全描画の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[研究版の描画](../crates/vocal-core/src/songbird_voice.rs#L215)

実装前に保存済みの `chirps-44100` を照合した。最初の制御変更は出力256フレーム目、呼気は320フレーム目から。標準版は内部放射の1033点目で固定上流と初めて分かれ、PCMは全48,510点で一致している。前回の短区間には別の音高入力を使ったため、既存のコール入力をそのまま使い、1033点目の差が後へ移るか、全PCMがビット一致するかを観測する。既存の呼気・放射・PCMの許容差と、追従のみ・呼気を含む発声・コール終了後の測定窓を事前登録した。[事前登録](../cases/songbird-chirps-full-pcm-44100.json)・[標準版と上流の全コール](../runs/songbird-calls-20261120-repeat/manifest.json)

通常の `render-pcm` で標準版の既存CSVとWAVをバイト再現し、30差分を適用した実験バイナリは短区間の検証時と同じSHA-256になった。標準版・実験版・上流でコールの開始211フレーム、最初の呼気320フレーム、コール終了32,384フレームは一致した。標準版と実験版では、制御値、鳴管開口、気嚢圧も全点でビット一致した。44.1 kHzの全48,510フレームと内部194,040点の比較は、登録した全許容差に収まった。[再実行の要約](../runs/songbird-chirps-full-pcm-44100-20261123-repeat/summary.json)

| 上流との比較 | 標準版の初差 | 実験版の初差 | 実験版の最大絶対差 |
| --- | ---: | ---: | ---: |
| 放射後退差分（内部サンプル） | 1033 | 1089 | 1.129×10⁻⁸ cm³/s² |
| 間引き後（出力フレーム） | 258 | 275 | 3.725×10⁻⁹ cm³/s² |
| DC除去後（出力フレーム） | 258 | 275 | 1.776×10⁻¹⁵ |
| 最終PCM（出力フレーム） | 全48,510点一致 | 全48,510点一致 | 0 |

実験版は、コール最初の制御更新後、最初の65内部サンプルで放射が上流と一致した。初差はまだ気嚢圧0の区間で、観測できる最初の差は内部放射だった。実験版の呼気前の放射差は206点から153点に減った。全区間では173,147点から167,774点に減り、放射の最大絶対差は約1.129×10⁻⁸ cm³/s²で両版共通だった。全版のPCMピークは0.601834で、0.7からのリミッタは働かなかった。保存放射からSciPyのFIRとDC除去を計算しても全版のPCMはビット一致し、別の標準ライブラリ実装でWAVのデータ領域とCSVを直接照合した。30差分は倍精度の気道内部を追う比較用として保持する。[窓別の差と独立FIR](../runs/songbird-chirps-full-pcm-44100-20261123-repeat/summary.json)・[RIFFとDC差分の照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-chirps-full-pcm-44100-20261123-verification.json)

初回は77フレーム分割で `--no-trace` を指定し、鳴禽の通常入口が計測CSVを要求して停止した。取得済みの128フレーム版CSVとWAVは成功版とバイト一致した。再実行では77フレーム分割のCSVを作業用ディスクに一時出力し、128フレーム版とサイズ・SHA-256が一致することを確認した。各実行で重複する時系列2本、約37.0 MB分の永続保存を省いた。WAVもブロック分割で一致した。[初回の停止記録](../runs/songbird-chirps-full-pcm-44100-20261123/manifest.json)・[成功時の全コマンド](../runs/songbird-chirps-full-pcm-44100-20261123-b/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で、研究ワークスペースと `/tmp` の各63判定に合格した。固定上流の音響・割り当ての7試験に合格した。初回の停止を含む531入力と24出力をハッシュ照合し、成功2実行の9出力がバイト一致した。採取物計94,348,294バイトをRTL9210B-CGに保存した。[再実行の保存記録](../runs/songbird-chirps-full-pcm-44100-20261123-repeat/manifest.json)・[独立照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-chirps-full-pcm-44100-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 \
  ../../.venv/bin/python tools/measure_songbird_chirps_full_pcm_44100.py \
  songbird-chirps-full-pcm-44100-local
```
