かなり改善余地があります。現在の「生成 → 試聴 → パラメータ修正 → 再生成」というループで最大のボトルネックになっているのは、**人間の聴覚がデバッガ・評価関数・最適化器を全部兼ねていること**だと思います。

調べた範囲では、特に相性が良いのは **analysis-by-synthesis（分析による合成）** の考え方です。これはかなり昔から調音合成で研究されており、「自然音声を分析 → 合成 → 両者の差を数値化 → パラメータを自動調整」というループを回します。実際、VocalTractLab を使った研究では、遺伝的アルゴリズムで gestural score を最適化し、自然音声との音響的距離を自動的に減らす方法まで実証されています。([PubMed][1])

したがって、このプロジェクトでは、

**「耳で音を作る」から「仕様を定義し、機械が探索し、耳で承認する」**

への転換を強く勧めます。

---

# 1. 問題の本質

現在おそらく、

> パラメータを変える
> ↓
> WAVを生成する
> ↓
> 聴く
> ↓
> 「少し /a/ っぽくなった」
> ↓
> また調整する

という開発になっていると思います。

これは、人間にとって非常に効率の悪い最適化です。

特に音声の場合、

* F1/F2/F3
* F0
* formant bandwidth
* spectral tilt
* aspiration
* voicing
* VOT
* burst
* friction noise
* nasal coupling
* coarticulation
* phoneme duration

など多数の変数が互いに干渉します。

例えば「/a/ が少し /o/ に聞こえる」と感じても、それが F1 なのか F2 なのか声道長なのか glottal source なのかを耳だけで逆算するのは困難です。

ここを機械化するべきです。

---

# 2. ボトムアップそのものを捨てる必要はない

重要なのは、

**ボトムアップ合成**と
**ボトムアップ開発**

は別物だという点です。

音声生成器そのものは、

> 声門
> → 声道
> → 共鳴
> → 放射
> → 音声

という物理的なボトムアップモデルで構いません。

しかし開発方法まで、

> とりあえず低レベル部品を作る
> → 音を聞く
> → 少し直す

とする必要はありません。

むしろ、

> 上から「この音響結果が欲しい」と要求する
> ↓
> 下の物理モデルのパラメータを探索する

という **top-down specification + bottom-up synthesis** にすると非常に強力です。

この二層構造が、今回かなり重要だと思います。

---

# 3. 私なら「音声生成器」の横に「音声検査器」を作ります

現在、

```text
text / phoneme
       ↓
   synthesizer
       ↓
      WAV
       ↓
     human
```

となっているなら、

```text
                    ┌───────────────┐
target ────────────→│ Speech Oracle │
                    └───────┬───────┘
                            │ expected
                            │
phoneme → synthesizer → WAV
                        │
                        ↓
                acoustic analyzer
                        │
             ┌──────────┼──────────┐
             ↓          ↓          ↓
           ASR       phonetics   quality
             │          │          │
             └──────────┼──────────┘
                        ↓
                  Error Vector
                        ↓
                    Optimizer
                        ↓
               synthesizer params
```

とします。

ここで **Speech Oracle** は、「/a/ならどうあるべきか」という仕様です。

例えば、

```text
/a/

F1 = target ± tolerance
F2 = target ± tolerance
F3 = target ± tolerance

voiced = true
nasality = low
duration = 100 ms
spectral tilt = range ...
```

のように記述します。

これだけでも、試聴のかなりの部分を削減できます。

---

# 4. まず最も簡単なのは「音響特徴量を自動測定する」こと

これはAIを必要としません。

Praat や openSMILE のようなツールを使えば、

F0、F1〜F3、formant bandwidth、HNR、jitter、shimmer、spectral slope などを自動抽出できます。openSMILE の eGeMAPS にも、F0、F1〜F3、bandwidth、HNR、jitter、shimmer などが既に含まれています。([GitHub][2])

つまり、

