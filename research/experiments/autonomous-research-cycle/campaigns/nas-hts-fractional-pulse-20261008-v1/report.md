# 共有HTSのpulse位置補間比較

新16日本語文×2条件×4方式の128波形。双方とも固定の校正LF0を使い、原pulse、4sample遅延pulse、同遅延下の線形/9tap窓付きsinc補間を比較した。全96対で全パラメータ・周期時計・固定支持が一致し、通常/隔離の全128件とCLI4件の波形hashも一致した。

|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|31/32|0/744|0/33|0/33|
|latency|32/32|30/32|1/744|12/33|6/33|
|linear|32/32|29/32|4/744|18/33|12/33|
|sinc|32/32|29/32|3/744|12/33|0/33|

候補を採択しない。欠測/失敗/群ごとの内容悪化を保持し、総CERによる相殺や出力後のgain/係数救済を行わない。旧31方式・支持31,601区間・欠測249区間・各ASR33群の旧判定は更新しない。

補間原理の一次資料: [J. O. Smith: Windowed Sinc Interpolation](https://ccrma.stanford.edu/~jos/pasp/Windowed_Sinc_Interpolation.html)。4sample遅延、2tap線形/9tap窓付きsincの固定独自実装。最適設計や聴取結果の再現、日本語知覚資格、品質改善の証明ではない。

源のcycle eventは共通の駆動時計であり、新波形のパルスや知覚pitchの正解を意味しない。DIO/全体ACF診断を短窓・動的・境界へ一般化しない。知覚資格なし、P5未開封、全体品質未達。

機械的位置誤差低減と実波形の全保護ゲートを区別し、補間の位相/利得と後続の有効な生成比較を判断する。

機械fixtureの基本周波数での位相誤差(sample): {'latency': {'maximum_error_samples': 1.0000000000000004, 'mean_error_samples': 0.4999999999999998}, 'linear': {'maximum_error_samples': 0.00017554815923307996, 'mean_error_samples': 2.455187939991249e-05}, 'sinc': {'maximum_error_samples': 9.16301537775331e-05, 'mean_error_samples': 1.3253875273724221e-05}}
原nativeへの工学/二ASR全33群保護: {'native': False, 'latency': False, 'linear': False, 'sinc': False}
位置補間の固定L2正規化は周波数ごとの利得を保存しない。遅延と補間の別対照を保持し、位相だけの効果と読み替えない。
