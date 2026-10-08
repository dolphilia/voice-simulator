# 共有HTSのLF0輪郭幅比較

新16日本語文×2条件×3方式の96波形。全方式が原HTSのalpha=.55フィルタ/励振算法を使い、校正LF0の指定Hz周りの輪郭幅を1/.5/0だけ変更した。全64対の保存列でMCP/LPF・duration・有声mask/無声sentinelと倍率式を直接照合し、固定支持も一致した。周期/励振列はLF0に従って変わる。通常/隔離の全96件とCLI4件の波形hashも一致した。

|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|30/32|0/769|0/33|0/33|
|half_contour|32/32|26/32|6/769|13/33|2/33|
|flat_contour|32/32|24/32|8/769|20/33|12/33|

候補を採択しない。欠測/失敗/群ごとの内容悪化を保持し、総CERによる相殺や出力後のgain/係数救済を行わない。旧31方式・支持31,601区間・欠測249区間・各ASR33群の旧判定は更新しない。

原理の一次資料: [SPTK公式: MLSAフィルタとall-pass constant](https://sp-nitech.github.io/sptk/latest/main/mglsadf.html)、[mc2bの係数変換](https://sp-nitech.github.io/sptk/latest/main/mc2b.html)。今回alphaは全方式.55固定。LF0の輪郭幅を指定Hz周りで事前固定倍率にする。元のsqrt(period)源振幅/周期時計はLF0へ従い、波形別の出力正規化は行わない。輪郭倍率の自然さをこの資料から主張しない。

源のcycle eventは共通の駆動時計であり、新波形のパルスや知覚pitchの正解を意味しない。DIO/全体ACF診断を短窓・動的・境界へ一般化しない。知覚資格なし、P5未開封、全体品質未達。

LF0輪郭の幅と音響診断/内容保護を全分母で評価する。flatは機構診断に限定し、半幅も知覚資格なしでは採択しない。原native保護と有効測定範囲を守った別要因へ進む。

機械fixtureの輪郭倍率/不変量: {'contour_control_checks': 36, 'all_control_checks_passed': True, 'original_native_wave_exact': True, 'full_saved_parameter_pairs_verified': 64, 'LF0_is_intentionally_changed': True, 'flat_is_not_naturalness_target': True}
原nativeへの全工学/二ASR33群保護: {'native': False, 'half_contour': False, 'flat_contour': False}
flat条件は輪郭変動と診断の関係を調べる単調源であり、ゲート通過しても自然さ候補へ採択しない。半幅は相対LF0振幅を意図的に変えるため、原輪郭保存と呼ばない。