```text
generate("a")
    ↓
out.wav

analyze(out.wav)
    ↓
F1 = 745 Hz
F2 = 1195 Hz
F3 = 2520 Hz
HNR = ...
```

というテストを自動化できます。

さらに、

```text
expected F1 = 750
actual   F1 = 745

PASS
```

とできます。

これは一般的なソフトウェアにおける unit test とほぼ同じです。

---

# 5. 音声認識を「テストスイート」として使う

これは特に面白い方法です。

AI音声生成を禁止していても、

**AIを評価器として使用すること**

まで禁止する必要はありません。

例えば生成した、

```text
/ka/
/ki/
/ku/
/ke/
/ko/
```

をASRに入れる。

期待値が、

```text
ka → "か"
ki → "き"
...
```

なら、

```text
Synthesizer
    ↓
ASR
    ↓
expected == recognized ?
```

という自動テストになります。

文章なら、

```text
入力:
「今日は天気が良いです」

生成音声
    ↓
ASR
    ↓
「今日は天気が良いです」

WER = 0
```

とできます。

これは自然さではなく、主に **intelligibility（明瞭度）** の検査ですが非常に有効です。

ただし、一つのASRだけだとその認識器固有の癖を拾うので、

```text
Recognizer A
Recognizer B
Recognizer C
```

の多数決にするとさらによいでしょう。

---

# 6. ASRより細かく「音素レベル」で検査する

文章単位のASRでは、

> なぜ聞き取りにくいのか

が分かりません。

そこで音素単位の検査器を加えます。

例えば、

```text
expected:
/ k a t a /

recognized:
/ k a t o /
```

なら、

```text
/a/ → /o/
```

という具体的な失敗として記録できます。

すると、

```text
phoneme confusion matrix

       a    i    u    e    o
a     98    0    0    0    2
i      0   97    2    1    0
u      0    1   96    0    3
...
```

が作れます。

これが非常に強力です。

「音質が悪い」という漠然とした問題が、

> /a/ と /o/ の識別境界に問題がある

という開発課題に変わります。

---

# 7. Forced Alignmentも非常に役立つ

Montreal Forced Aligner のような forced alignment ツールを使えば、

```text
音声
+
期待する音素列
```

から、

```text
k    0–72 ms
a   72–180 ms
t  180–241 ms
a  241–380 ms
```

のような位置合わせができます。

最新のMFAでは alignment 同士の比較や phone duration deviation なども計算できます。([モントリオール強制アライナー][3])

これを使えば、

> /t/ は聞こえるが、閉鎖時間が短すぎる

とか、

> vowel onset が早すぎる

といった問題を自動検出できます。

---

# 8. 「自然音声との差」を直接目的関数にする

さらに一歩進めます。

自然音声を**音声素片として使う必要はありません**。

教師というか、測定対象としてだけ利用します。

例えば自然な「あ」を録音し、

```text
natural.wav
synthetic.wav
```

から、

```text
ΔF1
ΔF2
ΔF3
ΔF0
Δspectral envelope
ΔMFCC
Δduration
ΔHNR
```

を計算します。

そして、

$$
L =
w_1D_{F1}
+w_2D_{F2}
+w_3D_{F3}
+w_4D_{spectral}
+w_5D_{duration}
+\dots
$$

という loss function を定義します。

すると問題は、

> 「いい声を作る」

ではなく、

$$
\min_\theta L(S(\theta),R)
$$

になります。

ここで、

* \(S\) = synthesizer
* \(\theta\) = synthesis parameters
* \(R\) = reference speech

です。

---

# 9. これは実際に研究されている

この方法はまさに **analysis-by-synthesis** と呼ばれる系統です。

例えばMaeda型調音モデルについて、自然音声と合成音声のF1〜F3の差を目的関数にし、quasi-Newton法で調音軌跡を逆算する研究があります。正則化と時間方向の連続性も目的関数に入れています。([PubMed][1])

さらにVocalTractLabでは、

