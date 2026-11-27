# 肺圧を下げた新規収録で咽頭の3組を照合する

7.2 cmH₂Oの固定 /i/ では、咽頭17枝に3組の周波数積を共通に入れると2,310 Hzの鼻端誤差が88.28%減った。周波数対を決めた収録での結果なので、今回は肺圧だけを5.76 cmH₂Oに下げて新しく収録する。前回と同じ3組と再構成した逆流補正で、鼻端の複素誤差が接線項だけの場合から50%以上減ると事前登録した。平均声門流量も下がると予測した。 [前回の観測](fixed-vowel-i-pharynx-harmonic-pairs.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.json)

固定上流の `HumanVoice::control` は指定肺圧を cmH₂O から dyn/cm² に変換してゲートを掛け、次の内部制御ブロックまでの増分を求める。 `render` は標本ごとにこの値を進め、肺ポートの流量による補償を加えた圧力を境界に渡す。声門モデルは前標本の声門上下の差圧から開口を決め、`AirwayNetwork::step` が現在の流量、圧力、放射を更新する。入力した肺圧の20%低下が各枝の瞬時流量に比例するとは限らないため、同じ窓の実測期間で比較する。上流の定常狭窄試験は、固定肺圧での流量をベルヌーイ近似と比較している。 [肺圧の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L528)・[内部標本の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L377)・[声門の差圧ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L163)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

観測は従来の通常CLIと隔離した上流の `HumanVoice::render` から採る。平均、残した6周波数、逆流符号の推定はすべて新しい5.76 cmH₂Oの収録から求める。3組の周波数自体は110 Hz＋2,200 Hz、−110 Hz＋2,420 Hz、220 Hz＋2,090 Hzに固定する。咽頭以外の圧力源は新しい収録の実測流量から求め、同じ圧力条件の鼻端複素比と照合する。 [周波数積と逆流補正](fixed-vowel-i-pharynx-harmonic-pairs.md)

## 実測

前回のケースとの全設定の比較で、変えた値は `voice.pressure_cm_h2o` の1点だった。通常CLIの `inspect` では断面、枝数、観測区間が一致した。400〜500 msの平均声門流量は134.138から109.501 cm³/sに減少した。低下率は18.37%。固定上流と研究版の圧力・流量を有向節点対で対応づけると、各列のピークに対する最大差は3.86×10⁻¹³だった。新しいPCMは前回から変化し、5.76 cmH₂Oの全32,768標本は両版でビット一致した。

| 咽頭内の圧力損失の計算 | 鼻端の複素相対誤差 |
| --- | ---: |
| 観測流量の2,310 Hz成分に接線抵抗を掛ける | 0.268236% |
| 接線項と1組の周波数積 | 0.108409% |
| 接線項と固定3組の周波数積 | 0.024165% |
| 固定3組と再構成波形の逆流補正 | 0.024096% |
| 固定3組と観測波形の逆流補正 | 0.024162% |
| 観測した全損失 | 1.26×10⁻⁸（相対値） |

固定3組と再構成した逆流補正で、鼻端の誤差が91.02%減り、事前基準の50%を両版で満たした。この条件の鼻端の振幅差は−0.000364 dB、位相差は−0.01360°。咽頭17枝の圧力係数のL2相対誤差は55.33%だった。全DFT周波数積と逆流補正による圧力係数は、符号付き二乗の直接計算に相対1.45×10⁻¹²以内で一致した。 [全判定と圧力源](../runs/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-repeat/summary.json)

観測では節点26→27から29→30までの4枝で逆流した。再構成による判定はこの4枝を見落とし、別の5枝に逆流が現れた。符号が異なったのは両版とも17枝×9,600標本のうち4,266標本だった。7.2 cmH₂Oでも同様に、観測した逆流枝と再構成で逆流した枝は重ならなかった。次は3組の二乗項を固定し、逆流用の波形だけに低次倍音を足して両圧力で比較する。 [7.2 cmH₂Oの逆流の観測](fixed-vowel-i-pharynx-harmonic-pairs.md#実測)

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。通常CLIの `inspect`、`render`、`render-pcm` を使い、固定上流は計測パッチを適用した隔離ビルドで収録した。研究ワークスペースと `/tmp` からの2回で各18判定が通り、要約と10点の観測成果がバイト単位で一致した。上流の定常狭窄試験も通過した。再収録では末尾の実行IDを変更する。 [初回マニフェスト](../runs/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_harmonic_pairs_low_pressure.py fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-repeat
```

第43版の全体監査は228実行・3,766成果・471判定を通過した。今回の3実行の1,647入力と36出力をSHA-256で照合した。RTL9210B-CG上の33出力パスは、同じ内容をハードリンクでまとめて22ファイル、計50,201,407バイトになった。 [第43版の実行記録](../runs/plan-completion-v43-fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124/manifest.json)
