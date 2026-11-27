# ビートボックスの単発キック `B`

## 上流の経路

`chimera-cli render beatbox` の単発レンダーは成人男性の `HumanVoice` を出力48 kHz、内部96 kHzで生成する。舌先を下切歯の後ろに置く中立姿勢から始め、`beat_ready` を基準目標に設定する。唇の開きは0.25 cm、顎は0.4 cm、唇の突出は0.1 cm、舌体の高さは較正済みの /ə/ に0.1 cmを足す。基準目標の変更は調音器の現在位置を保つので、打音前にも形状が変わる。呼気ゲートの目標は0、基準ピッチは100 Hz、呼気圧の設定は8 cmH₂O。初期F0は110 Hzで、基準値へ滑らかに近づく。[単発レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L619)・[準備姿勢](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L31)・[調音器の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L78)

`BeatPlayer::gestures` は音色の生成関数を呼び、各保持区間を `hit − latency` だけ移す。今回は `hit = 0.250 s`、`latency = 0.010 s`、アクセント1.0。パターン再生の `tick` もこの入口を使う。単発レンダーは4ジェスチャーを先にスコアへ登録し、0.5秒分を描画する。[予約と単発の共通入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)・[音色表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L272)

| 対象 | 目標 | 保持区間（秒） | 立上り／減衰（秒） | 重み | 速度倍率／保持（秒） |
| --- | --- | --- | --- | --- | --- |
| 唇開度 | −0.25 cm | 0.143–0.221 | 0.030／0.010 | 40 | 3.5／0.045 |
| 顎 | 0.3 cm | 0.165–0.240 | 0.050／0.050 | 2.2 | 基準 |
| 声門閉鎖 | 1 | 0.153–0.270 | 0.012／0.030 | 8 | 基準 |
| 喉頭 | 1.55 cm | 0.190–0.244 | 0.030／0.080 | 40 | 3.0 |

