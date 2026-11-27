# 咽頭枝の平均流量から鼻端の複素応答を近似する

固定 /i/ のポートのみ開条件では、2,310 Hzの鼻端に残った複素差の方向への射影の96.94%を咽頭内の枝が占めた。今回は咽頭内17枝に平均流量まわりの接線抵抗を入れ、咽頭内の損失を省いたときに比べて鼻端の複素誤差が50%以上減ると事前登録した。咽頭以外の二次損失は前回の観測値を外部圧力源として保つ。 [前回の枝損失の測定](fixed-vowel-i-velum-supraglottal-loss.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-mean-flow-tangent.json)

固定上流の `HumanVoice::render` は声門開口と肺圧を更新してから `AirwayNetwork::step` を呼ぶ。通常枝の流量 `U` は、前標本の圧力差・運動量を使って `L fs (Uₙ − Uₙ₋₁) + R Uₙ + K(Uₙ) Uₙ|Uₙ|` を解いて求める。枝が流量を更新した後、壁、節点圧、放射を更新する。 `K` は流向別で、上流側の最小面積と下流側の平均面積の差を逆数で表した拡大損失を含む。上流の定常狭窄試験は全セルと1/4セルを占める狭窄をベルヌーイ近似に照合している。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝方程式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L954)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

平均流量 `ū` で二次損失を展開すると、2,310 Hzに寄与する一次項の係数は `ΔR = 2 K(ū)|ū|` となる。流量は cm³/s、損失は dyn/cm²、追加抵抗は dyn·s/cm⁵。平均付近の定数項は100 msに231周期が入る観測窓の2,310 Hz成分から消える。抵抗を `R + ΔR` に置き換える節点解と、元の節点系に `N = ΔR U` を返して17枝間の結合も含めて解く方法を照合する。さらに実測流量の複素係数に `ΔR` を掛ける診断を置き、二次項の近似と流量の再計算を分けて確かめる。 [ポート1枝での接線抵抗](fixed-vowel-i-velum-mean-flow-tangent.md)・[離散節点方程式](fixed-vowel-i-velum-harmonic-transfer.md)

帰還計算では、追加圧力源をゼロにした咽頭の複素流量を `U₀`、追加圧力源 `N` から流量への応答を `S` と置く。 `S` は枝自身の `−N/Z` と、節点圧が変わることで他枝にも及ぶ流量変化を含む。 `D = diag(ΔR)` とすると `(I − D S) N = D U₀` を解けばよい。節点圧と枝流量を、抵抗を直接組み替えた解に相対10⁻⁹以内で照合した。 [解析の実装](../tools/measure_fixed_vowel_i_pharynx_mean_flow_tangent.py)

## 実測

400〜500 msの9,600内部標本で、17枝の平均流量は134.138 cm³/sでほぼ同じだった。逆流の標本数は枝により0〜661で、最大寄与の22→23では0だった。鼻端の複素誤差は、同じ窓で実測した鼻端流量と声門流量の複素比を基準に計算した。

| 咽頭内の扱い | 鼻端の複素相対誤差 |
| --- | ---: |
| 二次損失を省く | 0.17978% |
| 平均流量まわりの接線抵抗を加える | 0.33381% |
| 観測流量の2,310 Hz成分に接線抵抗を掛ける | 0.33475% |
| 観測した二次損失を戻す | 2.59×10⁻⁸（相対値） |

誤差は85.68%増加し、50%改善の事前仮説は両版で不成立だった。咽頭の実測損失が作る鼻端の複素寄与に対して、接線抵抗が作る寄与の同方向成分は229.50%、位相差は+30.10°だった。観測流量を保つ診断と流量を解き直した計算の誤差は近く、接線で損失則を近似した段階ですでに差が生じていた。抵抗の局所差分、二つの解法、前回の鼻端と咽頭寄与の再現は両版で登録許容差を満たした。 [観測値と全判定](../runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-repeat/summary.json)

### 節点22→23で差が生じる項

この枝の流量は最小9.901 cm³/sで、観測窓全体を通じて順方向だった。 `U = ū + U'` とすると、定数項を除いた二次損失は `2Kū U' + K(U')²`。観測した圧力損失から接線項を引いた2,310 Hz成分を声門流量で正規化すると、`0.012234 + 0.011727i` dyn·s/cm⁵だった。同じ収録にNumPyのFFTを適用し、平均との差の二乗から得た値は絶対差2.80×10⁻¹⁵ dyn·s/cm⁵以内で一致した。

この確認では `a = fft(U - mean(U)) / 9600` とし、正規化前の二乗項を `K * sum(a[j] * a[(231 - j) % 9600] for j in range(9600))` でも照合した。2,310 Hzへ加わる組のうち、110 Hzと2,200 Hzの寄与が最大だった。次いで2,420 Hzと−110 Hz、220 Hzと2,090 Hzが寄与し、位相の違いで一部が打ち消し合った。この順位は事前の合否判定とは別の、節点22→23の観測に基づく診断である。次は少数の周波数対を用いた推定を、他の咽頭枝と逆流のある枝の観測に照合する。 [22→23の保存した流量・圧力損失係数](../runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-repeat/summary.json)・[解析に用いた収録](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/manifest.json)

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` から解析し、要約がバイト単位で一致した。固定上流の定常狭窄試験も通過した。8件の照合が両方の実行で成立し、登録仮説の判定が偽だったため終了コードは1になった。再計測では末尾の実行IDを新しくする。 [初回マニフェスト](../runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_mean_flow_tangent.py fixed-vowel-i-pharynx-mean-flow-tangent-20261124-repeat
```

第41版の全体監査は222実行・3,718成果・459判定を通過した。今回の3実行の1,369入力と12出力をSHA-256で照合した。観測時系列は既存のRTL9210B-CG上の収録を参照しており、追加出力は重複統合後に8ファイル、計13,214バイトだった。 [第41版の実行記録](../runs/plan-completion-v41-fixed-vowel-i-pharynx-mean-flow-tangent-20261124/manifest.json)
