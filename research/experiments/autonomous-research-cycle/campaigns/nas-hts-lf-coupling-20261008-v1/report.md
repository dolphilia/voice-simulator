# 固定LFと原HTS混合励振の結合

有声のsqrt(period) impulseだけを連続周期RMS=1の固定LF derivativeへ置換した。元counter/period・noise算法/呼出条件・LPF ring演算・MCP/LF0/LPF/MLSAを保持する。phaseは元counter更新後、period補間前のfmod(counter/period,1)。新しい位相積分器ではなく、時間変動の周期面積0やaliasingを保証しない。

人工8条件(110/280Hz×LPF0/1/31tap、上昇/下降F0×31tap)でbare/native完全一致・源時計/noise/入力完全一致、独立Pythonの周期関数/LPF混合、rawの因果前半、LPF tail終了後の無声励振一致を確認した。56生成/96DSP。未知日本語の内容・固定音素支持・通常隔離/CLI・知覚品質は別契約。

HTS-BSDを保持し、変更した励振を明示する。LFは一次式に基づく独自実装。波形別gain/係数/phaseの選別なし。旧封印/欠測と全凍結保持。P5未開封・品質未達。
