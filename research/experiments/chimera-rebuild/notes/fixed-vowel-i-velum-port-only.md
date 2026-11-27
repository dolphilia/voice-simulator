# 固定 /i/ で口蓋帆の輪郭とポート面積の作用を分ける

前回の通常条件では口蓋帆の入力が、矢状面の輪郭と鼻腔へのポート面積の両方を変えた。上流の `HumanVocalTract::compute` は口蓋帆入力から角度と曲率を変え、別にポート面積 `max(a, 0) × k²` を算出する。 `HumanAirway::apply` は組織の輪郭から管の断面を作り、ポートには面積の目標値を設定する。上流の `HumanVoice::control` は毎制御ブロックでこれらの目標を更新し、`begin_block` が補間量を決める。上流の鼻音化試験は /ɛ/ と /a/ の開口と400〜900 Hz帯の比を確認している。 [上流の口蓋帆の輪郭](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L749)・[ポート面積の算出](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1270)・[制御時の断面更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L491)・[鼻音化試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks_acoustic.rs#L94)・[前回の観測](fixed-vowel-i-velum-radiation.md)

研究版は `SagittalModel` で輪郭を計算し、`FixedAirwaySettings::build` が輪郭由来の面積曲線とポート面積を `HumanAirway::fixed_from_profile` へ渡す。固定姿勢の比較では、輪郭の計算が終わった時点から、音響ポートの面積だけをcm²で指定できる。面積の指定を初期状態から適用すれば、片側の咽頭圧と反対側の鼻腔圧、枝運動量、方向別の圧力損失が、指定面積の枝だけに対応する。節点圧は枝流量と壁速度の後に更新されるため、ポートの二次式を検査するときは前標本の両端圧を使う。 [研究版の固定気道の入口](../crates/vocal-cli/src/geometry_case.rs#L182)・[枝と圧力の更新](../crates/vocal-core/src/airway/network.rs#L719)・[事前登録](../cases/fixed-vowel-i-velum-port-only.json)

CLIの `fixed_voice_probe.velum_area_override_cm2` で音響ポートの面積を指定する。 `inspect` には入力の調音値と実効ポート面積が表示される。上流は隔離コピーで、最初の発声前にポートの目標を設定し、`snap_to_targets` で初期値へ反映する。その後は各制御ブロックで輪郭を計算した直後、`begin_block` の前に同じ目標面積を設定する。ポート面積を全区間で一定に保ち、姿勢、音源、時刻の処理は通常の発声入口を使う。 [CLIの設定箇所](../crates/vocal-cli/src/geometry_case.rs)・[固定上流の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L688)・[固定上流の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L491)

| 条件 | 口蓋帆の輪郭を決める入力（cm²） | 実効ポート面積（cm²） |
| --- | ---: | ---: |
| 前回の閉条件 | −0.15 | 0 |
| ポート面積だけを変更 | −0.15 | 0.30 |
| 輪郭だけを変更 | 0.30 | 0 |
| 前回の開条件 | 0.30 | 0.30 |

## 実測

同じ輪郭でポート面積だけを変えた組は、輪郭CSVと全セルの断面積・長さが一致した。前回の閉条件と開条件に対応する2組は、通常CLIの観測CSV・WAVと固定上流の観測・PCMを保存値までバイト再現した。指定面積は全65,536内部標本で一定だった。負の面積は `inspect` と `render` の両方でエラーになり、後者はCSVを作成しなかった。 [観測と判定](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/summary.json)・[入力検査](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/artifacts/input-validation.json)

輪郭を固定してポートだけを開くと、流量はポートで標本31、鼻端で52から現れた。通常開閉と同じ21標本の間隔だった。壁の放射は標本33、口端流量は49、PCMはフレーム22に初差が出た。輪郭だけを変えた条件は、壁の標本14とPCMのフレーム7という通常開閉の初差を再現し、鼻端流量は全標本で0だった。研究版では輪郭のみと通常開条件のPCMがフレーム0〜21でビット一致し、フレーム7の振幅は両条件で−3.85×10⁻²⁸だった。これは初めてビット差が出た時刻の比較である。 [開閉と分離条件の時刻](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/summary.json)

定常窓19,200〜23,999フレームで、ポートだけを開いた鼻端流量のRMSは70.68 cm³/s、通常の開条件は71.09 cm³/sだった。PCM差のRMSはポートのみ0.04099、輪郭のみ0.00894、通常開閉0.04598。開口効果を2つの輪郭で計算して引き合わせると、差のRMSは0.01065で、通常開閉差の23.16%だった。この差の通常開閉方向への射影は−0.43%で、各RMSの比と射影は異なる量を表す。壁・口端・鼻端から求めた線形出力の差の和は、合算放射を使った計算と絶対3.61×10⁻¹⁵以内で一致した。開口ポートの圧力残差は両版を通じてピーク比3.37×10⁻¹⁴以内だった。 [定常窓と圧力収支](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/summary.json)

4条件とも、保存した放射を使った独立計算で全PCMを再現した。通常CLIと固定上流の比較で、ポートだけを開いた条件のフレーム20,437に1 ULP（約1.16×10⁻¹⁰）の差があった。この条件の版間差は観測系列のうち声門上圧の標本14に最初に出た。放射微分から独立に求めた量子化前の値は丸め境界0.0014891692553646863に対して、研究版が約7.28×10⁻¹⁶上、上流が約1.90×10⁻¹⁵下で、保存PCMの1ビット差を再現した。ほかの3条件のPCMは版間でビット一致した。 [固定上流と研究版の差](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/summary.json)

次の比較点を選ぶため、両輪郭で求めた開口効果の差に定常窓のハン窓を掛け、FFTを確認した。50〜500 Hz帯が電力の79.30%を占め、帯域内の最大は440 Hzだった。1,500〜3,000 Hz帯は18.78%で、最大は2,310 Hzだった。この観察をもとに、次は同じ4条件の線形伝達と発声時の複素比をこの2周波数で照合する。 [解析元PCM](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/manifest.json)

## 実行記録

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースから次を実行した。`/tmp` からPythonとスクリプトを絶対パスで指定し、実行IDを変更して再実行した。両実行は各35判定と固定上流の鼻音化試験に通過し、要約と33成果はバイト一致した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_velum_port_only.py fixed-vowel-i-velum-port-only-20261124-registered
```

[初回マニフェスト](../runs/fixed-vowel-i-velum-port-only-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-only-20261124-repeat/manifest.json)

第36版の全体監査は206実行・3,509成果・427判定に通過した。研究版のRustテスト53件、固定上流の17件、現行Webのビルドも通過した。今回の3実行の1,468入力・82出力をSHA-256で照合した。RTL9210B-CG上の79出力は同一内容の実体を共有し、43ファイル分の106,972,805バイトを使用する。 [全体監査の要約](../runs/plan-completion-v36-fixed-vowel-i-velum-port-only-20261124/summary.json)・[監査マニフェスト](../runs/plan-completion-v36-fixed-vowel-i-velum-port-only-20261124/manifest.json)