唇は /p/ の閉鎖目標を借りる。両唇閉鎖向けに、閉鎖指示を22 ms早め、開く指示を19 ms早める。キックは唇の減衰を10 msに縮め、速度倍率3.5を減衰完了後も45 ms保つ。顎は弱い補助目標なので、この上書きの対象外になる。喉頭の目標は `min(1.6, 1.25 + 0.3 × accent)` cm。上流テストでは全音色で打音前にジェスチャーが始まり、打音後にも継続することと、パターン予約の重複がないことを検査する。[目標と閉鎖のタイミング](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[キックのレシピ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L159)・[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs)

## 更新順序と事前登録

上流の制御更新は出力64フレームごとに、秒単位の時計でジェスチャーを合成し、調音位置と速度を進める。閉鎖指示は `目標値 × min(重み / 2, 1)`。その姿勢から声道断面の目標を決め、内部サンプルごとに断面の変化による体積流量、声門流量、伝搬・放射を更新し、間引きしてPCMを出す。無振動時も静的声門面積は残る。完全に立ち上がった閉鎖指示では開大と後部隙間の合計に0.08が掛かるため、この入力の定常値は `(0.1 × 0.15² + 0.008 + 0.03 × 0.15) × 0.08 = 0.00118 cm²` となる。[声道と呼気の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L456)・[声門面積の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L220)

閉唇中の口腔末端で正圧が増え、開口直後に口端流量とPCMのピークが出ると予測した。肺のゲート、声門面積と流量、喉頭の高さ、唇の最小断面、口腔末端と声門上の圧力を別々に観測する。1出力フレームの末尾を採取時点とし、時刻を `(frame + 1) / 48000` 秒とする。物理挙動の判定窓、上流との数値許容差、2種類のホストブロック幅は実装と比較に先立って登録した。[ケース定義](../cases/beatbox-kick-b.json)

## 再実装と第1版の結果

単発の `B` をコンパイルする関数は、発話用の両唇閉鎖ジェスチャーを使い、唇の戻り時間と速度をキック用に変更する。準備目標には既存の /ə/ のデータを使う。CLIは中立姿勢で声道を作ってから基準目標を与え、発話・歌唱と同じ合成コアでスコア、圧力・流量のCSV、モノラルf32 WAVを生成する。[レシピ](../crates/vocal-core/src/phonetics/beatbox.rs)・[CLIの音源接続](../crates/vocal-cli/src/timing_case/speech_voice.rs)

第1版では、PCMと調音時刻は上流に一致した。閉鎖した口端セルでは正圧の増加が見えず、圧縮の判定は両方で未達だった。固定上流は狭窄が `2×10⁻⁴ cm²` を下回る放射端で直前の節点圧に0.98を掛け続ける。閉鎖中のこの値は、声道内に残った空気の圧力を観測する用途に適さない。初回の閉鎖時刻も、探索窓が打音の90 ms前に始まるため窓の左端で切れていた。第2版では圧縮の観測点を咽頭入口の声門上圧にし、閉鎖開始の探索を打音130 ms前まで広げた。音源の設定と数値比較の許容差は同じ入力を使った。[閉鎖セルの圧力更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1074)・[第1版の未達](../runs/kick-b-20261120-a/summary.json)・[第2版](../cases/beatbox-kick-b-v2.json)

## 第2版の結果

| 観測 | 再実装の値 |
| --- | --- |
| 閉鎖開始、再開口 | 141.271 ms、249.375 ms |
| 閉鎖中の最高喉頭位置 | 1.5480 cm |
| 閉鎖中の声門上圧ピーク | 231.104 msに15,314.14 dyn/cm²。閉鎖直後5 msの平均から15,019.98 dyn/cm²増加 |
| 同時刻の声門面積 | 0.0011800000053 cm²。無振動時の静的な計算値との差は `5.25×10⁻¹² cm²` |
| 再開口後20 msの流量・PCM | 口端流量の絶対ピーク717.05 cm³/s、PCMピーク0.07182 |
| 呼気と発声 | 全期間でゲート0、声門振動の観測値0。末尾50 msのPCM絶対ピークは `1.99×10⁻⁵` |

登録した13項目が通過した。上流の通常コマンドが出す浮動小数点WAVと、比較用プローブの24,000フレームはビット一致した。再実装と固定上流の最大差はPCMで `7.28×10⁻¹²`、声門上圧で `7.77×10⁻¹⁰ dyn/cm²`。128フレームと77フレームのホストブロックで、再実装のWAVとフレーム索引CSVはバイト一致した。上流既定のピッチ変動が働くので、発声がない間も声門のF0の観測値には最大0.326 Hzの差がある。第2版ではF0を診断系列に指定し、面積・流量・振動はそれぞれ合否に含めた。独立した対照で圧縮に対する喉頭上昇の寄与を定量化する場合は、準備姿勢と声門閉鎖を保ち、喉頭のジェスチャーだけを外す。[第2版の結果](../runs/kick-b-20261120-b/summary.json)・[実行記録](../runs/kick-b-20261120-b/manifest.json)

`/tmp` からも13項目を通過し、再実装と上流のPCM・時系列、結果要約を初回とバイト単位で照合した。発話 `ɑpɑ` の回帰も7項目を通過し、従来の通過版とWAV・観測CSVが一致した。候補のRustワークスペースの整形・テスト・Clippyも通過した。[別ディレクトリからの再実行](../runs/kick-b-20261120-c/manifest.json)・[両唇破裂音の回帰](../runs/kick-b-20261120-bilabial-regression/summary.json)・[従来の結果](../runs/bilabial-p-20261119-f/summary.json)

研究ワークスペースで、NumPyとSciPyを利用できるPython環境を使い、新しい実行IDを指定する。別ディレクトリから実行するときはスクリプトの場所を指定する。[実行手順](../README.md)

```bash
python3 tools/measure_beatbox_kick.py kick-b-local-1
```
