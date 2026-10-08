# 原HTSと共有HMMのMCP分布交換比較

新16文×2条件×2方式64波形。公式Mei1.4 happyの文脈別MCP状態平均/分散だけをnormalへ交換した。原時間配分・LF0/LPF・GV・励振と源時計、MLPG/vocoder/gain.25は保持。通常/隔離64組・CLI4・実拒否を確認した。

|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|31/32|0/821|0/33|0/33|
|happy_mcp|32/32|24/32|9/821|5/33|3/33|

保存全21664frameでLF0/LPF/durationの完全一致とMCPの有限性を確認した。全32対でMCPだけ意図的に変わった。全happyモデルではなく、normalの時間・源・GVを保持した共有emission分布交換である。

HTS Voice Mei v1.4、MMDAgent Project Team / Nagoya Institute of Technology Department of Computer Science、Copyright 2009–2013。[公式配布](https://github.com/mmdagent-ex/example/tree/main/voice/mei)・[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)。元配布モデルは不改変。状態MCP平均/分散交換が派生処理であり、提供者の推奨を主張しない。

旧31方式・支持31,601・欠測249・二ASR33群と凍結経路を保持。日本語知覚資格なし・P5未開封・品質未達。最終採択なし。

全件研究保護: {'native': False, 'happy_mcp': False}
共有MCP状態分布の内容/工学保護を全件保持する。同コホートの別style/補間/gain探索は封印し、別の文脈または調音制御を事前登録する。