> 自然音声
> → 初期 gestural score
> → synthesis
> → acoustic feature comparison
> → genetic algorithm
> → gestural score更新

というほぼ今回の用途そのものに近い実験があります。([ISCAアーカイブ][4])

MFCC差によって articulatory target を反復最適化する研究もあります。([VocalTractLab][5])

つまり、この方向は十分に筋が通っています。

---

# 10. 「手で調整」から「探索」に変える

例えばフォルマント合成なら、

```text
F1
F2
F3
B1
B2
B3
F0
source tilt
noise
...
```

があります。

今、

```text
F1 += 20
聞く

F2 -= 30
聞く
```

としている部分を、

```text
optimizer.propose()
       ↓
synth()
       ↓
analyze()
       ↓
loss()
       ↓
optimizer.update()
```

にできます。

ここにはAIは不要です。

CMA-ES、遺伝的アルゴリズム、Nelder–Mead、BFGS、Bayesian Optimizationなどで十分です。

特に音声合成は、

* 非線形
* 局所解が多い
* パラメータ間依存が強い

ので、勾配を簡単に計算できないなら **CMA-ESや遺伝的アルゴリズム** はかなり相性が良いでしょう。

VocalTractLabのcopy synthesisでも遺伝的アルゴリズムが coordinate descent より良い acoustic distance を得ています。([ISCAアーカイブ][4])

---

# 11. さらに重要なのが「正則化」

単に音を一致させるだけでは危険です。

例えば、

```text
natural speech
      ↑
かなり変な声道形状
      ↑
synthetic speech
```

でも音響的には一致する場合があります。

音声生成は典型的な inverse problem だからです。

そこで、

$$
Loss =
AcousticError
+\lambda_1 PhysicalPenalty
+\lambda_2 MotionPenalty
+\lambda_3 ComplexityPenalty
$$

のようにします。

つまり、

```text
音が似ている
+
物理的にあり得る
+
時間変化が滑らか
```

を同時に要求します。

実際の acoustic-to-articulatory inversion 研究でも regularization と continuity constraint が使われています。([PubMed][1])

これは物理モデル方式なら特に重要です。

---

# 12. 音素を一個ずつ完成させる方法も見直した方がよい

ボトムアップ開発でもう一つ起きがちな問題が、

```text
/a/ 完成
/i/ 完成
/u/ 完成
...
/k/ 完成
...
```

です。

実際の音声では音素は独立していません。

```text
/a/
/ka/
/aka/
/kai/
```

では /a/ の状態が異なります。

したがって、開発単位を

```text
phoneme
```

から

```text
gesture
```

へ上げることを検討するとよいと思います。

VocalTractLab自体も、肺、声門、F0、母音、舌、唇、軟口蓋などを独立tierとして持つ gestural control を採用しています。([VocalTractLab][6])

つまり、

```text
/k/
/a/
```

を作るより、

```text
velar closure gesture
vowel target gesture
voicing gesture
```

を時間上で重ねる。

これは coarticulation を後付けするよりかなり自然です。

---

# 13. VocalTractLabは非常に良い比較対象になる

今回のプロジェクトなら一度詳しく調べる価値があります。

VocalTractLab 2.4は2025年12月に公開されており、現在も開発中です。MRI由来の声道モデル、声門モデル、aero-acoustic simulation、gestural scoreなどを持っています。([VocalTractLab][7])

興味深いのは「完成したTTS」より、

**音声生成研究用の実験環境**

になっている点です。

さらに自然発話から phone duration と pitch contour を持ってきて再合成する copy synthesis の例も公開されています。([VocalTractLab][8])

ここで自然音声そのものを出力に混ぜているわけではありません。

したがって、今回の制約にもかなり近い思想です。

---

# 14. Pink Trombone型のモデルも参考になる

もっと軽量な方向では Pink Trombone があります。

これは声門音源＋声道を digital waveguide でシミュレーションする物理モデルです。Rust実装なども存在し、パラメータをプログラムから制御できます。([GitHub][9])

