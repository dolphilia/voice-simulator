# 単発ハイハット `t` の閉鎖と摩擦

固定上流の `chimera-cli render beatbox` は、中立姿勢から準備姿勢へ移る成人男性の音源に、48 kHz出力・内部96 kHz、呼気圧8 cmH₂O、基準F0 100 Hz、演奏者の呼気ゲート0を設定する。 `BeatPlayer::gestures` は、単発 `t` の `hat` が生成した相対時刻を `hit − latency` で移す。公称打音0.250秒、テーブルの遅延−0.005秒なので、相対時刻0は0.255秒になる。[単発レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L619)・[予約と遅延補正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L198)・[音色テーブル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L272)

`hat` は `oral_gestures_into` を2回呼ぶ。最初は歯茎破裂音 /t/ で、舌先X/Yの閉鎖目標は6.25/9.68 cm。舌先を31 ms早く指示し、開く指示を20 ms早め、速度倍率3.5、減衰10 msに上書きする。舌体を前に出す目標と顎0.3 cmには弱い重みを与える。次は摩擦音 /s/ で、舌先Yの較正値9.111 cmを使う。立上りを8 msへ制限し、閉鎖を早く緩める影響を抑える。 `blow` は呼気目標と声門開大を加え、呼気ランプの終了後も開大を20 ms保持する。[キットのレシピ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L124)・[調音ジェスチャーの規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[成人男性の子音較正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json#L21)

| 目標 | 保持開始–終了（秒） | 立上り／減衰（秒） | 重み |
| --- | --- | --- | --- |
| 舌先の閉鎖 | 0.174–0.235 | 0.030／0.010 | 40 |
| 舌体、閉鎖時の顎 | 0.205–0.255 | 0.050／0.050 | 1.2／2.2 |
| /s/ の舌先と顎 | 0.259–0.285 | 0.008／0.018 | 40 |
| 摩擦中の舌体 | 0.267–0.285 | 0.008／0.050 | 1.2 |
| 声門開大0.36 cm² | 0.225–0.321 | 0.020／0.030 | 6 |
| 呼気倍率1.25 | 0.215–0.281 | 0.020／0.020 | 1 |

64出力フレームごとの制御更新で、ランプの活性を余弦から求め、調音器を更新する。同じ更新で、呼気目標に対するゲートの時定数を上り25 ms、スコア後の下り20 ms、通常の下り70 msに選ぶ。調音から声道断面を求め、声門開大と圧差から声門面積・流量を更新し、狭窄や歯に配置される乱流源を含めて伝搬と放射を計算する。閉鎖中は口腔内に閉じたセルがあり、再開口後の細い流路で摩擦が生じると予測した。肺圧の基準値と実際のゲート、声門面積と振動は別々に観測する。上流のテストでは全音色の準備と余韻が予約の前後に収まること、既定パターンのレンダーが参照波形と一致することを検査している。[音源の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L456)・[乱流源の位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L55)・[事前登録ケース](../cases/beatbox-hat-t.json)

## 再実装と比較

単発 `t` は発話と同じ舌先閉鎖、舌体補助、較正済みの /s/ の調音目標を組み合わせ、音色固有の速度とランプを適用する。 `beatbox_voice` の入力から7ジェスチャーを生成し、既存の可動声道、肺圧、声門、乱流、出力段を通す。候補の `render` では舌先座標、口腔セルの最小断面、呼気ゲート、声門面積と流量、各乱流源の振幅を採取する。上流プローブにも同じ観測点を追加し、上流CLIの `t.wav` とプローブのPCMがビット一致することを確認した。[音色レシピ](../crates/vocal-core/src/phonetics/beatbox.rs)・[共通の波形出力](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[上流プローブ](../tools/upstream_beatbox_single_probe.rs)

制御の独立計算では、実測した状態を使わず、登録時刻と余弦ランプから各周期の呼気目標 `G` を作り、 `g₁ = G + (g₀ − G) exp(−Δt/τ)` でゲートを進めた。開大は呼気と独立に、基準0.00225 cm²に `0.36 × min(1, 3 × 開大ランプの活性)` cm²を加えた。全24,000フレームで独立計算との差は、ゲート最大 `8.88×10⁻¹⁵`、開大最大 `4.30×10⁻¹⁴ cm²` だった。[独立計算と測定](../tools/measure_beatbox_hat.py)・[上流単独の先行計測](../runs/hat-t-20261120-upstream/summary.json)

## 結果

| 観測 | 再実装の値 |
| --- | --- |
| 口腔閉鎖と再開口 | 202.667–249.000 ms、46.333 ms。閉鎖開始は口腔セル11（0始まり） |
| 閉鎖中の口唇端最小断面 | 最小0.5854 cm² |
| 声門開大とゲート | 最大0.36225 cm²と1.19355。全期間で声門振動の観測値0 |
| 打音5–60 ms後の乱流振幅 | 狭窄65.01、歯121.74、声門86.28 |
| 同区間のPCMのRMS | 0.02445 |
| 末尾50 ms | ゲート最大0.000438、PCM絶対ピーク `3.25×10⁻⁵` |

歯の乱流源は256.000 ms、狭窄の乱流源は256.875 msで最大だった。全区間での声門乱流源の最大は315.917 msで、口腔の二つのピークより約60 ms遅い。乱流の振幅は圧力注入前の値なので、各源がPCMに占める寄与を測るには、同じ調音スコアで歯の乱流源だけを切る対照が必要になる。[乱流の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[計測結果](../runs/hat-t-20261120-a/summary.json)

登録した13項目を2回とも通過した。固定上流とのPCM最大差は `7.28×10⁻¹²`、声門上圧は `2.17×10⁻¹⁰ dyn/cm²`。128と77フレームのホスト幅でWAVと索引CSVはバイト一致した。診断用の声門F0は上流既定のピッチ変動により最大0.326 Hzの差が残る。単発 `B` と発話の /s/ は回帰でWAVと観測CSVが従来の通過実行に一致した。Rustの整形・ワークスペーステスト・Clippyも通過した。[初回](../runs/hat-t-20261120-a/manifest.json)・[リポジトリルートからの再実行](../runs/hat-t-20261120-root/manifest.json)・[キックの回帰](../runs/hat-t-20261120-kick-regression/summary.json)・[摩擦音の回帰](../runs/hat-t-20261120-sibilant-regression/summary.json)

今回の入口はCLIの単発 `t`。パターンの異種音色の予約、ブラウザの実時間再生、開ハイハットの可変長は今後の比較対象。

```bash
python3 tools/measure_beatbox_hat.py hat-t-local-1
```
