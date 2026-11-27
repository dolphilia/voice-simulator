# 声門流量から咽頭の10周波数を求める

前回は咽頭の実測流量から平均と10周波数を抽出し、2つの肺圧で逆流した枝をすべて検出した。今回は平均を保ち、波形の変動に必要な10周波数は咽頭入口の声門流量と声門上の固定形状から計算する。平均で線形化した節点解の事前基準は、17枝×10周波数の複素流量のL2相対誤差10%以下、逆流枝を半数以上検出、符号不一致が全標本の1%以下。 [前回の逆流判定](fixed-vowel-i-pharynx-reversal-low-harmonics.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-from-glottal-flow.json)

固定上流の `HumanVoice::render` は声門開口を更新した後に `AirwayNetwork::step` を呼び、枝流量は前標本の節点圧と運動量で更新される。続いて壁、節点圧、終端放射を更新する。固定形状の周波数領域では、`d = exp(−2π i f/fs)`、枝インピーダンス `Z = R + L fs(1−d)` と置くと、流量は `(d ΔP − N)/Z`。 `ΔP` は両端の圧力差、`N` はその周波数の二次損失による圧力源。節点では圧縮性・壁・並列R–Lの放射負荷を合算する。上流の周波数領域テストは、一様でない固定管のFDTD出力と周波数応答でフォルマント帯域幅を照合している。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝と壁の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1024)・[節点と放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1111)・[周波数応答の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L128)

声門枝はグラフから切り、観測した声門流量を咽頭入口に注入する。粘性抵抗だけの条件と、声門上61枝で `2K(ū)|ū|` を加えた条件を比較する。ここで `ū` は観測窓の平均で、再構成時の直流値にも使う。どちらの計算も変動する枝圧・枝流量を入力せず、別の照合用の計算にだけ観測した二次損失と窓端項を入れる。流量は cm³/s、圧力は dyn/cm²。 [離散節点の実装](../tools/measure_fixed_vowel_i_velum_harmonic_transfer.py)・[枝平均まわりの線形化](fixed-vowel-i-pharynx-mean-flow-tangent.md)

400〜500 msで計算する複素係数には、枝の前標本の遅延を取ったときに流量と両端圧の窓端項が出る。窓の標本数を `M` と置き、`L fs(Uₘ₋₁−U₋₁)/M + (ΔPₘ₋₁−ΔP₋₁)/M` を二次損失と同じ符号で照合用の圧力源へ加える。その複素係数と観測した節点圧から直接求めた枝流量も、観測した流量のDFTに照合する。 [枝の有限窓補正](fixed-vowel-i-velum-supraglottal-loss.md)・[解析コード](../tools/measure_fixed_vowel_i_pharynx_from_glottal_flow.py)

## 実測

観測した圧力差と損失から直接求めた61枝の複素流量は、対象10周波数で観測流量に相対1.97×10⁻¹²以内で一致した。観測損失と枝の窓端項を節点解へ入れた対照でも、咽頭17枝のL2相対誤差は7.2 cmH₂Oで1.04×10⁻⁹、5.76 cmH₂Oで7.80×10⁻¹⁰だった。

| 肺圧 | 枝インピーダンス | 17枝×10周波数のL2相対誤差 | 逆流枝の検出 | 符号不一致の標本数 |
| --- | --- | ---: | ---: | ---: |
| 7.2 cmH₂O | 粘性抵抗 | 0.3954% | 5/5 | 193 |
| 7.2 cmH₂O | 粘性抵抗と接線抵抗 | 0.1834% | 5/5 | 215 |
| 5.76 cmH₂O | 粘性抵抗 | 0.3127% | 4/4 | 79 |
| 5.76 cmH₂O | 粘性抵抗と接線抵抗 | 0.1386% | 4/4 | 69 |

接線抵抗を使うと全周波数の複素誤差が両肺圧で減った。符号不一致は7.2 cmH₂Oで22標本増え、5.76 cmH₂Oで10標本減った。17枝×9,600標本に対する不一致率は接線抵抗で0.1317%と0.0423%。どちらも逆流枝の見落としや過検出がなく、両版で3つの事前基準を満たした。実測10周波数の再構成の不一致は236標本と80標本で、前回と一致した。 [全判定と周波数ごとの複素流量誤差](../runs/fixed-vowel-i-pharynx-from-glottal-flow-20261124-repeat/summary.json)

接線抵抗を使った周波数ごとの最大誤差は両肺圧とも660 Hzで、3.16%と3.02%だった。10周波数の変動は声門の流量を起点に計算した。枝ごとの平均流量は観測入力として残っている。次は声門流量の平均を入力とする定常枝の方程式で声門上の平均流量を求め、同じ10周波数と逆流を照合する。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。通常CLIと固定上流の既存収録を参照し、研究ワークスペースと `/tmp` の両方で15判定が通り、要約がバイト単位で一致した。固定上流の `airway_adversarial` は全6試験に通過した。再計測時は末尾の実行IDを変更する。 [初回マニフェスト](../runs/fixed-vowel-i-pharynx-from-glottal-flow-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-pharynx-from-glottal-flow-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_from_glottal_flow.py fixed-vowel-i-pharynx-from-glottal-flow-20261124-repeat
```

第45版の全体監査は235実行・3,792成果・485判定を通過した。今回の3実行の1,448入力と12出力をSHA-256で照合した。時系列はRTL9210B-CG上の既存データを参照し、外部SSDの追加出力は9ファイル、計14,207バイトだった。 [第45版の実行記録](../runs/plan-completion-v45-fixed-vowel-i-pharynx-from-glottal-flow-20261124/manifest.json)
