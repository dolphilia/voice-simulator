# 声道の扇状走査線の一時割り当て

## 固定上流の読解と事前登録

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanAirway::commit` は調音状態から `HumanVocalTract::compute` を呼び、格子と断面を更新する。上流は最大64件の交差距離と退出フラグを `Scratch` に事前確保する。`ray_crossings` は輪郭の線分順に距離と退出フラグを記録し、`fan_inner` は距離が厳密に大きい場合だけ先行値を移動する。かすめた頂点の出入りは同距離なので元の順序が残る。`geometry_continuity` は頂点接触と較正母音の遷移を検査する。[上流の気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[交差の取得](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L144)・[扇状走査](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L947)・[上流のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L205)

候補の `Ray::crossings` は走査線 `o + t d` と輪郭線分の交差を線分の順に列挙する。`t` は cm、退出は `cross(d, edge) < 0` で決まる。先に外側で最も近い距離 `roof` を取り、内側の交差を `roof + 1.5 cm` まで集める。先頭が退出ならそこを起点にし、残る組織層の厚さを起点に足す。先頭が進入か交差がなければ、逆向きに最大2.5 cm探す。隙間は `max(0, roof − floor)`。初期版では取得の段階で64件に制限した後、走査線ごとに `Vec` へ集めて安定ソートしていた。 `HumanTractControl::apply` はこの格子を `area_profile_from_contacts` と `resample` に通し、必要なら接触補正後に `reapply` で再計算する。[候補の走査](../crates/vocal-core/src/anatomy/grid.rs#L100)・[調音から断面への経路](../crates/vocal-core/src/airway/tract_control.rs#L91)

変更範囲は扇状走査線の交差の格納と並べ替え。同距離は比較上等しいまま扱い、最初の64件という打ち切り位置、退出フラグ、距離・厚さの計算順を保持する。独立に計算できる折り返し輪郭では、同距離に退出・進入が並ぶ順に応じて起点込みの値は9 cmと−2.5 cmになる。交差が65件ある鋸歯状輪郭では、64件までの最後の進入から外壁までを組織として合計すると48 cmになる。交差のない輪郭では−2.5 cm。通常の入口は `ɑpɑ` の実時間発話と、母音・口唇・舌接触のCLIケース。固定した再実装・上流と同じ断面・PCMを予測し、基準で45,656回あったネイティブの割り当てを全区間と冒頭32量子以降で60%以上削減できると予測する。描画時間と予算超過は同じ条件で記録する。[登録条件](../cases/fan-crossing-allocations.json)・[固定した実時間基準](../runs/worklet-live-ipa-20261119-d/manifest.json)

## 実装と再現手順

`Ray::fan_floor` の交差をローカルの固定長配列に集めながら挿入ソートする。先に取得件数を制限し、距離が厳密に大きい先行要素だけを後ろへ移すので、同距離の退出フラグや符号付きゼロの順序は輪郭の線分順になる。使用中の範囲だけを従来の層の計算へ渡す。折り返しのテストでは65件目を先頭と同じ距離に戻し、距離順に並べる前に65件目が除かれることを検査した。[実装とテスト](../crates/vocal-core/src/anatomy/grid.rs#L145)

比較ツールは基準のマニフェスト、保存された走査コード、使用する保存出力のSHA-256を照合する。候補のブラウザ発話と3条件のCLIの子実行を再生成し、子実行のマニフェスト・ハッシュを要約に記録する。実時間のソース記録は基準から `grid.rs` だけが変わったことを検査する。比較全体の終了コードは登録結果を反映する。[比較ツール](../tools/measure_fan_crossing_allocations.py)

```bash
python3 tools/measure_fan_crossing_allocations.py fan-crossing-allocations-local-1
```

## 結果と採用判断

同じケースを研究ディレクトリと `/tmp` から実行した。両回で49,828フレームの実時間・オフラインPCM、断面・声門・圧力・流量の観測値は基準版とビット一致した。CLIの詳細な発話時系列と母音・口唇・舌接触の3つの断面時系列はバイト一致。候補の交差テスト4件と、上流の形状連続性テスト5件が通過した。上流では既知の突き出した下唇の段差を扱う1件が既定で除外されている。[初回の判定](../runs/fan-crossing-allocations-20261119-a/summary.json)・[再実行の判定](../runs/fan-crossing-allocations-20261119-b/summary.json)・[上流のテストログ](../runs/fan-crossing-allocations-20261119-b/artifacts/upstream-geometry-tests.log)

| ネイティブ計数の区間 | 基準 | 候補 | 削減率 |
| --- | ---: | ---: | ---: |
| 全390量子 | 45,656回 | 23,370回 | 48.81% |
| 冒頭32量子以降 | 41,752回 | 21,450回 | 48.63% |

削減率60%の予測は両区間で未達。候補の残りは完全な128フレームの量子で毎回60件、末尾36フレームで30件だった。登録範囲の `Ray::fan_floor` の一時配列から22,286件を取り除き、全区間で60%に達するにはあと5,108件を減らす必要がある。数値の一致と削減件数の再現を根拠に、固定長の実装を採用した。登録条件は維持し、両実行の総合判定は不通過のまま保存した。[実時間の計数](../runs/fan-crossing-allocations-20261119-b-live/artifacts/native-allocations.log)・[総合判定](../runs/fan-crossing-allocations-20261119-b/manifest.json)

実時間発話そのものは各19項目を通過した。冒頭32量子以降の処理時間のp99は1 msと2 msで、基準は2 ms。測定時計は1 ms刻みで、どちらの実行でも全区間で2量子が2.667 msの予算を超過した。線形メモリ増加と発話中の量子番号の欠落は両回とも0件。残る割り当ての出所は、まず輪郭生成の `SagittalModel::compute`、接触格子、断面再標本化を区間別に計数する。[初回の実時間測定](../runs/fan-crossing-allocations-20261119-a-live/summary.json)・[再実行の実時間測定](../runs/fan-crossing-allocations-20261119-b-live/summary.json)・[輪郭生成](../crates/vocal-core/src/anatomy.rs#L175)

10母音の隣接遷移、ブラウザの英語発話・歌唱も回帰検証を通過した。英語発話・歌唱のWAVと観測JSONは、前回の通過実行とバイト一致した。[10母音の遷移](../runs/fan-crossing-allocations-20261119-ten-vowels-regression/summary.json)・[英語発話](../runs/fan-crossing-allocations-20261119-english-regression/summary.json)・[英語歌唱](../runs/fan-crossing-allocations-20261119-song-regression/summary.json)
