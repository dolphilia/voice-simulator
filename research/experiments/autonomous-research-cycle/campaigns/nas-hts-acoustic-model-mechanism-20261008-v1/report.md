# 共有HMMのMCP状態分布交換

公式Mei v1.4 happy一つを事前固定し、同じfull-contextラベルのMCP状態平均/分散だけをnormalへ交換した。元の時間配分・LF0/LPF・GV・window・MLPG・vocoderは保持する。発話固有表・教師・ニューラル推論・波形からの係数推定は含まない。

4文×2条件の機構試験で、元モデルへの恒等交換の列/波形完全一致、別MCPへの交換と源時計/励振・他状態分布・GVの完全保持を確認した。全24生成と72DSPを課した。比較音声の内容・自然さ・pitchの資格とはしない。

HTS Voice Mei v1.4、MMDAgent Project Team、Nagoya Institute of Technology Department of Computer Science、Copyright 2009–2013。公式配布モデルは不改変、MCP分布交換が研究の変更因子。[公式配布](https://github.com/mmdagent-ex/example/tree/main/voice/mei)・[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)。提供者の推奨を主張しない。

次は未使用16文×2条件のnative/happy_MCPを出力前登録して工学・二ASR・隔離を比較する。旧凍結/欠測を保持。日本語知覚資格なし・P5未開封・品質未達。
