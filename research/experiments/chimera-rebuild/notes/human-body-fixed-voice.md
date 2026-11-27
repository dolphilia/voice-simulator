# 体型を反映した固定姿勢での発声

共通の調音座標を各体型に写した気道を、呼気と体型別の声門で駆動する。[事前登録ケース](../cases/human-body-fixed-voice.json)・[固定気道の比較](human-body-airway.md)・[成人男性の事前回帰](../runs/bodyvoice-20261120-male-before/summary.json)

## 固定上流版での読解

- エンジンの `default_f0` は端点で 110、205、260 Hz を選ぶ。中間は男性・女性・子どもの重みを各音高の自然対数に掛け、足してから指数を取る。半音で見た距離を補間する計算に相当する。通常のエンジンはこの値を音高の目標として声に渡し、現在値は制御更新ごとに目標へ近づく。[engine.rs の default_f0](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L26)・[human_voice.rs の音高更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L540)
- `HumanVoice::apply_source` は、声門の振動による面積係数に振動部長比と体型の長さ比 `k` を掛ける（`0.17 × fold_length × k` cm²）。安静開大と後部の隙間はもともとの設定に `k²` を掛ける。後部の隙間は閉位相にも通気を残し、開放時間を延長する計算からは除かれる。基準開放率は `0.78 − 0.36 × tension + open_phase`。体型による増分は男性で 0、女性・子どもで 0.13。声門では圧力に応じた強さと安静開大が開放率を変え、周期位相を進めてから開閉曲線を評価する。振幅・開大の平滑時定数は 4 ms で、開放率には更新前の隙間、面積には更新後の隙間が効く。[human_voice.rs の apply_source](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)・[glottis.rs の next](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L149)
- `HumanAirway::new` は気管断面 `2.5k²` cm² で肺ポートの直列抵抗 `R_ac = ρc/(2A)` を決める。補償抵抗 `R_ex = R_ac − 0.8 × 980.665/(1000k³)` は dyn·s/cm⁵。内部サンプルレート `fs` で平滑係数 `α = 1 − exp(−R_ex × k/(0.0052 × fs))` を作る。制御周期は出力64フレーム相当で、平滑したゲートを圧力目標に変換し、内部サンプル間を直線で補間する。内部サンプルごとに旧肺ポート流量を低域通過させ、`R_ex × U_filtered` を呼気圧に加える。それから旧声門上下圧で面積を更新し、伝搬後の流量を次時刻の入力に使う。圧力は dyn/cm²、流量は cm³/s。[human_airway.rs の肺ポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L149)・[human_voice.rs の render](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[呼気の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L512)
- 上流のテストは体型ごとの較正済み /a/、男性 112 Hz、女性 205 Hz、子ども 260 Hz で、周期流量の振幅、閉じるときの流量勾配、H1–H2 を比較する。既定の揺らぎとゲインを含むため、今回の比較は共通座標、共通ゲイン、揺らぎを0にした条件で登録する。既定音高と同じ周波数へ初期化してグライドを抑え、女性の 110 Hz 条件を置いて音高を揃えた比較も行う。[上流の body_source.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_source.rs)

## 検証設計

同じ座標のため、体型を変えると声道と音源の両方が変わる。周期面積は測定した位相、ゲート、発声係数から独立に再構成し、流量と PCM は同じ時刻の上流系列に照合する。64 kHz の直結条件では、すべての内部サンプルの上流肺ポート流量を読み、旧流量に対する低域通過フィルタと呼気圧の補間から候補の圧力境界を検査する。男性 110 Hz は変更前後で旧ケースを再実行して比較する。

計測器は `git archive` で固定版を一時ディレクトリに展開し、その場で `git init` してから、現在の音高を初期化する1メソッドのパッチを適用する。ビルドした計測用の上流プローブは声門・気道・出力の通常の `render` を実行する。初回は現在値のフィールドが非公開だったためプローブのビルドで中断した。2回目は親の Git リポジトリの配下でパッチを適用しようとしたため、対象パスが除外された。一時ディレクトリのリポジトリを独立させて修正した。[比較のパッチ](../tools/patches/upstream-fixed-voice-initial-pitch.patch)・[初回の実行](../runs/bodyvoice-20261120-a/manifest.json)・[2回目の実行](../runs/bodyvoice-20261120-b/manifest.json)

## 実装と結果

断面から気道を作る時点で体型係数と肺ポートの直列抵抗を保持し、同じ値を `FixedVoice` の呼気と声門に渡した。CLI の固定姿勢ケースは `voice.f0_hz` があればその値、なければ `body` の既定値を使う。声門係数と肺の回路は CHIMERA の式に従う。[固定気道](../crates/vocal-core/src/airway/human.rs)・[固定発声](../crates/vocal-core/src/voice.rs)・[CLI](../crates/vocal-cli/src/geometry_case/voice.rs)・[上流のMIT通知](../LICENSE-CHIMERA)

| 条件 | F0（Hz） | 声門が開いていた最後の位相 | 声門面積の最大と最小の差（cm²） | 声門流量の最大と最小の差（cm³/s） | PCMのRMS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 成人男性 | 110 | 0.6021 | 0.14025 | 397.59 | 0.11299 |
| 成人女性 | 205 | 0.7318 | 0.08457 | 246.35 | 0.17608 |
| 子ども | 260 | 0.7308 | 0.03632 | 113.58 | 0.10130 |
| 3体型の混合 | 169.4993 | 0.6771 | 0.08935 | 259.58 | 0.14743 |
| 成人女性、音高を揃えた条件 | 110 | 0.7317 | 0.08457 | 261.08 | 0.04854 |
| 子ども、内部・出力とも64 kHz | 260 | 0.7309 | 0.03632 | 113.99 | 0.10873 |

定常値は開始後0.4〜0.7秒。開放終了の位相は、面積が推定した閉位相の面積を `10⁻⁸ cm²` 以上上回った観測点から取った。110 Hz で揃えると女性は男性より0.1296周期長く開いていた。同じ女性の体型・姿勢で205 Hz と110 Hzを比べると、声門面積の振幅は小数点以下5桁まで同じで、PCMのRMSは205 Hzで約3.63倍だった。どの高調波・共鳴が差に寄与したかは未計測。[数値と観測系列](../runs/bodyvoice-20261120-c/summary.json)

6条件の全60項目が通過。上流とPCMサンプルがバイト一致し、内部系列の差は各上流系列のピークに対して最大 `4.12×10⁻¹³`。64 kHz の直結では、独立計算との差が全サンプルで声門面積 `9.30×10⁻¹⁶ cm²`、肺境界圧 `3.09×10⁻¹¹ dyn/cm²` 以下だった。成人男性の旧 /ɑ/ ケースでは変更前後のWAVと出力・内部時系列がバイト一致した。成人男性の固定 /i/ の Worklet 回帰も12項目を通過し、CLIとブラウザのWAVが一致した。[実行記録](../runs/bodyvoice-20261120-c/manifest.json)・[変更前](../runs/bodyvoice-20261120-male-before/manifest.json)・[変更後](../runs/bodyvoice-20261120-male-after-b/manifest.json)・[Worklet](../runs/bodyvoice-20261120-worklet/manifest.json)

`/tmp` からの再実行も全60項目を通過し、ケース・観測・PCM・要約の56ファイルでSHA-256が一致した。体型別の比較は固定姿勢のCLIで実施した。体型別の較正済み母音目標と、可動調音やブラウザからの体型選択は次の工程に残る。[再実行](../runs/bodyvoice-20261120-repeat/manifest.json)・[再開地点](../progress.md#未達の条件と次の作業)
