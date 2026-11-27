# 固定母音 /i/ の声門枝で持ち越す運動量

## 読解と予測

固定上流の `HumanVoice::render` は声門の面積を更新して気道を進める。声門ポートは気管末端から咽頭セル0に接続され、枝の更新後に両側の流量の収支へ加わる。次の内部サンプルまで持ち越す状態は流量 `U`（cm³/s）、慣性 `L`（g/cm⁴）、その積の運動量 `L × U`（g/(cm·s)）。上流では開口が広がって慣性が下がったときに今回の `L` と前回の `U` の積を使い、慣性が増すときは前回の運動量を保つ。それにサンプルレート `Fs`（Hz）を掛けると、枝の駆動圧に足す項（dyn/cm²）になる。研究版では `min(L, L_prev)` を先に `dt` で割り、前回流量を掛けるため、同じ量でも丸める順序が変わる。[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[声門ポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[上流の枝の状態更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[研究版の持ち越し](../crates/vocal-core/src/airway/network.rs#L189)

枝の運動量式の線形係数は `L × Fs + R`、非線形の係数は流れの向きで選ぶ。今回の対照はこの線形係数をすでに上流順に揃えた実験版で、同じ固定姿勢・時刻・声門面積のまま持ち越し項の演算順を比較する。固定上流の狭窄の試験は抵抗とジェット損失を含む定常流をBernoulliの式に照合し、ホスト分割の試験は操作時刻を揃えたPCMを照合する。前回の52内点では声門枝の慣性が各点で減少した。固定姿勢の連続描画からこの区間と発声の全区間を採る。[狭窄の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[ホスト分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[慣性換算の比較](fixed-voice-glottal-branch-48000.md#連続描画での効果)

時間換算を揃えた版の観測値を固定して先に再演算した。持ち越し項を `(L × U_prev) × Fs` に替えると8,214点目までの流量は保たれ、8,215点目で上流の流量 `1.2292890015553428e-6` cm³/s と声門上圧 `3.450062679813696e-5` dyn/cm² を復元した。本実験でもこの2値を再現すると予測し、固定上流と隔離した通常CLIの出力を照合する。[事前登録](../cases/fixed-voice-glottal-momentum-48000.json)・[先行する置換の証拠](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-branch-48000.json)

## 連続描画と次の差

前回のビルド入力と3つの差分を保存ハッシュから復元した。対照の声門枝CSVと全8,240内部点の状態系列は、慣性換算版の保存分とバイト一致した。声門枝の持ち越し圧の順だけを変えた実験版を通常CLIで描画すると、8,214点目までの流量は対照と一致し、8,215点目の流量と声門上圧は予測どおり上流とビット一致した。独立計算は52点すべてで枝方程式と圧力収支を再現した。[隔離ソースの差分](../runs/fixed-voice-glottal-momentum-48000-a/artifacts/candidate-momentum-scale.patch)・[実験版の内部系列](../runs/fixed-voice-glottal-momentum-48000-a/artifacts/momentum-internal.csv)・[実験結果](../runs/fixed-voice-glottal-momentum-48000-a/summary.json)

流量と声門上圧の次の初差は8,217点目。枝を解く前の気管末端圧が研究版 `0.015307743795696938`、上流 `0.015307743795696934` dyn/cm²で、咽頭入口の前回圧は一致していた。この点の慣性と持ち越し圧も一致していた。スリット抵抗は研究版 `408.97377106687344`、上流 `408.9737710668735`。同じ面積・スリット幅・長さを使う独立計算で、幅と逆面積の積をまとめる順序から両値を復元した。気管側の圧力と抵抗を両方上流値にすると、流量 `8.535131922566455e-6` cm³/sを再現した。次は気管末端圧が更新された8,216点目の収支を採り、その圧力差の起点を確認する。[枝のCSV](../runs/fixed-voice-glottal-momentum-48000-a/artifacts/momentum-branch.csv)・[抵抗の研究版](../crates/vocal-core/src/airway/network.rs#L98)・[抵抗の上流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1010)

48 kHzの全93,056フレームで、128・77フレーム分割はビット一致した。上流と値が異なるPCMフレームは対照の16から13に減り、最初の差は59,761から4,802フレーム目へ移った。上流との最大絶対差は約1.819×10⁻¹²のままだった。最初の差、差のあるフレーム数、最大差をそれぞれ記録した。[全区間の比較](../runs/fixed-voice-glottal-momentum-48000-a/summary.json)

## 実行環境と再現確認

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、研究ワークスペースと `/tmp` から各11判定に合格した。固定上流のエンジン6試験と気道6試験が通過した。両実行で、先行版と実験版の各観測CSV、WAV2件、実験の差分はバイト一致した。十進計算で各52点の枝流量、8,217点目の圧力と抵抗の置換、WAVのPCMを照合した。296入力と28出力をハッシュ照合し、出力のうち6,006,342バイトをRTL9210B-CGへ保存した。各隔離ビルドの実行ファイルのSHA-256はマニフェストから参照できる要約に記録した。[再実行の保存記録](../runs/fixed-voice-glottal-momentum-48000-repeat/manifest.json)・[固定上流の試験](../runs/fixed-voice-glottal-momentum-48000-repeat/artifacts/upstream-tests.log)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-momentum-48000.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_glottal_momentum.py fixed-voice-glottal-momentum-48000-new
```
