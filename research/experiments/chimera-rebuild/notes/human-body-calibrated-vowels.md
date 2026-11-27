# 体型ごとの較正済み母音目標

共通の姿勢を複数の体型で使った前回に続き、各体型の較正目標を使って固定姿勢を作る。対象は音素単位で選んだ発話用の部分的な調音目標と、固定 /a/ の断面、線形応答、発声。[事前登録ケース](../cases/human-body-calibrated-vowels.json)・[固定姿勢を揃えた前回の測定](human-body-fixed-voice.md)

## 上流の読み順

1. `calibrate::vowels` は体型ごとに96 kHzの気道を作る。咽頭入口に入力して声門枝を切った線形応答を対数間隔で掃引し、最小断面と最初の3共鳴を得る。目的関数は音響目標との対数比の二乗と、狭窄、顎、舌体、唇などの事前条件の和。範囲付きNelder–Meadを2回再始動して、姿勢と共鳴を生成表に書く。表の `target` は較正時の目標周波数、`formants` はその姿勢での線形モデルの共鳴、`artic` は頭部の基準座標系の調音値。今回の入力は固定コミットに保存されている表。[較正と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/calibrate.rs#L137)・[生成表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/vowelTargets.generated.json)
2. `plan_utterance` は二重母音などを区間へ分けた後、各区間のIPAと `BodyMix` から `vowel_artic` を呼ぶ。体型の表で母音が見つからない場合は成人男性の項目を使う。表から9成分を取り出し、舌先の巻きが0.05を超える場合と /ɿ/ の場合は舌先座標を加える。例えば /a/ の表には舌先座標があるが発話の目標には含めない。顎・舌・唇の開きと突出・喉頭はcm、唇の広がりと舌先の巻きは無次元。[母音の抽出](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L166)・[発話からの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L319)
3. 成人女性の比を `f`、子どもの比を `c` とすると、重みは `((1−c)(1−f), (1−c)f, c)`。端点ならその目標を直接選ぶ。混合時は正の重みで成分を持つ目標だけを集め、同じ成分の重み付き合計をその成分の重みの和で割る。成分が全て欠けていれば不在のまま。混合するのは形状計算より前の調音目標。重み付きの平均断面や平均周波数を計算する工程はない。[体型の重み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L350)・[部分目標の合成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L220)
4. 上流の `body_mix` は端点と成人中間の目標を照合し、/a/ の子ども50%で中立姿勢に部分目標を重ねたときの最初の2共鳴を両端と比較する。上流の `render::vowels` は較正表の全成分を持つ目標を設定して `tip_free = true` で動かす。発話時も `ArticulatorBank::step` が舌先の追従姿勢やジェスチャーを合成する。今回の固定比較は `body_mix` と同じく中立姿勢に部分目標を適用した形状を保持し、既存の固定発声と同じ条件でPCMを測る。[上流の体型のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs#L42)・[上流の10母音レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L827)・[調音器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)

照合点は候補と上流の部分目標、独立に目標を重ねた固定姿勢、気道セルの長さ・面積、放射の周波数応答、内部サンプルと対応する発声状態、加工前のPCM。登録した全26母音は目標を照合し、音響は /a/ を代表として測る。固定単母音の入口に二重母音を渡した場合のエラーも記録する。

## 実装と実行

固定コミットの較正表をバイト単位で保持し、Rustの母音モジュールが実行時に部分目標へ変換する。既存の成人男性の母音ジェスチャーとビートボックスの準備姿勢もこの表を読む。CLIの姿勢ケースは `"posture": {"vowel": "a"}` を受け、`inspect` は部分目標を出力し、`transfer` と `render-pcm` は解決した同じ姿勢を使う。固定ケースでの舌先追従と接触補正は止め、未指定の舌先位置は中立値とした。比較用の上流発声は前回の初期音高パッチを同じ手順で適用した。[実装](../crates/vocal-core/src/phonetics/vowels.rs)・[較正表](../crates/vocal-core/src/phonetics/vowel-targets.generated.json)・[上流のMIT通知](../LICENSE-CHIMERA)・[ケース](../cases/human-body-calibrated-vowels.json)

初回は周波数応答と発声の上流プローブが同じファイル名を使ったため、成人男性の発声保存で中断した。後続の実行では発声の出力ディレクトリを指定し、登録したケースと許容差を使って再試行した。上流の `body_mix` は4件が通過し、形状連続性は5件が通過した。上流で既知の突出した下唇のテストはそのテスト自身の設定で除外されている。[初回の中断](../runs/calbody-20261120-a/manifest.json)・[上流テストの記録](../runs/calbody-20261120-b/artifacts/upstream-tests.log)

## 結果

5体型で全26母音の部分目標が上流と数値一致し、Pythonで重み付き和を独立に計算した場合の最大差は `1.78×10⁻¹⁵`。舌先座標を指定する母音は /ɝ ʅ ɿ/ の3つだった。現行表は3端点で記号と成分の有無が揃うため、特定の端点での欠落や成分が一部にしかないときの実データは得られなかった。二重母音 /aɪ/ が固定姿勢の入口で拒否されることを確認した。[全判定](../runs/calbody-20261120-b/summary.json)

| /a/ の体型 | 顎の目標（cm） | 喉頭の目標（cm） | F1（Hz） | F2（Hz） | F0（Hz） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 成人男性 | 1.649 | 0.370 | 679.11 | 1470.94 | 110.00 |
| 成人女性 | 1.637 | 0.641 | 778.47 | 1770.22 | 205.00 |
| 子ども | 1.816 | −0.092 | 940.37 | 2019.36 | 260.00 |
| 成人男性と子どもの中間 | 1.7325 | 0.139 | 789.19 | 1705.95 | 169.12 |
| 3端点の混合 | 1.69574 | 0.30728 | 771.00 | 1685.59 | 169.50 |

子ども50%ではF1・F2が両端の間に入り、端点の算術平均よりそれぞれ20.55 Hz、39.19 Hz低かった。最小断面積の上流との差は最大 `1.87×10⁻¹⁴ cm²`、伝達振幅の差は上流の最大振幅に対して `9.12×10⁻¹⁵` 以下。数値差は目標を適用した後のセル構成から観測され、最初に異なる節点は成人男性で18番、3端点の混合で13番だった。発声の出力ではこの2条件が各1フレームで隣接する単精度値に丸まり、最大絶対差は `5.82×10⁻¹¹`。成人女性、子ども、成人男性と子どもの中間のPCMは上流とバイト一致した。[計測とファイルの所在](../runs/calbody-20261120-b/manifest.json)

成人男性の既存ジェスチャーは変更前後で候補・上流・要約を含む4ファイルが一致した。同じ姿勢で体型だけを替える以前の6条件も60項目すべて通過し、ケース・PCM・観測・要約の56ファイルが前回と一致した。ブラウザの成人男性IPA回帰は12項目を通過し、CLIとブラウザのPCMが一致した。[旧ジェスチャーの変更前](../runs/calbody-20261120-gestures-before/manifest.json)・[変更後](../runs/calbody-20261120-gestures-after/manifest.json)・[共通姿勢の再検証](../runs/calbody-20261120-common-pose-regression/manifest.json)・[ブラウザ](../runs/calbody-20261120-ipa-worklet/manifest.json)

成功した実行と `/tmp` からの再実行はともに458項目を通過し、条件・観測・PCM・要約の362ファイルでSHA-256が一致した。体型選択を使った時系列の調音、IPA・歌唱への接続、ブラウザでの体型切り替えは次の工程に残る。[再実行の記録](../runs/calbody-20261120-repeat/manifest.json)・[再開地点](../progress.md#未達の条件と次の作業)
