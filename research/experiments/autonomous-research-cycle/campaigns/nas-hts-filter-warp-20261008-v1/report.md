# 原励振固定のHTSフィルタ周波数軸比較

新16日本語文×2条件×3方式の96波形。全方式が固定の校正LF0と原pulse/noise励振を使い、MLSAのalpha=.55/.50/.60だけを比較した。全64対で全パラメータ・全sample励振列・周期時計・固定支持が一致し、通常/隔離の全96件とCLI4件の波形hashも一致した。

|方式|工学E0通過|pitchゲート通過|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|31/32|0/697|0/33|0/33|
|alpha_low|32/32|26/32|6/697|12/33|6/33|
|alpha_high|32/32|31/32|1/697|3/33|4/33|

候補を採択しない。欠測/失敗/群ごとの内容悪化を保持し、総CERによる相殺や出力後のgain/係数救済を行わない。旧31方式・支持31,601区間・欠測249区間・各ASR33群の旧判定は更新しない。

原理の一次資料: [SPTK公式: MLSAフィルタとall-pass constant](https://sp-nitech.github.io/sptk/latest/main/mglsadf.html)、[mc2bの係数変換](https://sp-nitech.github.io/sptk/latest/main/mc2b.html)。MCP35は変更せず、mc2bとMLSAの実alphaを同時に変更する独立因子。包絡/フィルタ利得の変化も因果効果に含み、波形別の出力正規化は行わない。

源のcycle eventは共通の駆動時計であり、新波形のパルスや知覚pitchの正解を意味しない。DIO/全体ACF診断を短窓・動的・境界へ一般化しない。知覚資格なし、P5未開封、全体品質未達。

原励振と共有係数の一致を保った周波数軸の因果結果を全分母で保持する。原nativeの全工学/二ASR条件を守る有効範囲を次の独立因子へ引き継ぎ、同じalpha係数探索による救済をしない。

機械fixtureの係数/伝達関数恒等式: {'mc2b_exact': True, 'maximum_log_transfer_identity_error': 5.329142797855409e-15, 'excitation_and_clock_exact': True, 'effective_alpha_only_factor': True, 'frequency_warp_is_not_uniform_tract_scale': True}
原nativeへの全工学/二ASR33群保護: {'native': False, 'alpha_low': False, 'alpha_high': False}
alpha変更を周波数一様倍率、物理的声道長、知覚改善の証拠と扱わない。原励振列の一致はフィルタ後の音響pitchや知覚pitchの一致を意味しない。
