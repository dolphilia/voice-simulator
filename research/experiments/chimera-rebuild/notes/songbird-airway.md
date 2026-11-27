# 左右の鳴管と共通気管

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。片側の振動子は8条件で上流と開口率を照合済み。今回は左右の振動子を気道に接続し、内部サンプルの開口・流量・圧力・放射を調べる。演奏側の入力平滑化を通った値に相当する条件を、両実装の気道制御へ直接渡す。[片側の鳴管](songbird-syrinx.md)・[今回の事前登録](../cases/songbird-airway.json)

## 入力から気道まで

`chimera-cli render creature songbird` が `CreatureVoice::new` を呼ぶ。48 kHz出力では内部レート192 kHz、制御間隔は64出力フレームに当たる256内部サンプル。初期制御は呼気ゲート0で適用して断面を目標へ即座にそろえ、レンダー中の制御更新はパラメータ・呼気を平滑化してから次の制御区間の断面補間を準備する。今回の比較は、その下の `CreatureSim::control` と `sample` を直接使うため、登録した制御値をサンプル番号で追える。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)・[制御とレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

空気嚢から左右0.8 cmの気管支に入る。各気管支の末端は長さ0.08 cmの可変ポートで3.6 cmの共通気管につながる。気管末端から喉頭のポートを経て口腔食道腔（OEC）へ入り、1.3 cmのくちばしを通って放射する。管のセル数は `floor(length/(35000/fs/0.93))` を3〜120に制限する。192 kHzでは左右4セルずつ、気管18セル、くちばし6セル。気管壁は質量0.6 g/cm²、抵抗1000 dyn·s/cm³、剛性10⁶ dyn/cm³で流量を蓄え、壁から外への放射係数は0。初期容積0.4 cm³のOECは、長さをその立方根とする1節点。[気道構成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L41)・[管の分割と壁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L8)・[気管壁の係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs#L29)・[空気嚢と空洞](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L466)

`Songbird::control` は空気嚢の固定圧を `pressure_kpa × 1000 × breath_gate × 10` dyn/cm²にする。右の指定音高は左に `2^(interval/12)` を掛ける。側別ゲートは `voices=0` で左のみ、0.5で両側、1で右のみ。呼気ゲートは空気嚢圧だけに掛かる。低い側の指定音高 `f` で OEC の目標容積 `0.03 / (0.35 × (f/5570)²)` cm³を作り、`purity` の割合で手動容積と混ぜて0.04〜2.5 cm³に制限する。くちばしの断面目標はセル中心 `u` に対して `0.012 + gape × (0.05 + 0.22u)` cm²。初期設定以降は目標断面に向けて制御区間内で線形補間する。[制御の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[補間の準備](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)

## 一サンプルの更新と予測

左右の振動子を一サンプル進め、開口率に0.03 cm²を掛けてポートに即時反映する。次いで `AirwayNetwork::step` が断面と体積流量源、枝流量、管壁、節点圧、放射の順に更新する。ポート面積が0.0002 cm²未満なら流量は0。開いたポートでは慣性 `L` と抵抗 `R`、流れ方向に応じた損失 `K` から、`(L/Δt + R)U + K|U|U = ΔP + min(L,L_prev)U_prev/Δt` を解く。共通気管の入口では壁流量と下流流量を左右の流入から差し引き、`Δt/C_eff` を掛けて圧力増分を得る。`C_eff` は容積由来の値と `Δt²Σ(1/L)/2.4` の大きい方。放射出力はくちばし外端を通る体積流量の差分を秒で割った値。[開口面積の反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[枝の損失と運動量](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L979)・[壁と節点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1052)

定常の片側・両側条件では、活動側の開口列は同じで流量は異なると予測した。両側の放射には2,600 Hzと7半音上の成分を見込む。呼気を0にした対照は初期形状を固定し、開口が振動しても流量と放射が0と予測する。別レートと途中の呼気・音程・OEC・くちばしの変更も照合する。上流の動物試験は出力とテレメトリ、気道の境界条件試験は三方向分岐と狭窄を検査する。[上流の音声とテレメトリの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[三方向分岐と狭窄の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L16)

## 実装と実測

左右の音源には既存の `SyrinxLabia`、分岐・壁・放射には既存の `AirwayNetwork` を使った。初期断面は制御パラメータから直接組み立て、圧力と流量は0から開始した。上流プローブは `songbird::def().create` で同じ鳴禽を作り、公開インターフェースで制御・断面初期化・内部サンプル更新を呼ぶ。各サンプルのCSVは枝と節点を更新した直後の観測値。観測した放射はくちばし先の体積流量と、その時間微分。[気道の実装](../crates/vocal-core/src/airway/songbird.rs)・[固定上流プローブ](../tools/upstream_songbird_airway_probe.rs)・[全判定](../runs/songbird-airway-20261120-a/summary.json)

固定上流に対し、6条件の開口率とポート面積は全サンプルで一致した。鳴管枝の流量の最大絶対差は `2.13×10⁻¹³ cm³/s`、気管支末端・共通気管入口の圧力では `3.71×10⁻¹⁰ dyn/cm²`、放射流量の時間微分では `1.23×10⁻⁸ cm³/s²` だった。192 kHzの両側条件で最初に観測した差はサンプル7の右気管支末端の圧力で `3.64×10⁻¹² dyn/cm²`。その時点の右ポート面積は0.000188 cm²で、右の流量は両実装とも0。後続の気道では共通気管入口の圧力がサンプル10、右ポート流量と放射がサンプル31で初めて異なった。観測上は、最初の差を呼気の加圧から気管支末端に伝わる区間まで絞れた。[差の時刻と絶対値](../runs/songbird-airway-20261120-a/summary.json)

独立計算では、前サンプルの圧力・流量と今回の開口面積から鳴管枝の流量を再計算した。上流と候補の最大誤差は `3.56×10⁻¹⁴ cm³/s` 以下。気管入口の枝・壁流量の収支から得た圧力更新は `7.28×10⁻¹² dyn/cm²` 以下の誤差だった。圧力増分が1 dyn/cm²以上の試料では流量収支から実効コンプライアンスを逆算し、式による値と照合した。192 kHzの両側の幾何由来の値は `6.44×10⁻⁹ cm³/(dyn/cm²)`、分岐の安定化下限の最大値は `4.24×10⁻⁹ cm³/(dyn/cm²)`。登録した全条件で幾何由来の値が使われ、無呼気の対照は圧力増分が0のため逆算の対象外だった。[枝と節点の判定](../runs/songbird-airway-20261120-a/summary.json)・[独立計算](../tools/measure_songbird_airway.py)

片側を開いた実行と両側を開いた実行で、活動側の開口は全サンプル一致した。0.09〜0.15秒の枝流量RMSは左が10.397から13.770 cm³/sへ増え、右が18.903から17.910 cm³/sへ下がった。同じ窓で両側の流量を観測すると、気管から気管支へ向かう逆流が左1,296、右1,317サンプルあった。放射のスペクトルには2,600 Hzと3,900 Hzのビンにピークがあった。周波数ビンの幅は約16.67 Hzで、右の指定は3,895.60 Hz。無呼気の対照では左右の開口が振動し、圧力・流量・放射は全サンプルで0だった。[片側と両側、および無呼気の対照](../runs/songbird-airway-20261120-a/summary.json)

制御を途中で変える条件では、サンプル15,360で呼気ゲートを1から0.6へ下げ、空気嚢圧は9,000から5,400 dyn/cm²へ同じサンプルで下がった。口腔食道腔の断面は0.53570から0.78794 cm²へ、くちばしの先端断面は0.15042から0.07492 cm²へ、256内部サンプルをかけて変わった。[制御ケース](../cases/songbird-airway.json)・[観測CSV](../runs/songbird-airway-20261120-a/artifacts/gesture/candidate.csv)

研究ディレクトリと `/tmp` から各232項目を通過し、出力CSVと個別ケース・設定JSONの24ファイルがハッシュ一致した。固定上流の気道・動物音声・リアルタイム試験13件、片側の鳴管音源の回帰71項目も通過した。176.4 kHzでは片側の気管支が3セルになり、同じ接続で照合できた。[初回](../runs/songbird-airway-20261120-a/manifest.json)・[再実行](../runs/songbird-airway-20261120-repeat/manifest.json)・[鳴管単体の回帰](../runs/songbird-airway-syrinx-regression-20261120/summary.json)
