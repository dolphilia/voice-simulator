# 調音器の目標追従と舌先の軌跡

## 固定上流の更新順序

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::control` は、必要に応じて `GestureScore::blend_all` で各部位の合成値・重み・速度倍率を求め、内部レートから換算した時間幅で `ArticulatorBank::step` を呼ぶ。その直後に姿勢を `HumanAirway::apply` に渡し、接触補正が入れば位置と速度を補正して断面を再計算する。今回の観測点は `step` 直後。入力には時刻付きの目標・速度倍率・合成済みジェスチャーを使う。[音声の制御ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[スコアの合成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/score.rs#L405)・[調音器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)

調音器は17成分の現在値・速度・基準目標・有効目標を持つ。顎、舌体と舌先の座標、舌根、唇の開きと突き出し、喉頭は cm。軟口蓋は開口を表す cm² で、負値は閉鎖側の制御。舌先の巻き、唇幅、下唇の引き込み、声門上と仮声帯、舌側面、舌背は無次元。速度はそれぞれの単位毎秒。目標を設定するときに部位ごとの可動域へ収め、目標の合成後にも同じ範囲を適用する。重み付き目標があると他の部位は重み付き平均を取る。軟口蓋は基準目標からジェスチャー目標へ `min(1, weight / 2)` だけ進める。重みが0の場合は速度倍率にもジェスチャーを適用しない。[目標と可動域](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L23)・[目標の設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L89)

舌先が自由なときは、そのフレームの全更新より先に、顎と舌体の現在値を読む。基準の舌先を顎の軸（−2.5, 10.5）cmの周りに `−jaw / 9.84` rad 回し、舌体の中立位置からの差を前後0.30、上下0.35倍だけ足す。得られた座標を次の有効目標として使う。取り込んだ目標を基に、各部位で `ω = 2π × 固有周波数 × 有効速度倍率`、`a = ω²(T−x)−2ωv` として、`v ← v+a·dt`、`x ← x+v·dt` の順で半陰的オイラー更新を行う。位置の差分から観測速度を復元できる。絶対値が `10⁻³⁰` 未満の速度と、目標0へ向かう微小位置は0にする。[舌先の基準位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L454)・[合成と積分順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)

上流の母音連続性テストは較正した始点と終点の間を直線補間し、幾何変換の急な不連続を調べる。今回の調音器の時間軌跡には上流クレートを直接呼ぶ計測プローブを用意し、半陰的オイラーの無次元化した漸化式でも別に検算する。[母音間の幾何連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)

## 実装前に登録した比較

内部96 kHz・制御ブロック128サンプル（約1.333 ms）で、指定された初期姿勢と速度0から全17成分を毎フレーム観測する。以前に検証した `/i ɑ u/` の姿勢を使い、フレーム8と144で目標を変更する。イベントを適用した後の状態を記録し、時刻は制御更新後の経過時間を表す。位置・有効目標の許容絶対差は `2×10⁻¹²`、速度は各単位毎秒で `2×10⁻¹⁰`。

| 条件 | 事前の予測 |
| --- | --- |
| [較正母音・舌先座標指定](../cases/articulation-vowels-pinned.json) | フレーム8で顎が6.70 cm/s前後で動き始める。舌先の高さの目標は即時に5.466 cm |
| [較正母音・舌先追従](../cases/articulation-vowels-free.json) | 顎は同じ軌跡。フレーム8の舌先の高さの目標は更新前の姿勢から求めた約7.2884 cm |
| [顎の速度倍率](../cases/articulation-jaw-pace.json) | 速度倍率1で約77 ms、2で約40 msに移動量の95%へ到達 |
| [目標の可動域と合成](../cases/articulation-blend-limits.json) | 弱いジェスチャーで顎の有効目標は約1.5333 cm、軟口蓋は−0.19 cm²で閉鎖側に残る |

## 実装と測定結果

Rustの調音器は基準目標と有効目標を保持し、1フレームの更新結果をまとめて反映する。CLIは各イベントをその制御フレームの先頭で適用し、更新後をCSVに保存する。`internal_start_sample` は制御区間の開始番号、`time_s` は積分後の経過秒。上流プローブの速度倍率列は、上流の基準倍率と指定した合成重みから算出した。[調音器](../crates/vocal-core/src/articulators.rs)・[CLI](../crates/vocal-cli/src/articulation_case.rs)・[上流のプローブ](../tools/upstream_articulation_probe.rs)

独立計算では `h=ω·dt`、`q=v·dt` と置き、`q′=(1−2h)q + h²(T−x)`、`x′=x+q′` の漸化式をNumPyで計算した。自由舌先の回転は複素数の積で求めた。顎の一定目標区間では、状態 `[x−T, q]` を更新する2×2行列のべき乗にも照合した。[独立計算](../tools/measure_articulation.py)

| 条件 | 結果 |
| --- | --- |
| [較正母音・舌先座標指定](../runs/articulation-vowels-pinned-20261119-b/summary.json) | フレーム8の顎は0.421927 cm、6.69554 cm/s。舌先の高さの有効目標は5.466 cmに切り替わった |
| [較正母音・舌先追従](../runs/articulation-vowels-free-20261119-b/summary.json) | 舌先座標以外の15成分は座標指定の条件と全フレームで一致した。同じフレームの更新後の姿勢で目標を求めると、実際の目標から最大0.06239 cmずれた。実際の舌先の高さの軌跡は、座標指定の条件と最大0.98279 cm違った |
| [顎の速度倍率](../runs/articulation-jaw-pace-20261119-b/summary.json) | 95%到達時間は倍率1で77.33 ms、戻りの倍率2で40.00 ms。速度のピークは23.481、47.906 cm/s。行列のべき乗から求めた位置との差は `8.89×10⁻¹⁶ cm` 未満 |
| [目標の可動域と合成](../runs/articulation-blend-limits-20261119-b/summary.json) | 弱い重みを適用した直後の目標は顎1.53333 cm、軟口蓋−0.19 cm²。強い重みでは顎2.6 cm、軟口蓋1.4 cm²で飽和した。重み0の舌背は速度倍率1を保った |

4条件・計32項目が通過した。944制御フレームの全17成分で再実装のCSVが上流とバイト一致した。独立計算との絶対差は位置・目標で最大 `1.78×10⁻¹⁵` 未満、速度で最大 `6.40×10⁻¹⁴` 未満。研究ディレクトリと `/tmp` からの再実行で24ファイルが一致し、固定声道・PCMなど既存5条件の54ファイルも一致した。[再実行の記録](../runs/articulation-vowels-free-20261119-b/manifest.json)・[PCMの回帰](../runs/vowel-voice-i-20261119-f/manifest.json)

```bash
python3 tools/measure_articulation.py articulation-vowels-free-local-1 articulation-vowels-free
python3 tools/measure_articulation.py articulation-jaw-pace-local-1 articulation-jaw-pace
```