ここで重要なのは音質そのものより、

> 少数の意味のあるパラメータで発話空間を操作する

という設計です。

今回のシステムでも、

```text
F1 = 730
F2 = 1210
```

という直接操作だけではなく、

```text
tongue_height
tongue_backness
lip_rounding
jaw_opening
velum
glottal_tension
```

のような**発声上意味のある中間パラメータ**を設けた方が探索が容易になります。

---

# 15. 評価関数は一つにしない方がよい

ここはかなり重要です。

「自然音声とのスペクトログラム距離」を一つだけ最小化すると、妙な音になる可能性があります。

私は評価を最低でも次のように分離します。

| 軸                     | 評価方法                     |
| --------------------- | ------------------------ |
| 音素として正しいか             | phoneme recognition      |
| 文として聞き取れるか            | ASR / WER                |
| vowel quality         | F1/F2/F3                 |
| pitch                 | F0 contour               |
| timing                | forced alignment         |
| voice quality         | HNR / jitter / shimmer   |
| spectrum              | MFCC / spectral envelope |
| transitions           | trajectory distance      |
| physical plausibility | articulatory constraints |
| 最終自然さ                 | 人間                       |

つまり、

```text
score = 0.83
```

ではなく、

```text
phoneme      0.98
ASR          1.00
formant      0.93
timing       0.71
source       0.88
naturalness  ?
```

とします。

こうすると、

> 音がおかしい

ではなく、

> 子音の timing が問題

と分かります。

---

# 16. PESQ/POLQA/STOIなどは補助的に使う

既存の客観音声評価指標も利用できます。

PESQ/POLQAなどは人間の知覚的品質を予測するために作られており、現在のITU-T P.863 POLQA は fullband まで対応しています。([ITU][10])

ただし注意が必要です。

これらは本来、

```text
original speech
↓
codec/network/degradation
↓
degraded speech
```

の評価用です。

したがって、

> 合成音声そのものが自然か

の万能指標ではありません。

今回なら、主評価ではなく**補助指標**として使うのが妥当です。

---

# 17. 人間による試聴も「絶対評価」から「比較評価」にする

どうしても耳が必要なところがあります。

しかし、

> この音は自然ですか？ 1〜5

より、

> AとBならどちらが良いか？

の方が人間は答えやすいです。

そこで optimizer が候補を例えば16個生成し、自動評価で上位4個まで絞ります。

```text
1000 candidates
      ↓
automatic tests
      ↓
100 candidates
      ↓
acoustic metrics
      ↓
10 candidates
      ↓
ASR / phoneme tests
      ↓
2 candidates
      ↓
human A/B
```

とします。

すると人間は1000回聞かず、

**最後の2つだけ聞けばよい。**

これは劇的な差になります。

---

# 18. さらにHuman-in-the-loop最適化も可能

「自然さ」は完全には数値化できません。

そこで、

```text
A or B?
```

だけ人間が答えます。

optimizer が、

```text
θ₁ vs θ₂ → θ₁ preferred
θ₃ vs θ₄ → θ₄ preferred
...
```

から好みを学習して探索します。

これは Bayesian optimization / preference optimization のような枠組みにできます。

ここで使われるモデルは「音声を生成するAI」ではありません。

単なるパラメータ探索器です。

もしAIという語を広義に捉えてこれも避けたいなら、単純な tournament + evolutionary algorithm でも十分成立します。

---

# 19. テスト用発話セットを作る

もう一つ強く勧めたいのが、

**毎回同じ音声セットを生成すること**

です。

一般のソフトウェアの regression test に相当します。

例えば日本語なら、

```text
Vowels:
a i u e o

CV:
ka ki ku ke ko
sa shi su se so
...

Contrasts:
ka / ga
ta / da
sa / za
...

Transitions:
ai
au
ia
...

Words:
...

Sentences:
...
```

