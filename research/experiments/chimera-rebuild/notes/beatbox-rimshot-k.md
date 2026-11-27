# リムショットの奥舌閉鎖と放出音

固定上流の単発キットは、成人男性の準備姿勢から `BeatPlayer::gestures` を呼ぶ。公称打音は0.250秒、アクセントは1、演奏者の呼気ゲートは0。 `K` の遅延は−0.0165秒なので、レシピの相対時刻ゼロは絶対0.2665秒になる。パターンの入口は128出力フレームごとに次の200 msを予約し、同じレシピを使う。今回の `K` は打音の持続可能時間を参照しない。[単発キット](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L621)・[音色表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L270)・[パターンの予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)

`rimshot` は /k/ の舌体Y=8.35 cmを軟口蓋の閉鎖に使う。舌体X=2.3 cmは弱い重み0.25の別ジェスチャー、顎0.35 cmは重み2.2の補助目標。閉鎖の指示を24 ms早く始め、解除の指示を34 ms早める。上流の `snap` は閉鎖の強い目標だけを速度4.0、減衰8 msに変更する。 `ejective` は声門閉鎖1を指示し、喉頭を `min(1.6, 1.25 + 0.3 × accent)` cmへ上げる。[リムショットと声門閉鎖](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L159)・[/k/ の目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L144)・[舌体閉鎖の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

| 目標 | 絶対時刻の保持開始–終了（秒） | 立上り／減衰（秒） | 重み |
| --- | --- | --- | --- |
| 舌体Y | 0.1625–0.2325 | 0.030／0.008 | 40 |
| 顎、舌体X | 0.1865–0.2665 | 0.050／0.050 | 2.2、0.25 |
| 声門閉鎖 | 0.1745–0.2965 | 0.012／0.030 | 8 |
| 喉頭 | 0.2165–0.2705 | 0.030／0.080 | 40 |

64出力フレームごとに目標の活性を合成し、調音器を進める。声道の断面と長さの変化は内部サンプルごとに容積差による体積流量を生む。喉頭が上がる時点で声門と舌体付近の流路が狭くなれば、閉鎖の内側で圧力が高まると予測した。声門の閉鎖指示は重みに従い `min(1, w/2)` まで有効になり、時定数4 msで平滑化される。声帯が振動しない区間の面積は、開大と後部隙間を平滑化した値に `1 − 0.92 × 平滑化した閉鎖` を掛けたもの。上流のテストは各音色の準備と解除が先読み範囲に収まること、複数音色のPCMが描画の分割幅に依存しないことを確認する。[調音と声道の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L456)・[容積変化の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L833)・[声門面積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L220)・[音色のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L55)・[Engineのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

単発の閉鎖は咽頭・口腔の最小断面の両方で追い、口端が開いたままか、閉鎖中の声門上圧と喉頭位置が上がるかを測る。解除直後の口端流量とPCM、余韻、呼気ゲート0も確認する。喉頭位置と静的な声門面積は別の積分で照合する。パターンでは `B . k> | -` の0.450秒の `K` をアクセント1.3で予約し、喉頭目標の上限1.6 cmと、128・77フレーム分割での一致を検証する。[単発ケース](../cases/beatbox-rimshot-k.json)・[パターンケース](../cases/beatbox-pattern-rimshot-k.json)

## 初回の差と測定条件の改訂

初回の単発とパターンでは、演奏者の呼気ゲートは終始0だった。単発の上流で声門の振動ゲートが0.1675秒から立ち上がり、最大0.001182、10⁻⁶を超える期間は49.44 msだった。口腔4番セル（0始まり）の完全閉鎖は0.1798秒からで、振動の立ち上がりが先行する。パターンの上流では振動ゲートが最大0.15066、10⁻⁶を超えるフレームの合計は152.46 msだった。静的な声門面積の式との照合と、全区間で振動ゲートを10⁻⁶以下とした初回判定は両方で不合格だった。[初回の単発](../runs/rim-20261120-single-a/summary.json)・[初回のパターン](../runs/rim-20261120-pattern-a/summary.json)

上流との差は瞬時F0のフレーム0に現れ、単発ではフレーム8041で声門面積に10⁻¹² cm²を超える差、フレーム8044で声門下圧に判定幅を超える差が出た。既定の粗さ0.1から周期ジッタ0.00455と振幅シマー0.042が決まり、5セントのドリフトとともに静音中から状態が進む。第3段階で個別に検証した声門モデルを打音用プロファイルからこの設定で呼ぶ。改訂版では瞬時F0を他の列と同じ上流比較に含め、振動ゲートの継続時間と減衰を確認する。声門面積の独立計算では、上流・候補から個別に測ったF0と振動ゲートを入力とし、位相、振幅、パルス波形、静的面積を構成する。元のケースと実行記録は保存した。[音源の既定値と揺らぎ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L332)・[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[単発の改訂条件](../cases/beatbox-rimshot-k-v2.json)・[パターンの改訂条件](../cases/beatbox-pattern-rimshot-k-v2.json)

## 実装と検証

既存のキックと喉頭・声門閉鎖の関数を共有し、奥舌のジェスチャーはレシピに個別に記述した。CLIの単発音とパターンは共通の打音用音源設定を使う。観測用CSVに舌体の座標と咽頭の最小断面を追加し、口腔と咽頭のどちらが先に閉じるかを測った。[打音レシピ](../crates/vocal-core/src/phonetics/beatbox.rs)・[CLIと観測点](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[独立計測](../tools/measure_beatbox_rimshot.py)

| 観測量 | 単発 `K` | `B . k> \| -` のパターン |
| --- | ---: | ---: |
| 観測フレーム数（出力48 kHz、内部96 kHz） | 24,000 | 40,320 |
| 閉鎖の時刻と持続 | 179.833–246.688 ms、66.854 ms |  |
| 閉鎖中の口端最小面積 | 0.58538 cm² |  |
| 閉鎖中の声門上圧ピーク | 29,250 dyn/cm² |  |
| 再開口直後の口端流量ピーク | 810.39 cm³/s |  |
| 喉頭の上昇ピーク | 1.54325 cm | 1.59806 cm（目標1.6 cm） |
| 振動ゲートの最大値 | 0.001182 | 0.150660 |
| 振動ゲートが10⁻⁶を超えた時間の合計 | 49.44 ms | 152.46 ms |
| 声門面積の独立計算との差（最大） | `6.01×10⁻¹⁶ cm²` 未満 | `4.34×10⁻¹⁵ cm²` 未満 |
| 固定上流との差（PCM最大絶対値） | `7.28×10⁻¹²` 以下 | `5.83×10⁻¹¹` 以下 |

単発13項目、パターン15項目が通過。単発のキットとパターンの通常の `Engine` をプローブのPCMと照合し、128・77フレームの出力分割でもそれぞれWAVがバイト一致した。比較のコマンド、入力と出力のハッシュ、Rust・Pythonの環境は実行記録にある。[単発](../runs/rim-20261120-single-b/manifest.json)・[パターン](../runs/rim-20261120-pattern-b/manifest.json)

瞬時F0は固定上流と両ケースの全フレームで一致した。研究ディレクトリと `/tmp` からの実行で、単発11ファイル、パターン12ファイルのハッシュが一致した。再実行はいずれもmacOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。Rustの整形・Clippy・ワークスペーステストと、固定上流の `beatbox`・`engine` テストが通過した。[単発の再実行](../runs/rim-20261120-single-repeat/manifest.json)・[パターンの再実行](../runs/rim-20261120-pattern-repeat/manifest.json)

既存の打音6ケースの再計測では、瞬時F0の列に既定ドリフトが反映され、他の観測列とPCMはバイト単位で一致した。発話側の声門・閉口条件は候補・上流の両CSVと要約が直前の実行と一致した。[キック](../runs/rim-20261120-kick-source/manifest.json)・[ハイハット](../runs/rim-20261120-hat-source/manifest.json)・[開ハイハット](../runs/rim-20261120-open-source/manifest.json)・[単発スネア](../runs/rim-20261120-pf-source/manifest.json)・[スネアのパターン](../runs/rim-20261120-pf-pattern-source/manifest.json)・[混在パターン](../runs/rim-20261120-mixed-source/manifest.json)・[声門・閉口](../runs/rim-20261120-existing-glottal/manifest.json)
