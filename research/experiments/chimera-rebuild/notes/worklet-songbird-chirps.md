# 実時間AudioWorkletでの鳴禽コール chirps のキー順

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`AudioEngine.playCall` がコールIDを送信し、Workletの `call` が種のコール一覧からインデックスを解決する。`engine_play_call` と `Engine::play_call` を経て、`CreatureVoice::play_call` がID、開始時の制御時計（秒）、音高倍率、呼気倍率を設定する。上流のゴールデン試験は全種のコール、移調、切り替え、テレメトリをTypeScript版と比べ、1・77・128・4,096フレームでブロックを分けたPCMも調べる。実時間試験ではコール開始・停止とレンダー・観測に割り当てがないことを確認する。[操作の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L296)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L152)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`songbird::def` は0から8までを添字 `i` とし、開始秒 `s = i(0.14 − 0.008i)` から4個ずつキーを足す。時刻 `s`、`s+0.01`、`s+0.06`、`s+0.07` 秒の呼気目標は0・1・1・0。音高は `s` で `7000−300i` Hzに切り替え、`s+0.06` までに `2400−80i` Hzへ指数補間する。`CallDef::resolve` は宣言順を保ち、`eval_call` はパラメータごとに、その値を含む最初の未来キーで探索を止める。後続キーの曲線がステップなら前値を保つ。正値の指数補間は `x0 × (x1/x0)^u`、線形補間は `x0 + (x1−x0)u` で、`u` は二つのキー間の経過割合。制御更新ではキーの目標を評価した後に呼気と音高を平滑化し、気嚢圧・鳴管・伝搬・放射・間引きを経てPCMを出す。今回の出力44.1 kHzでは内部176.4 kHz、制御は64出力フレームごと。[キー生成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L139)・[解決時の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L179)・[評価と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[実装の探索](../crates/vocal-core/src/songbird_voice/call.rs#L182)

## 実装前の予測と判定

44.1 kHz・48,510フレームの `chirps-44100` を用いる。211で識別子が変わり、256で最初のキーが反映され、32,384で自然終了する。0から64フレームごとの制御更新直後、開始指示の直前・直後と最初のキー直前の210・211・255、末尾を観測する。宣言順と時刻順で組んだ独立計算は、呼気目標が22,016、音高目標が22,336で最初に分かれると予測した。初期の呼気差は、先に宣言された `i=4` の終了キー0.502秒を読む条件と、先に現れる `i=5` のステップ開始0.500秒を読む条件との差。経過0.610–0.616秒の最初の制御では、宣言順で `i=6` の呼気1の区間、時刻順で `i=8` の開始から補間した呼気約0.744を予測した。音高目標の差は少なくとも300 Hzとする。[事前登録](../cases/worklet-songbird-chirps.json)・[CLIでのキー順の実測](songbird-calls.md)

加工前PCMのCLI比較はビット一致で判定する。順序の影響を波形まで追うため、宣言順と時刻順の独立計算で得た呼気・全パラメータの目標を、各制御境界で手動イベントにして同じCLIへ入力する。宣言順の手動対照とブラウザのPCMを許容差 `1e-6` で照合する。二つの手動対照のPCM差は同じ閾値を使い、最初の呼気目標の差から128フレーム以内の発生と、絶対差の最大が0.01以上になることを判定する。コール本体の処理時間は起動後8量子を除くp95を約2.90 msの予算と比較する。[固定上流とCLIの基準](../runs/songbird-chirps-before-worklet-1/summary.json)

## 実装と結果

「鳴禽のコール」に `chirps` のケースを追加した。登録したイベントを既存のWorklet経由でRustの `SongbirdVoice` へ送り、書き出したケースをCLIで再実行する。順序の対照では、固定上流から出力したキーの宣言順を保つ独立計算と、同じキーを安定ソートして時刻順にする独立計算を使う。両方の制御目標を64フレームごとの手動イベントに変換し、同一条件のCLIから加工前PCMと気嚢圧・開口・放射を出力する。ブラウザ本体で使うコールのキー列は上流と同じ宣言順を維持した。[ブラウザのケース選択](../../../../web/prototypes/chimera-research/src/main.tsx)・[比較器](../tools/measure_worklet_songbird_chirps.py)

44.1 kHzで全48,510 PCMフレームがCLIと固定上流にビット一致した。762観測点でCLIと共通の29列、上流と共通の24列の最大差は0。コールの識別子は211で3、32,384で0になり、最初の音高目標7,000 Hzは256で評価された。比較は21項目すべて通過し、ネイティブで `chirps` の開始から末尾までの描画中に追加の割り当ては0件だった。[最初の実行](../runs/worklet-songbird-chirps-20261120-a/summary.json)

| 観測値 | 出力フレーム | 宣言順 | 時刻順 |
| --- | ---: | ---: | ---: |
| 呼気目標が最初に分かれる点 | 22,016 | 0.857596 | 1.000000 |
| 音高目標が最初に分かれる点 | 22,336 | 5,437.28 Hz | 5,500.00 Hz |
| 経過0.610975秒の呼気目標 | 27,200 | 1.000000 | 0.743764 |
| 経過0.610975秒の音高目標 | 27,200 | 1,952.96 Hz | 2,401.77 Hz |

二つの手動対照のPCMは22,023で最初のビット差が生じ、22,028で差が `1e-6` を超えた。呼気目標の差から12フレーム後（約0.272 ms）で、PCM差の最大絶対値は0.9013。宣言順の手動対照とブラウザのPCMの最大差は `1.86e-9` だった。この小差に先立ち、256フレームで独立計算側の音高目標が7,000 Hzより約 `9.1e-13` Hz小さくなった。指数補間の始点で、独立計算が `exp(log(x0))`、合成器が `x0 × pow(x1/x0, 0)` と評価する差がある。[宣言順の手動対照](../runs/worklet-songbird-chirps-20261120-a/artifacts/declared-targets.wav)・[時刻順の手動対照](../runs/worklet-songbird-chirps-20261120-a/artifacts/chronological-targets.wav)・[目標とPCMの比較](../runs/worklet-songbird-chirps-20261120-a/summary.json)

手動対照の全パラメータは22,336の直前まで共通で、先行する入力差は22,016からの呼気にあった。そのフレームで平滑呼気と気嚢圧に差が現れ、放射は内部サンプル88,089、間引き・DC除去は出力フレーム22,022が最初だった。左右の開口と平滑音高は22,336で変わった。キー順による波形差を、呼気から気道・放射へ伝わる初期の変化と、後から重なる音高・開口の変化として追える。[合成段ごとの最初の差](../runs/worklet-songbird-chirps-20261120-stages/summary.json)

研究ディレクトリと `/tmp` で行った3回は21項目すべて通過し、WASM、ブラウザとCLIのWAV、再実行ケース、手動対照の入出力など計11ファイルのSHA-256と762観測点の値が揃った。Chromium 156.0.8078.4の量子は128フレーム間隔。起動後の8量子を除くp95・p99は各回1 msだった。計時は1 ms刻みの `Date.now` で、合成段を測った回は1量子が予算を超えた。`flute` と `trill` の再計測でも、以前のWAVと観測値が一致した。[別ディレクトリからの実行](../runs/worklet-songbird-chirps-20261120-repeat/manifest.json)・[最終記録](../runs/worklet-songbird-chirps-20261120-stages/manifest.json)・[flute回帰](../runs/worklet-songbird-flute-chirps-regression-20261120/summary.json)・[trill回帰](../runs/worklet-songbird-trill-chirps-regression-20261120/summary.json)
