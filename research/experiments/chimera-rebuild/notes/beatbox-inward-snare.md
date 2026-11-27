# 吸気スネアの奥舌閉鎖、負圧と逆向きの乱流

成人男性の単発キットは準備姿勢に移り、F0の目標を100 Hz、肺の圧力設定を8 cmH₂O、演奏者ゲートを0とする。 `BeatPlayer::gestures` は `^K` の遅延−14 msを引くため、公称打音0.250秒に対するレシピの原点は0.264秒。パターンも128出力フレームごとに200 ms以内のステップを予約して同じレシピを呼ぶ。 `^k>` は `^K` のアクセント1.3として解釈される。上流テストは記譜の正規化、すべての音色の前後時間と先読み、 `^K` を含むセッションのホスト幅不変性を検査する。[キット](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L621)・[予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)・[記譜と先読みのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L37)・[分割のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)

`inward_snare` は /k/ の舌体Y=8.35 cmに強い目標を与え、顎0.35 cmと舌体X=2.3 cmを別の弱い目標として足す。閉鎖の準備を24 ms、解除を34 ms前倒しし、強い目標を速度4、減衰8 msで解放する。後続の /x/ は舌体Yを7.35 cmへ移し、口腔の狭窄を残す。強い目標の原速度1.4は舌体用の式 `1 + (1.4 − 1) × 0.35` で1.14になる。立上りは8 msに短縮される。声門開大の目標は0.5 cm²、肺には負の `−1.7 × accent` を与える。単発の保持時間は次のとおり。[音色とレシピ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L210)・[音素表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L144)・[調音目標の分配](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

| 目標 | 保持開始–終了（秒） | 立上り／減衰（秒） | 重み |
| --- | --- | --- | --- |
| /k/ の舌体Y | 0.180–0.230 | 0.030／0.008 | 40 |
| /k/ の顎、舌体X | 0.204–0.264 | 0.050／0.050 | 2.2、0.25 |
| /x/ の舌体Y | 0.268–0.349 | 0.008／0.030 | 40 |
| /x/ の舌体X | 0.276–0.349 | 0.008／0.050 | 0.25 |
| 声門開大 | 0.214–0.349 | 0.020／0.040 | 6 |
| 吸気 | 0.229–0.349 | 0.015／0.050 | 2 |

64出力フレームごとに、重み付きの呼気目標に活動度 `min(1, w)` を掛ける。負の値は演奏者のゲートより優先される。ゲートがさらに下がるときは20 ms、負から戻るときは25 msの指数緩和を使う。肺の目標は `設定圧 × 980.665 × ゲート` dyn/cm²。内部サンプルでは、その目標までの直線補間に前サンプルから更新した肺ポート流量の補償を足し、声門、気道の順に更新する。努力量は肺圧の絶対値から求め、声帯の励振ゲートは声門上下の符号付き圧差で決まる。[肺圧と声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L385)・[呼気の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L509)

乱流の候補は咽頭と口腔を通した最小の正の断面積で決まる。レイノルズ数に流量の絶対値を使い、順流は前方の枝に圧力を足し、逆流は後方の枝から引く。狭窄源の両枝、噴流の符号、口端と声門の流量を同時に観測する。閉鎖が続く間から負の肺圧が発生し、開口後に吸い込む流れと狭窄乱流が同時に現れると予測した。単発とアクセント付きパターンで区間としきい値を固定し、時間、開大、呼気は独立した制御計算で照合する。[狭窄源の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L328)・[符号つき圧力注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[単発ケース](../cases/beatbox-inward-snare.json)・[パターンケース](../cases/beatbox-pattern-inward-snare.json)

## 初回の差と改訂条件

初回の両ケースはジェスチャー、波形、符号付き呼気と乱流注入で上流に一致した。時系列の初差はフレーム1600の噴流流量で、候補−12.095965、上流−12.074718 cm³/sだった。候補の `noise_jet_flow_cm3_s` は乱流源の設定時に保持した値で、上流プローブが採ったのは出力フレーム末尾の瞬時値だった。候補の既存列を保持し、両方で同じ枝の瞬時値を `constriction_jet_flow_cm3_s` として採る。[初回の単発](../runs/inward-20261120-single-a/summary.json)・[初回のパターン](../runs/inward-20261120-pattern-a/summary.json)・[乱流源の登録時に保持する流量](../crates/vocal-core/src/airway/human/frication.rs)

単発の末尾50 msでは、最初の制御区間で固定上流もゲートの絶対値が0.120423となり、登録上限0.12を超えた。0.450688秒で0.114169へ下がった。第2版では同じ0.12とPCMの観測窓を使い、ゲートは0.455秒までにしきい値へ戻り、描画末尾までその範囲に収まるかを判定する。ゲートの全フレームを独立計算と照合する条件も維持する。[初回ケース](../cases/beatbox-inward-snare.json)・[第2版](../cases/beatbox-inward-snare-v2.json)

改訂後の並行実行2件は、CLIの観測CSV生成中にSIGKILLで中断した。中断時のマニフェストを保存し、実行を一件ずつにした。[単発の中断](../runs/inward-20261120-single-b/manifest.json)・[パターンの中断](../runs/inward-20261120-pattern-b/manifest.json)

## 実装と検証

リムショットと同じ奥舌閉鎖を使い、解除後の舌体目標、声門開大、負の呼気を `^K` のスコアに加えた。既存の呼気制御と乱流を使って単発・シーケンサーを描画した。負のゲートと声門開大は、打音時刻を入力とする別の制御計算と全フレームで照合した。最大誤差はゲート `2.06×10⁻¹³`、開大 `1.87×10⁻¹³ cm²`。[調音レシピ](../crates/vocal-core/src/phonetics/beatbox.rs)・[肺の制御](../crates/vocal-core/src/breath.rs)・[計測器](../tools/measure_beatbox_inward_snare.py)

| 観測量 | 単発 `^K` | アクセント1.3のパターン |
| --- | ---: | ---: |
| 閉鎖開始–解除 | 197.167–244.021 ms | 397.167–444.021 ms |
| 閉鎖中の肺境界圧の最小（dyn/cm²） | −11,007 | −14,083 |
| 開口後の肺境界圧の最小（dyn/cm²） | −24,199 | −29,733 |
| 開口後の狭窄枝流量の最小（cm³/s） | −1,784.99 | −2,052.19 |
| 摩擦区間の後方枝への乱流圧注入の最大絶対値（dyn/cm²） | 41.25 | 50.45 |
| 摩擦区間の前方枝への乱流圧注入の最大絶対値（dyn/cm²） | 0 | 0 |
| 摩擦区間のPCM RMS | 0.01680 | 0.01970 |
| PCMの上流との差（最大絶対値） | `1.87×10⁻⁹` 以下 | `7.28×10⁻¹²` 以下 |

単発の肺境界圧が最小となる時刻は274.646 ms。その時点の `8 × 980.665 × ゲート` は−12,491 dyn/cm²で、観測した肺境界圧−24,199 dyn/cm²の絶対値は約1.94倍だった。肺境界には肺ポート流量の低域補償項も加わる。負圧が開口後に大きくなる過程を調べるには、同じ流量履歴から補間した基礎圧と補償項を個別に求める。[単発の時系列と要約](../runs/inward-20261120-single-c/manifest.json)

単発13項目、パターン16項目が通過。出力48 kHz、内部96 kHz、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。固定上流の単発キットと通常の `Engine` をそれぞれプローブのPCMに照合し、128・77フレームの分割でもバイト一致を確認した。候補のRust整形、Clippy、ワークスペーステストと上流の `beatbox`・`engine` テストも通過した。[単発の実行](../runs/inward-20261120-single-c/manifest.json)・[パターンの実行](../runs/inward-20261120-pattern-c/manifest.json)

研究ディレクトリと `/tmp` から再実行し、候補・上流の観測CSV、PCM、設定、要約などのハッシュが単発11ファイル、パターン12ファイルで一致した。[単発の再実行](../runs/inward-20261120-single-repeat/manifest.json)・[パターンの再実行](../runs/inward-20261120-pattern-repeat/manifest.json)

奥舌閉鎖を共有したリムショット `K` は、単発とアクセント付きパターンを実装の前後で比較した。各ケースの設定、PCM、観測CSV、要約など7ファイルがバイト一致した。[単発の回帰](../runs/inward-20261120-rimshot-after/manifest.json)・[パターンの回帰](../runs/inward-20261120-pattern-after/manifest.json)
