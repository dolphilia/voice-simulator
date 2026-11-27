# 実時間AudioWorkletでの buzz から trill への切り替え

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`AudioEngine` の `setCreatureParams`、`playCall`、`stopCall` から、Workletの `cparams`、`call`、`stopCall` を経てWASMと `Engine` に届く。上流のゴールデン試験は操作時刻でレンダーを分け、旧コールと新コールを同じ `CreatureVoice` に通してPCMとテレメトリを照合する。128・1・77・4,096フレームの分割を比較し、実時間試験ではキー再生中のパラメータ操作と停止による追加割り当てを測る。[操作の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L291)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L518)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L145)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L16)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`CallDef::resolve` は各コールが所有するパラメータ名をキー列から集める。`CreatureVoice::set_params` は手動値を `performer` に保存し、現在のコールが所有しない値だけを `target` に反映する。`play_call` は先に `end_call` を呼び、旧コールの所有目標を手動値へ戻して旧コールの呼気目標を消し、新コールと開始時計を設定する。この間も手動呼気、平滑値、鳴管・気道の状態、出力段の履歴が続く。次の制御境界で新しいキーを評価し、無次元の張力・純度、半音単位の左右の音程差、kPaの気嚢圧目標を `target + (previous−target) × exp(−Δt/τ)` で平滑化する。音高はHzの正値を対数補間し、呼気は手動とコールの大きい方へ平滑化する。出力48 kHzで `Δt=64/48000` 秒。張力・純度・音程差の時定数は20 ms、気嚢圧は10 ms、音高は8 ms、呼気の減衰は12 ms。[所有する項目の解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L179)・[手動値とコールの切り替え](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[再実装の入力と平滑化](../crates/vocal-core/src/songbird_voice.rs#L90)

## 実装前の予測と判定

`switch` の57,600フレームを使用する。73で `buzz` を開始し、3,601で張力0.65、純度0.7、音程差−4半音、気嚢圧1.05 kPaを含む手動値と呼気0.2を送る。気嚢圧の目標は3,601、平滑値は3,648から変わる。張力・純度・音程差の目標は `buzz` の0.15・0.1・0.5半音を維持すると予測した。9,601で `trill` に切り替えると識別子が4から2へ変わり、旧コールの目標が手動値へ戻って呼気は手動目標0.2になる。9,663までは平滑値が同じで、9,664で新コールの音高目標2,475 Hzと平滑値を観測する。31,213の停止後は31,232で平滑呼気の減衰が始まる。64フレームごとの制御直後に加え、操作直前、直後、次回制御直前の観測点を登録した。[新規登録](../cases/worklet-songbird-switch.json)・[入力ケース](../cases/songbird-calls.json)・[CLIでの切り替え](songbird-calls.md)

切り替えだけを省いた対照もCLIで出力する。ブラウザの加工前PCMは元のケースを実行したCLIにビット一致することを要求する。対照との比較では、9,664より前の全PCMがビット一致し、それ以降128フレーム以内に絶対差が `1e-6` を超えると予測した。目標と平滑値に加えて気嚢圧、ポート面積・流量、放射、間引き、DC除去の最初の差を調べる。実時間評価は起動後8量子を除く128フレーム量子のp95を約2.67 msの予算と比較する。[固定上流とCLIの基準](../runs/songbird-switch-before-worklet-1/summary.json)

## 実装と実測

画面の「鳴禽のコール」に `buzz → trill` を追加した。ケースの手動設定、コール開始・切り替え・停止を、既存のWASMへ入力する。Workletは描画量子の途中でも、指定された出力フレームの手前でレンダーを分ける。対照では9,601の切り替え指示だけを省き、手動設定と31,213の停止を同じCLIへ渡した。WASMの割り当て試験にも旧コール再生中の手動設定と、同じハンドルでの切り替えを加えた。[画面のプリセット](../../../../web/prototypes/chimera-research/src/main.tsx)・[WASMホスト](../crates/vocal-wasm/host/songbird.ts#L97)・[比較器](../tools/measure_worklet_songbird_switch.py)

| 観測値 | 切り替え直前の目標 | 9,601で復帰した目標 | 9,664の平滑値 |
| --- | ---: | ---: | ---: |
| 張力 | 0.15 | 0.65 | 0.182258 |
| 純度 | 0.10 | 0.70 | 0.138728 |
| 左右の音程差（半音） | 0.50 | −4.00 | 0.210077 |

手動設定の3,601では、コールが所有しない気嚢圧目標が1.05 kPaへ更新された。次の制御3,648で平滑値は0.9から0.918724 kPaへ移った。9,601では旧コールの識別子4が新コールの2へ変わり、呼気目標は0.393333から手動値0.2へ、音高目標は1,200 Hzから手動値3,100 Hzへ戻った。平滑値は9,663までそのまま続き、9,664で新コールが音高目標2,475 Hzを設定した。平滑音高は1,341.055 Hzに、平滑呼気は0.566845から0.528268に変わった。31,213の停止では識別子と呼気目標が0、次の31,232では平滑呼気が0.903297から0.808306に下がった。各更新は独立した一次平滑化の計算と登録した許容差内で一致した。[操作前後の観測](../runs/worklet-songbird-switch-20261120-a/summary.json)

## 波形と合成段の比較

48 kHzで全57,600フレームの加工前PCMがCLI・固定上流とビット一致した。913観測点では、CLIとの29列と固定上流との24列も最大差0。切り替えを省いた対照と比べると、9,601で識別子と呼気目標が分かれ、9,664で平滑呼気、音高、気嚢圧、左右のポート面積・流量が分かれた。放射の最初の差は内部サンプル38,661で、間引き・DC除去後の差は9,665から。PCMは9,672に初めてビット差が出て、9,676に絶対差 `1e-6` を超えた。制御境界から12フレーム後で、PCM差の最大絶対値は0.49958だった。[切り替えを省いた再実行ケース](../runs/worklet-songbird-switch-20261120-a/artifacts/held-buzz.json)・[対照WAV](../runs/worklet-songbird-switch-20261120-a/artifacts/held-buzz.wav)・[差が現れた合成段](../runs/worklet-songbird-switch-20261120-a/summary.json)

切り替えの63フレーム後に新しい目標が平滑値へ効き、判定閾値を超える波形差は指示から75フレーム後に出た。今回の差は旧コールと新コールの目標の組み合わせを含む。同じ指示を制御境界の直前・境界上・直後に置くと、伝搬や間引き後の遅れと制御待ちの長さを比較できる。[切り替えと対照の実測](../runs/worklet-songbird-switch-20261120-a/summary.json)

Chromiumヘッドレスシェル156.0.8078.4で、研究ディレクトリと `/tmp` からの両回とも22項目が通過した。WASM、CLIとブラウザのWAV・再実行ケース、対照の入出力など計8ファイルのSHA-256と913観測点が一致した。起動後8量子を除いた442量子では、128フレームの描画間隔が続き、処理時間のp95・p99は両回1 msだった。計時分解能は1 msで、再実行の1量子が約2.67 msの予算を超えた。ネイティブ試験の追加割り当ては0。`chirps` と `buzz` も以前のブラウザWAVと観測値に一致した。[別ディレクトリからの再実行](../runs/worklet-songbird-switch-20261120-repeat/manifest.json)・[処理時間と結果](../runs/worklet-songbird-switch-20261120-repeat/summary.json)・[chirps回帰](../runs/worklet-songbird-chirps-switch-regression-20261120/summary.json)・[buzz回帰](../runs/worklet-songbird-buzz-switch-regression-20261120/summary.json)
