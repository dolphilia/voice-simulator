# 逆流補正用の波形に低次倍音を追加する

固定 /i/ の7.2と5.76 cmH₂Oでは、3組の周波数対で2,310 Hzの鼻端誤差が下がった。一方、従来の6周波数から再構成した逆流波形で検出した枝は、実際に逆流した枝と両肺圧で重ならなかった。今回は第3〜第6倍音の330、440、550、660 Hzを逆流補正用の波形だけに加える。符号不一致の半減、逆流枝の半数以上の検出、過検出枝の減少と、鼻端誤差の増加5%以内を事前登録した。 [7.2 cmH₂Oの測定](fixed-vowel-i-pharynx-harmonic-pairs.md#実測)・[5.76 cmH₂Oの測定](fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-reversal-low-harmonics.json)

固定上流では `HumanVoice::render` が声門を更新し、`AirwayNetwork::step` が前標本の圧力差と運動量から枝流量を求める。駆動項の符号に対応して流量が正なら `K₊U²`、負なら `−K₋U²` が圧力損失になる。 `K₊` と `K₋` は上流側の最小断面と下流側の平均断面を使う流向別の係数。上流の定常狭窄試験は、全セルと1/4セルを占める狭窄の流量をベルヌーイ近似に照合する。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[二次係数と枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L954)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

逆流補正は `−(K₊ + K₋)U² · 1[U < 0]`。今回は補正を求める流量波形だけを6周波数から10周波数へ広げ、補正の2,310 Hz成分を咽頭の各枝に入れる。3組の順流側の二乗項、接線項、咽頭外の圧力源は共通にする。400〜500 msの各標本で逆流符号を照合し、その補正の節点応答を両肺圧で検査する。 [周波数対と符号補正](fixed-vowel-i-pharynx-harmonic-pairs.md)

## 実測

400〜500 msの9,600標本を咽頭17枝で照合した。追加分を正弦波の和として加えた流量は、平均と10周波数を残して逆FFTした流量と相対10⁻⁹以内で一致した。両方から計算した逆流補正と、逆流補正の差だけを節点方程式に入れて得た鼻端応答も同じ許容差を満たした。追加前の流向と鼻端の複素応答は前回の要約に照合した。 [解析コード](../tools/measure_fixed_vowel_i_pharynx_reversal_low_harmonics.py)・[要約と全判定](../runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-repeat/summary.json)

| 肺圧 | 符号不一致の標本数 | 実際に逆流した枝の検出 | 逆流を過検出した枝 | 鼻端の複素相対誤差 |
| --- | ---: | ---: | ---: | ---: |
| 7.2 cmH₂O | 5,924 → 236 | 0/5 → 5/5 | 9 → 0 | 0.039232% → 0.039432% |
| 5.76 cmH₂O | 4,266 → 80 | 0/4 → 4/4 | 5 → 0 | 0.024096% → 0.024162% |

符号不一致は96.02%と98.12%減り、両肺圧で事前に登録したすべての基準を満たした。追加後にも、7.2 cmH₂Oでは見落とし135標本と過検出101標本、5.76 cmH₂Oでは見落とし27標本と過検出53標本が残った。逆流補正そのものの2,310 Hzの複素係数は、観測した補正に対する17枝のL2相対誤差がそれぞれ3.31%と1.31%だった。鼻端誤差の増加は0.51%と0.27%で、観測波形で逆流を補正した参照の鼻端誤差とほぼ一致した。

今回は保存した各枝の流量から倍音係数を得ており、結果はその入力に対する再構成の精度を示す。次は枝の平均流量を保ち、声門の流量を入力とする離散節点解で咽頭の10周波数の複素流量を求める。実測の倍音と逆流符号を同じ2肺圧で比較する。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。初回はNumPyの論理スカラーが要約のJSONに残り、保存に失敗した。判定をPythonの論理値に変換して再実行すると、研究ワークスペースと `/tmp` で各16判定が通り、要約がバイト単位で一致した。事前登録のケースは初回と再実行で共通。上流の定常狭窄試験にも通過した。 [初回のエラー記録](../runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-registered/manifest.json)・[修正後](../runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-serialized/manifest.json)・[再実行](../runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_reversal_low_harmonics.py fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-repeat
```

再計測時は末尾の実行IDを新しい値にする。保存済み時系列はRTL9210B-CGの収録を参照する。

第44版の全体監査は232実行・3,780成果・479判定を通過した。初回の保存エラーと修正後の再現を照合した。今回の1,492入力・14出力をSHA-256で照合し、RTL9210B-CG上の11出力パスは重複統合後に9ファイル・13,737バイトだった。 [第44版の実行記録](../runs/plan-completion-v44-fixed-vowel-i-pharynx-reversal-low-harmonics-20261124/manifest.json)
