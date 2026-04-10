# 調査メモ: フォルマントフィルタ / 波動管以外の音声合成・発声シミュレーション手法

## 概要

このメモは、これまで本リポジトリで扱ってきた

- フォルマントフィルタによる擬似的な母音生成
- 1D 波動管 / 多管チューブモデル

以外の選択肢、およびそれらをさらに発展させた方向を整理するための調査メモである。

目的は、現時点で一つの方式に決め打ちすることではない。むしろ、

1. どのような系統の手法が存在するか
2. それぞれが何を得意とし、何を苦手とするか
3. 本プロジェクトの短期・中期・長期の候補として何がありうるか

を明確にすることを目的とする。

## まず結論

現時点で、本プロジェクトにとって特に重要そうな候補は次の 5 系統である。

1. **伝送線路 / 回路アナロジー型の声道モデル**
2. **デジタルウェーブガイドメッシュ**
3. **FDTD / FEM などの 3D 波動数値計算**
4. **生体力学モデルと音響モデルの結合**
5. **機械学習を制御側に使うハイブリッド構成**

このうち、短中期で現実的に試しやすいのは 1 と 2、研究用の高忠実度検証として価値が高いのは 3、長期テーマとして重要なのは 4 と 5 である。

## 1. 伝送線路 / 回路アナロジー型の声道モデル

### 概要

声道を音響管としてだけでなく、電気回路に類似した **伝送線路 / RLC ネットワーク** として表現する系統である。

波動管モデルと近いが、以下のような利点がある。

- 損失を抵抗や周波数依存要素として導入しやすい
- 分岐路や側枝を回路接続として表現しやすい
- 声帯や口唇放射を境界インピーダンスとして扱いやすい
- 連続体モデルと離散回路モデルの中間として整理しやすい

### 本プロジェクトへの示唆

現在の波動管モデルを大きく捨てずに、より精密な損失、鼻腔分岐、側枝、境界条件を導入する足場として有力である。

「今の延長線で選択肢を増やす」意味では、もっとも実装しやすい。

### 向いていること

- 1D モデルの高機能化
- 鼻腔や分岐の導入
- 声帯音源との結合の改善
- オフラインでもリアルタイムでも扱える中間モデル

### 限界

- 3D 由来の効果は本質的には弱い
- 幾何形状の自由度は 3D 系より低い

## 2. デジタルウェーブガイドメッシュ

### 概要

1D 波動管を 2D / 3D のメッシュへ拡張し、格子状に波動を伝搬させる系統である。

通常の 1D 波動管よりも、

- 複雑な形状
- 分岐
- 面的な広がり
- 局所的な共鳴

を扱いやすい。

一方で、FDTD や FEM ほど重くない中間案として位置づけられることが多い。

### 本プロジェクトへの示唆

これはかなり有力な探索候補である。

現状の「フォルマントフィルタより物理的」「3D 波動解析より軽い」という中間レイヤーとして、独自性を出しやすい。

特に、

- ブラウザまたは軽量ネイティブ実装で試作できる余地がある
- 2D 可視化との相性がよい
- 鼻腔や側枝のような構造拡張に進みやすい

という点が大きい。

### 向いていること

- 2D/準 3D のインタラクティブ試作
- 波動管モデルの次の段階
- 形状と音の関係を体験的に見せるプロトタイプ

### 限界

- メッシュ分解能と計算コストのバランス調整が難しい
- 3D を本格化すると急に重くなる

## 3. FDTD / FEM / FVM などの 3D 波動数値計算

### 概要

声道内部の音波を、3D の波動方程式として直接数値的に解く系統である。

代表例:

- FDTD（Finite Difference Time Domain）
- FEM（Finite Element Method）
- FVM（Finite Volume Method）

これらは、MRI などから得た 3D 形状に対して高忠実度な音響応答を求める際に強い。

### 本プロジェクトへの示唆

これは主に **研究 / 検証系** として重要である。

最初からこれを主実装にするのは重いが、

- 1D / 2D 近似モデルの妥当性確認
- 3D 特有のディップや側枝効果の確認
- 将来の高忠実度モデルの参照先

として非常に価値がある。

### 向いていること

- オフライン生成
- 高忠実度検証
- MRI / 3D データを用いた比較

### 限界

