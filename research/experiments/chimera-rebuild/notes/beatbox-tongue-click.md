# 舌打ち音の二重閉鎖と空洞圧

単発キットは成人男性の準備姿勢と肺のゲート0を用い、`BeatPlayer::gestures` に打音0.250秒を渡す。舌打ち音 `!` の遅延−7 msを引くため、調音スコアの原点は0.257秒。シーケンサーも200 msの先読みで打音時刻を予約し、同じ調音レシピを使う。アクセントとステップ長はこの音色の調音には反映されない。上流の音色テストには全音色の前後時間と先読み、プリセットの記譜の往復がある。Engineのテストは打音の予約とホスト分割の影響を検査する。[単発入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L621)・[タイミング](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L195)・[音色レシピ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L220)・[音色試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L46)・[Engine試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

`tongue_click` は /t/ の舌先を前側の閉鎖に使い、通常の歯茎音で舌体を前に出す補助目標を取り除く。奥は /k/ を使い、舌体Yの目標を7.85 cm、顎を0.4 cmにして舌背を下げる余地を取る。舌体Yの速度は1.35倍。舌背の目標は無次元1で、速度は2倍。単発の各目標の保持時間は次のとおり。[音素の目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L137)・[タイミングと強度の算出](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

| 目標 | 保持開始–終了（秒） | 立上り／減衰（秒） | 重み |
| --- | --- | --- | --- |
| 舌先X/Y | 0.106–0.237 | 0.030／0.010 | 40 |
| 奥舌の舌体Y | 0.113–0.258 | 0.030／0.030 | 40 |
| 顎、舌体X | 0.137–0.292 | 0.050／0.050 | 2.2、0.25 |
| 舌背下降 | 0.227–0.263 | 0.040／0.030 | 40 |

基準姿勢に重み0.05を置き、ジェスチャーを余弦ランプで合成する。舌背は自然周波数9 Hzの二次系で、制御更新ごとに速度、位置の順に積分する。形状計算では舌体中心から舌先までの正規化X座標を `u` とし、その内側で `−0.9 × dorsum × sin²(πu⁰·⁸)` cmを舌の円弧と舌面の内点に足す。体積はセルの平均断面積と長さから算出し、気道ソルバーは内部サンプルごとの `−ΔV/Δt` を低域通過させて流量源へ加える。閉鎖の判定はセルの最小断面積で行う。空洞の空気が減圧され、前側が開くと口端が放射するという順序を予測した。[調音器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L102)・[舌背の形状](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L862)・[体積変化の注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L834)

音響格子の口腔セルごとの最小断面積、圧力、体積を記録する。閉じたセルの連続区間の間に開いたセルがあるフレームを探し、同じ閉鎖の組で空洞体積が増えるか、体積で重みを付けた内部圧力が下がるかを判定する。前側閉鎖の解除後35 msのPCMと口端流量も確認する。発声経路と独立の計算では登録した保持時間と重みから舌背の位置を復元する。[単発ケース](../cases/beatbox-tongue-click.json)・[パターンケース](../cases/beatbox-pattern-tongue-click.json)

```mermaid
flowchart LR
    A["奥舌と舌先で閉鎖"] --> B["舌背が下がり空洞が拡大"]
    B --> C["空洞の圧力が低下"]
    C --> D["舌先が先に開き空気が流入"]
```

## 初回の差と判定の改訂

初回の単発はスコアと舌背の運動、閉鎖・解除の時刻、各セルの断面・圧力・体積、PCMが許容差内だった。最初に異なったのはフレーム6527の最小セル番号。候補では2番と3番の最小面積がともに0 cm²、上流では2番が `1.075×10⁻¹⁸ cm²`、3番が0 cm²だった。幾何補間の端数で最小セルの番号が隣に移ったフレームが64件あった。判定第2版では、選ばれた双方のセル面積が、両方の時系列で `10⁻¹² cm²` 以下のときに限り閉鎖の同率とする。この値は気道の閉鎖閾値0.0002 cm²より8桁以上小さい。各セルの面積と音響状態は従来の許容差で検査する。[初回](../runs/click-20261120-single-a/summary.json)・[初回ケース](../cases/beatbox-tongue-click.json)・[第2版](../cases/beatbox-tongue-click-v2.json)

## 実装と検証

`!` の調音スコアを単発・パターンの共通レシピに追加し、上流と同じ出力フレーム末尾で口腔18セルの最小断面、圧力と体積を採った。舌背の変位は独立した二次系の積分と、単発・パターン全体で最大 `1.72×10⁻¹³` の差に収まった。空洞の体積と平均圧は出力CSVから再計算できる。[レシピ](../crates/vocal-core/src/phonetics/beatbox.rs)・[計測器](../tools/measure_beatbox_tongue_click.py)・[上流の観測](../tools/upstream_beatbox_oral_trace.rs)

| 観測量 | 単発 `!` | アクセント付きパターン `B . !> \| -` |
| --- | ---: | ---: |
| 二重閉鎖を作る口腔セル（0始まり、声門側から） | 5、11 | 5、11 |
| 二重閉鎖の開始–舌先解除 | 137.083–246.750 ms | 337.083–446.750 ms |
| 二重閉鎖中の空洞体積の初期値–最大値（cm³） | 0.833–3.922 | 0.833–3.922 |
| 二重閉鎖中の空洞圧の最小（dyn/cm²） | −58,224 | −58,603 |
| 舌先解除後35 msの口端流量の最大絶対値（cm³/s） | 498.61 | 501.35 |
| 舌先解除後35 msのPCMピーク | 0.59554 | 0.59692 |
| PCMの上流との差（最大絶対値） | `2.92×10⁻¹¹` 以下 | `5.83×10⁻¹¹` 以下 |

単発・パターンの空洞圧が最小となるのは、舌先の解除を検出する1出力フレーム前だった。その後の口端流量の最大絶対値は、空気が口へ入る負方向で観測された。セル5の最小断面が0.0002 cm²を最初に超えるのは、両条件ともセル11の44.021 ms後だった。上流の `artifacts/upstream.csv` または `artifacts/upstream-trace.csv` で、`oral_cell_5_minimum_cm2`、`oral_cell_11_minimum_cm2`、`lip_flow_cm3_s` の列から時刻と符号を照合した。[単発の実行](../runs/click-20261120-single-b/manifest.json)・[パターンの実行](../runs/click-20261120-pattern-b/manifest.json)

単発13項目、パターン16項目が通過。出力48 kHz、内部96 kHz、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。128・77フレームで波形がバイト一致し、上流プローブのPCMは単発キットと通常の `Engine` のPCMに一致した。候補のRust整形、Clippy、ワークスペーステストと上流の打音・Engineテストも通過した。

研究ディレクトリと `/tmp` からの実行で、設定、PCM、時系列、要約など単発11ファイルとパターン12ファイルがバイト一致した。奥舌閉鎖のヘルパーを共有する吸気スネアの単発・パターンも再実行し、変更前と設定、PCM、時系列、要約など各7ファイルがバイト一致した。[単発の再実行](../runs/click-20261120-single-repeat/manifest.json)・[パターンの再実行](../runs/click-20261120-pattern-repeat/manifest.json)・[吸気スネア単発の回帰](../runs/click-20261120-single-after/manifest.json)・[吸気スネアパターンの回帰](../runs/click-20261120-pattern-after/manifest.json)
