# スネア `Pf` の唇の破裂と唇歯摩擦

固定上流の単発キットは、準備姿勢の成人男性を出力48 kHz・内部96 kHzで描画する。公称打音0.250秒、入力長0.15秒、アクセント1。パターン再生は128出力フレームごとに先読み200 msの範囲を予約し、記譜の `pF>` を `Pf`、アクセント1.3に正規化する。いずれの入口も `BeatPlayer::gestures` で `snare` を呼び、遅延18 msを引いた時刻へ4ジェスチャーを移して音源のスコアに足す。今回の `Pf` は入力長に依存しない。[単発キット](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L619)・[パターンからの予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)・[音色表と記譜](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L270)

`snare` は破裂音 /p/ の唇開度−0.25 cmを使う。両唇閉鎖のタイミング規則で、区間の開始より22 ms先行させ、終了より19 ms早く解除指示を出す。速度3.5、解除側のランプ10 msに変更する。唇歯摩擦音 /f/ では下唇を上切歯へ寄せる無次元目標 `labiodental = 1` と較正済みの唇開度0.016 cmを使う。摩擦側の立上りを8 msに縮め、両唇の破裂側の目標を早く緩めるのを防ぐ。 `blow` では声門開大0.45 cm²と呼気倍率 `1.7 × accent` を加え、呼気の40 msランプが終わっても開大目標を20 ms保持する。[スネアのレシピ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L196)・[口腔ジェスチャーの規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[/f/ の較正値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json#L9)

| 目標 | 保持開始–終了（秒） | 立上り／減衰（秒） | 重み |
| --- | --- | --- | --- |
| 両唇閉鎖 | 0.150–0.213 | 0.030／0.010 | 40 |
| 唇歯摩擦 | 0.242–0.312 | 0.008／0.018 | 40 |
| 声門開大 | 0.187–0.367 | 0.020／0.030 | 6 |
| 呼気 | 0.177–0.307 | 0.020／0.040 | 1 |

出力64フレームごとに調音を半陰的Euler法で進め、下唇縁を切歯直下の点へ移す。 `labiodental` が0.5へ近づくにつれ、接触モデルで両唇の隙間を制限する項は滑らかに外れ、切歯と下唇による狭窄が残る。音響計算は呼気のゲートで肺境界圧を動かし、声門面積、流量、狭窄起点の乱流、放射を順に更新する。歯へ噴流が衝突する別の乱流源には狭窄から歯までの距離条件があるため、これも単独の系列として観測する。スコアテストは正規化した `Pf` を含む記譜を、Engineテストは複数音色のPCMと描画ブロックの分割を確認する。[唇の幾何](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L809)・[唇の接触](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1165)・[乱流源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[上流のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L37)

単発は両唇の閉鎖中に声門上圧が増加し、開く際の波形ピークの後、270–306 msの窓で下唇が上がり狭窄由来の乱流が続くと予測した。呼気・声門開大に加え、唇歯調音器の位置を独立に積分する。パターン `B . pF> | -` では、0.450秒にアクセント1.3のスネアが予約され、呼気目標が2.21となる。休符を含む予約の時刻、音響、分割幅128と77での一致を確認する。[単発ケース](../cases/beatbox-snare-pf.json)・[パターンケース](../cases/beatbox-pattern-snare-pf.json)

## 実装と検証

Rustの音色レシピは、既存の両唇閉鎖、摩擦の調音手順、呼気のジェスチャーを使う。単発とパターンは同じレシピを呼び出す。観測CSVには唇歯調音器の無次元位置を追加し、最小断面や狭窄の歯からの距離と照合した。独立計算では呼気と声門開大の余弦ランプを絶対時刻から組み立て、唇歯調音器については目標 `w / (0.05 + w)` を使って周波数10 Hzの二階方程式を制御周期ごとに積分した。 `w` は摩擦ジェスチャーの重み。単発での独立計算との差は、ゲート最大 `2.69×10⁻¹⁴`、開大 `9.96×10⁻¹⁴ cm²`、唇歯位置 `3.33×10⁻¹⁴` だった。[再実装のレシピ](../crates/vocal-core/src/phonetics/beatbox.rs)・[測定と独立計算](../tools/measure_beatbox_snare.py)

単発の初回は波形と内部系列が固定上流に一致した。閉鎖の観測窓を232 msで終えたため、閉鎖から開口への判定が双方で未達だった。第2版では窓を摩擦の観測が始まる270 msまで広げた。音源の設定、閉鎖の断面積の閾値、波形比較の許容差は同じ条件を使った。[初回の結果](../runs/pf-20261120-single-a/summary.json)・[第2版のケース](../cases/beatbox-snare-pf-v2.json)

| 単発での観測 | 再実装の値 |
| --- | --- |
| 両唇の閉鎖と再開口 | 148.708–238.688 ms、89.979 ms |
| 閉鎖中の声門上圧の上昇 | 12,284.84 dyn/cm² |
| 開口後のPCMピーク | 243.229 msに0.19279 |
| 270–306 msの唇歯位置と口腔最小断面 | 中央値0.9635と0.2986 cm² |
| 同区間の狭窄から歯までの距離 | 中央値0.1632 cm |
| 同区間の狭窄乱流と歯への衝突乱流 | 振幅ピーク122.72と0 |
| 単発の呼気と声門 | ゲート最大1.69389、開大最大0.45225 cm²、声帯振動0 |

再開口フレームの唇開度は−0.02817 cm、唇歯位置は0.13020だった。接触モデルの引き継ぎ補正を計算すると、有効唇開度は+0.03246 cmになる。唇開度の負値と閉鎖判定が一致しない区間では、下唇が切歯へ移動しているか、音響グラフの最小断面が正になっているかも観測する必要がある。[上流の接触計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1165)・[第2版の観測とハッシュ](../runs/pf-20261120-single-b/manifest.json)

単発とパターンは各14項目を通過した。単発の上流プローブは公式キットの `Pf.wav` とビット一致し、再実装のPCM最大差は `1.46×10⁻¹¹`。パターンのアクセント1.3ではゲート最大2.20206、PCM最大差は `7.28×10⁻¹²`。ホスト幅128・77で候補のWAVはバイト一致し、診断用の声門F0には最大0.475 Hzの差が残った。既存の開ハイハットと混在パターンの回帰、候補のRustテスト・整形・Clippyも通過した。[単発の結果](../runs/pf-20261120-single-b/summary.json)・[パターンの結果](../runs/pf-20261120-pattern-a/summary.json)・[開ハイハットの回帰](../runs/pf-20261120-open-hat-regression/summary.json)・[混在パターンの回帰](../runs/pf-20261120-mixed-regression/summary.json)

リポジトリルートからの再実行でも、各14項目を通過し、要約、観測CSV、WAV、索引CSVが先行の通過実行と一致した。今回の検証範囲は成人男性・48 kHzのCLI再生。ブラウザの実時間接続は今後の比較対象。[単発の再実行](../runs/pf-20261120-single-root/manifest.json)・[パターンの再実行](../runs/pf-20261120-pattern-root/manifest.json)

```bash
python3 tools/measure_beatbox_snare.py snare-pf-local-1
python3 tools/measure_beatbox_pattern.py snare-pattern-local-1 --condition snare
```