- 計算コストが高い
- リアルタイム性は基本的に期待しにくい
- UI と一体化した軽量試作には向かない

## 4. 流体力学ベースの統合モデル

### 概要

音源とフィルタを分けるのではなく、声門流・声道流・圧力変動を一体の流体現象として扱う方向である。

ここには、

- 声帯と声道の強い結合
- 非線形性
- 乱流
- 摩擦音や息漏れの生成

が自然に入る。

### 本プロジェクトへの示唆

短期的に全面採用するには重いが、

- 子音
- 摩擦音
- 息成分
- 声帯-声道結合

を本気で扱うなら避けて通れない論点である。

したがって、これは「今すぐ主方式」ではなく、将来の研究テーマとして重要とみなすのがよい。

### 向いていること

- 非線形現象の扱い
- 乱流音や息漏れの検討
- 声帯と声道の相互作用の解析

### 限界

- 実装難度が非常に高い
- 計算量も大きい
- 初期の操作可能な試作には不向き

## 5. 生体力学モデルと音響モデルの結合

### 概要

これは音響計算そのものというより、**舌・唇・顎・軟口蓋・咽頭壁などの運動モデル** を強化する方向である。

たとえば、

- 2D / 3D の解剖学的形状モデル
- 有限要素ベースの舌モデル
- 調音パラメータから声道形状を生成するモデル

を用い、その出力形状に対して別の音響モデルを適用する。

### 本プロジェクトへの示唆

これは波動管や FDTD と競合するというより、**前段の形状生成系** として組み合わせる候補である。

本プロジェクトが今後、

- 共調音
- 発話運動
- 話者差
- 直感的な操作 UI

に踏み込むなら、非常に重要になる。

### 向いていること

- 調音運動の可視化
- 共調音や動的変化の導入
- UI と調音制御の結びつき

### 限界

- パラメータ設計が難しい
- 音響モデルとは別に複雑さが増える

## 6. 機械学習を制御側に使うハイブリッド構成

### 概要

これは「深層学習で最終波形を直接作る」方向ではなく、

- 音響モデルは物理ベースのまま保持し
- 機械学習を声道形状推定や調音制御に使う

という構成である。

たとえば、

- 調音パラメータ推定
- 3D/2D 声道形状の補間
- 物理モデルのパラメータ探索
- 逆問題としてのターゲット音声へのフィッティング

に使える。

### 本プロジェクトへの示唆

これは「物理モデルの透明性」と「制御しやすさ」の折衷案としてかなり有効である。

本プロジェクトの主目的はブラックボックス TTS ではないため、学習モデルを主役にするのではなく、**制御補助** として使うのが自然である。

### 向いていること

- 逆問題
- パラメータ自動探索
- 話者適応
- 操作支援

### 限界

- 学習データが必要
- 可解性や一般化性能の検証が必要

## 7. ロボット / 物理レプリカ系

### 概要

人工声道、人工声帯、 talking robot のような系統である。

これはソフトウェア内の主方式ではないが、

- どの自由度が音に効くか
- どの機構が子音や母音に重要か
- どの程度まで単純化できるか

を考えるうえで非常に参考になる。

### 本プロジェクトへの示唆

特に、機構設計の視点や自由度選定の視点で有用である。

「何を物理モデルに含め、何を省略するか」を考える際の発想源として価値がある。

## 比較のための整理

ざっくりした位置づけを表にすると次のようになる。

| 手法 | 物理妥当性 | 計算コスト | リアルタイム性 | 実装難度 | 本プロジェクトとの相性 |
|---|---|---:|---|---:|---|
| フォルマントフィルタ | 低〜中 | 低 | 高い | 低 | 初期試作向き |
| 1D 波動管 | 中 | 低〜中 | 高い | 中 | 現在の主線 |
| 伝送線路 / 回路アナロジー | 中〜高 | 低〜中 | 高い | 中 | 次の改良候補 |
| デジタルウェーブガイドメッシュ | 中〜高 | 中 | 中 | 中〜高 | 次の探索候補 |
| FDTD / FEM / FVM | 高 | 高 | 低い | 高 | 研究・検証向き |
| 生体力学 + 音響 | 高 | 中〜高 | 低〜中 | 高 | 長期テーマ |
| ML + 物理ハイブリッド | 可変 | 可変 | 可変 | 中〜高 | 制御面の拡張候補 |

