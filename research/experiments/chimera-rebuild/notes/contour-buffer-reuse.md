# 矢状面の輪郭領域の再利用

## 固定上流の読解

固定コミットは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。制御更新と接触補正後の再適用は `HumanAirway::commit` に集まる。保持している `HumanFrame` を取り出して `HumanVocalTract::compute` に渡し、輪郭を更新してから管を再標本化する。最後に前回の断面を基準として、平均断面と最小断面の変化速度を制限する。接触補正で再適用するときも制御周期と制限の基準を共有する。[HumanAirway::commit](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)

`HumanVocalTract::compute` は顎の変位を顆頭のまわりの回転角に換算し、軟口蓋の開口面積を角度に写す。姿勢から舌・唇・咽頭の境界を作り、合流点の重複を除いて輪郭を連結する。点の座標と隙間は cm、軟口蓋の開口と断面は cm²、回転の計算は rad。輪郭の順序は境界や接触部位を指す範囲と対応する。輪郭から接触と断面を評価し、表示用の点列を `clear` と追記で更新する。[輪郭と格子の処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L736)・[表示点列](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1240)

上流は中間点列と結果の点列をそれぞれ `Scratch` と `HumanFrame::with_capacity` に確保する。`compute_new` は所有する新しいフレームが要る呼び出し向けの入口。形状の数値確認には、調音範囲と基準母音間の連続性、頂点への接線、唇の折り込みを扱う既存テストを使う。[領域の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L553)・[compute_new](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L729)・[形状連続性テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs)

## 事前登録

固定入力 `ɑpɑ` の7つの制御フレームで、通常の発声ループから得た姿勢を同じ形状処理に渡す。輪郭、接触格子、断面、管への再標本化、制限用断面の複製を別々に計数する。フレーム0の初期姿勢付近から閉鎖・開口・無音までを採り、割り当てと再割り当ての合計を1回の形状計算あたりの回数で比較する。制御フレーム間の合成は通常の `ArticulatedVoice::step` で進める。接触補正が走る場合の再適用やその他の描画処理を含む全件数は、既存のWASM ABIをネイティブで動かして別に計数する。

輪郭生成では舌の曲線と唇の内外に固定点数の一時点列があり、外壁・内壁の容量も点数の和から見積もれる。最も割り当てが多い処理と予測した。そこを変更したとき、準備後の輪郭計算が割り当て0回、加工前PCM・内部観測とCLIの時系列は基準に一致、扇状走査の改修前からの累積削減は全区間と冒頭32量子後の双方で60%以上と予測する。Workletの処理時間とメモリ成長も既存の比較器で記録する。[事前登録](../cases/contour-buffer-reuse.json)・[直前の走査線比較](fan-crossing-allocations.md)

## 変更前の区間別計数

登録した7フレームはいずれも輪郭22、接触格子3、断面変換1、再標本化2、制限用配列の複製2。通常の制御更新でも各30回を観測し、分解した件数と一致した。全779更新でこの分布が同じなら、輪郭の22回を除くと `30 × 779 = 23,370` 回から `8 × 779 = 6,232` 回になる。これは区間別計測後に立てた予測で、合否は登録済みの発話全区間の計数で決める。[変更前の計数](../runs/contour-buffer-reuse-20261119-a/manifest.json)

## 再実装

`HumanTractControl` にフレームを一つ持たせ、初期姿勢、通常の制御更新、接触補正後の再適用で使う。`SagittalModel::compute_into` は外壁・内壁・舌・軟口蓋・上下の唇を `clear` して同じ順で追記し、接触判定に使う添字範囲も現在の姿勢から作り直す。外壁の最大点数は咽頭・軟口蓋・口蓋・上唇の和で、内壁は舌、喉頭蓋、接続点、口腔底、歯と下唇の点数から容量を見積もった。CLIの単一姿勢から所有フレームを得る既存の `compute` も同じ計算を使う。[矢状面の実装](../crates/vocal-core/src/anatomy.rs)・[調音制御の入口](../crates/vocal-core/src/airway/tract_control.rs)

舌根は9点、舌体の円弧は32点、舌先は7点、下面は6点。唇は内側7点と外側6点、軟口蓋は片側11点を固定長配列で計算する。補間の各反復は `p + (q - p) × t` のまま実行し、同じパラメータと点順で合流点を処理する。上流の「フレームを制御器が所有する」設計を取り入れ、固定点数の中間結果は配列に置いた。

## 計測結果と採用

研究ワークスペースと `/tmp` からの2回が各11判定を通過した。7つの姿勢と輪郭以外の区間別計数は変更前と一致。輪郭は各22回から0回、通常の制御更新は各30回から8回になった。発話全体の779更新と、冒頭32量子後の715更新の実測も、それぞれ `8 × 779`、`8 × 715` と一致した。[初回](../runs/contour-buffer-reuse-20261119-b/summary.json)・[再実行](../runs/contour-buffer-reuse-20261119-c/summary.json)

| 測定区間 | 走査線改修前 | 走査線改修後 | 輪郭領域の再利用後 | 累積削減率 |
| --- | ---: | ---: | ---: | ---: |
| 全390量子 | 45,656回 | 23,370回 | 6,232回 | 86.35% |
| 冒頭32量子後 | 41,752回 | 21,450回 | 5,720回 | 86.30% |

Worklet実時間・オフライン・CLIの加工前PCM 49,828フレームはビット一致した。声門、圧力・流量、断面、ネイティブ時系列も固定基準と一致した。矢状面の2姿勢と母音遷移・口唇・舌接触の3ケースは候補版のCSVがそれぞれ基準とバイト一致し、上流および独立計算の判定も通過。固定上流との発話PCM差は最大 `1.82×10⁻¹²` で、既存の許容差以内だった。上流の形状連続性テストは5件通過し、突き出した下唇の折り込みに関する既知の1件は上流の定義どおり除外された。[Workletと上流](../runs/contour-buffer-reuse-20261119-b-live/summary.json)・[中立姿勢](../runs/contour-buffer-reuse-20261119-b-sagittal-neutral/summary.json)・[舌接触](../runs/contour-buffer-reuse-20261119-b-tract-slew-contact/summary.json)

描画中のWASM線形メモリ増加は両回0件。冒頭32量子後のp99は両回2 msで、走査線改修直後の基準と同じだった。48 kHz・128フレームの予算を超えた量子は2件と1件で、最大5 msと3 msはいずれも発話開始時に観測された。採用の根拠は、二つの区間で登録した累積60%を超え、音響出力と内部状態の一致を確認できたこと。[初回の実時間計測](../runs/contour-buffer-reuse-20261119-b-live/manifest.json)・[再実行の実時間計測](../runs/contour-buffer-reuse-20261119-c-live/manifest.json)

10母音遷移の断面CSVと、英語発話・歌唱のブラウザWAVおよび観測JSONは、前回の通過結果とバイト一致した。[10母音](../runs/contour-buffer-reuse-20261119-ten-vowels-regression/manifest.json)・[英語発話](../runs/contour-buffer-reuse-20261119-english-regression/manifest.json)・[歌唱](../runs/contour-buffer-reuse-20261119-song-regression/manifest.json)

次に計数を掘り下げる場合は、接触格子の3回を屋根の弧長表、走査点、接触点の領域に分ける。同じ発話を使い、格子点・接触補正後の断面・PCMが一致した状態で1回の制御更新あたりの削減を測れる。[接触格子と屋根の弧長表](../crates/vocal-core/src/anatomy/contact.rs)
