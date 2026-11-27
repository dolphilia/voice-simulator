# アフリカゾウの `rumble`

上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `render creature elephant` は48 kHzの持続音1.2秒と停止0.4秒のあと、`elephant::def` のコールを順に描画する。最初の `rumble` は出力76,800から始まり、最終キーの3.1秒に0.5秒を足した172,800フレームを占める。今回の比較は公式CLIの先頭249,600フレームと、そのうち `rumble` の区間を対象とする。上流の `elephant-call-rumble` は単独156,960フレームを、`elephant-pitched` は22 Hzを指定した43,200フレームを固定試験に使い、保存PCMとテレメトリ、ホスト分割の一致を検査する。[公式CLIの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[キーの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L138)・[テレメトリとホスト分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)

`CallDef::resolve` はキー名をゲート・演奏パラメータに分け、コールが所有するパラメータを集める。`rumble` のキーは `mode=0`、`trunk=1`、音高15 Hzを時刻0で設定する。ゲートは0から0.3秒で1に上がり、2.7秒まで1を保ち、3.1秒で0になる。音高を持つキーは0秒と2.7秒の二つなので、その間は15 Hzから12 Hzへ直線で下がる。移調指定があれば目標は指定音高を基準14 Hzで割った倍率を掛け、8〜45 Hzに収める。経路と発声モードは単一キーの値を保持する。呼気圧と粗さには手動の目標が入る。[キーの解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L179)・[コールの評価](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

`CreatureVoice` は64出力フレームごとに制御し、時計に `64/fs` 秒を加算する。開始要求の時点の時計を保存するため、制御境界の間に要求しても次の境界で経過ゼロのキーを評価する。制御時には、所有値を更新してから音高を対数空間で時定数0.05秒、経路を線形で0.04秒の一次遅れに通す。ゲート目標は手動とコールの大きい方で、増加は0.012秒、減少は0.06秒で平滑化し、肺圧を `980.665 × 呼気圧 × ゲート` dyn/cm²にする。音高と経路をコールが所有している間の手動変更は保存され、停止要求または制御時計が3.15秒を超えた時点で目標に戻る。平滑値と口先・軟口蓋の断面はその後も徐々に変わる。固定発声モードでは鼻の弁を4.5 cm²に保つ。[開始と終了](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L234)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[固定発声と放射経路](elephant-fixed-voice.md)

## 事前登録

48 kHzの公式順序、44.1 kHzで移調とゲート変更を含む途中停止、96 kHzで境界外から始める自然終了を比較する。44.1 kHzでは開始要求173・初回制御192、停止61,913・停止後の初回制御61,952に着目する。96 kHzでは加算時計による所有の終了を302,528と予測した。持続区間の早い窓と遅い窓で平均瞬時F0を比較し、目標の下降が声門の周期に伝わることを確かめる。[登録した比較条件](../cases/elephant-rumble.json)

## 実装と実測

CLIの `play_call` を、64フレームごとの目標更新と既存の声門・気道に接続した。音高と経路の保持、手動ゲートとの合成、移調、停止を実際の描画中に検査した。独立計算には、登録したキーの線形補間、経過秒の累積、対数空間での音高の一次遅れ、口先と軟口蓋の区間内補間を使った。3レートで制御時計は上流・独立計算と一致し、独立計算との平滑音高の最大絶対差は `1.39×10⁻¹³ Hz`、肺圧は `3.64×10⁻¹¹ dyn/cm²` だった。[再生の実装](../crates/vocal-core/src/airway/elephant/call.rs)・[判定と数値差](../runs/elephant-rumble-20261120-a/summary.json)

| 条件 | 開始要求・初回制御・所有終了の出力フレーム | PCMの最大絶対差 |
| --- | --- | ---: |
| 48 kHz、公式順序 | 76,800・76,800・228,032 | `3.73×10⁻⁹` |
| 44.1 kHz、22 Hz指定と途中停止 | 173・192・61,913 | `1.86×10⁻⁹` |
| 96 kHz、境界外の開始と自然終了 | 17・64・302,528 | `1.86×10⁻⁹` |

公式順序では呼気キーの0.3秒に当たる出力91,200でゲート目標は1、平滑値は0.96218だった。3.1秒に当たる225,600で加算時計の端数により目標が `6.87×10⁻¹³` 残り、平滑値は0.14815だった。所有終了の228,032では、音高目標が12 Hzから手動の14 Hzに戻り、平滑値は12.04878 Hz、ゲートは0.06367だった。96 kHzでは302,464で音高目標12 Hzを保持し、次の制御302,528で14 Hzに戻った。[境界時刻と値](../runs/elephant-rumble-20261120-a/summary.json)

時刻を最初の制御から数え、公式条件の0.6〜1.2秒と2.0〜2.6秒を比べた。平均瞬時F0は14.004から12.504 Hzへ下降し、鼻先の流量RMSは1,042.16から1,035.84 cm³/s、PCMのRMSは0.08142から0.07200へ変わった。96 kHzでも同じ二つの区間で平均瞬時F0は14.060から12.507 Hzに下がった。[区間測定](../runs/elephant-rumble-20261120-a/summary.json)

44.1 kHzの移調では初回目標が `15 × 22/14 = 23.57143 Hz` になった。フレーム30,013の手動変更では呼気圧22 cmH₂Oと粗さ0.6が目標に直ちに入り、音高と経路はコールが保持した。手動ゲート0.95は制御40,064で採用され、手動ゲートを0に戻すと54,848でコールの0.8に戻った。停止61,913で音高・経路の目標が31 Hz・0.2へ戻り、平滑値は初回の停止後制御61,952で変化した。[移調・手動変更・停止](../runs/elephant-rumble-20261120-a/summary.json)

同じ44.1 kHz条件の出力192〜255ではゲートと肺圧がゼロだった。口先断面の縮小と同時に出力192で口端流量とPCMが現れ、この区間のPCM絶対値の最大は0.18883だった。両方のCSVで当該64フレームのPCMを単精度値に直して比較し、ビット一致を確認した。上流の気道では断面の移動で生じた体積変化を流量源に加える。断面だけを固定した対照で、この立ち上がりに対する寄与を調べられる。[候補の時系列](../runs/elephant-rumble-20261120-a/artifacts/manual-stop-44100/pcm-128.csv)・[上流の時系列](../runs/elephant-rumble-20261120-a/artifacts/manual-stop-44100/upstream.csv)・[上流の体積変化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L851)

## 残る差と再現

公式CLIの先頭249,600フレームのうち、50フレームのPCM単精度値に差があった。`rumble` 区間の172,800フレームでは37フレーム、最大絶対差は `3.73×10⁻⁹`。公式順序の最初の内部差は持続音のフレーム1の肺流量にあり、気管端圧34、声門流量35、壁面放射36へ現れた。最初のPCM差は12,783、`rumble` 区間に限ると全体の82,528だった。44.1 kHzでは最初の内部差が断面移動後のフレーム197の放射、96 kHzでは136の肺流量に現れた。固定上流プローブのPCMは、比較した全249,600フレームで公式CLIのWAVとビット一致した。[初回結果](../runs/elephant-rumble-20261120-a/summary.json)・[コマンドとSHA-256](../runs/elephant-rumble-20261120-a/manifest.json)

研究ディレクトリと `/tmp` で各202項目を通過した。結果要約、WAV、CSV、設定や定義のJSONを含む計測ファイル26件が一致した。直前のゾウの固定発声とアリゲーターの `dance` も回帰を確認した。[再実行](../runs/elephant-rumble-20261120-repeat/manifest.json)・[固定発声の回帰](../runs/elephant-fixed-voice-rumble-regression-20261120/manifest.json)・[danceの回帰](../runs/alligator-dance-rumble-regression-20261120/manifest.json)