## このプロジェクトで有望な進め方

現時点では、次の 3 層で考えるのが自然に見える。

### 1. 短期

既存の波動管系を拡張する。

候補:

- 伝送線路的な整理
- 周波数依存損失
- 鼻腔分岐
- 側枝共鳴
- 声帯-声道結合の改善

### 2. 中期

デジタルウェーブガイドメッシュや 2D 近似モデルを試す。

候補:

- 2D メッシュでの軽量試作
- インタラクティブ UI と一体化した可視化
- 鼻腔や分岐の自然な導入

### 3. 長期

研究ワークスペースで高忠実度モデルと制御系を強化する。

候補:

- 3D FDTD / FEM による検証
- 生体力学モデル
- ML を使った逆問題・自動調整

## 暫定的な優先順位

今後の探索優先度を暫定的に並べると、次の順が有力に見える。

1. **伝送線路 / 回路アナロジーとしての再整理**
2. **デジタルウェーブガイドメッシュの最小実験**
3. **研究側での 3D 高忠実度検証**
4. **生体力学的形状生成の導入**
5. **ML による制御支援**

## 参考資料

### 分野全体のレビュー

- [Kröger 2022, Computer-Implemented Articulatory Models for Speech Production: A Review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9040071/)

### 伝送線路 / 回路アナロジー

- [Mermelstein 1973, Articulatory model for the study of speech production](https://pubmed.ncbi.nlm.nih.gov/4765801/)
- [Sondhi & Schroeter 1987, A hybrid time-frequency domain articulatory speech synthesizer](https://pubmed.ncbi.nlm.nih.gov/3694748/)
- [Jones & Harris 1996, Silicon Vocal Tract](https://scholarsmine.mst.edu/ele_comeng_facwork/7094/)

### デジタルウェーブガイドメッシュ

- [Mullen, Howard, Murphy 2003, Digital waveguide mesh modeling of vocal tract acoustics](https://pure.york.ac.uk/portal/en/publications/digital-waveguide-mesh-modeling-of-the-vocal-tract-acoustics)
- [Howard, Murphy, Mullen 2009, 3D digital waveguide mesh vocal tract modeling](https://pubmed.ncbi.nlm.nih.gov/17981014/)
- [Speed, Murphy, Howard 2013, Three-Dimensional Digital Waveguide Mesh Simulation of Cylindrical Vocal Tract Analogs](https://pure.royalholloway.ac.uk/en/publications/three-dimensional-digital-waveguide-mesh-simulation-of-cylindrica)
- [Gully et al. 2017, Articulatory text-to-speech synthesis using the digital waveguide mesh](https://pure.york.ac.uk/portal/en/publications/articulatory-text-to-speech-synthesis-using-the-digital-waveguide)

### 3D 高忠実度音響解析

- [Takemoto et al. 2010, Acoustic analysis of the vocal tract during vowel production by finite-element method](https://pubmed.ncbi.nlm.nih.gov/21218904/)
- [Birkholz et al. 2020, Dresden Vocal Tract Dataset](https://www.nature.com/articles/s41597-020-00597-w)
- [Lim et al. 2019, 3D dynamic MRI of the vocal tract during natural speech](https://pubmed.ncbi.nlm.nih.gov/30390319/)

### 生体力学 / 調音制御

- [Birkholz 2013, Modeling Consonant-Vowel Coarticulation for Articulatory Speech Synthesis](https://pmc.ncbi.nlm.nih.gov/articles/PMC3628899/)

### ロボット / 機械的再現

- [Nishikawa et al. 2004, Speech production of an advanced talking robot based on human acoustic theory](https://waseda.elsevierpure.com/en/publications/speech-production-of-an-advanced-talking-robot-based-on-human-aco/)

### ML と組み合わせた方向

- [Maqsood et al. 2022, Speaker adaptation using articulatory-to-speech synthesis](https://www.mdpi.com/1424-8220/22/16/6056)
- [Automatic generation of the complete vocal tract shape for acoustic simulation 2022](https://www.sciencedirect.com/science/article/pii/S0167639322000607)

## 備考

このメモは、今後の方式選定のための粗い見取り図であり、個別方式の詳細比較や実装候補の絞り込みは別途行う前提の資料である。
