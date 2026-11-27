# 鳴禽の代表コール flute

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。持続音と停止の出力段を使い、`flute` のパラメータ自動化を再現する。[持続音の照合](songbird-sustain-pcm.md)・[事前登録](../cases/songbird-flute.json)

## キーと制御の順序

上流CLIの `render creature songbird` は持続・停止の1.6秒を作った後、`flute` から順にコールを再生する。`flute` のキーは0〜1.2秒で、呼気ゲートと音高（Hz）、右の音程差（半音）、左右の混合比、駆動を指定する。基準音高は2,600 Hz。コール開始で実行中のコールを終え、現在の制御時計を開始時刻に保存する。上流の時計は各64出力フレームの制御を評価した後に1周期進むので、制御境界の途中から開始しても次の評価に渡る経過時間は0秒になる。[CLIの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L793)・[キーの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L175)・[開始と時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

`CallDef::resolve` はキーからパラメータ別の識別子と、コールが操作するパラメータ集合を作る。`eval_call` はそのパラメータが現れる前後のキーだけを探し、後続キーがステップなら手前の値を保持する。後続キーが指数補間で両端が正なら、`x=x₀(x₁/x₀)^u`。それ以外は `x=x₀+(x₁−x₀)u`。ここで `u=(t−t₀)/(t₁−t₀)`。呼気と音高は補間後に倍率を掛ける。呼気倍率はコールの amplitude、音高倍率は指定音高を2,600 Hzで割った値。音程差は半音のまま評価する。呼気の目標には手動の値とコールの値の大きい方を使い、その後で持続音と同じ平滑化を適用する。[キーの解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L178)・[補間と呼気の競合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

手動の演奏値はコールの目標から独立して保持する。コールが操作する値を手動で変えると、保存中の演奏値だけが変わる。手動停止または最後のキーの0.05秒後を超えた最初の制御評価で、目標を保存中の演奏値へ戻し、コール側のゲートを0にする。手動停止の時刻が制御境界の途中なら、平滑値の変化は次の制御更新から。上流の比較試験はTypeScript由来の `songbird-call-flute`、移調・停止と複数ブロック長を検査し、リアルタイム試験は開始・停止・テレメトリ中の割り当てを調べる。[目標の復帰](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)・[波形とテレメトリの比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[割り当ての検査](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 事前の予測

48 kHzのフレーム73から始めると、最初のコール目標は128で2,000 Hzになり、自然終了は60,160。3,380 Hzを指定した条件では音高のキーだけが1.3倍され、最初の音高目標は2,600 Hz。停止条件ではフレーム5,371で変更した手動音高3,000 Hzが、停止フレーム17,291の目標として現れる。平滑化された音高は17,344で復帰を始め、手動ゲート0.35は引き続き効く。3段階の制御値と放射、PCMを照合し、実際のCLIの最初のコールを含む先頭3.3秒も比較する。[登録条件と許容差](../cases/songbird-flute.json)

## 実装と実測

既存の `SongbirdVoice` に演奏値、コールによる目標、制御時計を保持する機能を加えた。キーはパラメータ別の固定配列で保持し、先行・後続キーを制御境界で参照する。固定上流由来のキーの出典とライセンスは実装に記載した。CLIは絶対フレームで操作を適用し、コールの有効状態、目標値、平滑値、放射、PCMを出す。上流プローブは公開インターフェースから目標とPCMを取得し、実行時に出力した上流のキー定義をPythonの独立補間にも使った。初回は計測器の集計でNumPyの真偽値をJSONへ変換できず中断した。判定条件とレンダーを保ち、集計を修正して再実行した。[キーと補間](../crates/vocal-core/src/songbird_voice/call.rs)・[ライセンス](../LICENSE-CHIMERA)・[初回の記録](../runs/songbird-flute-20261120-a/manifest.json)・[独立計算](../tools/measure_songbird_flute.py)

| 条件 | 開始指示 → 最初の制御（フレーム） | 初回の音高目標 (Hz) | 終了フレーム |
| --- | --- | ---: | ---: |
| 標準48 kHz | 73 → 128 | 2,000 | 60,160 |
| 移調・途中停止48 kHz | 73 → 128 | 2,600 | 17,291 |
| 移調96 kHz | 147 → 192 | 2,600 | 120,256 |
| 上流CLIの持続・停止直後 | 76,800 → 76,800 | 2,000 | 136,832 |

途中停止では、17,291で音高目標が3,342.21から3,000 Hzに変わった。実際の平滑値は次の制御まで3,346.56 Hzを保ち、17,344で3,290.87 Hzになった。呼気の手動目標0.35はそのまま有効だった。コールが割り当てていない空気嚢圧の目標は、演奏値の変更フレーム5,371で1.1 kPaになった。[途中停止の比較](../runs/songbird-flute-20261120-b/summary.json)

標準48 kHzでは、制御フレーム128で音高目標が2,000 Hzになった。呼気ゲートと空気嚢圧は191まで0。PCMは129から非ゼロで、呼気の開始前のピークは0.001008だった。音高に追従する口腔食道腔の断面補間による体積流量源が関与する可能性がある。確認には、その流量源だけを切り替えた対照が必要になる。[標準条件の観測CSV](../runs/songbird-flute-20261120-b/artifacts/offgrid-48000/pcm-128.csv)・[口腔食道腔の制御](songbird-airway.md#入力から気道まで)

4条件の408,960出力フレームが固定上流のPCMとビット一致した。上流CLIのWAV先頭3.3秒（持続・停止および最初のコール）も158,400フレームすべてが一致した。128フレームと77フレームに分けた出力は各条件でハッシュが等しかった。標準条件で上流との差を最初に観測したのは、内部放射のサンプル518と間引き後のフレーム129。全条件で内部放射の最大絶対差は `1.30×10⁻⁸ cm³/s²`、DC除去後は `2.75×10⁻¹⁵` だった。途中停止条件は末尾20 msのRMS比が `9.93×10⁻⁷` で、事前の上限 `10⁻⁶` を満たした。[PCMと内部系列の判定](../runs/songbird-flute-20261120-b/summary.json)

集計修正後は研究ディレクトリと `/tmp` からの実行で各346項目を通過し、WAV、CSV、設定、上流のキー定義を含む30ファイルがハッシュ一致した。固定上流の動物音声と実時間の試験は計7件、持続音の回帰は298項目を通過した。[再実行マニフェスト](../runs/songbird-flute-20261120-repeat/manifest.json)・[持続音の回帰](../runs/songbird-flute-sustain-regression-20261120/summary.json)