という固定 corpus を作ります。

各commitごとに、

```text
synth-test
```

を実行して全部生成・解析します。

すると、

```text
revision 142

/a/ F1 error       -5%
/i/ F2 error       +1%
/s/ recognition    +7%
/t/ timing         -12%
WER                unchanged
```

というレポートになります。

これは普通のプログラムでいう、

```text
237 tests passed
3 failed
```

です。

音声生成でも同じことをすべきだと思います。

---

# 20. 「parameter sweep」を徹底的に使う

かなり単純ですが非常に効果があります。

例えば、

```text
F1 = 500..900 Hz
```

なら、

```text
500
520
540
...
900
```

を一括生成します。

さらに、

```text
F1 × F2
```

を総当たりして、

```text
             F2
       900 1100 1300 1500
F1 500
   600
   700
   800
```

のマップを作ります。

各セルに、

```text
ASR result
formant error
```

を置く。

すると、

**「人間がどう聞こえるかの地形」**

が見えてきます。

これは手作業で1個ずつ調整するより圧倒的に有用です。

---

# 21. 一番おすすめなのは「音響空間を先に作る」方法

ここまでをさらに進めると、私は開発そのものを、

```text
音 → 作る
```

ではなく、

```text
音響空間 → モデルを当てはめる
```

に変えると思います。

例えば母音なら、

```text
          F2
           ↑
       i   |   u
           |
           |
       e   |   o
           |
           a
           └────→ F1
```

という既知の空間があります。

ここに自然音声corpusを分析して分布を作ります。

```text
/a/
mean F1
variance F1
mean F2
variance F2
...
```

そして synthesizer がこの領域に入れば合格。

つまり、

```text
人間:
「/a/に聞こえるまで調整」

↓変更

機械:
「/a/ distributionに入るまで探索」
```

になります。

人間の仕事量は大幅に減ります。

---

# 22. さらに「自然音声の模倣」から「知覚境界の探索」へ

これは研究としてかなり面白い方向です。

例えば、

```text
/a/ ←────────→ /o/
```

の間を連続的に合成します。

ASRや人間に分類させると、

```text
parameter 0.00 → a
0.10 → a
...
0.47 → a
0.48 → o
...
```

という境界が求まります。

すると重要なのは、

```text
「正確な自然音声パラメータ」
```

ではなく、

```text
「/a/として知覚される領域」
```

になります。

これは synthesis parameter space を理解する上で非常に価値があります。

---

# 23. そこで目標を3段階に分ける

このプロジェクトでは「良い音声」という一つの目標にしない方がよいと思います。

私は、

**Stage A — Identification**

> 正しい音素として認識される。

**Stage B — Intelligibility**

> 単語・文章として正確に理解できる。

**Stage C — Naturalness**

> 人間らしく自然である。

に分けます。

Aはかなり自動化できます。

BもASRで相当自動化できます。

Cだけが難しい。

つまり現在、

```text
A + B + C
```

を全部耳でやっている可能性があります。

それを、

```text
A → machine
B → machine
C → human
```

にするだけでも、試聴量が大幅に減るはずです。

---

# 24. 開発ループをこう変えるのがおすすめです

最終的には、こんな構成がかなり理想に近いと思います。

```text
                Target specification
                         │
            ┌────────────┴─────────────┐
            │                          │
     Acoustic targets          phonetic targets
            │                          │
            └────────────┬─────────────┘
                         ↓
                  parameter search
                         ↓
                    synthesizer
                         ↓
                       WAV
                         ↓
      ┌──────────┬───────┼────────┬──────────┐
      ↓          ↓       ↓        ↓          ↓
   Formants    ASR     Phones   Timing    Spectrum
      │          │       │        │          │
      └──────────┴───────┼────────┴──────────┘
                         ↓
                    Error vector
                         ↓
                 automatic optimizer
                         │
                  ┌──────┴──────┐
                  ↓             ↓
               reject        candidate
                                ↓
                            human A/B
                                ↓
                           accepted model
```

