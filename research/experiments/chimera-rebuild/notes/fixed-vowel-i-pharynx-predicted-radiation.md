# 予測した二次損失の2,310 Hz成分で鼻端放射を求める

前回は、声門流量と形状から予測した10周波数を使い、平均流量の分流を補正した。今回は同じ平均と変動成分から全61枝で二次損失の2,310 Hz成分を求める。接線モデルを一度補正したとき、鼻端の複素流量の相対誤差が接線モデルの半分以下かつ0.30%以下になると事前登録した。 [平均分流の測定](fixed-vowel-i-pharynx-averaged-loss.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-predicted-radiation.json)

固定上流の `HumanVoice::render` は各標本で声門開口を決め、`AirwayNetwork::step` が枝流量、壁、節点圧、放射の順に状態を更新する。枝流量は cm³/s、圧力損失は dyn/cm²。前標本の圧力と慣性に加え、枝には流向別の二次損失が入る。口端・鼻端では並列R–Lの負荷から放射流量を求め、後段で合算放射の差分を取る。今回は微分前の鼻端放射流量を同じ内部標本位置で観測する。上流の周波数領域の試験は、固定された不均一管のFDTD出力と伝達関数の共鳴帯域幅を照合する。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1024)・[放射流量の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[周波数応答の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L128)

接線解の流量を `U₀`、そこから再構成した波形の符号付き二次損失の2,310 Hz圧力成分を `N(U₀)` と置く。平均流量で加えた接線抵抗 `ΔR` を残した補正には、すでに接線抵抗に含まれる `ΔR U₀` を除いた残差圧力 `N(U₀)−ΔR U₀` を使う。独立対照では元の粘性抵抗へ予測した全損失 `N(U₀)` を圧力源として戻す。枝流量と圧力に基づく観測損失の対照では、前標本を含む窓端項も加える。全枝をまとめた節点解と、転置方程式で求めた鼻端への枝ごとの寄与を照合する。 [圧力源の節点方程式](fixed-vowel-i-velum-supraglottal-loss.md)

## 実測

400〜500 msの9,600内部標本を使った。平均分流と10周波数の咽頭流量は前回と同じ値を再現した。予測した二次損失の2,310 Hz成分を直接求めた値とFFTの値が一致し、補正圧力を一括で与えた節点解と枝ごとの寄与の和も事前の相対許容差10⁻⁹以内で一致した。

| 鼻端放射の計算 | 7.2 cmH₂Oの複素相対誤差 | 5.76 cmH₂Oの複素相対誤差 |
| --- | ---: | ---: |
| 粘性抵抗だけ | 1.0300% | 0.9233% |
| 平均流量まわりの接線抵抗 | 0.9119% | 0.8177% |
| 予測した二次損失を元の粘性モデルに入れる | 0.2469% | 0.2018% |
| 接線抵抗を保ち予測残差で一度補正 | 0.2409% | 0.1994% |
| 窓端項を含む観測二次損失を再投入 | 1.31×10⁻⁸（相対値） | 9.30×10⁻⁹（相対値） |

予測残差を一度入れると、鼻端の複素誤差が接線モデルより73.58%と75.62%減り、両肺圧・両版で事前基準を満たした。位相差は+0.5154°から−0.00045°、+0.4652°から+0.02564°に変わった。振幅差はそれぞれ−0.01339 dBから+0.02090 dB、−0.00875 dBから+0.01686 dBになった。 [全判定と複素流量比](../runs/fixed-vowel-i-pharynx-predicted-radiation-20261124-repeat/summary.json)

全61枝の予測圧力源は、観測値に対してL2相対誤差23.38%と21.94%だった。元の粘性モデルに予測損失と観測損失を入れた差を枝単位で求めると、口蓋帆ポートの30→49が両肺圧で最大だった。その誤差を観測鼻端流量で正規化した大きさは0.275%と0.218%。咽頭内の群では0.0428%と0.0267%だった。枝の複素寄与は位相を保って足し合わせる。次は口蓋帆ポートで実測流量の全帯域と10周波数に限った波形の損失を比べ、予測波形との差を照合する。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。既存の通常CLIと固定上流の収録を参照し、研究ワークスペースと `/tmp` の各実行で19判定が通り、要約がバイト単位で一致した。固定上流の `airway_adversarial` は6試験に通過した。再計測時は末尾の実行IDを変更する。 [初回マニフェスト](../runs/fixed-vowel-i-pharynx-predicted-radiation-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-pharynx-predicted-radiation-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_predicted_radiation.py fixed-vowel-i-pharynx-predicted-radiation-20261124-repeat
```

第48版の全体監査は244実行・3,828成果・503判定を通過した。今回の3実行の1,490入力と12出力をSHA-256で照合した。既存の観測時系列はRTL9210B-CGから参照し、追加出力は9ファイル、計14,243バイトだった。 [第48版の実行記録](../runs/plan-completion-v48-fixed-vowel-i-pharynx-predicted-radiation-20261124/manifest.json)
