# 鳴禽の持続音とPCM

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。左右の開口から気道の放射までの照合を踏まえ、演奏側の制御と放射からPCMまでを接続する。[気道の照合](songbird-airway.md)・[事前登録した条件と判定](../cases/songbird-sustain-pcm.json)

## 入口と制御

上流の `render creature songbird` は48 kHzの `CreatureVoice` を生成し、`voices` を0へ動かしてゲート1で1.2秒、続いてゲート0で0.4秒をレンダーする。続くコールとは別に、WAV先頭1.6秒を持続音の照合に使える。初期化時はパラメータの初期値から鳴禽の形状を直接そろえ、呼気と音響状態を0から開始する。[上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)

出力レートが60 kHz以下なら鳴禽の内部レートは4倍、60 kHz超では2倍。制御周期は内部レートで `64×倍率` サンプル、出力では64フレームで一定。演奏側の指示は次の制御更新で読む。区間時間を `Δt=64/fs_out` 秒として、呼気は `g ← g+(target−g)×(1−exp(−Δt/τ))` で更新する。上がる場合のτは0.004秒、下がる場合は0.012秒。ゲート指示の上限は1.5。空気嚢圧は `pressure_kpa×1000×g×10` dyn/cm²として同じ制御更新で適用する。各パラメータもそれぞれの時定数で平滑化し、音高とOEC容積は比率の指数補間、その他は値の差の補間を使う。気道の断面目標はその後に区間内で補間する。[操作](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[時定数と範囲](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L161)

## 放射から出力まで

くちばしからの放射流量の時間微分（cm³/s²）を、Kaiser窓のFIR（β=8.5、タップ数 `24×倍率+1`、遮断 `0.46/倍率`）に入れる。ホストのレンダーブロックが変わっても、内部分割の最後のサンプルだけから新しい出力フレームを取る。間引いた値を `4.8×10⁻⁷×level` 倍して無次元にし、前の入力と出力を用いて `h=x−x_prev+exp(−2π×12/fs_out)×h_prev` を計算する。次に絶対値が0.7を超えた試料を `sign(h)×(0.7+0.3×tanh((|h|−0.7)/0.3))` に写し、f32にする。静かな区間では上流が制御更新時に微小な履歴を0へそろえる。波形の分割独立性、固定上流のPCM、FIRとDC除去の各段を比較する。[PCM出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[間引き](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs)・[気道の微小状態](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)・[ブロックと波形の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 事前の予測

48 kHzと44.1 kHzの開始指示73はフレーム128、停止指示11567は11584で初めて呼気に反映する。96 kHzは倍率2を通り、開始指示147を192、停止指示23135を23168で読む。呼気が活性化するまでPCMは0で、最後の20 msは持続区間のRMSに対し `10⁻⁸` 以下になる。増幅と制御変更の条件では振幅制限の適用が少なくとも10フレームあると予測する。測定区間と許容差はケースに固定した。[条件と閾値](../cases/songbird-sustain-pcm.json)

## 実装と実測

`SongbirdVoice` は気道とFIRの履歴、現在値と目標値、次の制御までのフレーム数を保つ。既存の `SongbirdAirway` とKaiser FIR、WAV書き出しを再利用し、鳴禽向けにゲートと演奏パラメータの制御、DC除去、振幅制限を接続した。CSVの内部放射は時系列順に並ぶ。上流比較は公開の `CreatureVoice::render` からPCMを取得し、同じゲートと制御値を与えた別の上流の気道で内部放射を観測した。SciPyではその放射を独立したFIRとDC除去に通し、上流と候補の出力段をそれぞれ照合した。[候補のレンダー](../crates/vocal-core/src/songbird_voice.rs)・[上流の計測](../tools/upstream_songbird_voice_probe.rs)・[独立計算](../tools/measure_songbird_sustain_pcm.py)

5条件の253,875出力フレームは上流の公開レンダーとf32ビット列が一致した。うち76,800フレームは上流CLIが `--float` で出力したWAVの持続・停止区間の先頭1.6秒とも一致した。候補のホストブロックを128から77フレームへ変えた結果、各条件のWAVとCSVは同じハッシュになった。[波形と段ごとの判定](../runs/songbird-sustain-pcm-20261120-a/summary.json)・[基準のCLIコマンドと出力](../runs/songbird-sustain-pcm-20261120-a/manifest.json)

| 条件 | 開始指示 → 呼気へ反映 → 非ゼロPCM（フレーム） | 停止指示 → 呼気へ反映（フレーム） | 末尾20 msと持続区間のRMS比 |
| --- | --- | --- | ---: |
| 44.1 kHz | 73 → 128 → 134 | 11567 → 11584 | `1.93×10⁻¹⁷` |
| 48 kHz | 73 → 128 → 135 | 11567 → 11584 | `4.18×10⁻¹⁸` |
| 96 kHz | 147 → 192 → 206 | 23135 → 23168 | `4.19×10⁻¹⁸` |

48 kHzではゲートがフレーム128で0.283469になり、停止後最初の制御で約1から0.894839へ下がった。96 kHzでは制御周期の秒数が半分になり、1回のゲートの立ち上がりは0.153518だった。開始・停止の要求を制御境界まで待つ時間は、気道を通って波形に最初に値が出る時間と個別に測れる。[ゲートと出力の時刻](../runs/songbird-sustain-pcm-20261120-a/summary.json)

48 kHzの標準条件で、上流との差は制御値より後の放射流量の時間微分のサンプル540で最初に観測され、間引きとDC除去ではフレーム137で初めて現れた。全条件の最大絶対差は内部放射で `1.50×10⁻⁸ cm³/s²`、DC除去後で `8.66×10⁻¹⁵`。f32に丸めたPCMは全サンプル一致した。別に持続中の演奏値と出力レベルを上げた条件では、DC除去後のピーク2.027714が制限後に0.999914になり、942フレームに振幅制限が掛かった。[状態列と振幅制限](../runs/songbird-sustain-pcm-20261120-a/summary.json)

研究ディレクトリと `/tmp` からの実行で各298項目を通過し、WAV、CSV、個別ケースと設定JSONの36ファイルがハッシュ一致した。上下流のPCMはf32を符号込みの32ビット列としても照合した。固定上流の動物音声・実時間試験は7件、既存の鳴禽の気道は232項目、共有するWAV出力段の人間の発声ケースは12項目を通過した。[再実行とハッシュ](../runs/songbird-sustain-pcm-20261120-repeat/manifest.json)・[鳴禽の気道の回帰](../runs/songbird-sustain-airway-regression-20261120/summary.json)・[動作済みPCM出力の回帰](../runs/songbird-sustain-pcm-regression-20261120/summary.json)
