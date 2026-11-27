# 固定 /i/ の口蓋帆を開いて放射を比べる

固定上流の `HumanVoice::render` は肺境界の圧力と声門面積を更新して `AirwayNetwork::step` に渡す。 `HumanAirway::apply` は咽頭と口腔の測定線から管の断面積・長さを設定し、咽頭末端から鼻腔入口へつなぐ枝の目標面積も設定する。成人男性の口蓋帆の角度は `194 + 46 × clamp(a / 1.2, 0, 1)` 度、鼻腔へのポート面積は `max(0, a)` cm²。入力を−0.15から0.30 cm²へ変えると、角度は194から205.5度、面積は0から0.30 cm²になる。同じ調音軸が咽頭・口腔の輪郭と鼻腔への接続の両方に作用する。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L155)・[口蓋帆の変形](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L749)・[管とポートの設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L305)

ポート枝は前標本の運動量と咽頭側から鼻腔側を引いた圧力差を使う。慣性はポート長と面積の比に隣接半セルの慣性を加え、粘性抵抗と流向別の運動損失を含む二次式を解く。閉鎖面積未満では枝流量と運動量を0にする。枝流量と壁の運動を更新した後で節点圧と端の放射を解くため、CSVに保存する節点圧は同じ標本の更新後の値になる。口側から鼻腔側への流量を正とし、流量は cm³/s、圧力は dyn/cm²。鼻腔入口の変化は鼻腔と上顎洞を含む分岐を伝わり、鼻端の放射負荷で観測する。 [上流のポートの更新式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)・[端の放射負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1135)

上流の `a_nasalized_vowel_is_nasal_and_an_oral_one_is_not` は /ɛ/ と /a/ でポート開口と400〜900 Hzの電力比を調べる。今回の固定 /i/ は肺圧・舌・唇などを揃え、鼻端流量の有無、壁と口端の差が届く順序、PCMを時間領域で調べる。 [上流の鼻音化試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks_acoustic.rs#L94)・[事前登録](../cases/fixed-vowel-i-velum-radiation.json)

研究版の通常CLIは `fixed_voice_probe.velum_port` が有効な場合、従来の放射列の後にポート面積、流量、両端圧の4列を書く。 `internal_trace` を使うと全内部標本を観測し、通常の出力フレームでは末尾の内部標本に対応する。上流は固定コミットの隔離コピーに観測だけを追加し、同じ実行ファイルで観測ありとなしを描画してPCMを照合した。閉条件は既存の画面を検証したときの通常CLI・固定上流の保存系列も再現した。 [CLIの観測](../crates/vocal-cli/src/geometry_case/voice.rs#L293)・[上流の観測差分](../runs/fixed-vowel-i-velum-radiation-20261124-repeat/artifacts/upper-voice.patch)・[閉条件の基準](fixed-vowel-i-radiation-screen.md)

## 実測

両版で開条件から閉条件を引いたときの最初の差は同じだった。閉条件のポートと鼻端の流量は全65,536内部標本で0。開条件では咽頭・口腔の35セルで初期断面積が変化した。

| 観測 | 最初の差の内部標本 |
| --- | ---: |
| 声門まわりの圧力と声門流量 | 13 |
| 壁の放射流量 | 14 |
| ポートの咽頭側圧 | 30 |
| ポート流量と鼻腔入口圧 | 31 |
| 口端流量 | 48 |
| 鼻端流量 | 52 |
| 声門面積 | 1,298 |

ポート流量から鼻端の最初の差まで21標本（約0.219 ms）だった。開口ポートから22セルの鼻腔を通り、21の直列枝を各標本で1枝ずつ伝わる出力の最初の差と対応する。この値は数値系列の最初の非ゼロ値を測った時間で、波束のピークを測った時間とは異なる。PCMの最初の差はフレーム7（内部標本15で出力）で、鼻端流量の変化より前だった。 [開閉の時刻表](../runs/fixed-vowel-i-velum-radiation-20261124-repeat/summary.json)

定常窓19,200〜23,999フレームで、開条件の鼻端流量のRMSは71.09 cm³/s、開閉PCM差のRMSは0.04598だった。放射からFIR・直流除去を通した線形出力差の方向への射影は、壁6.54%、口端58.03%、鼻端35.44%。成分別の差を足した値は直接計算した線形出力差と最大2.68×10⁻¹⁵以内で一致した。前標本の両端圧と流量を使ってポートの式を独立に検査すると、圧力残差は両版でピーク比3.37×10⁻¹⁴以内だった。 [流量と出力差](../runs/fixed-vowel-i-velum-radiation-20261124-repeat/summary.json)

通常CLIとWasmは128・77フレーム分割で全32,768フレームの放射とPCMがビット一致した。固定上流とのPCMも開閉両条件でビット一致し、内部観測の最大相対差は閉条件3.56×10⁻¹³、開条件2.09×10⁻¹³だった。開条件で上流との差が最初に観測された列は声門上圧で、内部標本13だった。 [通常CLI・Wasm・固定上流の照合](../runs/fixed-vowel-i-velum-radiation-20261124-repeat/summary.json)

## 実行記録

macOS 15.6.1 arm64、Rust 1.94.1、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースから次のコマンドを実行した。再実行は `/tmp` からPythonとスクリプトを絶対パスで指定し、実行IDを変えた。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_velum_radiation.py fixed-vowel-i-velum-radiation-20261124-echo-corrected
```

初回は、検証コードが `inspect` の中で観測指定を設定報告と入力ケースの両方に表示する点を見落とし、開閉の2判定が落ちた。両方を照合するよう修正し、初回の保存値を再集計すると他の判定と数値は一致した。修正後の2実行は各26判定に通過し、上流の鼻音化試験も通過した。3実行の40成果がバイト一致した。 [初回](../runs/fixed-vowel-i-velum-radiation-20261124-registered/manifest.json)・[修正後](../runs/fixed-vowel-i-velum-radiation-20261124-echo-corrected/manifest.json)・[再実行](../runs/fixed-vowel-i-velum-radiation-20261124-repeat/manifest.json)

第35版の全体監査は203実行・3,427成果・421判定に通過した。研究版のRustテスト53件と固定上流の17件、現行Webのビルドも通過した。今回の4実行の1,572入力・141出力をSHA-256で照合した。RTL9210B-CG上の137出力は同一内容の実体を共有し、45ファイル分の94,833,364バイトを使用する。 [全体監査の要約](../runs/plan-completion-v35-fixed-vowel-i-velum-radiation-20261124/summary.json)・[監査マニフェスト](../runs/plan-completion-v35-fixed-vowel-i-velum-radiation-20261124/manifest.json)
