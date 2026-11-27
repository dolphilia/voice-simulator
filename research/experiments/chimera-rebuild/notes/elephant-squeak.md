# アフリカゾウの `squeak`

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の公式CLIは、単一の `CreatureVoice` でゾウの持続音、停止、`rumble`、`trumpet` を順に描画し、出力333,600で `squeak` の再生を要求する。最後のキー0.5秒に0.5秒を加えた48,000フレームで終了する。`elephant-call-squeak` は48 kHzの32,160フレーム、`elephant-96k` は96 kHzの38,400フレームでPCMとテレメトリを照合する。`elephant-stop` は `squeak` を `trumpet` に置き換える上流の固定試験である。[CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[squeakの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L158)・[固定試験の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)

`elephant::def` の `squeak` は弁音高を0〜0.45秒で820から880 Hzへ上げて保持する。呼気圧は0〜0.5秒で20から16 cmH₂Oへ下がり、モードは同時に1から0へ下がる。ゲートは0から0.04秒の1まで上がり、0.5秒で0へ下がる。`CreatureVoice::eval_call` は同じパラメータを含む前後のキーから `x₀+(x₁−x₀)(t−t₀)/(t₁−t₀)` を計算し、最後の値を保持する。ゲートは振幅倍率を受ける。弁音高は定義上の基準850 Hzを持つコールの中にあり、パラメータ自体はキーの値820〜880 Hzで駆動される。[キーごとの補間と倍率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[音高の役割とキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L129)

コールが所有するパラメータはモード・弁音高・呼気圧。`trumpet` が所有する粗さは置き換え時に演奏値へ戻る。終了条件は `制御時計−開始時計 > 0.55 秒`。64出力フレームごとに、目標を更新した後で弁音高を対数空間、モード・呼気圧を線形の一次遅れに通す。音響サンプルごとに声門の開口を更新し、平滑モードが0.02を超えると差圧とモードの積で弁を駆動する。実断面は自由開口と `4.5(1−m)` の大きい方になる。閾値以下では変位と速度を保持し、実断面を4.5 cm²に戻す。声門と弁の開口を反映して気道と放射を進める。[演奏値の復帰](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L260)・[制御の平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[入口弁と放射の観測](elephant-valve.md)

## 事前登録

48 kHzの公式全区間、44.1 kHzの置き換えと途中停止、96 kHzの自然終了と初期モードの対照を比べる。公式条件では開始要求333,600と初回制御333,632、所有終了360,064を区別する。96 kHzでは開始要求31、初回制御64、自然終了52,928を予測した。初期モード0と1は同じ96 kHzの入力を受け、最初の制御での実断面と、呼気の立ち上がり前後の出力を比較する。[登録ケース](../cases/elephant-squeak.json)

## 実装と実測

既存のゾウのコール再生に `squeak` の区間を加えた。目標は独立した線形補間、平滑値は別に計算した一次遅れに照合した。4条件における弁音高の独立計算との差は、目標が最大 `5.68×10⁻¹³ Hz`、平滑値が `3.52×10⁻¹² Hz`。肺圧の最大差は `2.36×10⁻¹¹ dyn/cm²` だった。弁の駆動差圧・変位・速度、声門、実断面、放射、PCMも比較した。[コールの実装](../crates/vocal-core/src/airway/elephant/call.rs)・[検証手順](../tools/measure_elephant_squeak.py)・[全条件の判定](../runs/elephant-squeak-20261120-a/summary.json)

| 条件 | 開始要求・初回制御・所有終了の出力フレーム | 上流との最大PCM差 |
| --- | --- | ---: |
| 48 kHz、公式デモ全体 | 333,600・333,632・360,064 | `3.73×10⁻⁹` |
| 44.1 kHz、置き換えと途中停止 | 19,917・19,968・35,011 | `3.73×10⁻⁹` |
| 96 kHz、自然終了 | 31・64・52,928 | `9.31×10⁻¹⁰` |
| 96 kHz、初期モード1 | 31・64・計測中は所有を継続 | `4.66×10⁻¹⁰` |

公式デモでは333,600の開始要求から32フレーム後の333,632で目標820 Hzが入り、平滑弁音高は487.18 Hzだった。0.04秒後の335,552でゲート目標は約1、平滑値は0.72648。355,264で弁音高の目標は880 Hz、平滑値は877.50 Hzだった。所有終了の360,064で弁音高の目標が手動値470 Hzに戻った時点でも、平滑ゲートは0.05540残った。開始から0.62〜0.84秒の窓ではPCMのRMSは `1.73×10⁻⁴` だった。[境界と観測窓](../runs/elephant-squeak-20261120-a/summary.json)

44.1 kHzでは19,917で `trumpet` を置き換えると粗さの目標が0.20711から保存済みの0.68へ戻った。`squeak` 中の25,123では粗さ0.25・声門音高25 Hz・経路0.7が目標に入り、弁音高・呼気圧・モードはコールが保持した。35,011の停止要求で保持していた目標が640 Hz・23 cmH₂O・0.45へ戻り、平滑値は次の制御35,072で動いた。[置き換えと停止](../runs/elephant-squeak-20261120-a/summary.json)

公式条件では弁を駆動した25,600フレームすべてで面積下限が自由開口を上回った。最小差は0.75321 cm²だった。96 kHzで初期モードだけを0から1へ変えると、最初の制御の実断面は4.40110から0.00936 cm²になり、開始後0〜0.04秒に自由開口が実断面を決めたフレーム数は0から754へ増えた。0.04〜0.20秒のPCM間の最大絶対差は0.18109だった。初期モードは弁の面積下限、声門の開大・振幅・乱流係数の立ち上がりに共通して効く。[初期モードの対照](../runs/elephant-squeak-20261120-a/summary.json)

## 残る差と再現

公式CLIの381,600フレームすべてを比較し、単精度値の差は112フレーム、最大 `3.73×10⁻⁹`。末尾の `squeak` 区間48,000フレームでは差は18フレーム、最大 `9.31×10⁻¹⁰` だった。全体の最初の内部差は持続音の出力1の肺流量に現れた。末尾区間のCSVを333,600で切り出すと、肺流量、鼻の基部圧、放射は区間の始点ですでに異なり、弁の駆動差圧で333,632、自由開口で333,633、PCMで337,890に差が現れた。この区間の呼気ゲート、弁音高、モード、実断面は上流と一致した。固定上流のプローブは全381,600フレームで公式CLIのWAVとビット一致した。[公式区間の判定](../runs/elephant-squeak-20261120-a/summary.json)・[コマンド・環境・SHA-256](../runs/elephant-squeak-20261120-a/manifest.json)

研究ディレクトリと `/tmp` で各361項目を通過し、要約とWAV・CSV・JSONの計測ファイル34件が一致した。`trumpet` の変更前後でも各359項目を通過し、要約と計測ファイル34件が一致した。[再実行](../runs/elephant-squeak-20261120-repeat/manifest.json)・[trumpetの回帰](../runs/elephant-trumpet-squeak-regression-20261120/manifest.json)
