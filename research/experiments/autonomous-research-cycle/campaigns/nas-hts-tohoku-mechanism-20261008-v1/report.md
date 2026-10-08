# 公開Tohoku共有HMM全モデルの限定機構

neutral一つを事前固定して取得し、全共有HMMをMeiと対比した。MCP/LF0/LPF/duration/MSD/GVはモデル固有で、二モデル間の源時計や音響列の一致を主張しない。辞書・ラベル、指定中央値への一様logF0制御、速度、MLPG/vocoder・48k/240/alpha.55、24k resample/12msfade/gain.25を共通化する。

4文×2条件×2モデルの16機構条件で、状態保持・MCP/LPF/voicing保持・指定LF0中央値・有限性・素の一次HTSと純粋観測版の波形完全一致を確認した。32生成・80DSP。日本語内容/自然さ/pitchの資格ではない。

HTS voice tohoku-f01、Copyright 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University。[公式配布](https://github.com/icn-lab/htsvoice-tohoku-f01)・[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。モデルは不改変、研究生成の一様LF0制御とresample/fade/gainを変更として表示する。提供者の推奨を主張しない。

次は未使用日本語の全モデル比較を生成前登録する。nativeの音素index支持を固定し、candidate固有の時間軸へ適用する。旧凍結/欠測を保持。日本語知覚資格なし・P5未開封・品質未達。
