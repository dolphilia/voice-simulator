# Chirp cascadeの押鍵直後に放射が分岐する演算

## 上流の入力から放射まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、鳴禽用のWeb MIDI押鍵が `CreatureVoice::play_call` を呼ぶ。`CreatureVoice::render` の内部制御境界で `eval_call` が音高とゲートの目標を読み、`control` が現在値を一次追従させる。48 kHzでは1出力フレームに4内部サンプルを使い、64出力フレームごとに制御を更新する。最初の押鍵では音高が先に動き、ゲートは0のまま進む。上流の `every_call_key_resolves` がキー解決を、`warm_creature_voice_does_not_allocate` が実時間の発音中の割り当てを、`creatures_match_typescript` が音と内部観測の回帰を確認する。[押鍵からコールまで](worklet-midi-songbird-chirps.md#固定上流の読み方)・[固定上流の制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[実時間の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)・[固定入力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)

`Songbird::control` では、左右の低い方の音高を `f` Hz、追従量を `purity` として、口腔食道腔の目標体積を `purity × (0.03 / 0.35) × (5570 / f)² + (1 − purity) × OEC` cm³で求め、0.04〜2.5 cm³に制限する。体積を一定の長さ `∛0.4` cmで割ると断面積になる。上流の `AirwayNetwork::begin_block` はこの差を256内部サンプルに分ける。`step` は断面を更新し、体積減少をサンプル間隔で割って流量源にする。この区間の腔の断面は0.12 cm²以上なので近隣への流量源の移し替えはなく、60 Hzの一次低域通過2段がかかる。枝流量と節点圧を順に進め、くちばし端では並列R–L負荷を使って放射流量を求める。最後にその時間差分をcm³/s²で返す。再実装のCLIは同じ位置の圧力と流量を観測できる。[腔の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[断面と伝搬の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[再実装の体積速度源](../crates/vocal-core/src/airway/network/geometry.rs#L118)・[通常のCLI入口](../crates/vocal-cli/src/songbird_case.rs#L29)

## 元の採用時刻と小規模な対照

先行のMIDI 60は48 kHzの出力フレーム8,320、192 kHzの内部サンプル33,280で採用された。先行記録から初期設定と採用時の音高2,691.345 Hz、左右配分、駆動を読み、256内部サンプルの無励振の後に同じ値を通常の `vocal-cli render` と固定上流の鳴禽プローブに入れた。最初の16内部サンプルの放射微分は、両版とも先行の記録とそれぞれ一致した。音高だけを更新する試行と、最初から音高追従を0にする試行を同じ区間で計測した。[元のケースと採用時刻](../runs/worklet-midi-songbird-chirps-20261121-final/manifest.json)・[事前登録](../cases/songbird-chirps-onset-radiation.json)・[計測コード](../tools/measure_songbird_chirps_onset.py)

押鍵相当の更新直後、腔の断面は約0.5357003から0.5355890 cm²に縮み、目標は約0.5071989 cm²だった。独立計算では最初の体積速度源は15.74999 cm³/s、低域通過後は約0.0000606021 cm³/s、腔の圧力は0.00111697182 dyn/cm²。両版の圧力と断面がその値に一致した。6内部サンプル後の放射は、192 kHzでは31.25 µs後に当たる。音高だけを変更しても最初の放射を再現し、追従0では腔の断面、圧力、流量、放射に変化がなかった。[第1版の結果](../runs/songbird-chirps-onset-radiation-20261122-a/summary.json)

## 放射微分の丸めを切り分ける

更新から6内部サンプル後、くちばし端の放射流量は両版で `0x1.790336ceea956p-23` cm³/sだった。再実装は流量差を `dt = 1 / 192000` で割り、上流は流量差に `192000` を掛ける。この点の放射微分はそれぞれ `0x1.1421daa48cd07p-5` と `0x1.1421daa48cd06p-5` cm³/s²となった。先行の判定を保存した上で、各版の16点をそれぞれの演算でビット単位に復元した。再実装の流量に上流の掛け算を適用すると、次の差は8内部サンプル後になった。その点では流量自体に約1.69×10⁻²¹ cm³/sの差があり、流量の演算内で先に異なる箇所の観測が残る。計算式を変えた比較は保存した流量への再計算として行った。[上流の差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)・[再実装の差分](../crates/vocal-core/src/airway/network.rs#L791)・[16点と16進値の比較](../runs/songbird-chirps-onset-radiation-20261122-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。第1版の31判定を保存し、第2版は研究ワークスペースと `/tmp` の各34判定が合格、要約はバイト一致した。上流の鳴禽を含む7試験も通過した。生CSVから体積・圧力と除算・乗算の16点を独立に再計算し、3実行の394入力・42出力を照合した。採取物2,666,757バイトはRTL9210B-CGに保存した。[第1版のマニフェスト](../runs/songbird-chirps-onset-radiation-20261122-a/manifest.json)・[第2版の再実行](../runs/songbird-chirps-onset-radiation-20261122-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_songbird_chirps_onset.py songbird-chirps-onset-local
```

## くちばし入口と放射負荷の丸めを分ける

固定上流の `Songbird::sample` は左右の鳴管を更新してから `AirwayNetwork::step` を呼ぶ。くちばし入口では、口腔食道腔とくちばしの最初のセルを結ぶ直列枝が、前のサンプルの圧力差・流量と現在の断面を読む。慣性を `L`、粘性抵抗を `R`、流量を `U` とすると、新しい流量は線形係数 `L / dt + R` と速度二乗の損失を含む方程式で求まる。くちばし端では流入と放射流量の差が終端セルの圧力変化に対応する。節点のコンプライアンスを `C`、放射負荷の抵抗を `Rr`、慣性を `Lr` とすると、放射の抵抗成分は中点圧力を `Rr` で割った流量、慣性成分は `Lr` で規格化した圧力を時間積分した流量の前後平均。流量はcm³/s、圧力はdyn/cm²、`dt` は秒。上流の一様管テストはこの放射終端を含む共鳴を、鳴禽を含む実時間テストは呼び出し中の割り当てを確認する。[固定上流の標本更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L109)・[直列枝の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L950)・[放射負荷の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)・[一様管テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[鳴禽を含む実時間テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)

前回の無励振からの押鍵と追従0を、192 kHz・256内部サンプル目の入力更新から16点ずつ再採取した。通常の `songbird_airway` ケースに `observe_beak: true` を指定すると、くちばしの全6セルについて断面・圧力・流入枝の列が加わる。固定上流も同じ位置を公開APIで採取した。追加列を外した観測値と、通常設定から再生成したCSVは、元の実行とそれぞれ一致した。断面から枝の慣性と抵抗を算出し、圧力から終端の慣性枝・抵抗枝を復元した独立計算では、流量の最大誤差が2.17×10⁻¹⁹ cm³/s、圧力の最大残差が5.56×10⁻¹⁷ dyn/cm²だった。追従0では圧力・流量を全点ゼロと確認した。[事前登録](../cases/songbird-chirps-beak-load.json)・[CLIの観測列](../crates/vocal-cli/src/songbird_case.rs#L74)・[上流の観測器](../tools/upstream_songbird_airway_probe.rs)・[確定版の要約](../runs/songbird-chirps-beak-load-20261122-c-repeat/summary.json)

| 観測点 | 入力更新から最初に差が出た内部サンプル | 照合結果 |
| --- | ---: | --- |
| くちばし入口の流量 | 4 | 前の流量と圧力差、枝の慣性は一致した。線形係数に入る `L / dt` と `L × fs` は末尾1ビット違い、この項だけを入れ替えて両版の流量を復元した。 |
| くちばし端の圧力 | 6 | 終端への流入は同じ。コンプライアンスの `C / dt` と `C × fs` の違いで圧力が1 ULP分かれた。 |
| くちばし端の放射流量 | 8 | 差は2 ULP、約1.69×10⁻²¹ cm³/s。再実装側の流入を使い、コンプライアンスの項だけ上流と揃えるとこの点の放射流量は一致した。加減算の括りも揃えると8点目まで圧力と放射流量がともに一致した。 |
| くちばし端への流入 | 9 | 流入がここで分かれ、放射負荷の式を揃えた対照にも差が出た。 |

各版の放射負荷をそれぞれの流入から再計算すると、16点の圧力と放射流量がビット一致した。上記の演算を入れ替えた試行は、記録した流入・圧力を使う対照として実行した。[丸めの再計算](../tools/measure_songbird_chirps_beak_load.py#L95)・[固定上流と再実装の比較](../runs/songbird-chirps-beak-load-20261122-c-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。第1版の29判定を保存した。第2版の最初の2実行は、判定のNumPy真偽値をJSONへ保存する段で停止した。生CSVを保存し、Pythonの真偽値へ変換して再実行した。生CSVは修正前後で一致し、確定版はワークスペースと `/tmp` から各36判定が通過して要約と採取CSVが一致した。固定上流6試験と現行のRust 52試験も通過した。5実行の688入力・63出力を独立に照合し、採取物5,199,945バイトをRTL9210B-CGに保存した。[最初の保存エラー](../runs/songbird-chirps-beak-load-20261122-b/manifest.json)・[確定版のマニフェスト](../runs/songbird-chirps-beak-load-20261122-c-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_load.py songbird-chirps-beak-load-local
```

## 最後の直列枝で運動量の時間換算を照合する

固定上流の `Songbird::control` が音高と口腔食道腔の目標を設定し、`Songbird::sample` が左右の鳴管の開口を更新して `AirwayNetwork::step` へ進む。節点の幾何と係数を更新してから、直列枝の新しい流量を前回の流量・前回の節点圧で解く。その流量を両端の収支に加えて圧力と放射負荷を更新する。通常CLIは `observe_beak` を指定すると、更新後の各セルの圧力、断面、流入枝の流量を記録する。今回の再計算は最後の直列枝なので、サンプル `n` の流量を復元する際は、圧力と流量を `n − 1`、断面を `n` の行から読む。[固定上流の鳴禽モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L950)・[再実装の枝更新](../crates/vocal-core/src/airway/network.rs#L189)・[通常CLIの観測](../crates/vocal-cli/src/songbird_case.rs#L74)

両端の断面は0.13025と0.1504167 cm²、セル長は1.3/6 cmで一定。慣性 `L` は両端のセル長と断面の比を足し、空気密度の半分を掛けて求める。枝の流量 `U`（cm³/s）は `bU + K|U|U = c` を解いて求める。`b = L/Δt + R`、`K` は流向に応じた断面変化の損失係数。駆動圧 `c`（dyn/cm²）は前回の両端圧の差と前回運動量の時間換算の和になる。慣性が一定の今回の窓で、上流は `(L × U) × fs`、再実装は `(L / Δt) × U` の順で後者を求める。上流の `fdtd_impulse_response_agrees_with_frequency_domain_model` は気道と放射の周波数応答を、`warm_creature_voice_does_not_allocate` は鳴禽を含む長さの異なる描画時の割り当てを確認する。[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[上流の実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

192 kHz、入力更新256点目から16点を測った。従来の押鍵と音高追従0の4 CSVが保存結果とバイト一致し、両版の最後の枝の流量を計64点すべてビット単位で復元した。追従0では全点で流量0。最初の流量差は予測どおり押鍵9内部サンプル後だった。前回の流量と入口側の圧力は一致し、先端側の圧力だけが2 ULP違った。この圧力差を有理数で計算すると、再実装の差は丸め先よりちょうど0.5 ULP大きく、上流の差は丸め先そのものだった。倍精度では偶数側に丸められ、両版の圧力差が同じ `0x1.a4e88399824f0p-8` になる。[事前登録](../cases/songbird-chirps-beak-tip-inflow.json)・[64点の中間値](../runs/songbird-chirps-beak-tip-inflow-20261123-repeat/artifacts/terminal-branch-steps.json)

先端側の前回圧だけの交換で流量差を再現する予測は外れた。前回の運動量の時間換算だけを上流の値へ換えると駆動圧が1 ULP動き、流量が約 `6.78 × 10⁻²¹ cm³/s` 減って上流とビット一致した。粘性抵抗にも差があったが線形係数を加算した時点で一致し、二乗損失係数だけを入れ替えた対照でも流量は同じだった。この置換は保存した前回状態を使った1更新の比較。音高や形状を変えた区間への一般化には、同じ観測点を保って別の出力レートで再計測できる。[最初の判定と交換結果](../runs/songbird-chirps-beak-tip-inflow-20261123-a/summary.json)・[再計算](../tools/measure_songbird_chirps_beak_tip_inflow.py)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各10判定に合格し、要約、入力一覧、64点の再計算系列が一致した。現行Rust 52試験と固定上流6試験が通過した。2実行の276入力と22出力をサイズとSHA-256で照合し、採取物2,014,450バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](../runs/songbird-chirps-beak-tip-inflow-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_tip_inflow.py songbird-chirps-beak-tip-inflow-local
```

## 44.1 kHz出力相当で最初の流入差を比較する

固定上流では鳴禽の `oversample` が4で、`CreatureVoice::new` は44.1 kHzを176.4 kHzに換算する。制御は64出力フレームごとに目標を更新し、`begin_block` が次の256内部サンプルへ断面の変更を配分する。再実装の `SongbirdVoice::new` もこのレートで4倍にする。管の分割は `dx_min = 35000 / fs / 0.93` cmを基準に決まる。1.3 cmのくちばしは両レートで6セル。再実装の通常CLIの形状出力では、気管が18から16セルへ、気管支が片側4から3セルへ変わった。上流試験の一様管のインパルスと実時間の割り当て確認は192 kHzの回帰で再実行し、今回の176.4 kHzの比較では両版の内部時系列を直接取得した。[上流のレートと制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)・[上流の管分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L8)・[再実装の出力レート](../crates/vocal-core/src/songbird_voice.rs#L57)・[CLIの形状出力](../runs/songbird-chirps-beak-tip-inflow-44100-20261123-repeat/artifacts/current-geometry.json)

192 kHzで保存した音高・呼気・開口・口腔食道腔の目標を固定した。主条件は元の制御間隔1,333.333 µsに最も近い235内部サンプル（1,332.200 µs）。通常の制御刻み256内部サンプル（1,451.247 µs）でも比較した。両条件と主条件の追従0について、通常の `vocal-cli render` と固定上流の観測器から入力更新直後16点を採った。6セルの全断面が192 kHzの記録と一致し、最後の枝の流量が両版・3条件の計96点で独立再計算とビット一致した。追従0では全点の流量が0だった。比較対象は間引き前の気道の内部更新。[事前登録](../cases/songbird-chirps-beak-tip-inflow-44100.json)・[全条件の再計算系列](../runs/songbird-chirps-beak-tip-inflow-44100-20261123-repeat/artifacts/terminal-branch-steps.json)

| 内部レートと制御間隔 | 最後の枝の初差 | 単独で上流の流量を再現した置換 |
| --- | --- | --- |
| 192 kHz・256点 | 9点後、46.875 µs、1 ULP | 前回運動量の時間換算 |
| 176.4 kHz・235点 | 8点後、45.351 µs、3 ULP | 手前のセルの前回圧 |
| 176.4 kHz・256点 | 7点後、39.683 µs、1 ULP | 手前のセルの前回圧、または前回運動量の時間換算 |

235点条件では先端圧・前回流量・運動量項が一致し、手前のセル圧だけを上流に換えると差が再現した。通常の256点条件は圧力差と運動量項のどちらを単独で換えても同じ流量になるため、この1点の流量では寄与を一意に決められない。押鍵から6〜12内部サンプルで初差が出る予測は両条件で成立し、運動量項だけで説明できる予測は235点で不成立だった。元CSVを遡ると、235点条件では押鍵1点後の口腔食道腔の圧力、256点条件では4点後のくちばし内の圧力・枝流量が、今回採った系列の中で最初に分かれた。[交換結果](../runs/songbird-chirps-beak-tip-inflow-44100-20261123-repeat/summary.json)・[元CSVの差の独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-chirps-44100-20261123.json)

初回の `songbird-chirps-beak-tip-inflow-44100-20261123-a` は192 kHzの参照マニフェストのハッシュを転記し損ね、参照照合で停止した。採取前の停止なので実行ディレクトリは作られなかった。正しいハッシュに修正した後、macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4の研究ワークスペースと `/tmp` で各14判定に合格し、要約・入力一覧・採取CSVは一致した。共通化した再計算を192 kHzにも通し、前回の要約・系列・CSVがバイト一致した。現行Rust 52試験と固定上流6試験も通過した。3実行の416入力と43出力を照合し、採取物3,348,261バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](../runs/songbird-chirps-beak-tip-inflow-44100-20261123-repeat/manifest.json)・[192 kHz回帰](../runs/songbird-chirps-beak-tip-inflow-20261123-rate-regression/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-chirps-44100-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_tip_inflow_44100.py songbird-chirps-beak-tip-inflow-44100-local
```

## 176.4 kHzの口腔食道腔で最初の圧力差を再現する

固定上流では `Songbird::control` が低い側の鳴管の音高から口腔食道腔の目標断面を決める。`AirwayNetwork::begin_block` が面積変更を制御区間へ分け、`Songbird::sample` から呼ばれる `AirwayNetwork::step` がまず面積を進めて体積 `V = Aℓ`（cm³）を求める。腔の断面は0.12 cm²以上だったため、変位した体積の近隣セルへの再配分は生じない。1標本で縮んだ体積を上流は内部レート `fs` で掛け、再実装は刻み `Δt = 1/fs` で割って体積速度（cm³/s）にする。60 Hzの一次低域通過を2段通し、各段の状態を `s += α(x − s)` で更新する。係数は `α = 1 − exp(−2π × 60 × Δt)`。固定上流の `sealed_cavity_compression_follows_the_linearised_adiabatic_law` は密閉した空洞を5%縮め、圧力を断熱圧縮の式と比較する。[固定上流の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[体積速度とフィルタ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[再実装の体積速度](../crates/vocal-core/src/airway/network/geometry.rs#L110)・[固定上流の圧縮試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)

フィルタ後の注入に気管側の流入を加え、くちばし側への流出を引く。腔の接続は2枝で壁の流量も無いため、幾何コンプライアンス `C = V/(ρc²)`（cm⁵/dyn）を使い、圧力（dyn/cm²）を `p += (Δt/C) × 正味流入` で更新する。上流は気管側、くちばし側の順に体積収支を更新し、再実装は逆順になる。通常CLIの `observe_oec` と上流観測器に、セル長、接続する両枝の流量、収支へ加える順序を追加した。再実装はフィルタ後の注入とコンプライアンスも保存する。上流の注入とコンプライアンスは公開の断面・セル長と、同じ入力からの独立計算で復元した。[上流の枝と圧力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1031)・[再実装の通常CLI](../crates/vocal-cli/src/songbird_case.rs#L84)・[上流の観測器](../tools/upstream_songbird_airway_probe.rs#L69)

前回の176.4 kHzの3条件をそのまま使い、入力更新から16点ずつを採取した。235点制御では押鍵1内部サンプル（5.669 µs）後の体積減少が両版で同じ約 `8.94 × 10⁻⁵ cm³` だった。体積速度の除算・乗算で1 ULP分かれ、低域通過2段後の注入と腔圧は各2 ULP分かれた。この時点のフィルタ係数・前回圧・コンプライアンス・両枝の流量は一致している。再実装の体積速度の換算だけを掛け算に変えた1更新では、注入と圧力が上流とビット一致した。収支の加算順だけを替えても差は移らなかった。両枝の流量は押鍵2内部サンプル後に初めて分かれた。[事前登録](../cases/songbird-chirps-oec-pressure-44100.json)・[再計算と置換結果](../runs/songbird-chirps-oec-pressure-44100-20261123-repeat/summary.json)

通常の256点制御では観測窓内の体積速度と圧力が両版で一致した。押鍵4内部サンプル後には、両枝と注入が同じまま収支の加算順で1 ULPの差が出たが、圧力増分の積は同じ値に丸められた。音高追従0では腔圧・注入・両枝の流量はすべて0。3条件・両版の腔圧96点と、再実装の注入・コンプライアンス各48点をビット単位で復元した。既存の観測列は保存済みCSVと一致し、`observe_oec` を省略した出力と、くちばしの観測を省いた出力も照合した。[96点の中間値](../runs/songbird-chirps-oec-pressure-44100-20261123-repeat/artifacts/oec-pressure-steps.json)・[独立検算の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-pressure-20261123.json)

初回の `songbird-chirps-oec-pressure-44100-20261123-a` は先行マニフェストのSHA-256の転記漏れで採取前に停止した。保存済みのファイルから求めた値に修正し、macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4の研究ワークスペースと `/tmp` で各27判定に合格した。要約・観測列・再計算系列はバイト一致し、現行Rust 52試験と固定上流9試験も通過した。2実行の286入力・32出力をサイズとSHA-256で照合し、採取物2,471,317バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](../runs/songbird-chirps-oec-pressure-44100-20261123-repeat/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-pressure-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 \
  ../../.venv/bin/python tools/measure_songbird_chirps_oec_pressure_44100.py songbird-chirps-oec-pressure-44100-local
```

## 体積速度の換算を替えて放射まで追う

前回は保存した前回状態に換算結果を与えて、1内部サンプルの腔圧を再計算した。今回は同じRustソースと辞書をRTL9210B-CG上の一時ディレクトリに複製し、固定したCargoロックファイルで通常版をビルドした。実験版の差分は `MovingAreas::step` の `ΔV / dt` を `ΔV × dt.recip()` に替えた1行。登録レート176.4 kHzで `dt.recip()` が176400を正確に返すことを確認した。通常版と実験版の両方で `vocal-cli render` を通し、先行実行が保存した固定上流のCSVと比較した。押鍵前の初期化から連続して描画し、押鍵後16内部サンプルを観測した。[事前登録](../cases/songbird-chirps-volume-rate-propagation-44100.json)・[保存した差分](../runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/artifacts/volume-rate.patch)・[実験コード](../tools/measure_songbird_chirps_volume_rate_propagation_44100.py)

固定上流の `Songbird::sample` から進む `AirwayNetwork::step` は、体積速度源の後に各枝の駆動圧を前回の両端圧と運動量から計算し、その流量を節点の収支へ加える。くちばし端では圧力と並列R–L負荷の状態を連立更新し、放射流量 `Urad`（cm³/s）を得る。出力は `Urad` の時間差分（cm³/s²）。上流は流量差に `fs` を掛け、再実装は `dt` で割る。固定上流の試験には一様管の時間応答と周波数応答の照合、可動壁の圧縮の解析値との照合がある。今回は既存の試験に使った通常版の演算を基準とし、変更した系の腔圧と放射微分を採取データから独立に復元した。[上流の鳴禽の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[直列枝](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1022)・[終端負荷と時間差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)・[時間応答の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[圧縮の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)

235点制御で、固定上流に対して各観測値が最初に分かれた位置を表に示す。単位は押鍵からの内部サンプル数。隔離してビルドした通常版の3条件の出力は先行実行とバイト一致した。実験版も256点制御と音高追従0の各条件で通常版とバイト一致した。3条件とも腔とくちばしの形状は一致し、実験版の注入量と圧力は各48点をビット単位で復元した。[比較結果](../runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/summary.json)・[圧力の再計算系列](../runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/artifacts/pressure-replay.json)

| 観測点 | 通常版 | 換算を乗算にした実験版 |
| --- | ---: | ---: |
| 口腔食道腔の圧力 | 1 | 14 |
| くちばしの2番目のセルへの流入 | 4 | 3 |
| 先端のセルへの流入 | 8 | 9 |
| 放射流量 | 8 | 11 |
| 放射流量の時間差分 | 8 | 9 |

実験版のくちばしでは、2番目のセルへの流入が押鍵3点後に1 ULP分かれた。両端の前回圧と流量をそろえた再計算で、前回運動量の時間換算だけを上流の `(L × U) × fs` に替えると、この流量が上流とビット一致した。押鍵9点後の放射微分差は直前2点の放射流量が一致していても生じた。保存済みの実験版流量に上流の掛け算を適用すると、残る最初の微分差は放射流量そのものが分かれる11点後へ移った。押鍵14点後に残る腔圧差は、同じ注入と前回圧のまま、くちばし側へ出る流量を上流の値に替えると再現した。[枝・放射・腔圧の置換](../runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/summary.json)・[元CSVからの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-volume-rate-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。第1回は16判定が通り、差が残る内部枝の独立計算を加えた後に研究ワークスペースと `/tmp` から各17判定に合格した。3実行の採取CSV・実験差分・圧力の再計算がバイト一致し、後者2実行では要約・入力一覧・両ビルドのバイナリのSHA-256も一致した。3実行の435入力と30出力を照合し、採取物1,839,617バイトをRTL9210B-CGに保存した。一時ビルドのディレクトリは実行後に片付けた。[第1回のマニフェスト](../runs/songbird-chirps-volume-rate-propagation-44100-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-volume-rate-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_volume_rate_propagation_44100.py songbird-chirps-volume-rate-propagation-44100-local
```

## くちばし内部5枝で運動量の計算順を替える

固定上流では `Songbird::control` が開口目標を設定し、`Songbird::sample` が両鳴管の開口を更新して `AirwayNetwork::step` を呼ぶ。直列枝では、その標本の慣性 `L` と前回の流量 `U`（cm³/s）から持ち越す運動量を決める。慣性が一定なら上流が保存する運動量は `L × U`。これに内部レート `fs` を掛けて前回の両端圧差に加え、駆動圧（dyn/cm²）を得る。再実装の `Branch::step` は、同じ項を `(L/dt) × U` で計算する。両版とも駆動圧から粘性と二乗損失を含む流量を求め、両端の節点収支に符号を反転して加える。上流の `fdtd_impulse_response_agrees_with_frequency_domain_model` は管の時間応答と周波数応答を照合し、`warm_creature_voice_does_not_allocate` は鳴禽を含む描画時の割り当てを調べる。[上流の鳴禽モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1022)・[再実装の枝](../crates/vocal-core/src/airway/network.rs#L189)・[上流の時間応答試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[上流の実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

外部ディスク上の隔離したCargoワークスペースに、前回保存した体積速度の乗算版を復元した。実験版では `SongbirdAirway::step` から、くちばし6セルを結ぶ5本の直列枝を指定し、該当する運動量項の計算順だけを `(L × U) × fs` に替えた。腔からくちばしへ入る枝はこの5本の外にある。176.4 kHzの235点制御、通常の256点制御、追従0を通常CLIから改めて描画し、入力更新後16点を固定上流のCSVに照合した。対照の3 CSVは前回の乗算版を再現し、3条件の形状と注入量は対照と実験版で一致した。両版の枝流量480点、腔圧・終端圧・放射流量各96点を独立式でビット照合した。[事前登録](../cases/songbird-chirps-beak-momentum-propagation-44100.json)・[隔離ビルドの差分](../runs/songbird-chirps-beak-momentum-propagation-44100-20261123-repeat/artifacts/beak-momentum.patch)・[計測コード](../tools/measure_songbird_chirps_beak_momentum_propagation_44100.py)

235点制御で、固定上流と初めて分かれた位置を示す。単位は押鍵からの内部サンプル数。

| 観測点 | 体積速度のみ乗算 | 内部5枝の運動量も乗算 |
| --- | ---: | ---: |
| 口腔食道腔の圧力 | 14 | 15 |
| くちばし入口への流入 | 4 | 4 |
| くちばしの2番目のセルへの流入 | 3 | 5 |
| 先端セルへの流入 | 9 | 9 |
| 放射流量 | 11 | 10 |
| 放射流量の時間差分 | 9 | 9 |

押鍵4点後に残る入口の流量差は、両端圧・前回流量・現在慣性を揃えた再計算で、線形係数の `L/dt` と `L×fs` の違いだけからビット再現した。その差は次の標本で内部の2番目のセルに現れ、以降の4枝でも圧力差だけを上流の値に替えると最初の流量差が再現した。放射流量が分かれた10点後の差は2 ULP。実験版の放射負荷の式に上流の終端流入を与えると、終端圧と放射流量が16点すべて一致した。終端流入を実験版に固定して上流の負荷の式だけを使うと、終端圧の差は9点後、放射流量の差は10点後に残った。235点では終端流入と放射流量の差が遅れるという予測は外れた。[枝と終端の置換](../runs/songbird-chirps-beak-momentum-propagation-44100-20261123-repeat/summary.json)

256点制御では、対照で7点後から分かれた終端流入と放射流量が、実験版では16点すべてで固定上流に一致した。放射流量を同じ式で時間差分すると放射微分も全点一致した。追従0の出力は実験版と対照でバイト一致した。235点・256点の違いと、235点の反証を同じ判定に保存した。[押鍵と追従0の要約](../runs/songbird-chirps-beak-momentum-propagation-44100-20261123-repeat/summary.json)・[元CSVの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-beak-momentum-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。初回は19判定が通り、終端負荷の再計算を追加した後、研究ワークスペースと `/tmp` で各22判定が通った。3実行で採取CSVとソース差分がバイト一致し、後者2実行で要約・入力一覧と両ビルドのSHA-256も一致した。3実行の444入力と27出力を照合し、採取物1,635,503バイトをRTL9210B-CGに保存した。一時ビルドは終了後に片付けた。[再実行のマニフェスト](../runs/songbird-chirps-beak-momentum-propagation-44100-20261123-repeat/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-beak-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_momentum_propagation_44100.py songbird-chirps-beak-momentum-propagation-44100-local
```

## くちばし入口の線形係数だけを揃える

固定上流の鳴禽モデルは `net.connect(oec, beak.first_node())` で腔の節点とくちばしの最初の節点を直列枝で結ぶ。`Songbird::sample` が鳴管の開口を更新した後、`AirwayNetwork::step` は現断面から枝の慣性 `L = (ρ/2) × (ℓa/Aa + ℓb/Ab)` と粘性抵抗 `R` を求める。駆動圧 `c`（dyn/cm²）は前回の両端圧差と持ち越し運動量の時間換算の和。流量 `U`（cm³/s）は `bU + K|U|U = c` を解いて求める。固定上流は線形係数を `b = L × fs + R`、再実装の通常経路は `b = L/dt + R` とする。得た流量を腔から引き、くちばしの最初のセルに加えて各圧力の更新へ進む。上流の管の時間応答試験は、数値描画による共鳴と周波数領域での共鳴を照合する。[上流の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L52)・[上流の慣性と抵抗](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L950)・[上流の流量と両端の収支](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1022)・[再実装の枝](../crates/vocal-core/src/airway/network.rs#L189)・[上流の時間応答試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

RTL9210B-CG上の隔離ビルドに、体積速度の換算と内部5枝の運動量を揃えた前回の差分を適用した。ここから入口の1枝だけを選び、線形係数の慣性項を `L × dt.recip()` に切り替えた。前回運動量の項は同じ式で描画を進めた。176.4 kHzの235点制御、通常の256点制御、追従0の3条件で、通常CLIから入力更新後16点のCSVを取得した。対照は前回のCSVとバイト一致し、両ビルドの形状と注入量は一致した。対照・実験版・固定上流の入口流量144点を独立計算でビット復元した。実験版と固定上流の腔圧・終端圧・放射流量もそれぞれ96点でビット照合した。[事前登録](../cases/songbird-chirps-beak-inlet-rate-propagation-44100.json)・[入口枝の差分](../runs/songbird-chirps-beak-inlet-rate-propagation-44100-20261123-repeat/artifacts/beak-inlet-rate.patch)・[入口項の再計算](../runs/songbird-chirps-beak-inlet-rate-propagation-44100-20261123-repeat/artifacts/inlet-replay.json)

235点制御で固定上流と最初に分かれた位置を示す。単位は押鍵からの内部サンプル数。

| 観測点 | 前回の運動量を揃えた版 | 入口の線形係数も揃えた版 |
| --- | ---: | ---: |
| 気管から腔への枝の流量 | 4 | 4 |
| くちばし入口の流量 | 4 | 5 |
| くちばしの2番目のセルへの流入 | 5 | 6 |
| 先端セルへの流入 | 9 | 11 |
| 放射流量 | 10 | 11 |
| 放射流量の時間差分 | 9 | 9 |

押鍵4点後の入口流量はビット一致した。5点後の残差は1 ULPで、両端圧差・線形係数・二乗損失係数が一致し、持ち越し運動量の時間換算だけを上流の値に置き換えると流量まで一致した。放射微分には9点後に別の丸め差が残る。保存した放射流量の差に上流と同じ `fs` を掛けると、微分の初差は放射流量と同じ11点後へ移った。終端へ入る流量だけを上流の値に置き換えた再計算では、終端圧と放射流量が16点すべて一致した。通常の256点制御と追従0では、対照と実験版のCSV全体がバイト一致した。[項別の置換と終端の照合](../runs/songbird-chirps-beak-inlet-rate-propagation-44100-20261123-repeat/summary.json)・[元CSVの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-inlet-rate-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各28判定に合格し、要約・入力一覧・CSV・差分・再計算系列および両バイナリのSHA-256が一致した。2実行の304入力・20出力を照合し、採取物1,291,086バイトをRTL9210B-CGに保存した。一時ビルドは終了後に片付けた。[再実行のマニフェスト](../runs/songbird-chirps-beak-inlet-rate-propagation-44100-20261123-repeat/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-inlet-rate-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_inlet_rate_propagation_44100.py songbird-chirps-beak-inlet-rate-propagation-44100-local
```

## くちばし入口の前回運動量を揃える

上流の鳴禽モデルでは `Songbird::control` が口腔食道腔の形状を更新し、`Songbird::sample` から気道の `step` を呼ぶ。口腔食道腔とくちばしを接続する入口枝では、慣性 `L` が前回より小さくなると現在の慣性と前回流量 `U`（cm³/s）を掛け、その他の場合は保存した運動量を使う。前回・現在の慣性の小さい方を `Lcarry` とすると、その運動量は `Lcarry × U`。これを上流は内部レート `fs` で掛けて駆動圧（dyn/cm²）に加える。再実装の入口は `(Lcarry / dt) × U` で計算する。枝流量を両端の収支に加えて節点圧を更新し、先端では並列R–L負荷から放射流量を求める。固定上流には一様管の時間応答と周波数応答の照合、鳴禽を含む実時間描画中の割り当ての試験がある。[上流の鳴禽モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[上流の運動量更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1022)・[再実装の枝更新](../crates/vocal-core/src/airway/network.rs#L189)・[上流の時間応答試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[上流の実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

RTL9210B-CG上の隔離ビルドに前回までの3差分を順に適用し、体積速度、内部5枝の運動量、入口の線形係数を揃えた版を対照にした。実験版では入口の線形係数を選ぶ既存の枝番号を再利用し、その1枝も運動量の積を先に求める経路に入れた。追加差分は隔離ビルドの1行。176.4 kHzの235点制御、通常の256点制御、音高追従0を通常CLIで描画し、押鍵後16内部サンプルを観測した。3条件の対照CSVは前回の実験版とバイト一致し、形状と注入量は対照と実験版で一致した。両ビルドと固定上流の入口流量144点、実験版と固定上流の腔圧・終端圧・放射流量各96点を独立計算でビット照合した。[事前登録](../cases/songbird-chirps-beak-inlet-momentum-44100.json)・[入口の追加差分](../runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/artifacts/beak-inlet-momentum.patch)・[入口の再計算系列](../runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/artifacts/inlet-momentum-replay.json)

235点制御で、入口流量の押鍵5点後の差と、終端流入・放射流量の11点後の差が消えた。235点と256点の両条件で、くちばし全6セルの圧力・流入と放射流量は16点すべて固定上流に一致した。放射微分の初差は235点制御で9点後、256点制御で11点後に残った。保存した実験版の流量差に上流の `fs` を掛ける独立計算では、両条件とも16点すべての放射微分が一致した。追従0のCSVは対照と実験版でバイト一致した。[条件別の判定と微分の再計算](../runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/summary.json)

気管側の首部を通る流量差は235点制御で4点後、256点制御で5点後から残った。235点制御の腔圧は最後の15点後に1 ULP分かれた。前回圧・注入・コンプライアンスは一致し、その点で気管側流量だけを上流に置き換えても圧力側の差は残った。同じ流量のまま節点収支の順を上流の「注入に気管側流量を足し、くちばしへの流量を引く」にすると、腔圧は上流とビット一致した。この窓は15点後で終わるため、腔圧差がその後くちばしへ伝わるかは追加の観測で確認できる。[残差の置換結果](../runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/summary.json)・[元CSVからの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-inlet-momentum-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各28判定が通り、入力一覧、要約、CSV、差分、再計算系列、両バイナリのSHA-256が一致した。2実行の310入力と20出力を照合し、採取物1,287,274バイトをRTL9210B-CGに保存した。一時ビルドは終了後に片付けた。[再実行のマニフェスト](../runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-inlet-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_inlet_momentum_44100.py songbird-chirps-beak-inlet-momentum-44100-local
```

## 口腔食道腔の流量収支を上流順に揃えて64点を観測する

固定上流の `Songbird::control` は口腔食道腔の目標断面を決め、`Songbird::sample` から気道の `step` を呼ぶ。口腔食道腔には気管から来る首部とくちばしへの出口がつながる。形状変化に由来する体積速度源（cm³/s）をフィルタ後に注入し、全枝の更新で節点ごとの正味流入 `Q` を集める。この腔は上流で気管側の流量を加えてからくちばしへの流量を引き、研究版では逆順に加減算する。圧力（dyn/cm²）の増分は `(dt/C) × Q` で、`C` は腔のコンプライアンス。固定上流の密閉空洞試験は断熱圧縮の解析値と照合し、一様管試験は時間領域と周波数領域の応答を比較する。[固定上流の接続と制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L48)・[流量源と枝の収支](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L903)・[圧力更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1111)・[空洞の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[一様管の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

外部ディスク上の隔離ビルドに前回の4差分を適用した版を対照にした。実験版は枝計算前の腔への注入を保存し、両枝の流量が決まった時点でこの腔だけを上流順に加減算する。CSVには実際の収支順を残す。176.4 kHzの235点制御、通常の256点制御、追従0で、押鍵後の観測を16点から64点へ延ばした。固定上流と対照版の先頭16点は保存済みCSVにバイト一致し、対照と実験版の断面形状・注入量は一致した。3条件の各版で腔圧と入口流量を各576点、固定上流と実験版で先端圧と放射流量を各384点ビット復元した。[事前登録](../cases/songbird-chirps-oec-sum-order-44100.json)・[隔離ビルドの差分](../runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/artifacts/oec-sum-order.patch)・[腔圧の再計算](../runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/artifacts/cavity-sum-replay.json)

| 制御周期 | 観測点 | 固定上流との差が出た最初の内部サンプル |
| --- | --- | --- |
| 235点 | 気管側流量 | 4 → 4 |
| 235点 | 腔圧 | 15 → 33 |
| 235点 | くちばし入口流量 | 16 → 29 |
| 235点 | 終端セルへの流入 | 22 → 23 |
| 235点 | 放射流量 | 18 → 18 |
| 256点 | 腔圧 | 54 → 45 |
| 256点 | くちばし入口流量 | 18 → 18 |
| 256点 | 放射流量 | 23 → 23 |

表は対照から実験版への変化を示す。235点の15点後では対照版の注入と両枝の流量を固定し、加算順だけを替えた独立計算で上流および実験版の腔圧を復元した。追従0の圧力・流量はすべて0。235点では腔圧の最初の差を18サンプル遅らせたが、放射流量の初差は18点後のままだった。その時点では実験版と上流の終端流入が一致し、終端圧が3 ULP、放射流量が1 ULP分かれた。この最初の放射差は、同じ終端流入で負荷の式だけを独立に替えて切り分けた。[比較結果](../runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/summary.json)・[元CSVの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-sum-order-20261123.json)

放射負荷では `C/dt` と `C×fs` がビット一致した。再実装は分子の係数を `C/dt − (g + h/2)`、固定上流は `C×fs − h/2 − g` の順で評価し、その係数は1 ULP異なった。分母側の加算結果は一致した。実験版の終端流入を固定して括りだけを上流と揃えると、235点制御で放射流量の初差は18点後から28点後へ移った。これは保存済みの流入を用いた負荷の再計算なので、終端圧をくちばしへ戻した連続描画での伝搬が次の比較に残る。[終端負荷の上流実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)・[再実装の放射負荷](../crates/vocal-core/src/airway.rs#L89)・[括りと時間換算の置換](../runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。初回の64点収録に終端係数の分離を追記し、研究ワークスペースと `/tmp` で各46判定が通った。3実行でCSV・差分・腔圧の再計算が一致し、後者2実行で要約・入力一覧・両バイナリのSHA-256も一致した。3実行の477入力・54出力を照合し、採取物6,350,902バイトをRTL9210B-CGに保存した。一時ビルドは終了後に片付けた。[初回のマニフェスト](../runs/songbird-chirps-oec-sum-order-44100-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/manifest.json)・[独立検算のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-sum-order-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_oec_sum_order_44100.py songbird-chirps-oec-sum-order-44100-local
```

## くちばし先端負荷の分子係数を連続描画で揃える

固定上流の `create` はくちばしの最後のセル中心に唯一の開口放射負荷を付ける。`Songbird::control` が音高追従の腔容積と開き量を設定し、`Songbird::sample` が鳴管の弁面積を更新して `AirwayNetwork::step` を呼ぶ。先に前回の節点圧を使って直列枝を進め、そこから求めた正味流入 `Q` が同じ標本の節点更新へ渡る。先端圧 `p`（dyn/cm²）と並列慣性枝の流量 `U_L`（cm³/s）は前回値を保持する。開いている先端では、断面から抵抗 `R_r` と慣性 `L_r` を求め、慣性が増えた場合は持ち越し流量を縮める。今回の3条件は開口面積が一定で、慣性の補正は発生しない。[固定上流の鳴禽](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[気道の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)

`g = 1/(2 R_r)`、`h = dt/(2 L_r)`、`C = A Δx/(ρ c²)` とおくと、`p' = (p × a + Q − U_L) / b`、`U_L' = U_L + h(p + p')`、`Q_rad = (U_L + U_L')/2 + g(p + p')` の順で更新する。`a` と `b` は流量を圧力で割った単位を持ち、`Q_rad` の差分を時間で割ると放射微分（cm³/s²）になる。新しい先端圧が最後の枝の駆動圧に入り得るのは次の内部標本から。既存の一様管の試験はインパルス応答と周波数領域の共鳴、狭窄を含む管の試験は時間領域と周波数領域のフォルマント帯域幅を照合している。今回の観測では先端から最後の枝へ戻る丸め差を点ごとに比較する。[固定上流の負荷更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)・[インパルス応答の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[帯域幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L128)

5差分を使った前回の収支順実験版を基準に、先端の `a` だけを `C/dt − (g + h/2)` から `(C/dt − h/2) − g` へ変更する。候補の通常入口は `vocal-cli render` から `songbird_case::run`、`SongbirdAirway::step`、気道ネットワークの節点更新へ進む。固定上流の系列は前回の64点をマニフェストのSHA-256で照合して再利用する。今回は235点、256点、追従0の全条件で同じ入力を描画し、先端・最後の直列枝・放射微分を独立計算で照合する。[事前登録](../cases/songbird-chirps-terminal-numerator-44100.json)・[再実装のCLI](../crates/vocal-cli/src/songbird_case.rs#L33)・[再実装の放射負荷](../crates/vocal-core/src/airway.rs#L89)・[固定上流の64点の記録](../runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/manifest.json)

| 観測点 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| 気管側の首部流量 | 4 → 4 | 5 → 5 |
| 口腔食道腔圧 | 33 → 53 | 45 → 45 |
| くちばし入口流量 | 29 → 53 | 18 → 18 |
| 先端への流入 | 23 → 60 | 18 → 23 |
| 先端圧 | 18 → 60 | 17 → 23 |
| 放射流量 | 18 → 60 | 23 → 24 |
| 放射微分 | 9 → 9 | 11 → 11 |

表は上流と最初に分かれた内部サンプルを、対照から実験版の順に示す。押鍵を0とし、1点は約5.67 µs。追従0の観測列は全て0だった。先端で使った分子係数は1 ULP変わり、固定上流では時間換算と分母の括りも異なるものの、この断面とレートでの分母は `0x1.a57ee52cacf21p-8` で一致した。保存した固定上流の終端流入を実験版の式へ渡すと、3条件すべてで64点の先端圧・放射流量が上流に一致した。[要約と置換比較](../runs/songbird-chirps-terminal-numerator-44100-20261123-repeat/summary.json)・[隔離ビルドの差分](../runs/songbird-chirps-terminal-numerator-44100-20261123-repeat/artifacts/terminal-numerator.patch)

235点条件で実験版と対照を直接比べると、先端圧は18点後に3 ULP分かれ、最後の枝の流量は22点後まで一致した。その一つ前の標本で、最後の枝の手前の圧力と持ち越し流量は同じで、先端圧だけが異なった。先端圧を対照の1更新に置き換えると、23点後の流量差1 ULPを再現した。その後、手前セル圧23点後、くちばし入口流量29点後、腔圧33点後の順に実験による差が現れた。対照の終端流入のまま負荷だけを再計算した場合は上流との最初の放射差が28点後に残る。連続描画では終端流入も変化し、上流と一致する区間が長くなった。256点制御では実験による流量差が先端圧の差の直後の18点後に戻る一方で、気管側5点後とくちばし入口18点後の上流との差が残った。[初回の枝入力と置換](../runs/songbird-chirps-terminal-numerator-44100-20261123-repeat/summary.json)・[CSVの独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-terminal-numerator-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各58判定が通り、先端圧、放射流量、最後の枝流量、放射微分はそれぞれ576点を独立計算でビット照合した。両実行でCSV、パッチ、要約と両ビルドのSHA-256が一致した。別のCSV照合では初回にCargoログまで同じハッシュと比較して停止した。ビルド順、一時パス、所要時間を正規化するとログの内容は一致し、各ログも保存時のハッシュと一致した。2実行の306入力と18出力を照合し、採取物1,455,878バイトをRTL9210B-CGへ保存した。現行Rustの52試験、固定上流の気道9試験も通過した。[初回の実行記録](../runs/songbird-chirps-terminal-numerator-44100-20261123-a/manifest.json)・[再実行の記録](../runs/songbird-chirps-terminal-numerator-44100-20261123-repeat/manifest.json)・[CSV照合スクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-terminal-numerator-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_terminal_numerator_44100.py songbird-chirps-terminal-numerator-44100-local
```

## 気管側の首部流量で最初の差を切り分ける

固定上流の `songbird::create` は、気管の最後のセルから口腔食道腔へ、断面0.03 cm²、長さ0.25 cmのポートを接続する。正の流量は気管から腔へ向かい、今回の押鍵は音高上昇で腔を縮めるため、初期には逆向きに流れる。`Songbird::sample` が鳴管の弁面積を更新してから `AirwayNetwork::step` を呼ぶ。気道では断面を当該標本まで補間し、枝の流量を求めてから節点圧を進める。首部の更新には当該標本の断面と、一つ前の気管端圧・腔圧を使う。[上流の首部の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)

首部の慣性 `L`（圧力を流量の時間変化率で割った単位）は首部自身の慣性と両端セルの半分ずつの和。粘性抵抗 `R`（圧力を流量で割った単位）は首部自身の寸法で決まる。二次損失係数 `K` は入り口での縮流と、流れの下流側へ出る噴流の拡大を加えた値で、逆流時は気管側の面積を使う。駆動圧は両端圧の差と乱流による圧力、持ち越し運動量の時間換算の和。線形項を `L/dt + R` とし、`K |U| U + (L/dt + R) U = 駆動圧` を解く。上流は持ち越す運動量を別に保持し、慣性が減った場合は新しい慣性と前回流量の積に置き換える。再実装は前回と今回の慣性の小さい方および前回流量から同じ量を求める。どちらも新しい流量（cm³/s）を気管側で差し引き、腔側で加える。上流の狭窄試験は、断面が狭まるときの定常流量を噴流損失を含むベルヌーイの式と比較している。[上流の係数と運動量](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1003)・[定常流の比較試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[再実装の枝の更新](../crates/vocal-core/src/airway/network.rs#L81)

通常CLIの任意指定 `observe_oec_neck` は、気管端の圧力・断面・セル長、首部の断面・乱流圧をCSVの末尾に加える。腔圧と腔面積は従来の列を使い、`observe_oec` で腔長と首部流量を併せて得る。既存の `trachea_pressure_dyn_cm2` は鳴管側の最初の気管セルを表す。固定上流は公開の気道観測を使い、両端の同じ位置を採る。前回の先端負荷まで揃えた隔離ビルドの6差分を適用し、押鍵後16点を再収録した。[事前登録](../cases/songbird-chirps-oec-neck-44100.json)・[通常CLIの観測指定](../crates/vocal-cli/src/songbird_case.rs#L24)・[上流の採取入口](../tools/upstream_songbird_airway_probe.rs#L185)

| 制御間隔 | 首部流量の初差 | 気管端圧の初差 | 腔圧の初差 |
| --- | ---: | ---: | --- |
| 235点 | 4点後に1 ULP | 4点後 | 窓内で一致 |
| 256点 | 5点後に1 ULP | 5点後 | 窓内で一致 |
| 追従0 | 全点0 | 全点0 | 全点0 |

両条件とも、最初に分かれた標本の一つ前では気管端圧、腔圧、流量が同じだった。235点制御ではこのとき首部と隣接セルを合わせた慣性が増えている。前回の慣性と流量を用い、候補の `(L_prev/dt) × U_prev` を上流の `(L_prev × U_prev) × fs` に替えると、駆動圧と流量が上流に一致した。256点制御でも同じ単独置換で復元した。逆流側の二次損失係数も1 ULP異なった。この係数だけを上流の値に替えた計算では、最初の流量差は残った。首部の流量更新に続いて同じ標本の気管端圧も分かれ、腔圧は16点とも一致した。[最初の差の項別置換](../runs/songbird-chirps-oec-neck-44100-20261123-repeat/summary.json)・[各点の再計算](../runs/songbird-chirps-oec-neck-44100-20261123-repeat/artifacts/neck-flow-replay.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。2つの作業ディレクトリから各27判定が通り、両版の首部流量を合計96点ビット照合した。既存の観測列は保存済みの系列の先頭と一致し、通常CLIでも観測指定を追加した実行の既存列は指定なしと一致した。両実行の要約、CSV、再計算系列、再実装バイナリのSHA-256は一致した。独立照合では上流の採取プログラムの実行ファイルまで同じハッシュを要求して初回に停止した。シンボル表の実行先パスを正規化すると一致し、機械語セクションもバイト一致した。各生成ファイルは各実行のマニフェストに従って個別に検証した。308入力と28出力を照合し、採取物計2,593,490バイトをRTL9210B-CGへ保存した。現行Rustの52試験と固定上流の気道6試験も通過した。[初回のマニフェスト](../runs/songbird-chirps-oec-neck-44100-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/songbird-chirps-oec-neck-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-neck-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_oec_neck_44100.py songbird-chirps-oec-neck-44100-local
```

## 気管側首部の前回運動量を連続描画で揃える

上流の `songbird::create` から首部の `add_port`、`Songbird::sample` から `AirwayNetwork::step` へ進む。首部で持ち越す状態は前回の慣性と運動量で、断面の動きで慣性が減る場合は今回の慣性と前回流量を掛けて持ち越し量を制限する。枝はこの量を `fs` で時間換算し、前回の気管端圧と腔圧の差、乱流の圧力源と足して駆動圧（dyn/cm²）を求める。二次損失を含む流量（cm³/s）を解いた後、前回状態を更新し、気管端から差し引いて腔に加える。再実装の通常入口は `vocal-cli render` から `songbird_case::run`、`SongbirdAirway::step`、ネットワークの `Branch::step` へ進む。上流の定常狭窄試験は流量をベルヌーイの式と照合し、閉鎖試験は開口が狭い条件の圧力と流量が発散しないことを確認する。[上流の首部接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の運動量の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L16)・[再実装の枝更新](../crates/vocal-core/src/airway/network.rs#L189)

前回の6差分を復元した隔離ビルドを対照にする。実験版では、既存の `(L_carried × U_prev) × (1/dt)` を使う枝に、気管側の首部1枝だけを加える。線形慣性係数や二次損失の式は対照と同じ。今回の176.4 kHzでは `1/dt` がサンプルレートにビット一致する。差は首部流量を決めた標本にまず現れ、その標本の圧力更新を経由する。くちばし入口の枝が新しい腔圧を参照するのは次の標本なので、最後のセルに届く最短の時刻は首部流量の変更から6内部点後になる。前回の16点で確認した局所置換を、235点・256点の両制御と追従0の64点の連続描画に広げる。[事前登録](../cases/songbird-chirps-oec-neck-momentum-44100.json)・[前回の局所置換](../runs/songbird-chirps-oec-neck-44100-20261123-repeat/summary.json)

| 観測点 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| 首部流量 | 4 → 6 | 5 → 25 |
| 気管端圧 | 4 → 6 | 5 → 13 |
| 腔圧 | 53 → 38 | 45 → 45 |
| くちばし入口流量 | 53 → 53 | 18 → 18 |
| 先端圧 | 60 → 60 | 23 → 23 |
| 放射流量 | 60 → 60 | 24 → 24 |
| 放射微分 | 9 → 9 | 11 → 11 |

表は、固定上流と最初に分かれた内部サンプルを、対照から実験版の順に示す。押鍵は0点とする。235点制御の6点後では、分子にあたる駆動圧は上流と一致し、線形係数中の慣性項 `L/dt` が `L × fs` と分かれた。慣性項だけを置換すると首部流量の3 ULPの差が消えた。38点後の腔圧の差は、同じ標本の首部流量を置換すると消えた。変更による腔圧の差はその標本で初めて現れ、くちばし全6セルの圧力・流量と放射流量は対照と全64点一致した。[差分と局所置換](../runs/songbird-chirps-oec-neck-momentum-44100-20261123-repeat/summary.json)

256点制御の首部流量は24点後まで上流と一致した。気管端圧は13点後から差が残り、24点後の気管端圧だけを上流の値に替えると25点後の首部流量が復元した。実験版と対照を比べると、首部流量と気管端圧は5点後、腔圧は54点後、くちばし入口流量は55点後、放射流量は61点後に初めて分かれた。追従0は全版で観測した圧力と流量が0だった。[首部の再計算系列](../runs/songbird-chirps-oec-neck-momentum-44100-20261123-repeat/artifacts/neck-momentum-replay.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` から各60判定が通り、3条件・3版で首部流量、腔圧、先端圧、放射流量と微分を各576点ビット照合した。前回の16点は上流・対照ともにバイト一致した。2実行の314入力と36出力を照合し、採取物計4,600,764バイトをRTL9210B-CGへ保存した。要約、CSV、差分、再計算系列と候補の両バイナリのSHA-256が一致した。ビルドログと上流の採取実行ファイルのハッシュは実行ごとに異なり、上流実行ファイルの機械語部分はバイト一致した。現行Rustの52試験と固定上流の気道6試験も通過した。[初回のマニフェスト](../runs/songbird-chirps-oec-neck-momentum-44100-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/songbird-chirps-oec-neck-momentum-44100-20261123-repeat/manifest.json)・[独立検算結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-neck-momentum-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_oec_neck_momentum_44100.py songbird-chirps-oec-neck-momentum-44100-local
```

## 気管側首部の線形慣性項を連続描画で揃える

上流の `songbird::create` が作る気管端から口腔食道腔へのポートを、`Songbird::sample` が呼ぶ `AirwayNetwork::step` まで追った。断面をその標本の値まで補間した後、首部自身と両側の半セルの慣性を足し、線形係数 `B = L × fs + R` を作る。上流は前回の節点圧と持ち越し運動量から駆動圧 `D` を求め、流量の向きに応じた二次損失 `K` を使って `sign(D) × 2|D| / (B + √(B² + 4K|D|))` を解く。`B` は圧力を体積流量で割った単位で、新しい流量（cm³/s）を両側の収支に入れてから圧力を更新する。上流の気道試験は、狭窄の定常流をベルヌーイの式と照合し、閉鎖に近い三分岐で作業レートの安定性を確認する。[鳴禽のポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の線形係数と枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1003)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L16)

首部の持ち越し運動量を揃えた前回の7差分を適用し、`vocal-cli render` で対照を復元する。隔離ビルドの実験版は首部1枝に対して、`Branch::step` の線形慣性項の乗算を選ぶ。前回の固定上流64点は保存時のハッシュを照合して使う。押鍵6点後の差の除去を予測し、235点制御、256点制御、追従0の64点で流量と節点圧の初差を調べる。[事前登録](../cases/songbird-chirps-oec-neck-linear-44100.json)・[前回の固定上流と実験版](../runs/songbird-chirps-oec-neck-momentum-44100-20261123-repeat/manifest.json)

| 観測点 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| 首部流量 | 6 → 14 | 25 → 25 |
| 気管端圧 | 6 → 12 | 13 → 13 |
| 腔圧 | 38 → 53 | 45 → 45 |
| くちばし入口流量 | 53 → 53 | 18 → 18 |
| 先端圧 | 60 → 60 | 23 → 23 |
| 放射流量 | 60 → 60 | 24 → 24 |
| 放射微分 | 9 → 9 | 11 → 11 |

表は固定上流との最初の差を、押鍵を0とした内部点で、対照から実験版の順に示す。235点制御の6点後の流量差は消えた。気管端圧には12点後に次の差が現れ、13点後の気管端圧だけを上流から与えると14点後の首部流量が一致した。このとき腔圧と前回の首部流量、現在の慣性は上流と一致している。53点後の腔圧は、腔からくちばしへ出る流量を上流の値へ置き換えると一致した。256点制御では前回と同じく、24点後の気管端圧だけの置換で25点後の首部流量を復元した。[要約の局所置換](../runs/songbird-chirps-oec-neck-linear-44100-20261123-repeat/summary.json)

対照と実験版を直接比べると、235点制御の首部流量と気管端圧は6点後、腔圧は38点後に分かれた。256点制御では首部流量と気管端圧が33点後から異なった。どちらの制御も、くちばし6セルの圧力・流量と放射の観測列は全64点で対照と一致した。追従0は両ビルドと固定上流で無励振だった。次の差の起点は首部の流量より先に分かれる気管端圧なので、気管末端に入る直列枝流量と壁流量を追加で観測すると切り分けられる。[保存した全系列とパッチ](../runs/songbird-chirps-oec-neck-linear-44100-20261123-repeat/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各56判定が通り、首部流量、腔圧、先端圧、放射流量と微分を各576点ビット照合した。対照は前回の実験版の全CSVをバイト再現した。共通化した比較処理では、前回の3条件の要約と再計算系列、46判定を再現した。先行要約の照合で最初にPythonのタプルと保存JSONの配列を直接比べて停止し、JSONで同じ形式に揃えて一致を確認した。2実行で要約、CSV、差分と両候補バイナリのSHA-256が一致した。実行ごとに変化したCargoログも各マニフェストに照合した。316入力と20出力を確認し、採取物2,576,042バイトをRTL9210B-CGへ保存した。上流の気道6試験は通過した。[初回の実行記録](../runs/songbird-chirps-oec-neck-linear-44100-20261123-a/manifest.json)・[再実行の記録](../runs/songbird-chirps-oec-neck-linear-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-oec-neck-linear-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_oec_neck_linear_44100.py songbird-chirps-oec-neck-linear-44100-local
```

## 気管末端の圧力を直列枝と壁の流量に分ける

上流の `songbird::create` は断面0.045 cm²の気管の各セルに軟壁パラメータを付け、最後のセルを首部経由で口腔食道腔へ接続する。`Songbird::sample` が呼ぶ `AirwayNetwork::step` は、前回の圧力で枝流量を進め、次に同じ前回圧を使って壁を進める。壁は面積あたりの質量0.6 g/cm²、抵抗1,000 dyn·s/cm³、剛性10⁶ dyn/cm³を持ち、半ステップの壁速度と変位を保持する。新しい壁速度にセルの壁面積を掛けた体積流量を、節点からの流出とする。気管末端の断面は今回の押鍵前後で一定で、この節点に入る体積変化の注入量は0。圧力（dyn/cm²）の更新は `P' = P + (dt/C) × ((Q_in − Q_neck) − Q_wall)` で、`C` はセル容積を空気の体積弾性率で割った値。流量の単位はcm³/s。上流の軟壁を含む一様管試験は、時間領域のインパルス応答と周波数領域の共鳴を比較する。[鳴禽の気管と首部](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[壁の係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs#L30)・[壁と節点圧の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[軟壁のインパルス応答試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

通常CLIと固定上流の採取入口に任意指定 `observe_trachea_end_balance` を加える。気管の一つ手前のセル圧、最後の直列枝からの流入、端セルの壁流量・変位、その直列枝の乱流圧を追加で取得する。`observe_oec_neck` の気管端圧と断面、`observe_oec` の首部流量と併せて節点圧を再計算する。首部の線形慣性項まで揃えた8差分の隔離ビルドと固定上流で、235点制御、256点制御、追従0の押鍵後16点を比較する。[事前登録](../cases/songbird-chirps-trachea-end-balance-44100.json)・[通常CLI](../crates/vocal-cli/src/songbird_case.rs#L24)・[上流の採取入口](../tools/upstream_songbird_airway_probe.rs)

| 固定上流と最初に分かれた観測点 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| 気管の壁流量 | 2 | 2 |
| 気管端へ入る直列枝の流量 | 8 | 13 |
| 気管端の一つ手前のセル圧 | 8 | 13 |
| 気管端圧 | 12 | 13 |
| 首部への流出 | 14 | 窓内で一致 |
| 気管端の壁変位 | 窓内で一致 | 窓内で一致 |

押鍵を0点とする。235点制御の12点後、256点制御の13点後で、直前の気管端圧と同じ標本の首部流量は両版で一致した。壁流量と手前から入る流量はそれぞれ異なった。直列枝流量だけを上流の値に置き換えると、最初の圧力差1 ULPが両条件で消えた。壁流量を単独で置き換えた圧力は候補の値と一致した。追従0では観測した圧力・流量・壁変位が0を保った。[圧力収支の置換](../runs/songbird-chirps-trachea-end-balance-44100-20261123-repeat/summary.json)

直列枝流量が最初に分かれた235点制御の8点後と256点制御の13点後では、直前の両端圧と枝流量が一致した。線形係数は丸め後も一致し、前回運動量の換算項を `(L/dt) × U_prev` から `(L × U_prev) × fs` に替えると、流量の1 ULP差が消えた。壁流量は `2√(πA) × Δx` と `2√π × √A × Δx` の丸め差で分かれ、壁質量の時間換算はこのレートで一致した。壁面積は、変位と速度を更新した後に流量へ換算する段で使う。壁変位は、圧力の差が出た後も16点の観測窓で一致した。[直列枝の運動量と壁の再計算](../runs/songbird-chirps-trachea-end-balance-44100-20261123-repeat/artifacts/trachea-end-replay.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各47判定が通り、両版・3条件の気管端圧、壁流量、壁変位、直列枝流量を各96点ビット照合した。新しい列を除いた系列は先行実行の当該区間とバイト一致し、通常CLIで観測を有効にしても既存列は一致した。再実行で要約、CSV、再計算系列と候補バイナリのSHA-256が一致した。上流の採取実行ファイルは全体のハッシュに差があったため、機械語部分を別に照合してバイト一致を確認した。316入力・28出力を照合し、採取物2,711,250バイトをRTL9210B-CGへ保存した。現行Rustの52試験と固定上流の気道9試験が通過した。[初回の実行記録](../runs/songbird-chirps-trachea-end-balance-44100-20261123-a/manifest.json)・[再実行の記録](../runs/songbird-chirps-trachea-end-balance-44100-20261123-repeat/manifest.json)・[独立検算結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-end-balance-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_end_balance_44100.py songbird-chirps-trachea-end-balance-44100-local
```

## 気管最後の直列枝の運動量換算を連続描画で揃える

固定上流の `songbird::create` が作る気管の最後の2セルは、同じ断面0.045 cm²の直列枝で結ばれる。`Songbird::sample` の呼ぶ `AirwayNetwork::step` では、枝慣性 `L` を両端の半セルから求め、前回の両端圧の差と持ち越し運動量の時間換算を足す。この枝は断面の段差による二次損失が0で、線形係数 `L × fs + R` で駆動圧を割って体積流量（cm³/s）を得る。上流の持ち越し状態には前回の流量と慣性の積を記録する。流量を両端の収支へ入れ、壁流量を引いて節点圧（dyn/cm²）を更新する。上流の軟壁つき一様管の試験では、時間応答の共鳴を周波数領域のモデルと照合する。[上流の気管形状](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の直列枝](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L968)・[運動量と流量の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[一様管の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

前回の8差分の隔離Rustビルドを基準に、気管の最後の直列枝を既存の `(L × U_prev) × (1/dt)` を使う対象へ加える。通常の `vocal-cli render` を使い、首部の線形慣性項や壁流量は対照と同じ式を使う。枝の変更は同じ標本に両端の圧力へ反映され得る。首部の枝と気管端の軟壁がその圧力を読むのは次の標本で、そこから腔圧とくちばしへ伝わる。235点制御、256点制御、追従0で64内部点の圧力と流量を採り、既存の16点と独立計算に照合する。[事前登録](../cases/songbird-chirps-trachea-end-momentum-44100.json)・[前回の流量の局所置換](../runs/songbird-chirps-trachea-end-balance-44100-20261123-repeat/summary.json)

| 固定上流との初差 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| 気管端の一つ手前のセル圧 | 8 → 12 | 13 → 13 |
| 最後の直列枝からの流入 | 8 → 13 | 13 → 14 |
| 気管端圧 | 12 → 13 | 13 → 14 |
| 首部流量 | 14 → 14 | 25 → 16 |
| 口腔食道腔圧 | 53 → 53 | 45 → 45 |
| 放射流量 | 60 → 60 | 24 → 24 |

表の数値は押鍵を0とした内部点で、対照から実験版の順に示す。両条件で、直列枝流量の初差が出る一つ前の標本は、気管端圧と枝流量が上流と一致した。残る入力差は手前側の圧力にあり、駆動圧の圧力差項だけを上流に替えると流入が一致した。同じ標本の気管端圧も、流入だけの置換で上流と一致した。256点制御では15点後の気管端圧を置換すると、16点後に現れた首部流量差を復元できた。[最初の差と置換](../runs/songbird-chirps-trachea-end-momentum-44100-20261123-repeat/summary.json)

実験版を対照と比較すると、首部流量は235点制御で28点後、256点制御で16点後に分かれた。両条件とも腔圧、くちばし全6セル、放射流量と微分は64点すべて一致した。固定上流との壁流量の初差は両条件で2点後のまま、追従0の圧力・流量は全版で0だった。[連続描画と再計算](../runs/songbird-chirps-trachea-end-momentum-44100-20261123-repeat/artifacts/trachea-momentum-replay.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` から各103判定を通過し、3版・3条件の気管端流入、壁流量・変位、気管端圧、首部流量、腔圧、先端圧と放射の系列を各576点ビット照合した。固定上流と対照の先頭16点は既存CSVにバイト一致した。共通の比較処理は先行の46判定を、気管の再計算処理は先行6系列と流入の局所置換を再現した。2実行の324入力と36出力を照合し、採取物5,182,400バイトをRTL9210B-CGに保存した。要約、観測CSV、差分、再計算系列と候補の両バイナリが一致した。上流の採取実行ファイルは全体のハッシュに差があったため、機械語部分を照合して一致を確認した。固定上流の気道9試験が通過した。[初回マニフェスト](../runs/songbird-chirps-trachea-end-momentum-44100-20261123-a/manifest.json)・[再実行マニフェスト](../runs/songbird-chirps-trachea-end-momentum-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-end-momentum-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_end_momentum_44100.py songbird-chirps-trachea-end-momentum-44100-local
```

## 気管端の一つ手前のセルで圧力収支を照合する

固定上流の `songbird::create` は断面0.045 cm²の気管を構成し、`Songbird::sample` から `AirwayNetwork::step` を呼ぶ。176.4 kHzの気管は16セルで、今回の対象は0始まりのセル14。セル13からの流入を足し、セル15へ出る流量と壁流量を差し引く。両側の枝は前回の節点圧と運動量から同じ標本の体積流量（cm³/s）を計算し、軟壁も前回の圧力から半ステップ速度と変位を更新する。その後、節点圧（dyn/cm²）に `(dt/C) × ((Q_in − Q_out) − Q_wall)` を加える。断面とセル長が一定なので、容積変化による注入量は0で、`C = A × Δx/(ρc²)` を使う。上流の軟壁付き一様管の試験は、この気道更新の時間応答を周波数領域の共鳴と照合する。[気管の生成と入力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の流量収支と節点圧](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1040)・[軟壁の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

通常CLIと固定上流の採取入口に、0始まりの内部セル番号を配列で渡す `observe_trachea_interior_cells` を加えた。端点は隣接する枝の構成が異なるため、内部の直列接続2本を持つセルに指定を限る。対象セルと一つ上流の圧力、両枝の流量、壁流量と変位、面積と長さ、流入枝の乱流圧を出力する。従来の列に加えてセル14だけを採り、圧力収支の再計算では従来の気管端用に `neck_outflow` と呼んだ項へ、セル14から15へ出る直列枝流量を渡す。先行の9差分を適用した隔離Rustビルドを通常の `vocal-cli render` で実行し、固定上流・候補の235点制御、256点制御、追従0を16点ずつ採る。[事前登録](../cases/songbird-chirps-trachea-interior-balance-44100.json)・[通常CLI](../crates/vocal-cli/src/songbird_case.rs#L27)・[上流の採取入口](../tools/upstream_songbird_airway_probe.rs)

| 固定上流との初差 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| セル13の圧力 | 9 | 10 |
| セル14へ入る流量 | 9 | 12 |
| セル14の壁流量 | 3 | 3 |
| セル14の圧力 | 12 | 13 |
| セル15へ出る流量 | 13 | 14 |
| セル14の壁変位 | 窓内で一致 | 窓内で一致 |

押鍵を0とする。セル14の最初の圧力差はいずれも1 ULPで、直前のセル14の圧力と同じ標本の流出量は一致した。流入量だけを上流値へ置き換えると圧力差が消え、壁流量だけの置換では差が残った。235点制御の9点後に出た流入差は、直前の両端圧と流量が等しい状態から、持ち越し運動量の `(L/dt) × U_prev` を `(L × U_prev) × fs` に替えると復元した。256点制御では、セル13の圧力が10点後に先に分かれ、11点後の圧力を置換して12点後の流入差を再現した。追従0では観測した圧力・流量・壁変位が0だった。[圧力と流入の局所置換](../runs/songbird-chirps-trachea-interior-balance-44100-20261123-repeat/summary.json)・[気管の各点の再計算](../runs/songbird-chirps-trachea-interior-balance-44100-20261123-repeat/artifacts/trachea-interior-replay.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。最初の実行は、CSVから列を抜き出した構造化配列のdtypeに元の列間隔が残り、名前の再割り当てで停止した。必要列を詰め直してから割り当て、保存済みの2系列で9列の値がビット一致することを確認した。修正後は研究ワークスペースと `/tmp` で各59判定を通過し、3条件と両版の圧力・壁流量・壁変位・流入量を各96点ビット照合した。通常CLIと固定上流の採取入口で、複数セルの出力順、従来列の一致、端点・範囲外・重複指定の拒否を確認した。初回を含む480入力と38出力を照合し、採取物3,895,868バイトをRTL9210B-CGに保存した。修正後の要約、CSV、再計算系列、候補バイナリが一致した。上流の実行ファイルは機械語領域の一致を確認した。現行Rustの52試験と固定上流の気道9試験が通過した。[初回の停止記録](../runs/songbird-chirps-trachea-interior-balance-44100-20261123-a/manifest.json)・[修正後の再実行](../runs/songbird-chirps-trachea-interior-balance-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-interior-balance-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_interior_balance_44100.py songbird-chirps-trachea-interior-balance-44100-local
```

## 気管セル13から14へ入る枝の運動量換算を揃える

固定上流の `songbird::create` が作る気管は、176.4 kHzで同じ断面の16セルに分かれる。`Songbird::sample` から `AirwayNetwork::step` に入り、セル13と14を結ぶ枝では直列の両半セルの慣性 `L` と粘性抵抗 `R` を用いる。同じ断面がつながるため、この枝の方向別の二次損失は0。前回の両端圧の差と持ち越し運動量 `L × U_prev` の時間換算の和が駆動圧で、線形係数 `L × fs + R` で割ると体積流量（cm³/s）になる。上流では新しい流量と慣性の積を次回用に記録し、同じ標本でセル13の収支から流量を引き、セル14の収支に足す。軟壁流量を引いた後の節点圧は、次の標本で隣の直列枝が読む。気管の軟壁を含む計算は、上流の一様管試験がインパルス応答と周波数領域の共鳴の一致を確認している。[上流の気管形状](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の直列枝係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L952)・[運動量と節点の収支](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[気道の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

前回の9差分を適用した隔離Rustビルドを対照とし、`Branch::step` が `(L × U_prev) × (1/dt)` を選ぶ気管内の枝に、セル13から14へ入る枝1本を加える。線形係数や壁の式は同じ状態から評価する。セル15への流入が変わるのは早くても次の標本、首部の流量はその次の標本。235点制御、256点制御、追従0を通常の `vocal-cli render` で64内部点描画し、気管セル14・15の圧力と壁、首部・くちばし・放射を独立計算と照合する。[事前登録](../cases/songbird-chirps-trachea-interior-momentum-44100.json)・[前回の局所置換](../runs/songbird-chirps-trachea-interior-balance-44100-20261123-repeat/summary.json)

| 固定上流との初差 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| セル13圧 | 9 → 11 | 10 → 10 |
| セル14への流入 | 9 → 12 | 12 → 12 |
| セル14圧 | 12 → 12 | 13 → 13 |
| セル15圧 | 13 → 13 | 14 → 14 |
| 首部流量 | 14 → 14 | 16 → 16 |
| 腔圧 | 53 → 53 | 45 → 45 |
| 放射流量 | 60 → 60 | 24 → 24 |

押鍵を0とし、対照から実験版の順に示した。235点制御ではセル14への流入が9〜11点後で上流と一致した。12点後の流入差では、前回のセル14圧と流入は一致し、セル13圧に差が残った。11点後のセル13圧を駆動圧へ反映させると流入を復元でき、その流入を12点後のセル14の収支に入れるとセル14圧も上流と一致した。256点制御では、前回に確認した11点後のセル13圧と12点後の流入差の関係が残った。[最初の圧力・流入差の置換](../runs/songbird-chirps-trachea-interior-momentum-44100-20261123-repeat/summary.json)

実験版と対照を比べると、首部流量は235点制御で27点後、256点制御で25点後に分かれた。腔圧、くちばし6セルの圧力・流量、放射流量と微分は両条件で全64点一致した。追従0は全版で0だった。次はセル13で生じる圧力差を調べるときに、既存の内部観測にセル13を加え、下流と同時に比較できる。[2セル・3版の再計算](../runs/songbird-chirps-trachea-interior-momentum-44100-20261123-repeat/artifacts/trachea-interior-momentum-replay.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各157判定を通過した。気管セル14と15の流入・圧力・壁流量・変位は各576点、首部と腔、先端と放射も各576点を独立計算とビット照合した。先行の気管内部セルの再計算6系列を共通の観測変換で再現した。固定上流と対照は先行16点にバイト一致し、2実行のCSV、要約、差分、再計算系列、両候補バイナリが一致した。上流採取実行ファイルの機械語部分も照合した。326入力と36出力を検証し、採取物7,092,508バイトをRTL9210B-CGに保存した。固定上流の気道9試験が通過した。[初回のマニフェスト](../runs/songbird-chirps-trachea-interior-momentum-44100-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/songbird-chirps-trachea-interior-momentum-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-interior-momentum-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_interior_momentum_44100.py songbird-chirps-trachea-interior-momentum-44100-local
```

## セル13と14を同時に観測しセル13圧の起点を調べる

上流の `songbird::create` は気管を均一断面と壁負荷を持つ管として組み立て、`Songbird::sample` が気道を1標本進める。気管内では直列枝の前回流量と慣性から持ち越し運動量を決め、前回の節点圧の差を足して新しい流量（cm³/s）を解く。流量を枝の上流節点の収支から引き、下流節点の収支に足す。その後、前回の圧力で進めた壁の流量を引き、コンプライアンス `C = A × Δx/(ρ c²)` から圧力 `p' = p + (dt/C) × ((Q_in − Q_out) − Q_wall)`（dyn/cm²）を求める。今回のセル13と14は隣接し、セル13側の流出とセル14側の流入は同じ枝の流量である。軟壁を含む上流の一様管試験では時間領域と周波数領域の共鳴を照合する。[気管の生成と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝の流量、壁、節点の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[一様管のインパルス応答試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

前回の10差分を適用した隔離Rustビルドを通常の `vocal-cli render` で描画する。既存のセル14に続けてセル13を `observe_trachea_interior_cells` へ指定し、従来の列をCSVの先頭から照合できるようにする。16点の局所計算では、セル14への流入に、前回揃えた持ち越し運動量の乗算を使う。セル13への流入では対照の除算を維持する。共通の計測CLIにケースファイルを渡し、過去の実行マニフェストが指定したパッチを記録順に適用する。[事前登録](../cases/songbird-chirps-trachea-cell13-balance-44100.json)・[前回の実行条件](../runs/songbird-chirps-trachea-interior-momentum-44100-20261123-repeat/manifest.json)

| 固定上流と最初に分かれた観測点 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| セル12圧 | 11 | 10 |
| セル13への流入 | 11 | 10 |
| セル13圧 | 11 | 10 |
| セル13から14へ流れる量 | 12 | 12 |
| セル13の壁流量 | 4 | 4 |
| セル13の壁変位 | 窓内で一致 | 11 |
| セル14圧 | 12 | 13 |

押鍵を0点とした。セル13圧が最初に分かれた標本で、直前の圧力とセル14への流出量は両版で一致した。セル12からの流入量だけを上流の値に替えると両条件で圧力の1 ULP差が消えた。壁流量だけを置き換えた場合は差が残った。セル13の流出とセル14の流入は、同じ枝を読んでいることを全点でビット照合した。[セル13と14の圧力収支](../runs/songbird-chirps-trachea-cell13-balance-44100-20261123-repeat/summary.json)

235点制御の11点後と256点制御の10点後でセル13への流入が最初に分かれたとき、直前のセル12圧・セル13圧と流量は一致していた。前回運動量の換算だけを `(L/dt) × U_prev` から `(L × U_prev) × fs` に替えると、流入の1 ULP差が消えた。その流入を使うと同じ標本のセル13圧も上流に一致する。セル12圧もこの標本で初めて分かれ、枝が参照する圧力はその一つ前の値なので、同時に生じたセル12圧差はその標本の枝入力に含まれない。追従0は両セルとも無励振だった。[両セルの再計算](../runs/songbird-chirps-trachea-cell13-balance-44100-20261123-repeat/artifacts/trachea-interior-replay.json)

最後の直列枝から二つ上流まで、前回運動量の時間換算で最初の差が出る条件を確認した。次は同じ換算を、一様断面の気管内の全15直列枝へ適用する対照を登録し、セル13から放射までどこまで差が消えるかを連続描画で測る。壁流量の面積換算、鳴管の弁、および首部の処理は同じ条件で比較できる。[最後の枝の比較](#気管最後の直列枝の運動量換算を連続描画で揃える)・[セル14への枝の比較](#気管セル13から14へ入る枝の運動量換算を揃える)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` から各102判定が通過し、セル13・14の圧力、流入、壁流量・変位を各96点ずつビット照合した。共通化した解析で先行ケースの6系列と36判定も再現した。要約、CSV、再計算系列と候補バイナリのSHA-256が一致した。ビルドログと上流採取実行ファイルは実行ごとにハッシュが異なり、上流実行ファイルの機械語部分は一致した。322入力と28出力を確認し、採取物3,180,380バイトをRTL9210B-CGへ保存した。上流の気道9試験は通過した。[初回の実行記録](../runs/songbird-chirps-trachea-cell13-balance-44100-20261123-a/manifest.json)・[再実行の記録](../runs/songbird-chirps-trachea-cell13-balance-44100-20261123-repeat/manifest.json)・[CSVの独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-cell13-balance-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_interior_balance_44100.py \
  songbird-chirps-trachea-cell13-balance-44100-local --case cases/songbird-chirps-trachea-cell13-balance-44100.json
```

## 気管内の全直列枝で運動量換算を揃える

固定上流の `songbird::create` が作る気管は、176.4 kHzでは長さ0.225 cm、断面0.045 cm²の16セルを15本の直列枝でつなぐ。`Songbird::sample` が呼ぶ `AirwayNetwork::step` では、前回の両端圧と前回運動量の時間換算の和を駆動圧とし、この一定断面では線形係数 `L × fs + R` で割って枝流量（cm³/s）を求める。新しい流量と慣性の積を持ち越し、各節点で流入・流出と壁流量を合わせて圧力（dyn/cm²）を更新する。上流の試験は、軟壁を含む一様管の時間応答と周波数領域モデルの共鳴を照合している。[上流の気管と鳴管の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[直列枝と前回運動量](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L965)・[流量と圧力の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

前回の10差分付きの隔離Rustビルドを対照として復元し、実験版では `(L × U_prev) × (1/dt)` を使う気管内の範囲を全15直列枝へ広げる。気管の外の枝、線形係数、壁の式はいずれも対照と同じ。既存の気管端とセル14・13のCSV列に残りの内部セルの観測列を加え、先行16点を保存済みの系列と照合する。235点制御、256点制御、追従0を64点ずつ連続描画し、全直列枝の流量と、気管端および内部14セルの圧・壁流量・変位を再計算する。全セルの観測CSVと判定を保存し、再計算の中間値はセル13・14・15を残す。[事前登録](../cases/songbird-chirps-trachea-all-momentum-44100.json)・[前回の局所置換](../runs/songbird-chirps-trachea-cell13-balance-44100-20261123-repeat/summary.json)

| 固定上流との初差 | 235点制御 | 256点制御 |
| --- | ---: | ---: |
| 気管内で最初に分かれた圧力 | 11 → 22 | 9 → 27 |
| 気管内で最初に分かれた直列枝流量 | 11 → 23 | 9 → 28 |
| セル13への流入 | 11 → 31 | 10 → 37 |
| セル14圧 | 12 → 29 | 13 → 39 |
| 気管端圧 | 13 → 34 | 14 → 40 |
| 首部流量 | 14 → 34 | 16 → 42 |
| 腔圧 | 53 → 38 | 45 → 45 |
| 放射流量 | 60 → 60 | 24 → 24 |

表は押鍵を0とした内部点で、対照から実験版の順に示す。実験版の気管内で最初に残った圧力差は、両条件とも鳴管に接続するセル0に移った。同じ前回圧から、流出を引き、左と右の鳴管からの流入を順に足し、壁流量を引いて更新すると、観測した圧力を両版でビット再現した。左鳴管側の流量だけを上流から与えると、235点制御の22点後の2 ULP、256点制御の27点後の1 ULPの圧力差が消えた。左鳴管側の流量自体が最初に分かれたのは19点後と18点後だった。[セル0の初差と独立した圧力更新](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-all-momentum-20261123.json)

235点制御のセル13圧には30点後に差が残り、同じ標本のセル14へ出る流量だけを置換して上流に一致した。31点後のセル13への流入は直前のセル13圧の差で復元できた。首部流量は34点後に初めて分かれ、その残差は現在の慣性から得た線形係数の項を上流値へ置換して消えた。一様気管の換算順が揃った後も、235点制御では腔圧の最初の差が53点後から38点後へ早まった。両条件の放射流量と微分は対照と全64点一致し、追従0は無励振を保った。[連続描画と局所置換](../runs/songbird-chirps-trachea-all-momentum-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の2回で各859判定が通過し、全15直列枝の流量を各576点、合計8,640点ずつ独立計算とビット照合した。固定上流と候補の対照を前回の16点に照合し、従来の1枝を比較するケースの3描画設定も再現した。2実行の要約、CSV、再計算系列、差分、候補の両バイナリが一致した。ビルドログと上流実行ファイルは実行ごとにハッシュが異なり、上流採取の実行ファイルは機械語部分が一致した。独立照合の補助スクリプトはCSV読み込み関数名の誤記で初回に停止し、修正後に328入力・36出力の照合とセル0圧の置換検証を完了した。採取物11,631,244バイトをRTL9210B-CGへ保存した。固定上流の気道9試験は通過した。[初回のマニフェスト](../runs/songbird-chirps-trachea-all-momentum-44100-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/songbird-chirps-trachea-all-momentum-44100-20261123-repeat/manifest.json)・[独立照合のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-all-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_interior_momentum_44100.py \
  songbird-chirps-trachea-all-momentum-44100-local --case cases/songbird-chirps-trachea-all-momentum-44100.json
```

## 左鳴管ポートの慣性を気管支側の半セルまで分解する

固定上流の `songbird::create` は左気管支の最後のセルと気管の最初のセルを、長さ0.08 cm、入口損失係数0.5、出口損失係数1.0のポートで結ぶ。`Songbird::sample` が `SyrinxLabia::next` の開口率に最大面積0.03 cm²を掛けてから気道を進める。面積が `2×10⁻⁴ cm²` を下回ると枝の流量と持ち越し運動量を0にする。開口中はポート自身の慣性と両側の半セル慣性を足す。慣性が減る標本では今回の慣性と前回流量を掛けて運動量を制限し、慣性が増える標本では前回の積を使う。両側の前回圧力差とその運動量の時間換算が駆動圧（dyn/cm²）、`L × fs + R` が線形係数で、流れの向きに応じた二次損失と合わせて流量（cm³/s）を解く。上流の狭窄試験は、定常流量を噴流損失込みのベルヌーイの式と比較する。[鳴管ポートの接続と弁更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[ポートの係数と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L989)・[定常流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

気管内の全15枝まで揃えた前回の通常CLI描画と固定上流の同条件CSVをハッシュ照合し、押鍵後32点を再計算した。235点制御では19点後、256点制御では18点後に左ポート流量が1 ULP分かれた。両条件とも、その標本の弁面積と、直前の気管支端圧・気管入口圧・流量はビット一致した。235点制御では開口が拡大し、今回の慣性を持ち越しに使う。256点制御では開口が縮み、前回の慣性を使う。どちらも線形係数の慣性項だけを上流値に替えると、最初の流量差が消えた。235点制御と追従0で左ポートが閉じた3点は流量が0になり、追従0の圧力と流量は全32点0だった。[事前登録](../cases/songbird-chirps-left-syrinx-port-44100.json)・[前回の描画](../runs/songbird-chirps-trachea-all-momentum-44100-20261123-repeat/manifest.json)・[初差の置換結果](../runs/songbird-chirps-left-syrinx-port-44100-20261123-repeat/summary.json)

両条件で、ポート自身の慣性と気管側の半セル項は一致した。気管支側のセル長を面積で割ると `0x1.aaaaaaaaaaaaap+3`、面積の逆数を掛けると `0x1.aaaaaaaaaaaabp+3` になり、その差がポート全体の慣性にも1 ULP残った。各慣性を固定したときの `L/dt` と `L × fs` はこのレートではビット一致した。気管支側の半セル項だけを上流順に変えた慣性を線形係数へ渡すと、両条件の流量が上流に一致した。235点制御では時間換算式を二つとも変更した対照でも流量が一致した。その対照では線形係数は対照の値のままで、駆動圧が変わった。256点制御の時間換算式の変更では流量差が残った。[慣性の構成項の独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-port-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` で各26判定を通過し、3条件と両版の流量計192点をビット照合した。共通のポート係数を使う先行の首部の6系列も再現した。2実行の58入力と4出力を照合し、再計算の出力364,300バイトをRTL9210B-CGに保存した。上流の気道6試験とリアルタイム処理の3試験は通過した。デノーマルの鳴禽試験はx86_64専用で、今回のarm64では対象外だった。[初回の実行記録](../runs/songbird-chirps-left-syrinx-port-44100-20261123-a/manifest.json)・[再実行の記録](../runs/songbird-chirps-left-syrinx-port-44100-20261123-repeat/manifest.json)・[独立検算スクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-port-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=16777216 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_syrinx_port_44100.py songbird-chirps-left-syrinx-port-44100-local
```

## 左鳴管ポートの気管支側半セル慣性を連続描画で揃える

固定上流は断面更新時に `AirwayNetwork::step` でセル長と面積の逆数を掛けて半セルの項を保存する。左鳴管では左気管支末端から気管入口に向かう流量を正に取り、ポート長0.08 cmの慣性に、両端の半セル分を加える。新規の慣性は、この標本の線形係数と、開口拡大時の持ち越し運動量に使う。次の標本では前回慣性になる。候補の `SongbirdAirway::step` も先に唇の開口率から面積を更新し、`Branch::update_geometry` に前回の慣性と流量を渡す。上流の定常狭窄試験では二次損失を含む流量、三分岐の試験では節点の安定化を確認できる。[上流の半セルと枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L859)・[鳴管の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

先行11差分を隔離したRustソースに適用し、左鳴管ポートの左端半セルでだけ `length / area` を `length * area.recip()` へ切り替えた。3条件で通常の `vocal-cli render` を使った。対照CSVは先行描画をバイト再現し、固定上流CSVは登録済み版のハッシュを照合して再利用した。押鍵を0とし、内部176.4 kHzで64点を比較した。左ポートの先行初差が消えること、変更の影響が更新順から求めた最短時刻より前に出ないこと、追従0で無励振となることを事前に登録した。[事前登録](../cases/songbird-chirps-left-syrinx-half-inertance-44100.json)・[実験差分](../runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123-repeat/artifacts/left-syrinx-half-inertance.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 左鳴管流量・左気管支末端圧 | 19点 → 23点 | 18点 → 19点 | 19点／18点 |
| 気管入口圧 | 22点 → 31点 | 27点 → 39点 | 22点／27点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 54点／54点 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 55点／55点 |
| 口腔食道腔圧 | 38点 → 38点 | 45点 → 45点 | 60点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

気管入口圧は、気管の最初の直列枝への流出を引き、左、右の鳴管流量を順に加え、壁流量を引いて再計算した。体積流量（cm³/s）から圧力増分（dyn/cm²）への係数は `dt / C`。三分岐の補正下限は全開を仮定しても幾何コンプライアンスの59.8%以下で、この係数には幾何値が使われる。235点制御の31点後に残った入口圧差は左流量または右流量の単独置換で消え、256点制御の39点後は気管最初の直列枝の流量の単独置換で消えた。左鳴管の残差は、235点制御では23点後の持ち越し運動量の換算、256点制御では19点後の線形慣性の時間換算でいずれも1 ULPを再現した。弁面積および直前の両端圧と流量は両ケースで一致した。[残差と置換](../runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123-repeat/summary.json)・[独立検算の出力](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-half-inertance-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各86判定を通過した。各回で3条件・3版の左ポート流量と気管入口圧をそれぞれ576点ビット照合した。両実行で差分・CSV・要約・候補ビルドのハッシュが一致した。342入力と26出力を照合し、採取物5,324,228バイトをRTL9210B-CGに保存した。既存の左ポート局所解析は26判定と再計算JSONが従来と一致し、固定上流の気道6試験と実時間処理3試験が通過した。追加の標準ライブラリ検算では初回に汎用の空気密度0.0012 g/cm³を使って圧力照合に失敗し、両Rust版の定数0.00114 g/cm³で再実行して全576点を照合した。[初回記録](../runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-half-inertance-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_syrinx_half_inertance_44100.py \
  songbird-chirps-left-syrinx-half-inertance-44100-local
```

## 左鳴管の持ち越し運動量の時間換算を連続描画で揃える

固定上流の `Songbird::sample` は左右の弁面積を設定してから `AirwayNetwork::step` を呼ぶ。圧力差で枝を更新する前に、今回の弁面積（cm²）で慣性 `L` を計算する。前回の慣性と流量（cm³/s）は枝の状態として残す。開口が拡大して慣性が減る場合は現在の慣性と前回流量の積を取り、慣性が増す場合は前回の積をそのまま使う。選んだ持ち越し運動量にサンプルレートを掛けると圧力（dyn/cm²）になり、両端の前回圧力差へ加わる。その駆動圧と線形係数、向き別の損失から流量を解き、端点の体積収支に加える。閉鎖時は流量と運動量を0にする。上流の狭窄試験は定常流と噴流損失を、三分岐試験は節点近傍の安定性を確かめる。[鳴管の標本更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L989)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

左の気管支側半セル慣性まで揃えた先行12差分を隔離ビルドに適用した。候補の枝更新で左鳴管ポートだけを既存の運動量乗算の対象に加え、`(Lcarry / dt) × Uprev` を `(Lcarry × Uprev) × fs` に替えた。現在の慣性の時間換算は既存の式を使った。通常CLIで先行の候補CSVをバイト再現し、固定上流はハッシュ照合した保存CSVを参照した。両制御と追従0で、内部176.4 kHzの押鍵後64点を比較した。[事前登録](../cases/songbird-chirps-left-syrinx-momentum-44100.json)・[実験差分](../runs/songbird-chirps-left-syrinx-momentum-44100-20261123-repeat/artifacts/left-syrinx-momentum.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 左鳴管流量 | 23点 → 27点 | 19点 → 19点 | 23点／50点 |
| 左気管支末端圧 | 23点 → 26点 | 19点 → 19点 | 23点／51点 |
| 右鳴管流量 | 28点 → 28点 | 19点 → 19点 | 35点／64点一致 |
| 気管入口圧 | 31点 → 36点 | 39点 → 39点 | 31点／56点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 56点／64点一致 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 61点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

235点制御の23点後の左流量差は消えた。残る27点後の左流量差は、26点後の左気管支末端圧だけを置換して再現した。右流量は28点後に1 ULP分かれ、その標本では持ち越し運動量の換算だけの置換で復元した。256点制御の左流量は19点後に分かれ、現在の慣性の時間換算だけを上流に揃えて復元した。右流量も19点後に分かれ、その標本では現在の慣性と持ち越し運動量の換算項を両方置換すると復元した。実験による右への影響は235点制御の35点後に初めて現れた。追従0では圧力と流量が全標本0だった。[最初の差と置換結果](../runs/songbird-chirps-left-syrinx-momentum-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各105判定を通過した。各実行で左右ポート流量と気管入口圧をそれぞれ576点ビット照合した。別の標準ライブラリ実装で候補2版の左流量384点と、235点制御の持ち越し項、256点制御の線形項の置換を照合した。348入力と26出力をハッシュ照合し、採取物6,389,228バイトをRTL9210B-CGに保存した。従来の局所解析26判定と左半セル実験の576点の再計算は一致し、固定上流の気道・実時間処理9試験を通過した。[初回記録](../runs/songbird-chirps-left-syrinx-momentum-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-left-syrinx-momentum-44100-20261123-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_syrinx_momentum_44100.py \
  songbird-chirps-left-syrinx-momentum-44100-local
```

## 左鳴管の線形慣性の時間換算を連続描画で揃える

上流の `Songbird::sample` は左右の鳴管面積を設定し、`AirwayNetwork::step` が両枝を直前の節点圧で進める。線形係数は、今回の弁面積と両端の半セルから求めた現在の慣性 `L` にサンプルレートを掛け、粘性抵抗 `R` を加える。単位は dyn·s/cm⁵。持ち越し運動量の寄与は駆動圧へ入る。求めた流量を左右の端点へ符号付きで加え、枝がそろってから壁運動と節点圧を更新するため、同じ標本の右流量が左流量から直接変化する経路はない。上流の定常狭窄試験は二次損失込みの流量を、三分岐試験は節点の安定性を確認する。[鳴管の標本更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L989)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

左の持ち越し換算まで適用した13差分を隔離したRustビルドに復元し、左ポートだけを既存の線形慣性乗算の対象に加えた。実験差分は `L / dt` から `L × fs` への切り替えに限った。押鍵を0とする内部176.4 kHzの64点を通常CLIで測定し、対照CSVをバイト再現した。固定上流のCSVは登録済み実行からハッシュを照合して再利用した。256点制御の19点後は、駆動圧、抵抗、方向別損失が一致し、時間換算した慣性が `3963.4899853090224` から `3963.489985309023` へ変わった。独立計算でも、この変更で左流量の1 ULP差が消えた。同じ標本の右流量は対照と一致し、固定上流との差が残った。[事前登録](../cases/songbird-chirps-left-syrinx-linear-44100.json)・[実験差分](../runs/songbird-chirps-left-syrinx-linear-44100-20261123-repeat/artifacts/left-syrinx-linear.patch)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-linear-20261123.json)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 左鳴管流量 | 27点 → 27点 | 19点 → 48点 | 50点／19点 |
| 左気管支末端圧 | 26点 → 26点 | 19点 → 23点 | 50点／19点 |
| 右鳴管流量 | 28点 → 28点 | 19点 → 19点 | 64点一致／62点 |
| 気管入口圧 | 36点 → 36点 | 39点 → 39点 | 64点一致／59点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 64点一致／64点一致 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 64点一致／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

256点制御で、左ポートは47点後には面積0.0001932 cm²で閉鎖しており、48点後に0.0003609 cm²で再び開いた。再開時は前回流量と慣性が0なので駆動圧に運動量項が加わらず、固定上流との最初の左流量残差は47点後の気管入口圧の置換だけで復元した。気管入口圧の初差は39点後で、1つ先の気管セルの38点後の圧力差を置換すると、39点後の最初の直列枝流量が一致した。38点後のセル圧差は次のセルへの流出の置換で復元した。右は19点後の現在の慣性と持ち越し運動量の換算項の組み合わせで復元できた。235点制御の左流量の残差は、引き続き26点後の左気管支末端圧に由来した。追従0では圧力・流量が全点0だった。[残差の置換結果](../runs/songbird-chirps-left-syrinx-linear-44100-20261123-repeat/summary.json)・[気管セル1の収支](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-linear-cell1-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各106判定に合格した。左右流量と気管入口圧は各回で各576点をビット照合した。標準ライブラリによる別計算でも入口圧576点を照合し、気管セル1の追加比較は12判定を通過した。既定の持ち越しケースは保存CSVから105判定と再計算JSONを再現した。この回帰比較の初回はPythonのタプルとJSON配列を直接比較して失敗し、両方をJSONへ変換した比較で一致した。固定上流の気道・実時間処理9試験が通過した。368入力と26出力を照合し、採取物6,389,138バイトをRTL9210B-CGへ保存した。[初回の記録](../runs/songbird-chirps-left-syrinx-linear-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-left-syrinx-linear-44100-20261123-repeat/manifest.json)・[別計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-syrinx-linear-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_syrinx_momentum_44100.py \
  songbird-chirps-left-syrinx-linear-44100-local --case cases/songbird-chirps-left-syrinx-linear-44100.json
```

## 右鳴管ポートの気管支側半セル慣性を連続描画で揃える

固定上流の `songbird::create` は、右気管支の末端と共通気管の入口を、長さ0.08 cmの右鳴管ポートで結ぶ。弁面積（cm²）は左右の唇モデルから標本ごとに設定する。上流の `AirwayNetwork::step` は、断面更新でセル長と断面積の逆数を掛け、右気管支側と気管側の2項をポート自身の慣性へ加える。右ポートの流量（cm³/s）は、前回の両端圧、今回と前回の慣性、前回流量、今の開口に応じた粘性抵抗と二次損失から決まる。流量を節点の体積収支に加え、壁と圧力を更新する。上流の気道試験は定常狭窄での流量と三分岐の安定性を確かめる。[鳴管の接続と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の半セルと枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L858)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

左鳴管の線形慣性までの14差分をハッシュ照合した順序で隔離ビルドに復元した。右鳴管ポートも右気管支側半セルの計算を `length / area` から `length × (1 / area)` に変更した。右の持ち越し運動量と線形慣性の時間換算は引き続き候補の式を使った。通常CLIで3条件を描画し、左の線形慣性まで揃えた対照CSVをバイト単位で再現した。固定上流は登録済みCSVをハッシュ照合して使い、押鍵を0とする内部176.4 kHzの64点を比較した。[事前登録](../cases/songbird-chirps-right-syrinx-half-inertance-44100.json)・[実験差分](../runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123-repeat/artifacts/right-syrinx-half-inertance.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 右鳴管流量 | 28点 → 28点 | 19点 → 19点 | 30点／19点 |
| 右気管支末端圧 | 25点 → 25点 | 19点 → 19点 | 30点／19点 |
| 左鳴管流量 | 27点 → 27点 | 48点 → 48点 | 35点／52点 |
| 気管入口圧 | 36点 → 34点 | 39点 → 39点 | 34点／42点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 56点／64点一致 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 59点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

256点制御の19点後では右弁が閉じる向きに動くため、持ち越し計算は前回慣性を使う。この前回慣性は三者で同じ値だった。変更で現在の慣性と線形係数の慣性項が一致し、上流との右流量差が4 ULPから1 ULPに縮んだ。事前登録の3 ULPは実験による流量の移動幅であり、変更前の上流との差は4 ULPだった。事前登録の16進表記の予測値は実測と一致した。残りは持ち越し運動量の時間換算だけを置き換えて消えた。235点制御の28点後は右弁の開口が増え、持ち越し計算が参照する現在の慣性は変更前から一致していた。このため、候補の右流量は28点後には変化せず、事前予測どおり30点後に初めて変化した。新たに34点後に現れた気管入口圧差は、その標本の右流量だけを上流値に置換して消えた。追従0は全点無励振だった。[最初の差と項の置換](../runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123-repeat/summary.json)・[ビット差と独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-syrinx-half-inertance-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から実行し、各106判定を通過した。各回で左右流量と気管入口圧を各576点ビット照合し、標準ライブラリだけのコードでも右流量576点および最初の差の局所置換を再現した。従来の左線形ケースは保存CSVから106判定と再計算JSONを再現した。上流の気道・実時間処理9試験が通過した。354入力と26出力をハッシュ照合し、採取物6,391,408バイトをRTL9210B-CGに保存した。[初回記録](../runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123-repeat/manifest.json)・[独立計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-syrinx-half-inertance-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_syrinx_half_inertance_44100.py \
  songbird-chirps-right-syrinx-half-inertance-44100-local
```

## 右鳴管の持ち越し運動量の時間換算を連続描画で揃える

固定上流の `Songbird::sample` が左右の面積を更新し、`AirwayNetwork::step` は右気管支末端から気管入口へ向かう流量を正として枝を解く。慣性 `L` が減る開口時は `Lnow × Uprev` を、慣性が増す閉口方向では保存した `Lprev × Uprev` を使う。運動量に `fs` を掛けた圧力（dyn/cm²）を両端の前回圧力差に加え、現在の線形係数と方向別の二次損失で流量（cm³/s）を決める。流量と運動量を保存し、両端の流量収支を更新する。狭窄と三分岐の試験で、噴流損失込みの定常流量と節点近傍の安定性を確認できる。[鳴管の標本更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1021)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

右気管支側半セルまでの15差分を隔離Rustビルドに復元した。右ポートだけを既存の持ち越し乗算の対象に加え、`(Lcarry / dt) × Uprev` を `(Lcarry × Uprev) × fs` に替えた。右の現在の慣性の時間換算は従来の式を使った。通常CLIで先行版のCSVをバイト再現し、登録済み固定上流のCSVをハッシュ照合した。内部176.4 kHzで押鍵を0とした64点を比較した。235点制御では28点後が開口側で現在の慣性、256点制御では19点後が閉口側で前回慣性を使う。事前に局所計算で予測した時点と16進流量に両条件で一致し、その標本で右流量が上流とビット一致した。[事前登録](../cases/songbird-chirps-right-syrinx-momentum-44100.json)・[実験差分](../runs/songbird-chirps-right-syrinx-momentum-44100-20261123-repeat/artifacts/right-syrinx-momentum.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 右鳴管流量 | 28点 → 30点 | 19点 → 41点 | 28点／19点 |
| 右気管支末端圧 | 25点 → 25点 | 19点 → 19点 | 28点／19点 |
| 左鳴管流量 | 27点 → 27点 | 48点 → 48点 | 36点／54点 |
| 気管入口圧 | 34点 → 33点 | 39点 → 39点 | 33点／53点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 54点／64点一致 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 55点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

235点制御の30点後に残る右流量差は、右気管支末端の前回圧を置き換えると消えた。256点制御の41点後では、気管入口の前回圧だけで同じ結果を得た。右気管支末端圧の最初の差は235点制御の25点後と256点制御の19点後に残った。その標本では上流と候補で直前の末端圧と今回の右ポート流量がビット一致した。次に右気管支の手前から末端へ入る枝流量を採り、圧力更新の各項を照合する。追従0は全点無励振だった。[残差と置換結果](../runs/songbird-chirps-right-syrinx-momentum-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各108判定を通過した。左右の流量と気管入口圧は各回でそれぞれ576点ビット照合した。標準ライブラリを用いた別計算でも候補2版の右流量384点と、開口・閉口方向の最初の差の単独置換を再現した。右半セルの既定ケースは保存CSVで従来の106判定と再計算JSONを再現した。固定上流の気道と実時間処理9試験が通過した。356入力と26出力をハッシュ照合し、採取物6,388,996バイトをRTL9210B-CGに保存した。[初回記録](../runs/songbird-chirps-right-syrinx-momentum-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-right-syrinx-momentum-44100-20261123-repeat/manifest.json)・[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-syrinx-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_syrinx_half_inertance_44100.py \
  songbird-chirps-right-syrinx-momentum-44100-local --case cases/songbird-chirps-right-syrinx-momentum-44100.json
```

## 左右の気管支末端の圧力を直列枝流量から再計算する

固定上流の `songbird::create` は左右とも長さ0.8 cm、断面積0.02 cm²の気管支を作る。内部176.4 kHzでは3セルで、末端に手前のセルからの直列枝と鳴管ポートが接続する。気管支には可動壁がない。上流の `AirwayNetwork::step` は前回の圧力と流量から枝を解き、末端に流入と流出の差を加えてから、`pnext = pprev + (dt / C) × (Uin − Uport)` で圧力（dyn/cm²）を進める。末端には2枝がつながり、コンプライアンス `C`（cm⁵/dyn）はセルの体積を空気の体積弾性率で割った値になる。直列枝の両側は同じ断面なので段差の二次損失は0で、右向きに符号を取った流量は駆動圧を線形係数で割って求める。固定上流の気道試験で確認した三分岐の安定化は、枝が3本以上つながる気管入口で関係する。[鳴管の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[管の構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L35)・[節点の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1111)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

通常の `vocal-cli render` に `songbird_airway.observe_bronchus_end_balance` を追加した。有効にすると手前のセル圧、枝流入（cm³/s）、末端の断面積（cm²）、セル長（cm）を左右別に採れる。末端圧とポート流量は既存列を使う。候補は右鳴管の持ち越し換算までの16差分を適用して描画し、上流は固定コミットの公開状態をプローブで採取した。観測を追加した状態で両版の既存列が保存CSVに一致し、観測を省略した235点制御のCSVはバイト単位で一致した。[事前登録](../cases/songbird-chirps-bronchus-end-balance-44100.json)・[候補CLI](../crates/vocal-cli/src/songbird_case.rs)・[上流プローブ](../tools/upstream_songbird_airway_probe.rs)

| 条件 | 右の直列枝流入の初差 | 右の末端圧の初差 | 左の直列枝流入の初差 | 左の末端圧の初差 |
| --- | ---: | ---: | ---: | ---: |
| 235点制御 | 19点後 | 25点後 | 18点後 | 26点後 |
| 256点制御 | 18点後 | 19点後 | 18点後 | 23点後 |

押鍵後64点の比較で、右の末端圧差は予測どおり、両条件で直列枝からの流入だけを置き換えると消えた。左の末端圧差も同じ置換で消えた。両側で最初に流入が分かれた標本は、枝の線形係数だけを置き換えて上流値を復元した。候補の枝慣性は `0x1.f212d77318fc4p-7`、上流は `0x1.f212d77318fc5p-7` だった。別計算では、線形項に渡す半セルの逆数との乗算と時間換算の乗算を両方そろえると流量が一致した。それぞれを単独でそろえた場合は候補と同じ流量になった。235点制御の右では、持ち越しの時間換算項にも丸め差があったが、最初の流量差は線形係数の置換だけで消えた。追従0は両側で全点0だった。[残差の置換](../runs/songbird-chirps-bronchus-end-balance-44100-20261123-repeat/summary.json)・[別計算の出力](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-bronchus-end-balance-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各56判定を通過し、両版・両側・3条件の流入と圧力を各回でそれぞれ768点ビット照合した。標準ライブラリの別計算で同じ768点の圧力と、流入初差の線形係数を照合した。上流プローブはファイル全体のハッシュが2回で異なった。機械語の `__TEXT,__text`、CSV、結果要約は一致した。346入力と32出力を照合し、採取物8,082,750バイトをRTL9210B-CGに保存した。既存の右持ち越しケースも現行CLIから再描画し、107判定を通過した。旧バイナリとのハッシュ比較はビルド入力が一致する場合に行い、今回の再描画では旧CSVをバイト照合した。[初回記録](../runs/songbird-chirps-bronchus-end-balance-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-bronchus-end-balance-44100-20261123-repeat/manifest.json)・[別計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-bronchus-end-balance-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_bronchus_end_balance_44100.py \
  songbird-chirps-bronchus-end-balance-44100-local
```

## 右気管支の最後の直列枝で線形慣性を連続描画で揃える

固定上流の `AirwayNetwork::step` は、セル長と断面積の逆数の積を `half_l` に用意し、直列枝の両端から `L = (ρ / 2) × (half_l[a] + half_l[b])` を作る。右気管支は断面が一様なので、セルの境界で二次損失が生じず、式は `U = (p[a] − p[b] + M × fs) / (L × fs + R)` になる。今回の枝では固定断面なので、保存済みの `M = L × Uprev` を次の標本で使う。線形係数の単位は dyn·s/cm⁵、駆動圧は dyn/cm²。正の流量は手前のセルから右気管支末端に向かう。枝流量は両端の体積収支にすぐ加わり、その標本の圧力更新に入る。上流の定常狭窄・三分岐試験は、流量の式と節点更新を検証する。[上流の半セル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L858)・[枝の流量更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L945)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

右鳴管の持ち越し換算までの16差分を隔離Rustビルドに復元した。右気管支の最後の直列枝だけで、両端のセルから上流順で計算した慣性に内部レート176.4 kHzを掛け、分母の慣性項へ渡した。持ち越し計算は従来の慣性と換算順を使った。対照の通常CLIは直前の実行の候補CSVとバイナリを再現した。固定上流CSVはハッシュ照合して再利用した。235点制御の19点後と256点制御の18点後に、事前予測の16進流量が実測と上流に一致した。[事前登録](../cases/songbird-chirps-right-bronchus-linear-44100.json)・[実験差分](../runs/songbird-chirps-right-bronchus-linear-44100-20261123-repeat/artifacts/right-bronchus-linear.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 右気管支末端への流入 | 19点 → 26点 | 18点 → 25点 | 19点／18点 |
| 右気管支末端圧 | 25点 → 26点 | 19点 → 29点 | 25点／19点 |
| 右鳴管流量 | 30点 → 27点 | 41点 → 41点 | 27点／42点 |
| 気管入口圧 | 33点 → 28点 | 39点 → 39点 | 28点／47点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 54点／64点一致 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 55点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

右気管支の枝流入に残る初差は、235点制御の26点後と256点制御の25点後だった。どちらも直前の両端圧と流量、分母の線形係数が一致し、持ち越し項の置換で流量差が消えた。別計算では、235点制御で持ち越し項の慣性の作り方と時間換算の両方を上流順にすると復元できた。256点制御では時間換算だけの置換でも復元した。末端圧の残差はいずれも流入だけの置換で消えた。235点制御の右鳴管流量の初差が早まった標本では、直前の右気管支末端圧を置換して上流値を得た。256点制御の右鳴管の初差には前回の気管入口圧が効いた。追従0では全点無励振だった。[残差と置換結果](../runs/songbird-chirps-right-bronchus-linear-44100-20261123-repeat/summary.json)・[別計算による項の分解](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-linear-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各180判定を通過した。別の標準ライブラリ実装で3条件・3版の右気管支の流入と末端圧を各576点ビット照合した。先行の末端収支解析の45判定、要約、全再計算系列を保存CSVから再現した。固定上流の気道・実時間処理9試験が通過した。360入力と26出力をハッシュ照合し、採取物8,313,492バイトをRTL9210B-CGに保存した。[初回記録](../runs/songbird-chirps-right-bronchus-linear-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-right-bronchus-linear-44100-20261123-repeat/manifest.json)・[別計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-linear-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_bronchus_linear_44100.py \
  songbird-chirps-right-bronchus-linear-44100-local
```

## 右気管支の最後の直列枝で持ち越し運動量を連続描画で揃える

固定上流の `AirwayNetwork::step` は、直列枝の両端でセル長に断面積の逆数を掛け、密度の半分を掛けた和を慣性 `L` に使う。空気嚢側から鳴管側への流量を正とし、右気管支の最後の枝は一様かつ固定断面なので、保存した `Mprev = L × Uprev` をそのまま持ち越す。今回の駆動圧は前回の節点圧力差（dyn/cm²）に `Mprev × fs` を加えた値になる。流量（cm³/s）を線形係数で解いた後、両端の節点へ符号付きで加えて圧力を更新する。気管支の構築は `songbird::create` と `build::tube`、固定上流の枝と節点の流れは狭窄・三分岐の試験からも確認できる。[気管支の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝の持ち越しと更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

右気管支の線形係数まで揃えた17差分を隔離Rustビルドに復元した。同じ右の末端枝1本で、前回流量に上流順で計算した慣性を掛け、その積をサンプルレートで時間換算した。固定断面なので、現在の慣性を前回慣性と同じ値として再計算できる。線形係数は先行版と同じ式と値を保った。通常CLIで対照バイナリとCSVを再現し、固定上流CSVはハッシュ照合した先行実行を使った。内部176.4 kHzの押鍵後64点で、235点制御の26点後と256点制御の25点後の流入は事前予測の値で上流と一致した。[事前登録](../cases/songbird-chirps-right-bronchus-momentum-44100.json)・[実験差分](../runs/songbird-chirps-right-bronchus-momentum-44100-20261123-repeat/artifacts/right-bronchus-momentum.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 右気管支末端への流入 | 26点 → 27点 | 25点 → 29点 | 26点／25点 |
| 右気管支末端圧 | 26点 → 30点 | 29点 → 29点 | 26点／30点 |
| 右鳴管流量 | 27点 → 32点 | 41点 → 41点 | 27点／42点 |
| 気管入口圧 | 28点 → 33点 | 39点 → 39点 | 28点／47点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 57点／64点一致 |
| 口腔食道腔の首部流量 | 34点 → 34点 | 42点 → 42点 | 59点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

右気管支の末端枝に残る最初の流量差は、両条件で右の手前セルの前回圧だけを置換して復元した。手前セル圧自体は235点制御で23点後、256点制御で26点後に既に分かれていた。その標本の直前の手前セル圧と、末端側への流出は両版で一致した。次の観測点は、右気管支の先頭セルから手前セルへ入る枝流量となる。今回の右末端圧の残差は流入の置換で消えた。右鳴管流量の残差は235点制御で前回の右気管支末端圧、256点制御で前回の気管入口圧のみの置換で復元した。追従0はすべて無励振だった。[残差と置換結果](../runs/songbird-chirps-right-bronchus-momentum-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各180判定を通過した。標準ライブラリだけの別計算で右気管支末端への流入と末端圧を各576点、最初の効果と残差の置換を各条件で照合した。先行の線形慣性ケースの180判定と再計算JSONを保存CSVから再現し、固定上流の気道・実時間処理9試験が通過した。366入力と26出力をハッシュ照合し、採取物8,312,847バイトをRTL9210B-CGに保存した。[初回記録](../runs/songbird-chirps-right-bronchus-momentum-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-right-bronchus-momentum-44100-20261123-repeat/manifest.json)・[別計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_bronchus_linear_44100.py \
  songbird-chirps-right-bronchus-momentum-44100-local --case cases/songbird-chirps-right-bronchus-momentum-44100.json
```

## 左右の気管支の手前セルの圧力を流入から再計算する

上流の `songbird::create` は、空気嚢側から数えて0〜2の3セルで各気管支を構成する。真ん中のセル1にはセル0からの枝と末端セル2への枝がつながる。上流の `AirwayNetwork::step` は両端の前回圧と枝の前回流量から今回の流量を解き、符号付きで両端の収支へ加える。壁や放射がないセル1の圧力（dyn/cm²）は、前回圧に `(dt / C) × (U01 − U12)` を加える。枝流量 `U` は cm³/s で、`C` はセル体積を空気の体積弾性率で割った値（cm⁵/dyn）。両端の断面が同じ直列枝では二次損失が0になり、駆動圧を線形係数で割る。上流の定常狭窄と三分岐の試験では狭窄での枝流量と分岐での節点の安定性を確認できる。[気管支の構成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝流量と節点更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1030)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

通常の `vocal-cli render` に `songbird_airway.observe_bronchus_interior_cells` を追加した。左右に同じセル番号を指定し、そのセル圧、流入と流出、手前のセル圧、面積とセル長を採る。右の最後の直列枝で持ち越しまで揃えた18差分を適用した候補と、固定上流プローブを使用した。観測を追加した全3条件で既存列が先行CSVにバイト一致した。追加観測を省略した235点制御も先行CSVと一致した。セル1の圧力と末端側への流出は、双方の末端観測で採った手前セル圧と末端への流入にビット一致した。[事前登録](../cases/songbird-chirps-bronchus-interior-balance-44100.json)・[CLI](../crates/vocal-cli/src/songbird_case.rs)・[上流プローブ](../tools/upstream_songbird_airway_probe.rs)

| 制御 | 右セル1圧の初差 | 右セル0から1の流量の初差 | 左セル1圧の初差 | 左セル1から2の流量の初差 |
| --- | ---: | ---: | ---: | ---: |
| 235点 | 23点後 | 19点後 | 18点後 | 18点後 |
| 256点 | 26点後 | 19点後 | 19点後 | 18点後 |

右のセル1圧は両条件とも、セル0からの流入だけを上流値に替えると一致した。先行する19点後の右流入差では前回の枝流量が0で、両端圧も一致した。粘性抵抗も一致し、時間換算した慣性が候補の `2681.2799999999997` と上流の `2681.28` に分かれた。線形係数だけを揃えるとこの最初の流量差が消えた。左のセル1圧の初差は、両条件ともセル2向きの流出だけの置換で消えた。235点制御の左でセル0からの枝が初めて分かれた19点後は、枝の線形係数と直前のセル1圧の両方を置換すると流入が一致した。追従0は全点無励振だった。[残差と置換結果](../runs/songbird-chirps-bronchus-interior-balance-44100-20261123-repeat/summary.json)・[別計算の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-bronchus-interior-balance-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各68判定を通過した。3条件・両版・両側の流量と圧力を各実行でそれぞれ768点ビット照合し、標準ライブラリだけの別計算でも照合した。366入力と32出力を検証し、計測物8,472,852バイトをRTL9210B-CGに保存した。上流プローブのファイル全体のハッシュは2実行で異なり、機械語の `__TEXT,__text`、CSV、要約は一致した。通常CLIで複数セルの列順と、先頭・末端・重複・負の番号の拒否を確認した。現行Rustワークスペースの52試験、固定上流の気道・実時間処理9試験、既存の右気管支持ち越しケースの179判定が通過した。観測を追加した後の既存ケースではバイナリの同一性を判定から外し、CSVのバイト一致を引き続き確認した。[初回記録](../runs/songbird-chirps-bronchus-interior-balance-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-bronchus-interior-balance-44100-20261123-repeat/manifest.json)・[別計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-bronchus-interior-balance-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_bronchus_interior_balance_44100.py \
  songbird-chirps-bronchus-interior-balance-44100-local
```

## 右気管支のセル0から1への枝で線形慣性を連続描画で揃える

固定上流の鳴禽では、空気嚢から右気管支のセル0へポートでつながり、直列枝がセル0と1を結ぶ。`AirwayNetwork::step` は固定断面の各セルで `length × (1 / area)` を保存し、枝の両端の項に空気密度の半分を掛けて慣性 `L` を求める。断面積が両端で同じなので、枝に段差による二次損失はない。線形係数 `B = L × fs + R`（dyn·s/cm⁵）と、前回の両端圧差・持ち越し運動量から流量（cm³/s）を解く。セル0から1へ進む流れを正として、セル0から引き、セル1に加えて両圧力を更新する。固定上流の定常狭窄と三分岐の試験も枝流量と節点更新の確認に使った。[鳴禽の気道構成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[固定上流の枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L947)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

先行の18差分を適用した隔離Rustビルドを対照にし、右のセル0から1への枝だけで、半セル慣性の計算と時間換算を上流順にして分母へ渡した。枝の持ち越し運動量と抵抗は候補の計算を使った。通常CLIで対照バイナリとCSVを再現し、固定上流のCSVはハッシュを確認して再利用した。内部176.4 kHzの押鍵後64点を比較した。最初の効果は両条件とも押鍵19点後で、事前予測の値と固定上流の流量にビット一致した。[事前登録](../cases/songbird-chirps-right-bronchus-interior-linear-44100.json)・[実験差分](../runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123-repeat/artifacts/right-bronchus-interior-linear.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 右気管支セル1への流入 | 19点 → 22点 | 19点 → 25点 | 19点／19点 |
| 右気管支セル1圧 | 23点 → 25点 | 26点 → 28点 | 23点／26点 |
| 右気管支末端への流入 | 27点 → 26点 | 29点 → 29点 | 26点／30点 |
| 右気管支末端圧 | 30点 → 26点 | 29点 → 29点 | 26点／30点 |
| 右鳴管流量 | 32点 → 27点 | 41点 → 41点 | 27点／51点 |
| 気管入口圧 | 33点 → 37点 | 39点 → 39点 | 33点／51点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 54点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

右のセル0から1への流量で次に分かれた標本は、235点制御の22点後、256点制御の25点後だった。両標本で前回の流量、両端圧、線形係数が一致し、持ち越し項を置き換えると流量差が消えた。別計算では、持ち越しに使う慣性の組み立てと時間換算を両方揃えた場合に流量が上流と一致した。そのうち一方だけの変更では候補と同じ値になった。セル1圧の25点後と28点後の差は流入だけを置換して消えた。235点制御の27点後に早まった右鳴管の流量差は、前回の右気管支末端圧で復元した。256点制御の41点後の右鳴管流量は前回の気管入口圧で復元した。追従0は全点無励振だった。[残差と置換結果](../runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123-repeat/summary.json)・[独立計算の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-interior-linear-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から各252判定を通過した。右セル1の流量と圧力は、3条件・3版で別計算したそれぞれ576点がビット一致した。従来の右末端枝の線形係数と持ち越しの各ケースは、保存CSVから各180判定と再計算JSONを再現した。固定上流の気道と実時間処理9試験も通過した。368入力と26出力をハッシュ照合し、採取物10,144,558バイトをRTL9210B-CGに保存した。[初回記録](../runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123-repeat/manifest.json)・[別計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-interior-linear-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_bronchus_linear_44100.py \
  songbird-chirps-right-bronchus-interior-linear-44100-local --case cases/songbird-chirps-right-bronchus-interior-linear-44100.json
```

## 右気管支のセル0から1への枝で持ち越し運動量を連続描画で揃える

固定上流の `AirwayNetwork::step` は、直列枝の流量を計算した直後に、現在の慣性 `L` と流量 `U` の積を次の標本の運動量として保存する。右気管支のセル0から1への枝は固定断面なので、次の標本でもこの慣性が使われる。次の駆動圧には前回の両端圧の差と `(L × Uprev) × fs`（dyn/cm²）が入り、線形係数で割って流量（cm³/s）が決まる。新しい流量はセル0の収支から引き、セル1に加える。上流の `songbird::create` に空気嚢側のポートと気管支を置く順序があり、狭窄と三分岐の試験で共通の枝・節点更新を確認できる。[気道の構成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

右気管支の内部枝の線形慣性を揃えた19差分を隔離Rustビルドに復元した。実験では同じ枝の持ち越しにも上流順で求めた慣性を渡し、流量を掛けた積をサンプルレートで時間換算した。線形係数は前回と同じ値を使った。通常CLIで先行の候補バイナリとCSVを再現し、固定上流はハッシュ照合した保存CSVを使った。内部176.4 kHzの押鍵後64点で、235点制御の22点後と256点制御の25点後に、流量が予測した値で上流とビット一致した。[事前登録](../cases/songbird-chirps-right-bronchus-interior-momentum-44100.json)・[実験差分](../runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123-repeat/artifacts/right-bronchus-interior-momentum.patch)

| 観測 | 235点制御の上流との差 | 256点制御の上流との差 | 実験と対照の初差（235点／256点） |
| --- | --- | --- | --- |
| 右セル0の圧力 | 22点 → 29点 | 25点 → 30点 | 22点／25点 |
| 右セル1への流入 | 22点 → 30点 | 25点 → 32点 | 22点／25点 |
| 右セル1の圧力 | 25点 → 39点 | 28点 → 32点 | 25点／28点 |
| 右気管支末端への流入 | 26点 → 42点 | 29点 → 33点 | 26点／29点 |
| 右気管支末端圧 | 26点 → 39点 | 29点 → 33点 | 26点／29点 |
| 右鳴管流量 | 27点 → 39点 | 41点 → 41点 | 27点／51点 |
| 気管入口圧 | 37点 → 37点 | 39点 → 39点 | 64点一致／51点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 64点一致／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

右セル1への流入に残る最初の差は、235点制御の30点後と256点制御の32点後で、どちらも前回のセル0圧だけを置換すると消えた。セル0圧は235点制御の29点後と256点制御の30点後に先に分かれた。その標本では、直前のセル0圧と今回のセル1向き流量が候補と上流で一致した。空気嚢ポートからセル0へ入る流量の観測が次の比較に必要になる。右鳴管流量の残差は両制御で気管入口の前回圧を置き換えて復元した。追従0では全点無励振だった。[残差と置換結果](../runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の各252判定を通過した。右セル1への流入とセル1圧は、3条件・3版で別計算した各576点がビット一致した。先行3ケースの保存CSVから各180・180・252判定と再計算結果を再現した。固定上流の気道と実時間処理9試験も通過した。374入力と26出力をハッシュ照合し、採取物10,139,600バイトをRTL9210B-CGに保存した。[初回記録](../runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123-repeat/manifest.json)・[独立計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-interior-momentum-20261123.py)・[独立計算の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-bronchus-interior-momentum-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_bronchus_linear_44100.py \
  songbird-chirps-right-bronchus-interior-momentum-44100-local --case cases/songbird-chirps-right-bronchus-interior-momentum-44100.json
```

## 空気嚢ポートと左右の気管支セル0の圧力収支

固定上流の `Songbird::control` は空気嚢の圧力を kPa から dyn/cm² に換算し、呼気ゲートを掛けて境界値にする。`sample` は左右の鳴管開口を更新し、`AirwayNetwork::step` に進む。空気嚢の左右にあるポートは長さ0.4 cm、断面0.05 cm²。ポートの慣性に両端の半セルを加える。流量 `U`（cm³/s）の符号は空気嚢から各気管支へ向かうときが正になる。前回のセル0圧、制御で設定済みの空気嚢圧と前回の運動量から駆動圧 `d` を求め、粘性抵抗を含む線形項 `B` と流れの向きに応じた損失 `K` で `B U + K |U| U = d` を解く。固定断面のセル0では、その流量を受けてセル1への流量を引き、`p_new = p_prev + (dt / C) × (U_sac − U_01)` で圧力を更新する。コンプライアンス `C` はセル容積を `ρ c²` で割った値。セル0の次数は2で、壁振動と放射端の項も入らない。上流の定常狭窄試験では固定圧の境界とポートを接続し、定常流量をベルヌーイ式に照合している。[上流の鳴禽](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝と節点の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L984)・[上流の定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

内部176.4 kHzで押鍵後64点を観測する。前回の右セル0圧の初差で、空気嚢側の流入だけを上流値へ置き換えると圧力が一致する、と観測コードを変更する前に登録した。空気嚢の圧力はブロック先頭で更新され、同じ標本のCSVに現れるため、ポート流量の独立計算には現在行の空気嚢圧を使い、セル0圧と流量履歴には直前行を使う。[事前登録](../cases/songbird-chirps-bronchus-inlet-balance-44100.json)

再実装の `SongbirdAirway::bronchus_interior_samples` と固定上流の観測プローブで、気管支セルに番号0を指定できるようにした。両側で空気嚢ポートの流量と空気嚢圧を入口側の状態として返す。セル1の観測に番号0を追加し、追加前の列を候補と上流の全3条件で再現した。既存列の空気嚢圧とセル1への流入が、新しい列の上流側圧力と流出にそれぞれ一致することも確認した。呼気ゲートを1にした短い確認では、最初の標本の空気嚢圧が9000 dyn/cm²、流入とセル0圧が正、セル1への流出がゼロだった。[再実装の観測](../crates/vocal-core/src/airway/songbird.rs)・[CLIの入口](../crates/vocal-cli/src/songbird_case.rs)・[上流プローブ](../tools/upstream_songbird_airway_probe.rs)

| 条件 | 右ポートの流量初差 | 右セル0圧の初差 | 左ポート流量／左セル0圧の初差 |
| --- | --- | --- | --- |
| 235点制御 | 押鍵22点後 | 29点後 | 20点後／19点後 |
| 256点制御 | 押鍵30点後 | 30点後 | 20点後／19点後 |
| 追従0 | 64点一致 | 64点一致 | 64点無励振 |

右セル0圧の初差では両条件とも直前のセル圧とセル1への流出が一致し、現在のポート流量だけの置換で圧力が一致した。235点制御ではポートの流量が先に分かれ、圧力がビット単位で分かれるまで7標本あった。右ポートの流量初差では両端圧・前回流量・線形係数・損失係数が一致した。残る持ち越し項を再実装の `(L / dt) × Uprev` から上流順の `(L × Uprev) × fs` に置換すると、235点制御では `-0x1.ef2a84d7b253dp-26`、256点制御では `-0x1.febc5eb4b8156p-16` cm³/sとなり、上流とビット一致した。左ポートの初差はセル0の前回圧で復元した。そのセル0圧の初差はセル1への流出だけで復元した。[置換結果](../runs/songbird-chirps-bronchus-inlet-balance-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各96判定を通過した。ポート流量とセル0圧は、3条件・両側・両版の各768点をビット単位で再計算した。独立した72桁の十進計算では、式の各項の絶対値の和で正規化した残差の最大値が流量式で1.92×10⁻¹⁶未満、圧力式で8.88×10⁻¹⁷未満だった。両実行の計372入力、32出力をハッシュ照合し、採取物9,120,290バイトをRTL9210B-CGに保存した。CSVと要約を含む13出力がバイト一致した。ビルド記録と上流プローブ実行ファイルのハッシュは実行間で異なった。プローブのMach-O UUIDが異なり、機械語と文字列領域はバイト一致した。現行Rust52試験と固定上流9試験も通過した。[初回記録](../runs/songbird-chirps-bronchus-inlet-balance-44100-20261123/manifest.json)・[再実行記録](../runs/songbird-chirps-bronchus-inlet-balance-44100-20261123-repeat/manifest.json)・[十進計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-bronchus-inlet-balance-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_bronchus_inlet_balance_44100.py \
  songbird-chirps-bronchus-inlet-balance-44100-local
```

## 右の空気嚢ポートで持ち越し運動量を連続描画で揃える

固定上流の `songbird::create` が右の空気嚢ポートを固定圧節点と右気管支セル0の間に置く。`Songbird::control` が境界圧、`sample` が鳴管の開口を設定して `AirwayNetwork::step` を呼ぶ。ポート慣性 `L` は長さと逆断面積から求めた管部分と両端半セルの和で、固定断面では標本間で一定になる。上流は体積流量 `U`（cm³/s）を解いた直後に `L × U` を保存し、次の枝更新でサンプルレートを掛けて駆動圧（dyn/cm²）の一部にする。圧力更新では各枝の新しい流量を使い、次の枝更新まで圧力を保持する。空気嚢側の圧力は固定境界なので、右から左への経路は鳴管と気管の合流点を経由する。上流の定常狭窄試験では圧力節点・ポート・管の構成を使い、無割り当て試験では実時間の動物音声レンダーを確認している。[固定上流の構成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L995)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

実装前に、右ポートの予測値を235点制御の押鍵22点後で `-0x1.ef2a84d7b253dp-26`、256点制御の30点後で `-0x1.febc5eb4b8156p-16` cm³/sと登録した。最短の伝播はセル0圧が同時、セル1への流入が1点後、末端への流入が2点後、右鳴管流量が3点後になる。丸めにより、ビット列で見える差はこの時刻より遅れることがある。[事前登録](../cases/songbird-chirps-right-sac-momentum-44100.json)

先行の20差分を隔離したRustビルドに復元し、`SongbirdAirway::step` から右の空気嚢ポートの枝番号を指定した。枝更新で既存の運動量計算順をその枝にも適用し、線形係数と損失係数は先行版の式で評価した。通常CLIで先行の対照バイナリとCSVを再現した。固定上流は前回の採取CSVをハッシュ照合して使った。予測した点で両条件の流量が上流値に一致し、追従0では全点無励振だった。[実験差分](../runs/songbird-chirps-right-sac-momentum-44100-20261123-b-repeat/artifacts/right-sac-momentum.patch)・[実行結果](../runs/songbird-chirps-right-sac-momentum-44100-20261123-b-repeat/summary.json)

| 観測 | 固定上流との初差の変化（235点制御） | 固定上流との初差の変化（256点制御） | 対照から変わった最初の点（235点／256点） |
| --- | --- | --- | --- |
| 右の空気嚢ポート流量 | 22点 → 43点 | 30点 → 44点 | 22点／30点 |
| 右セル0圧 | 29点 → 41点 | 30点 → 43点 | 29点／30点 |
| 右セル1への流入 | 30点 → 41点 | 32点 → 43点 | 30点／32点 |
| 右セル1圧 | 39点 → 40点 | 32点 → 42点 | 39点／32点 |
| 右気管支末端への流入 | 42点 → 40点 | 33点 → 42点 | 40点／33点 |
| 右気管支末端圧 | 39点 → 39点 | 33点 → 41点 | 40点／33点 |
| 右鳴管流量 | 39点 → 39点 | 41点 → 41点 | 41点／52点 |
| 気管入口圧 | 37点 → 37点 | 39点 → 39点 | 43点／52点 |
| 気管末端圧 | 34点 → 34点 | 40点 → 40点 | 64点一致／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

右ポートに残った43点後と44点後の流量差は、セル0の前回圧だけを置き換えると消えた。そのセル0圧とセル1圧は、いずれの制御でも現在の下流向き流量だけの置換で初差を復元できた。セル2の末端圧も右鳴管への流出だけで復元した。右鳴管の流量初差は、両制御とも直前の気管入口圧だけで復元した。気管入口圧の初差は、235点制御の37点後では左鳴管からの流入、256点制御の39点後では気管セル1への流出の単独置換で消えた。[右ポートとセル0・1の置換](../runs/songbird-chirps-right-sac-momentum-44100-20261123-b-repeat/summary.json)・[下流の照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-right-sac-momentum-downstream-20261123.py)・[下流の照合結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-right-sac-momentum-downstream-20261123.json)

初回実行では、候補固有の口腔食道腔の体積源列 `oec_filtered_injection_cm3_s` を固定上流のCSVにも要求して集計が停止した。以後はその列を候補内で追跡し、上流との比較には両方で採取した列を使う。事前の合否条件は維持し、失敗時の6本のCSVが再実行でもバイト一致したことを確認した。[失敗時の記録](../runs/songbird-chirps-right-sac-momentum-44100-20261123/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各119判定を通過した。ポート流量とセル0圧は3条件・3版・両側の各1,152点、右セル1への流入と圧力は3条件・2版の各384点をビット照合した。独立した72桁の十進計算でも正規化した最大残差は流量式で1.92×10⁻¹⁶未満、圧力式で8.88×10⁻¹⁷未満だった。先行のポート収支の要約と全再計算系列を保存CSVから再現し、下流の追加36判定と固定上流の9試験が通過した。370入力と26出力をハッシュ照合し、採取物8,014,368バイトをRTL9210B-CGに保存した。CSVと要約を含む12出力は実行間でバイト一致した。[実行記録](../runs/songbird-chirps-right-sac-momentum-44100-20261123-b/manifest.json)・[再実行記録](../runs/songbird-chirps-right-sac-momentum-44100-20261123-b-repeat/manifest.json)・[十進計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-sac-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_sac_momentum_44100.py \
  songbird-chirps-right-sac-momentum-44100-local
```

## 256点制御の気管入口圧の差をセル10の壁までたどる

固定上流の `songbird::create` が軟壁付きの気管を組み、`Songbird::sample` が鳴管ポートの開口を更新してから `AirwayNetwork::step` を呼ぶ。気管の内部節点では、前回の両端圧と前回の枝運動量から両方向の流量（cm³/s）を求める。壁は前回の圧力と壁速度・変位から新しい速度 `v`（cm/s）を計算する。固定断面 `A` とセル長 `dx` から壁の側面積 `S`（cm²）を求め、壁流量 `Uwall = S × v` を節点の流量収支から引く。圧力更新は `p' = p + (dt/C) × ((Uin − Uout) − Uwall)`。上流の側面積は周長係数が1のとき `2 × sqrt(π) × sqrt(A) × dx`、再実装では `2 × sqrt(π × A) × dx`。固定断面0.045 cm²では両式の結果が1 ULP異なる。上流の軟壁試験は時間応答と線形周波数応答の共鳴を照合している。[鳴禽の作成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[壁の面積と段階更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)

前回のCSVにはセル1・2を含む気管の全内部セルがある。256点制御でセル1から2への流量が最初に分かれる38点後の起点を、セル2の前回圧から末端側へさかのぼる。先行記録では、セル10の最初の圧力差が28点後、両側の枝流量の最初の差は29点後と34点後だった。そこで、28点後の圧力は壁流量の置換だけで復元できると予測し、セル10だけの壁面積の演算順を揃える比較を事前登録した。[事前登録](../cases/songbird-chirps-trachea-cell10-wall-surface-44100.json)

先行の21差分を隔離Rustビルドに復元し、`SongbirdAirway::step` からセル10の節点を指定して `AirwayNetwork` の壁流量に使う側面積の演算順を切り替えた。両版でセル10の壁速度と変位の式を従来どおり評価する。通常CLIで先行バイナリとCSVを再現し、固定上流のCSVをハッシュ照合した。内部176.4 kHzの押鍵後64点で、両制御の7点後の壁流量が予測値で上流とビット一致した。7点後の直前の壁速度・変位は両版でゼロで、最初の壁流量差を面積の丸めで再現できた。[実験差分](../runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123-repeat/artifacts/wall-surface.patch)・[再計算系列](../runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123-repeat/artifacts/wall-surface-replay.json)

| 256点制御の観測 | 上流との初差の変化 | 対照と実験版の初差 |
| --- | --- | --- |
| セル10の壁流量 | 7点 → 58点 | 7点 |
| セル10圧 | 28点 → 55点 | 28点 |
| セル9圧 | 29点 → 57点 | 29点 |
| セル3圧 | 35点 → 51点 | 35点 |
| セル2圧 | 37点 → 49点 | 37点 |
| セル1から2への流出 | 38点 → 49点 | 38点 |
| セル1圧 | 38点 → 48点 | 38点 |
| セル0から1への流出 | 39点 → 48点 | 39点 |
| 気管入口圧 | 39点 → 47点 | 39点 |

対照のセル10圧の28点後は、壁流量だけの置換で上流値に一致した。セル9から1までの最初の圧力差は、それぞれ末端側の枝流量だけの置換で復元した。各枝の最初の流量差は末端側セルの前回圧だけで復元した。連続描画ではこの一連の差が解消し、セル10圧の次の差は55点後に移った。その標本では末端側への流出だけの置換で圧力が一致した。235点制御ではセル10圧の33点後の差が残り、これも末端側への流出で復元した。両制御の放射流量とその後退差分は対照と全64点一致した。追従0は無励振だった。[両条件の局所置換と初差](../runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123-repeat/summary.json)

256点制御に残る気管入口圧の47点後は、右鳴管からの流量だけを上流値へ置き換えると復元した。右鳴管流量は押鍵46点後に先に分かれ、同じ慣性 `L` の時間換算を `L / dt` から `L × fs` に変更した局所計算だけで上流とビット一致した。47点後の右鳴管の流量は前回運動量の項を上流値へ置き換えて復元した。[右鳴管の追加照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-trachea-cell10-syrinx-20261123.py)・[46点後と47点後の置換](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-trachea-cell10-syrinx-20261123.json)

第1版では上流CSVのマニフェストのSHA-256を転記する際に誤りがあり、入力照合で描画前に停止した。第2版でマニフェストの実測値と前回実行の入力記録を照合し、`35f05ab2dd5b3112469f68c3402fb64d702745ad191d6cde5125d0e6d9cd8647` に修正した。仮説と合否基準は第1版から共通とした。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各1,278判定を通過した。独立した72桁の十進計算では枝流量8,640点と壁流量・圧力各8,064点を照合し、方程式の各項の絶対値の和で正規化した残差の最大値は5×10⁻¹⁶未満だった。先行のセル13・14の要約と再計算系列を保存CSVから再現し、固定上流の気道・実時間処理12試験と右鳴管の追加10判定も通過した。384入力と26出力をハッシュ照合し、CSVと要約を含む12出力が実行間でバイト一致した。採取物6,689,286バイトをRTL9210B-CGに保存した。[初回の記録](../runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123/manifest.json)・[再実行の記録](../runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123-repeat/manifest.json)・[十進計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-cell10-wall-surface-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_trachea_wall_surface_44100.py \
  songbird-chirps-trachea-cell10-wall-surface-44100-local
```

## 右鳴管の線形慣性の時間換算を連続描画で揃える

上流の `songbird::create` は右気管支末端と気管入口を、長さ0.08 cmの時変ポートでつなぐ。`Songbird::sample` が鳴管開口に応じてポート面積を設定し、`AirwayNetwork::step` が端点の前回圧と前回の流量・慣性から正負の体積流量 `U`（cm³/s）を求める。線形係数はポートと両端半セルの現在の慣性 `L` をサンプルレートで換算した値と粘性抵抗 `R` の和になる。駆動圧は気管支末端の前回圧から気管入口の前回圧を引き、持ち越し運動量の時間換算を加えた値（dyn/cm²）。流量は `(L × fs + R)U + K|U|U = d` を解いて決め、開口が閾値より小さいときは0になる。右気管支から気管へ向かう流量を正として、気管支末端の収支から引き、気管入口に足す。上流の定常狭窄試験は方向別損失を含む流量をベルヌーイ式と比較している。[右鳴管の接続と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[ポートの係数・枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L995)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

先行の保存CSVで現在慣性の換算のみを変えて再計算し、右鳴管流量が最初に変わる値を登録した。押鍵後0〜63点のうち、235点制御では45点後に `-0x1.42017e48ad52bp-10`、256点制御では46点後に `-0x1.ce6c4b3c157c2p-10` cm³/sになると予測した。両方とも該当標本の上流値である。[事前登録](../cases/songbird-chirps-right-syrinx-linear-time-44100.json)

先行の22差分を隔離Rustビルドへ復元した。既存のポートの枝番号を使い、右鳴管で `Branch::step` に渡す線形係数の換算だけを乗算に切り替えた。通常の描画CLIで対照バイナリと全CSVを再現し、固定上流CSVをハッシュ照合した。両制御で最初の効果量が予測どおり上流値とビット一致した。追従0は全点無励振だった。[実験差分](../runs/songbird-chirps-right-syrinx-linear-time-44100-20261123-repeat/artifacts/right-syrinx-linear-time.patch)・[初差と再計算](../runs/songbird-chirps-right-syrinx-linear-time-44100-20261123-repeat/summary.json)

| 観測 | 上流との初差の変化（235点制御） | 上流との初差の変化（256点制御） | 対照と実験版の初差（235点／256点） |
| --- | --- | --- | --- |
| 右鳴管流量 | 39点 → 39点 | 46点 → 64点一致 | 45点／46点 |
| 右気管支末端圧 | 39点 → 39点 | 47点 → 64点一致 | 45点／47点 |
| 左鳴管流量 | 27点 → 27点 | 48点 → 55点 | 54点／48点 |
| 気管入口圧 | 37点 → 37点 | 47点 → 60点 | 45点／47点 |
| 気管セル1への流入 | 38点 → 38点 | 48点 → 61点 | 46点／48点 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

256点制御では、47点後の気管入口圧が上流と一致し、次の入口圧の差は60点後に出た。235点制御の入口圧は37点後に初めて分かれた。どちらも左鳴管流量だけを上流値に替えると復元した。左鳴管の最初の流量差は27点後と55点後で、いずれも左気管支末端の前回圧の置換で消えた。左末端圧の初差は26点後と23点後で、末端の直列枝からの流入だけの置換で一致した。この枝の流量は両条件で18点後に初めて分かれ、分母の線形係数だけを上流値に替えると一致した。[左側の照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-right-syrinx-linear-time-left-20261123.py)・[左側の置換結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-right-syrinx-linear-time-left-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各78判定を通過した。両鳴管の流量1,152点、気管入口圧576点をビット再計算した。独立十進計算では開口939点で流量式の正規化残差が2.45×10⁻¹⁶未満、閉鎖213点で流量ゼロ、入口圧の残差が9.38×10⁻¹⁷未満だった。補助の十進検証は長さとファイルパスに同じ変数名を使って初回に停止し、名前を分けて再計算した。固定上流の12試験、先行の鳴管再計算45判定、左側の追加12判定も通過した。388入力と26出力をハッシュ照合し、CSVと要約を含む12出力がバイト一致した。採取物7,230,504バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/songbird-chirps-right-syrinx-linear-time-44100-20261123/manifest.json)・[再実行マニフェスト](../runs/songbird-chirps-right-syrinx-linear-time-44100-20261123-repeat/manifest.json)・[独立十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-right-syrinx-linear-time-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_syrinx_linear_time_44100.py \
  songbird-chirps-right-syrinx-linear-time-44100-local
```

## 左気管支末端の直列枝で線形慣性を連続描画で揃える

固定上流の `songbird::create` は気管支を長さ0.8 cm、断面0.02 cm²の管として作る。176.4 kHzでは3セルに分かれ、最後の直列枝がセル1と末端セル2をつなぐ。`Songbird::sample` から呼ぶ `AirwayNetwork::step` では各セルの半慣性に使う幾何項を `dx × (1/A)` として保持する。枝慣性 `L` は両側の幾何項の和に密度の半分を掛けて求める。左右の断面が同じため二次損失はゼロで、前回の両端圧差と持ち越し項の和を `L × fs + R` で割ると体積流量（cm³/s）が得られる。枝流量をセル1の収支から引き、セル2に加えて圧力を更新する。セル2から鳴管への流出は、その次の標本に新しい圧力を読む。固定上流の三分岐・定常狭窄の試験で共通の枝更新と収支を確認した。[上流の気管支の生成と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[直列枝の慣性と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L947)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

変更前の両制御で、押鍵18点後の左末端への流入は前回流量0、前回の両端圧と抵抗は上流と一致していた。線形慣性だけを再計算して、235点制御の `-0x1.c6d3afae2cf2bp-30`、256点制御の `-0x1.96f09c1d06be1p-30` cm³/sを予測値として登録した。観測窓は押鍵後0〜63点とする。[事前登録](../cases/songbird-chirps-left-bronchus-linear-44100.json)

先行の23差分を隔離Rustビルドに復元した。`SongbirdAirway::step` が左気管支の最後の直列枝を指定し、`AirwayNetwork` で両側の半セルの幾何項を `dx × (1/A)` で求めて時間換算する。得た慣性は分母の線形係数に使い、持ち越し運動量は先行版の式で評価する。通常の描画CLIで対照バイナリと全CSVを再現し、固定上流CSVをハッシュ照合した。両制御の18点後の流量が予測値で上流とビット一致した。[実験差分](../runs/songbird-chirps-left-bronchus-linear-44100-20261123-repeat/artifacts/left-bronchus-linear.patch)・[判定結果](../runs/songbird-chirps-left-bronchus-linear-44100-20261123-repeat/summary.json)

| 観測 | 上流との初差の変化（235点制御） | 上流との初差の変化（256点制御） | 対照と実験版の初差（235点／256点） |
| --- | --- | --- | --- |
| 左末端への流入 | 18点 → 23点 | 18点 → 22点 | 18点／18点 |
| 左末端圧 | 26点 → 23点 | 23点 → 32点 | 23点／23点 |
| 左鳴管流量 | 27点 → 32点 | 55点 → 58点 | 27点／55点 |
| 右鳴管流量 | 39点 → 39点 | 64点一致 → 64点一致 | 39点／64点一致 |
| 気管入口圧 | 37点 → 38点 | 60点 → 63点 | 37点／60点 |
| 気管末端圧 | 34点 → 34点 | 50点 → 50点 | 62点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

左末端への流入に残る差は235点制御の23点後、256点制御の22点後に出た。どちらも直前の両端圧・前回流量と線形係数は一致した。持ち越し項に使う慣性の組み立てと時間換算を両方揃えると、235点制御は `-0x1.43abf8efee589p-18`、256点制御は `-0x1.88af1c994c0a5p-20` cm³/sとなり、上流を復元した。変更を片方だけにした局所計算では、どちらの条件も候補値と同じだった。[持ち越し項の照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-left-bronchus-linear-20261123.py)・[組み立てと時間換算の比較](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-linear-momentum-20261123.json)

235点制御では左末端圧の初差が26点後から23点後へ早まった。256点制御では23点後から32点後へ移った。各初差は末端へ入る枝流量だけの置換で復元した。両条件の左鳴管流量の初差は左末端の前回圧だけで、気管入口圧の初差は左鳴管流量だけで復元した。放射の2列は対照と全64点一致し、追従0は全点無励振だった。[圧力と流量の単独置換](../runs/songbird-chirps-left-bronchus-linear-44100-20261123-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各141判定を通過した。独立十進計算で3条件・3版・両側の末端流量と圧力を各1,152点照合し、式の各項の絶対値の和で正規化した残差の最大値は流量で1.99×10⁻¹⁶未満、圧力で6.48×10⁻¹⁷未満だった。固定上流の12試験と先行の右鳴管比較の3条件も再現した。作業準備では、先行差分の相対パスが隔離ビルド先で解決できず、絶対パスで復元し直した。392入力と26出力をハッシュ照合し、CSVと要約を含む12出力がバイト一致した。採取物10,596,362バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/songbird-chirps-left-bronchus-linear-44100-20261123/manifest.json)・[再実行マニフェスト](../runs/songbird-chirps-left-bronchus-linear-44100-20261123-repeat/manifest.json)・[独立十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-bronchus-linear-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_bronchus_linear_44100.py \
  songbird-chirps-left-bronchus-linear-44100-local
```

## 左気管支末端の直列枝で持ち越し運動量を連続描画で揃える

固定上流の `songbird::create` が左の気管支を一様断面の3セルで作り、`Songbird::sample` が開口面積を更新した後に `AirwayNetwork::step` を呼ぶ。セル1から末端セル2への直列枝は、流量 `U`（cm³/s）を求めた直後に、その標本の慣性 `L` と `U` の積を次回用に保存する。断面と長さが一定のため、次の枝更新ではその積にサンプルレートを掛ける。時間換算した項と両端の前回圧との差が駆動圧（dyn/cm²）となり、同断面の枝では粘性抵抗を含む線形係数で割る。節点更新は枝の流量をセル1から引き、セル2へ足す。次の標本の左鳴管流量はそこで更新した末端圧を読む。固定上流の三分岐・定常狭窄の試験でもこの流量と収支の順序が使われる。[上流の鳴禽](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[気道の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

先行の保存CSVから、その枝の持ち越し項だけを変更して最初に変わる流量を予測した。235点制御の押鍵23点後は `-0x1.43abf8efee589p-18`、256点制御の22点後は `-0x1.88af1c994c0a5p-20` cm³/sを登録した。両条件の直前の両端圧・流量と線形係数は一致していた。[事前登録](../cases/songbird-chirps-left-bronchus-momentum-44100.json)・[先行の局所計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-linear-momentum-20261123.json)

隔離Rustビルドに先行の24差分を復元した。左末端枝では既に分母に使っていた上流順の慣性を持ち越し項にも渡し、`(L × Uprev) × fs` で駆動圧へ換算した。通常CLIで対照バイナリと全CSVを再現し、固定上流CSVをハッシュ照合した。線形係数が全条件で先行版とビット一致することを確認した。両制御の予測流量は同じ標本の上流値と一致し、追従0は全点無励振だった。[実験差分](../runs/songbird-chirps-left-bronchus-momentum-44100-20261123-b-repeat/artifacts/left-bronchus-momentum.patch)・[先頭の差と判定](../runs/songbird-chirps-left-bronchus-momentum-44100-20261123-b-repeat/summary.json)

| 観測 | 上流との初差の変化（235点制御） | 上流との初差の変化（256点制御） | 対照と実験版の初差（235点／256点） |
| --- | --- | --- | --- |
| 左末端への流入 | 23点 → 26点 | 22点 → 26点 | 23点／22点 |
| 左末端圧 | 23点 → 26点 | 32点 → 26点 | 23点／26点 |
| 左セル1圧 | 23点 → 23点 | 22点 → 25点 | 23点／22点 |
| 左鳴管流量 | 32点 → 42点 | 58点 → 57点 | 32点／57点 |
| 右鳴管流量 | 39点 → 45点 | 64点一致 → 59点 | 39点／59点 |
| 気管入口圧 | 38点 → 41点 | 63点 → 57点 | 38点／57点 |
| 気管末端圧 | 34点 → 34点 | 50点 → 50点 | 55点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

両条件で26点後の左末端への流量差はセル1の前回圧だけで、同じ標本の末端圧は流入だけで復元した。セル1圧の初差は235点制御の23点後と256点制御の25点後で、セル0から入る流量の単独置換で解消した。セル0からセル1へ入る枝の流量は両条件で19点後に初めて分かれ、線形係数だけで復元した。気管入口圧の初差は、235点制御の41点後では気管セル1への流出、256点制御の57点後では左鳴管流量の置換で復元した。[左セル1の照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-left-bronchus-momentum-20261123.py)・[左セル1の置換結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-momentum-inner-20261123.json)

初回実行は、線形係数の照合で再計算結果の系列を選ぶ際に辞書のキーを参照し、描画後に集計が停止した。対照と実験版の候補系列を選ぶように修正し、初回の6本のCSVが修正後の実行とバイト一致したことを確認した。[初回の失敗記録](../runs/songbird-chirps-left-bronchus-momentum-44100-20261123/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各144判定が通過した。独立十進計算で両側の末端流量と圧力を各1,152点照合し、式の各項の絶対値の和で正規化した残差は流量で1.99×10⁻¹⁶未満、圧力で6.62×10⁻¹⁷未満だった。先行する線形慣性の141判定と全再計算系列を再現し、左セル1の12判定と固定上流12試験を通過した。394入力と26出力のハッシュを確認し、CSV・要約を含む12出力がバイト一致した。採取物10,587,710バイトをRTL9210B-CGに保存した。[実行記録](../runs/songbird-chirps-left-bronchus-momentum-44100-20261123-b/manifest.json)・[再実行記録](../runs/songbird-chirps-left-bronchus-momentum-44100-20261123-b-repeat/manifest.json)・[独立十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-bronchus-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_bronchus_linear_44100.py \
  songbird-chirps-left-bronchus-momentum-44100-local --case cases/songbird-chirps-left-bronchus-momentum-44100.json
```

## 左気管支のセル0から1への枝で線形慣性を連続描画で揃える

固定上流の `songbird::create` は空気嚢ポートの次に左気管支の入口セル0を置き、`Songbird::sample` から `AirwayNetwork::step` を呼ぶ。セル0と1を結ぶ枝では、入口向きと末端向きの流量（cm³/s）を一つの符号付き状態で持つ。前回の両端圧差と運動量から駆動圧（dyn/cm²）を作る。上流は各セルの幾何項を `dx × (1/A)` で作り、その和に空気密度の半分を掛けて慣性 `L` を求める。同断面のこの枝では二次損失がゼロで、線形係数 `L × fs + R` が駆動圧を流量に換算する。新しい流量をセル0の収支から引き、セル1に足す。セル2へ流れる次の枝は、次標本の更新でセル1の新しい圧力を使う。上流の三分岐・定常狭窄試験は共通の枝更新と節点収支を参照している。[鳴禽の生成と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[幾何項と枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L865)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

先行の局所計算では、両制御の押鍵19点後に前回流量0、両端の前回圧と抵抗が一致していた。線形慣性を上流順に再計算し、235点制御の `-0x1.f63d1d5fa7aa7p-31` と256点制御の `-0x1.c15c224ea00fap-31` cm³/sを予測値として登録した。[事前登録](../cases/songbird-chirps-left-bronchus-interior-linear-44100.json)・[先行の枝流量と収支](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-momentum-inner-20261123.json)

先行の25差分を隔離Rustビルドに復元し、`SongbirdAirway::step` から左セル0と1を結ぶ枝を指定した。`AirwayNetwork` で上流順に計算した慣性をこの枝の分母に渡し、持ち越し項には先行版の慣性を使った。通常の描画CLIで対照バイナリとCSVを再現し、固定上流CSVのハッシュを照合した。235点・256点制御で19点後の流量が予測値で上流と一致し、追従0は全点無励振だった。[実験差分](../runs/songbird-chirps-left-bronchus-interior-linear-44100-20261123-repeat/artifacts/left-bronchus-interior-linear.patch)・[初差と判定](../runs/songbird-chirps-left-bronchus-interior-linear-44100-20261123-repeat/summary.json)

| 観測 | 上流との初差の変化（235点制御） | 上流との初差の変化（256点制御） | 対照と実験版の初差（235点／256点） |
| --- | --- | --- | --- |
| 左セル1への流入 | 19点 → 24点 | 19点 → 24点 | 19点／19点 |
| 左セル0圧 | 19点 → 27点 | 19点 → 24点 | 19点／19点 |
| 左セル1圧 | 23点 → 28点 | 25点 → 24点 | 23点／24点 |
| 左気管支末端への流入 | 26点 → 29点 | 26点 → 25点 | 26点／25点 |
| 左気管支末端圧 | 26点 → 29点 | 26点 → 30点 | 26点／26点 |
| 左鳴管流量 | 42点 → 31点 | 57点 → 32点 | 31点／32点 |
| 右鳴管流量 | 45点 → 39点 | 59点 → 59点 | 39点／60点 |
| 気管入口圧 | 41点 → 38点 | 57点 → 57点 | 38点／59点 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

24点後の左セル1への流入差では両端の前回圧、前回流量と線形係数が一致し、持ち越し項だけの置換で復元した。235点制御では既存の慣性を使って時間換算順だけを変えても上流値 `-0x1.ec58a241f86b5p-19` になる。256点制御では慣性の組み立てと時間換算の両方を上流順にすると `-0x1.6473e19d382f1p-19` となり、上流と一致した。左セル1圧の初差は流入だけの置換、左鳴管流量の初差は左末端の前回圧だけの置換、気管入口圧の初差は左鳴管流量だけの置換で復元した。[持ち越し項の補助計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-left-bronchus-interior-linear-20261123.py)・[24点後の置換結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-interior-linear-momentum-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行し、研究ワークスペースと `/tmp` から各177判定を通過した。独立十進計算では左セル1と両側の末端の流量・圧力を各1,728点照合し、式の各項の絶対値の和で正規化した残差は流量で2.08×10⁻¹⁶未満、圧力で8.96×10⁻¹⁷未満だった。先行の左末端枝の線形慣性141判定と持ち越し144判定を、要約と全再計算系列まで再現した。固定上流の12試験も通過した。396入力と26出力のハッシュを確認し、CSV・要約を含む12出力がバイト一致した。採取物12,118,940バイトをRTL9210B-CGに保存した。放射流量と後退差分は対照と全64点一致した。[初回マニフェスト](../runs/songbird-chirps-left-bronchus-interior-linear-44100-20261123/manifest.json)・[再実行マニフェスト](../runs/songbird-chirps-left-bronchus-interior-linear-44100-20261123-repeat/manifest.json)・[独立十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-bronchus-interior-linear-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_bronchus_linear_44100.py \
  songbird-chirps-left-bronchus-interior-linear-44100-local --case cases/songbird-chirps-left-bronchus-interior-linear-44100.json
```

## 左気管支のセル0から1への枝で持ち越し運動量を連続描画で揃える

固定上流の `songbird::create` は左気管支のセル0と1を同断面の直列枝でつなぐ。`Songbird::sample` が鳴管の開口を更新して `AirwayNetwork::step` を呼ぶ。この枝の流量 `U`（cm³/s）を求めた直後に、上流は各半セルから得た慣性 `L` と流量の積を保存する。断面が固定なので、次の枝更新で同じ慣性を使い、保存した積にサンプルレートを掛けて駆動圧（dyn/cm²）の履歴項とする。両端の前回圧差にこの項を加え、線形係数 `L × fs + R` で割る。枝の流量をセル0の収支から引いてセル1に足し、両端の圧力を更新する。上流の三分岐と定常狭窄の試験もこの枝と節点の更新を通る。[気道構成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[枝運動量と節点の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

先行の局所計算で特定した24点後を対象に、235点制御の `-0x1.ec58a241f86b5p-19`、256点制御の `-0x1.6473e19d382f1p-19` cm³/sを予測値として登録した。左セル0と1の圧力、左鳴管と気管入口圧までを押鍵後64点で追う。[事前登録](../cases/songbird-chirps-left-bronchus-interior-momentum-44100.json)

先行の26差分を隔離Rustビルドに復元した。左セル0から1への枝で、既に線形係数に使っていた上流順の慣性を持ち越し項にも渡し、流量を掛けた積をサンプルレートで換算した。通常CLIで対照バイナリとCSVを再現し、固定上流CSVをハッシュ照合した。両制御の24点後の流量が予測値で上流と一致し、先行版の線形係数は全標本でビット一致した。追従0は全点無励振だった。[実験差分](../runs/songbird-chirps-left-bronchus-interior-momentum-44100-20261123-repeat/artifacts/left-bronchus-interior-momentum.patch)・[初差と判定](../runs/songbird-chirps-left-bronchus-interior-momentum-44100-20261123-repeat/summary.json)

| 観測 | 上流との初差の変化（235点制御） | 上流との初差の変化（256点制御） | 対照と実験版の初差（235点／256点） |
| --- | --- | --- | --- |
| 左セル1への流入 | 24点 → 30点 | 24点 → 30点 | 24点／24点 |
| 左セル1圧 | 28点 → 30点 | 24点 → 30点 | 28点／24点 |
| 左セル0圧 | 27点 → 26点 | 24点 → 27点 | 26点／24点 |
| 左気管支末端への流入 | 29点 → 31点 | 25点 → 31点 | 29点／25点 |
| 左気管支末端圧 | 29点 → 31点 | 30点 → 31点 | 29点／30点 |
| 左鳴管流量 | 31点 → 32点 | 32点 → 32点 | 31点／57点 |
| 右鳴管流量 | 39点 → 39点 | 59点 → 64点一致 | 60点／59点 |
| 気管入口圧 | 38点 → 38点 | 57点 → 64点一致 | 39点／57点 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

両制御の30点後の左セル1への流量は、セル0の前回圧だけを上流値へ置換すると一致した。セル0の初差は235点制御の26点後と256点制御の27点後で、どちらも空気嚢ポートからの流入だけで復元した。空気嚢ポート自身の初差は22点後と27点後で、両端圧と線形係数が一致していた。その2点の流量は、持ち越し項の時間換算を `(L × Uprev) × fs` に揃えると復元した。256点制御の右鳴管流量と気管入口圧は、別のCSV照合でも全64点で上流とビット一致した。[左の空気嚢ポートの照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-left-bronchus-interior-momentum-20261123.py)・[局所置換の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-interior-momentum-inlet-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行し、研究ワークスペースと `/tmp` の各180判定を通過した。独立十進計算で左セル1と両側の末端の流量・圧力を各1,728点照合し、式の各項の絶対値の和で正規化した残差は流量で2.08×10⁻¹⁶未満、圧力で8.96×10⁻¹⁷未満だった。固定上流12試験、先行の141・144・177判定と再計算系列、左空気嚢側の追加38判定を確認した。398入力と26出力をハッシュ照合し、CSVと要約を含む12出力がバイト一致した。採取物12,109,884バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/songbird-chirps-left-bronchus-interior-momentum-44100-20261123/manifest.json)・[再実行マニフェスト](../runs/songbird-chirps-left-bronchus-interior-momentum-44100-20261123-repeat/manifest.json)・[独立十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-bronchus-interior-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_left_bronchus_linear_44100.py \
  songbird-chirps-left-bronchus-interior-momentum-44100-local --case cases/songbird-chirps-left-bronchus-interior-momentum-44100.json
```

## 左の空気嚢ポートで持ち越し運動量を連続描画で揃える

固定上流の `songbird::create` は空気嚢の固定圧節点から左気管支セル0へ、長さ0.4 cm、断面積0.05 cm²のポートをつなぐ。`Songbird::control` が空気嚢圧を設定し、`Songbird::sample` が鳴管開口を更新して `AirwayNetwork::step` を呼ぶ。空気嚢ポートの現在の慣性 `L` は管部分と両端半セルの和。固定断面なので、前回の流量 `Uprev`（cm³/s）との積を保持し、次の標本でサンプルレートを掛ける。これを空気嚢圧とセル0の前回圧の差に足した駆動圧（dyn/cm²）から、線形係数と流れの向きに応じた損失で現在流量を解く。空気嚢からセル0へ向かう流れを正とし、セル0の収支に加える。空気嚢は固定圧なので、右気管支には左右の鳴管がつながる気管入口を経由して変化が届く。[気道の構成と制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[ポートの慣性と枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L995)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

先行の保存CSVを使い、左ポートの持ち越し項だけを局所的に変更した。235点制御では押鍵22点後に `-0x1.f8e2586fd59a3p-25`、256点制御では27点後に `-0x1.74adf9bd042c8p-17` cm³/sとなった。これを連続描画の最初の効果として事前登録した。[事前登録](../cases/songbird-chirps-left-sac-momentum-44100.json)・[先行の局所計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-interior-momentum-inlet-20261123.json)

先行の27差分を隔離Rustビルドに復元した。右だけを指定していた運動量換算の対象に左の空気嚢ポートを加え、既存の `(L × Uprev) × fs` を適用した。通常の描画CLIで対照バイナリと全CSVを再現し、固定上流CSVをハッシュ照合した。両制御の22点後、27点後の流量が予測値で上流に一致した。左ポートの線形慣性、抵抗、正逆の損失係数は、対照と全標本でビット一致した。追従0は全点無励振だった。[実験差分](../runs/songbird-chirps-left-sac-momentum-44100-20261123-repeat/artifacts/left-sac-momentum.patch)・[初差と判定](../runs/songbird-chirps-left-sac-momentum-44100-20261123-repeat/summary.json)

| 観測 | 上流との初差の変化（235点制御） | 上流との初差の変化（256点制御） | 対照と実験版の初差（235点／256点） |
| --- | --- | --- | --- |
| 左の空気嚢ポート流量 | 22点 → 54点 | 27点 → 64点一致 | 22点／27点 |
| 左セル0圧 | 26点 → 53点 | 27点 → 64点一致 | 26点／27点 |
| 左セル1への流入 | 30点 → 53点 | 30点 → 64点一致 | 30点／30点 |
| 左セル1圧 | 30点 → 51点 | 30点 → 64点一致 | 30点／30点 |
| 左気管支末端への流入 | 31点 → 51点 | 31点 → 64点一致 | 31点／31点 |
| 左気管支末端圧 | 31点 → 49点 | 31点 → 64点一致 | 31点／31点 |
| 左鳴管流量 | 32点 → 49点 | 32点 → 64点一致 | 32点／32点 |
| 右鳴管流量 | 39点 → 46点 | 64点一致 → 64点一致 | 39点／64点一致 |
| 気管入口圧 | 38点 → 41点 | 64点一致 → 64点一致 | 38点／64点一致 |
| 放射流量 | 60点 → 60点 | 24点 → 24点 | 64点一致／64点一致 |
| 放射流量の後退差分 | 9点 → 9点 | 11点 → 11点 | 64点一致／64点一致 |

256点制御では、左右の空気嚢ポートから気管支の各セル圧・枝流量、両鳴管流量、気管入口圧までを、押鍵後64点すべてで上流とビット照合した。235点制御の左ポート流量の残差はセル0の前回圧で復元し、セル0圧とセル1圧の各初差は下流側への流量だけで復元した。235点制御の41点後の気管入口圧は、気管セル1への流出だけの置換で再現した。[左右の観測と局所置換](../runs/songbird-chirps-left-sac-momentum-44100-20261123-repeat/summary.json)・[気管入口圧の独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-sac-momentum-output-20261123.json)

放射流量とその後退差分は両制御とも対照と全64点一致した。固定上流との後退差分の初差は9点後と11点後に残り、その時点までの放射流量は上流と一致していた。同じ保存流量に上流順の時間換算を適用すると、差分の初差は放射流量自体が初めて分かれる60点後と24点後へ移った。次は放射流量の後退差分を計算する箇所で、この換算だけを通常の連続描画に適用する。[再計算のコード](/Volumes/RTL9210B-CG/voice-simulator/scratch/trace-songbird-left-sac-momentum-output-20261123.py)・[時間換算の比較結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-sac-momentum-output-20261123.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行し、研究ワークスペースと `/tmp` の各122判定を通過した。独立十進計算では両側のポート流量とセル0圧を各1,152点照合し、式の各項の絶対値の和で正規化した残差は流量で1.92×10⁻¹⁶未満、圧力で7.43×10⁻¹⁷未満だった。先行の右空気嚢ポートの119判定と再計算系列、気管入口と放射の追加13判定、固定上流12試験を再現した。398入力と26出力をハッシュ照合し、CSVと要約を含む12出力がバイト一致した。採取物8,014,914バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/songbird-chirps-left-sac-momentum-44100-20261123/manifest.json)・[再実行マニフェスト](../runs/songbird-chirps-left-sac-momentum-44100-20261123-repeat/manifest.json)・[独立十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-left-sac-momentum-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_right_sac_momentum_44100.py \
  songbird-chirps-left-sac-momentum-44100-local --case cases/songbird-chirps-left-sac-momentum-44100.json
```

## 放射流量の後退差分を連続描画で揃える

固定上流の `Songbird::sample` は左右の鳴管開口を更新して `AirwayNetwork::step` を呼ぶ。気道は壁の放射寄与と各放射端の流量を合計し、総流量 `U[n]`（cm³/s）を作る。鳴禽では壁の放射係数が0で、くちばし先端が唯一の放射端。前回の総流量 `U[n−1]` を引いて、構築時に `inv_t` へ格納した内部サンプルレート `fs`（Hz）を掛ける。返値は `(U[n] − U[n−1]) × fs`（cm³/s²）。差分を求めた後で現在の総流量を次回用の状態に保存する。初回の前回流量は0。通常の音声描画では `CreatureVoice::render` がこの値を間引き器へ送り、計測用プローブは `Songbird::sample` の返値と先端流量を同じ行へ出す。[鳴禽の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[壁の既定値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L25)・[気道の放射更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1054)・[音声描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[上流プローブ](../tools/upstream_songbird_airway_probe.rs#L223)

研究版も同じ順で流量を保存するが、時間換算では `T = 1/fs` で割る。実数として等しい二式は binary64 で結果が分かれる。固定上流の `fdtd_impulse_response_agrees_with_frequency_domain_model` は内部出力を角周波数で割って放射流量の伝達関数と照合し、`the_creatures_hold_at_the_lighter_rate` は鳴禽を含む鳴き声の有限性とRMSを32 kHz・48 kHzで確認する。今回の比較では差分の値そのものを各内部標本で照合する。[研究版の差分式](../crates/vocal-core/src/airway/network.rs#L791)・[一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L24)・[鳴禽を含む出力試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L118)

実装前に、1回前の標本も含む保存流量から差分を再計算した。235点制御では押鍵9点後の値が `0x1.2b31398c7fbadp+2`、256点制御では11点後の値が `0x1.6c2676f098de6p+3` cm³/s²となり、どちらも固定上流と一致する。比較窓で値が変わるのは11点と6点。上流に対する初差は流量自体が分かれる60点後と24点後へ移ると予測した。[事前登録](../cases/songbird-chirps-radiation-derivative-scale-44100.json)

左の空気嚢ポートまでの28差分を隔離Rustビルドに適用した。対照のバイナリと3条件のCSVが先行実行と一致したことを確認し、気道の構築時に保持した整数のサンプルレートを後退差分の乗数に使った。間隔の逆数は再計算せず、既存の `dt` は流量と圧力の計算に引き続き使った。通常の `vocal-cli render` で、押鍵前も含めて差分以外の全列が対照とビット一致した。[比較コード](../tools/measure_songbird_chirps_radiation_derivative_scale_44100.py)・[Rustの実験差分](../runs/songbird-chirps-radiation-derivative-scale-44100-20261123-repeat/artifacts/derivative-scale.patch)

| 条件 | 最初に変更した差分値（cm³/s²） | 最初の上流との差 | 上流との一致数 |
| --- | --- | --- | --- |
| 235点制御 | 9点後の `0x1.2b31398c7fbadp+2` | 9点後から60点後へ | 60/64 |
| 256点制御 | 11点後の `0x1.6c2676f098de6p+3` | 11点後から24点後へ | 36/64 |
| 追従0 | 全点無励振 | 差なし | 64/64 |

変更した差分は11点と6点で、実測の全値が局所再計算と一致した。最初に残った差では前回の放射流量が両版で同一で、現在の放射流量だけを上流の値に置くと差分もビット一致した。最初の流量差は235点制御で1 ULP、256点制御で2 ULPだった。前回状態として保持した流量は、後退差分の結果と独立に更新され、今回の変更で気道には差が戻らなかった。[実行の各判定と流量置換](../runs/songbird-chirps-radiation-derivative-scale-44100-20261123-repeat/summary.json)

放射端を流入から再計算し、実験版・上流の先端圧と放射流量を3条件とも全64点で照合した。上流の流入だけを実験版の放射負荷へ渡すと全点一致した。実験版の流入を上流の負荷へ渡すと、先端の初差は残った。くちばしセル0への流入は235点制御で53点後、256点制御で18点後に最初に分かれた。この2点では前回の両端圧の差が一致し、半セル慣性を `dx × (1/A)` で求める局所計算で流量が上流に一致した。235点制御では前回形状の慣性が持ち越し項に効き、256点制御では現在形状の慣性が分母の線形係数に効いた。次の連続描画では、口腔食道腔からくちばしセル0へ入る枝にこの慣性の組み立てを適用する。[入口枝の上流実装](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1218)・[終端とくちばし入口の置換](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-radiation-derivative-scale-20261123-verification.json)

研究ワークスペースと `/tmp` の各35判定が通過し、要約・CSV・差分を含む11出力がバイト一致した。CSVをPython標準の有理数で読み直し、差を丸めてから時間換算を丸める順で各実行2,754点をビット照合した。丸めなしの式に対する差分の最大相対誤差は、対照で1.19×10⁻¹⁶未満、実験版で1.01×10⁻¹⁶未満。固定上流の `airway`、`airway_adversarial`、`engine` の15試験に合格した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。全402入力・24出力をサイズとSHA-256で照合し、採取物4,599,904バイトをRTL9210B-CGに保存した。[初回の保存記録](../runs/songbird-chirps-radiation-derivative-scale-44100-20261123/manifest.json)・[再実行の保存記録](../runs/songbird-chirps-radiation-derivative-scale-44100-20261123-repeat/manifest.json)・[独立照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-radiation-derivative-scale-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_radiation_derivative_scale_44100.py \
  songbird-chirps-radiation-derivative-scale-44100-local
```

## くちばし入口の半セル慣性を連続描画で揃える

固定上流の `songbird::create` は、口腔食道腔（OEC）からくちばしセル0へ `AirwayNetwork::connect` で直列枝をつなぐ。制御更新で音高追従のOEC断面を設定し、`Songbird::sample` が鳴管弁の面積を更新した後に `AirwayNetwork::step` を呼ぶ。気道の標本更新は、節点の面積と長さを補間してから、各節点で `ia = 1/max(A, 10⁻⁶)`、`half_l = dx × ia` を計算する。この枝の現在の音響慣性 `L`（g/cm⁴）は両節点の `half_l` の和に空気密度の半分を掛けた値。正の流量 `U`（cm³/s）はOECからセル0へ流れる。[鳴禽の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[直列枝の構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L455)・[形状と慣性の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L850)

枝は前回の流量・慣性・運動量を保持する。慣性が減った更新では現在の慣性と前回流量から運動量を求め、増えた更新では前回運動量を使う。その運動量に内部サンプルレートを掛け、両端の前回圧の差（dyn/cm²）を加える。線形係数には現在の慣性を時間換算した値と粘性抵抗が入る。流量を解いた後に運動量を保存し、OECから流量を引き、セル0に加える。気道の合流点試験は時系列の安定性、鳴禽を含む描画試験は継続描画中の割り当てを調べている。今回の試験はこの直列枝の流量と、圧力・放射への伝播を標本単位で照合する。[流量と状態の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1027)・[合流点の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L16)・[鳴禽を含む継続描画試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

研究版の通常入口 `vocal-cli render` は `songbird_case::run` から `SongbirdAirway::step` を呼ぶ。研究版の直列枝では `dx/A` を使う。前回の保存流量を入力に両端の `dx × (1/A)` を再計算すると、235点制御の押鍵53点後が `0x1.27fe5f1284f4dp-4`、256点制御の18点後が `0x1.40f2bcaad7fe6p-9` cm³/sとなる。前者は前回形状の慣性、後者は現在形状の慣性を揃えると復元する。両方の値を連続描画の最初の効果として事前登録した。[再実装の枝係数](../crates/vocal-core/src/airway/network.rs#L81)・[事前登録](../cases/songbird-chirps-beak-inlet-half-inertance-44100.json)・[先行の項置換](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-radiation-derivative-scale-20261123-verification.json)

先行の29差分を隔離ビルドで復元した。既存の線形慣性の時間換算で使う枝番号を再利用し、その枝の動的形状更新に両端の逆数乗算を適用した。先行の鳴管ポートで使う片側の乗算も同じ選択で維持した。対照バイナリとCSVは先行実行と一致した。235点制御・256点制御の最初の入口差は予測値に一致し、押鍵後64点ではくちばし6セルの圧力・流入・断面と、放射流量・後退差分の計20列が上流とビット一致した。対照との幾何・押鍵前・追従0の照合、および最小伝播時間の判定も通過した。[実験差分](../runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123-repeat/artifacts/beak-inlet-half-inertance.patch)・[全列の初差](../runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123-repeat/summary.json)

| 条件 | 入口流量の初差を解消 | くちばし端の流入・圧力の初差を解消 | 放射流量・後退差分の初差を解消 |
| --- | --- | --- | --- |
| 235点制御 | 53点後 | 60点後 | 60点後 |
| 256点制御 | 18点後 | 23点後 | 24点後 |

放射負荷は各版の流入からビット再計算できた。256点制御では終端への流入と圧力が23点後に変わり、放射流量と後退差分の最初の効果は1点後だった。今回の比較窓で放射は上流と一致したが、気管末端の壁流量は両制御で2点後から微小差が残った。235点制御ではOEC圧の38点後、気管入口圧の41点後の差も残っている。次は同じ差分を呼気の立ち上がりと減衰を含む `chirps-44100` の既存全コールに適用し、内部放射から間引き・DC除去・PCMへの差を比較する。既存のケース、上流系列、PCMを保存時のハッシュで読めることを確認した。[気道側の残差](../runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123-repeat/summary.json)・[全コールの参照](../runs/songbird-calls-20261120-repeat/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` の各50判定に合格した。CSVから72桁の十進計算で入口の流量に対する圧力収支を各実行576点で照合し、正規化残差は最大2.07×10⁻¹⁶未満だった。同じ独立スクリプトで、上流とのビット一致を3条件の20列×64点で確認した。固定上流12試験に合格し、全408入力と24出力をハッシュ照合した。11出力がバイト一致し、採取物計4,605,764バイトをRTL9210B-CGに保存した。[初回の保存記録](../runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123/manifest.json)・[再実行の保存記録](../runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123-repeat/manifest.json)・[独立計算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-beak-inlet-half-inertance-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_songbird_chirps_beak_inlet_half_inertance_44100.py \
  songbird-chirps-beak-inlet-half-inertance-44100-local
```