この形なら、人間が音声を聞くのは、

> デバッグのたび

ではなく、

> 自動評価を通過した候補だけ

になります。

---

# 結論

今回最も大きな改善になるのは、新しい合成アルゴリズムを探すことよりも、**開発方法そのものを「聴覚による手動調整」から「analysis-by-synthesisによる自動探索」に変えること**だと思います。

特に有望なのは、

**自然音声 → 音響特徴抽出 → 合成 → 差分計算 → パラメータ自動最適化**

というループです。これは研究上も実績があり、VocalTractLab周辺では自然発話からgestural scoreを最適化するところまで実施されています。VTL 2.4自体も、声道形状・声門・肺圧・F0・gestural scoreを操作できる現在進行形の研究環境です。([VocalTractLab][11])

そして、ASRを「音声を作るAI」ではなく**自動テスター**として使うのは、今回の制約とも矛盾せず、かなり大きな効果が期待できます。

私ならこのプロジェクトの次の段階として、合成器そのものより先に **「Speech Synthesis Test Harness」** を作ります。固定テストコーパスを一括合成し、F0/F1/F2/F3・スペクトル・音素認識・WER・duration・alignmentを計測し、変更前後を自動比較するシステムです。そこからさらに optimizer を接続して **「自動的に合成パラメータを探索する synthesis laboratory」** に発展させるのが、このプロジェクトには特に合っていると思います。

この方向をさらに進めると、単なる効率化ではなく、**「AIを使わずに、音声生成器自身を測定・最適化・検証できる開発アーキテクチャ」**という、かなり面白い設計テーマになります。

[1]: https://pubmed.ncbi.nlm.nih.gov/21476670/?utm_source=chatgpt.com "A study of acoustic-to-articulatory inversion of speech by analysis-by-synthesis using chain matrices and the Maeda articulatory model."
[2]: https://github.com/audeering/opensmile-python/blob/main/opensmile/core/config/gemaps/v01b/GeMAPSv01b_core.lld.conf.inc?utm_source=chatgpt.com "opensmile-python/opensmile/core/config/gemaps/v01b/GeMAPSv01b_core.lld.conf.inc at main · audeering/opensmile-python · GitHub"
[3]: https://montreal-forced-aligner.readthedocs.io/en/latest/user_guide/workflows/evaluating_alignments.html?utm_source=chatgpt.com "Comparing and evaluating alignments (mfa compare_alignments) — Montreal Forced Aligner 3.X documentation"
[4]: https://www.isca-archive.org/interspeech_2019/gao19e_interspeech.html?utm_source=chatgpt.com "ISCA Archive - Articulatory Copy Synthesis Based on a Genetic Algorithm"
[5]: https://www.vocaltractlab.de/publications/promon-2013-interspeech.pdf?utm_source=chatgpt.com "Training an Articulatory Synthesizer with Continuous Acoustic Data"
[6]: https://vocaltractlab.de/publications/weitz-2017-essv.pdf?utm_source=chatgpt.com "GESTURE-BASED ARTICULATORY TEXT TO SPEECH SYNTHESIS∗"
[7]: https://www.vocaltractlab.de/index.php?page=news&utm_source=chatgpt.com "VocalTractLab"
[8]: https://vocaltractlab.de/index.php?page=vocaltractlab-examples&utm_source=chatgpt.com "VocalTractLab"
[9]: https://github.com/lostmsu/pink-trombone?utm_source=chatgpt.com "GitHub - lostmsu/pink-trombone: Pink Trombone (vocal cord simulator) implementation in Rust · GitHub"
[10]: https://www.itu.int/ITU-T/recommendations/rec.aspx?id=14283&utm_source=chatgpt.com "ITU-T Recommendation database"
[11]: https://www.vocaltractlab.de/index.php?page=targetoptimizer-about&utm_source=chatgpt.com "VocalTractLab"
