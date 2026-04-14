# 調査メモ: 反響・伝搬シミュレーション、物理モデリング音源、音声解析の周辺技術

## 概要

声道・声帯の直接的なモデルからは少し離れるが、技術的に深く関連する周辺領域として、音の反響や伝搬のシミュレーション、物理モデリング音源、音声解析手法がある。これらの分野は、発声器官シミュレーションそのものよりも資料が豊富であり、基礎技術や設計原理の供給源として重要である。

ざっくり言えば、音の反響・伝搬と物理モデリング音源の分野はかなり成熟しており、音声解析も手法の選択肢は非常に多い。一方で、発声器官シミュレーションのためにこれらを統合している実装知は少なく、このギャップは本プロジェクトにとって重要な着眼点になりうる。

## 1. 音の反響・伝搬シミュレーション

この分野は大きく、幾何音響ベースの手法と、波動ベースの手法に分かれる。

### 幾何音響系

- [Allen & Berkley 1984, Image Method for Efficiently Simulating Small-Room Acoustics](https://www.sciencedirect.com/science/article/abs/pii/0003682X84900112)
- [MDPI overview of room acoustic simulation](https://www.mdpi.com/2075-5309/4/2/113)

Image source method は、室内音響や初期反射シミュレーションの古典であり、軽量でリアルタイム性を確保しやすい。初期反射やインパルス応答の概算には強いが、低周波域や複雑な波動現象には限界がある。

### 波動ベース系

- [Prinn 2023, Finite Element Method for Room Acoustics: A Review](https://www.mdpi.com/2624-599X/5/2/22)
- [Bilbao et al. 2016, Finite volume time domain room acoustics simulation under general impedance boundary conditions](https://www.research.ed.ac.uk/en/publications/finite-volume-time-domain-room-acoustics-simulation-under-general/)
- [Hölter et al. 2024, FDTD and nonlinear Euler acoustics](https://acta-acustica.edpsciences.org/articles/aacus/full_html/2024/01/aacus240004/aacus240004.html)

FEM、FDTD、FVM のような波動ベース手法は、低域や回折、境界条件の厳密な扱いに強いが、計算コストが高くなる。高忠実度な検証やオフライン計算には向くが、リアルタイム性を重視するシステムではそのまま使いにくい。

### 中間的なアプローチ

- [Mondet et al., Combining Image and Equivalent Sources for Room Acoustic Simulations](https://orbit.dtu.dk/en/publications/combining-image-and-equivalent-sources-for-room-acoustic-simulati)

幾何音響と波動ベースの間を埋めるような手法も存在する。こうした折衷的な考え方は、声道シミュレーションでも有用である可能性がある。

### 示唆

この領域から得られる重要な構図は、軽量でリアルタイム向きのモデルと、高忠実度だが重いモデルを明確に分けて扱う設計である。これは声道・声帯のシミュレーションにもそのまま応用できる。

## 2. 物理モデリング音源

この領域には、楽器音響を中心に非常に豊富な研究と実装知がある。特に digital waveguide、modal synthesis、artificial reverberation は重要な柱である。

### 基礎資料

- [Julius O. Smith, Physical Audio Signal Processing](https://freecomputerbooks.com/Physical-Audio-Signal-Processing.html)
- [Waveguide Simulation of Non-Cylindrical Acoustic Tubes](https://quod.lib.umich.edu/i/icmc/bbp2372.1991.071?rgn=main%3Bview%3Dfulltext)
- [Digital Waveguide Architectures for Virtual Musical Instruments](https://link.springer.com/chapter/10.1007/978-0-387-30441-0_25)

Digital waveguide は、管や弦、共鳴体のような構造を、比較的軽量に物理的な意味を保ったままモデル化するための有力な枠組みである。非円筒チューブの扱いや scattering の考え方は、声道シミュレーションにも非常に近い。

### 残響アルゴリズム

- [Schlecht 2018, Feedback Delay Networks in Artificial Reverberation and Reverberation Enhancement](https://www.researchgate.net/publication/322951473_Feedback_Delay_Networks_in_Artificial_Reverberation_and_Reverberation_Enhancement)
- [Time-varying feedback matrices in FDNs](https://pubmed.ncbi.nlm.nih.gov/26428777/)
- [Directional Feedback Delay Network](https://www.researchgate.net/publication/336835646_Directional_Feedback_Delay_Network)

FDN は人工残響の中心的な手法であり、直接的に声道モデルそのものではないが、エネルギーの分配、損失、反射、周波数依存の挙動などをどう設計するかという意味で示唆が大きい。

### 最近の見取り図

- [Frontiers 2025, physical modeling synthesis special issue editorial](https://www.frontiersin.org/journals/signal-processing/articles/10.3389/frsip.2025.1715792/full)

最近でも物理モデリング音源は活発な分野であり、リアルタイム性と物理妥当性のバランスを取る技法は継続的に発展している。

### 示唆

この分野の知見は、声道・声帯シミュレーションに直接流用できる部分が多い。特に waveguide、scattering、boundary condition、loss、分布定数系と集中定数系の切り分けは、本プロジェクトの設計原理として重要になる可能性が高い。

## 3. 音声解析手法

音声解析は手法の種類が非常に多く、目的に応じて使い分ける必要がある。ここでは、発声シミュレータ開発との関連が強そうなものを中心に見る。

### 基本理論

- [The Source-Filter Theory of Speech](https://cir.nii.ac.jp/crid/1360013168855541376)

音声の解析・合成の基礎的な考え方として、source-filter モデルは依然として重要である。発声器官シミュレーションでも、声帯由来の励振と声道由来のフィルタをどう分けて考えるかの基礎になる。

### フォルマント解析

- [Praat manual: Sound: To Formant (burg)](https://www.fon.hum.uva.nl/praat/manual/Sound__To_Formant__burg____.html)
- [Praat manual: Sound: To FormantPath (burg)](https://www.fon.hum.uva.nl/praat/manual/Sound__To_FormantPath__burg____.html)

Praat のマニュアルは、実務的な観点から非常に有用である。フォルマント解析はよく使われるが、設定値によって結果が大きく変わるため、手法そのものだけでなく運用上の注意点も重要になる。

### 声質評価・声の指標

- [Acoustic analysis of voice quality: a review of perturbation, shimmer, and related metrics](https://www.sciencedirect.com/science/article/pii/S2212017313002788)
- [CepstralVox 2025](https://www.sciencedirect.com/science/article/pii/S0892199725004059)

jitter、shimmer、HNR、cepstral 指標などは、生成された音声の評価や、声帯モデルの挙動観察に使える可能性がある。

### 手法の限界や注意点

- [Recent review touching formant analysis limitations](https://link.springer.com/article/10.1186/s12915-025-02188-w)

解析手法は豊富だが、正しい条件で使わないと解釈を誤る危険がある。特に LPC やフォルマント推定は、設定が不適切だともっともらしいが意味の薄い値を返すことがある。

### 示唆

音声解析は、シミュレーションの「正しさ」を直接保証するものというより、モデルの振る舞いを観察し、比較し、変化を把握するための道具として位置づける方がよい。開発初期から解析ツールを整えておく価値は高い。

## 4. 何が多く、何が少ないか

### 多いもの

- 室内音響や反響シミュレーションのアルゴリズム
- Digital waveguide や FDN などの物理モデリングの基盤技術
- 音声解析の基本手法と実装ノウハウ
- Source-filter 理論に基づく古典的な分析・合成の知見

### 少ないもの

- 発声器官モデルと室内音響・残響を一体的に扱う設計資料
- 発声器官シミュレータ向けに最適化された物理モデリング実装事例
- 子音、乱流、非線形性まで含めた軽量かつ改造しやすい統合実装
- 音声解析をシミュレータのデバッグ用途として整理した資料

## 5. このプロジェクトへの示唆

この周辺領域を見て分かるのは、必要な基礎技術そのものは十分存在しているということである。問題は、それらが発声器官シミュレーション向けに統合されていない点にある。

現時点では、以下の方向性が有力に見える。

1. 音の伝搬部分は waveguide、tube、scattering のような軽量な物理モデルを中心に考える
2. 高忠実度な検証や将来拡張のために FDTD、FEM、FVM を参照する
3. 残響や空間音響はシミュレータ本体から分離し、後段の音響モジュールとして扱う
4. フォルマント、LPC、スペクトル、cepstrum などの解析手法を、生成音の観察と評価のために導入する
5. 物理モデリング音源の知見を、人間の声向けに再構成すること自体をプロジェクトの価値の一つとして考える

## 備考

このメモは、プロジェクト初期段階における粗い調査結果であり、今後の文献調査や実装方針の具体化に応じて更新される前提の資料である。
