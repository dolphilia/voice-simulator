# 限定YIN型測定の人工範囲検証

6機構信号で独立スカラー差分/累積正規化を照合し、855人工条件の全分母・保留・不通過を保存した。完全YINの全手順再現とは呼ばない。静的/動的は音響周期の式をtruthとし、知覚truthにはしない。

|範囲|窓ms|通過|保留|全件通過|
|---|---:|---:|---:|---|
|static|20|60/105|45|False|
|static|40|105/105|0|True|
|static|80|105/105|0|True|
|dynamic|20|48/96|48|False|
|dynamic|40|96/96|0|True|
|dynamic|80|72/96|24|False|
|boundary|20|59/72|59|False|
|boundary|40|47/72|47|False|
|boundary|80|36/72|36|False|
|unvoiced|20|12/12|12|True|
|unvoiced|40|12/12|12|True|
|unvoiced|80|12/12|12|True|

差分幅N-floor(fs/70)は全lagで固定し、差分幅が選択周期未満なら保留する。動的truthは窓中央の位相導関数で、推定lagに合わせた時刻変更で救済しない。境界窓は全体周期truthがなく、推定保留を要求した。

旧DIO/ACF、旧支持/249欠測、旧判定は変更しない。成功した事前groupだけが人工限定資格であり、HTS音響・短窓の一般資格・知覚自然さを主張しない。同fixtureの閾値救済は封印する。P5未開封・品質未達。

一次資料: [YIN書誌/要旨](https://pubmed.ncbi.nlm.nih.gov/12002874/)、[librosa公式YIN](https://librosa.org/doc/0.11.0/generated/librosa.yin.html)、[aubio公式実装](https://github.com/aubio/aubio/blob/master/src/pitch/pitchyin.c)。著者原論文PDF/出版社本文は取得できず、公式実装の説明と式の範囲で独立実装した。
