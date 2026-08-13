# 発声開始 development 自動解析

この結果は知覚自然さの判定ではなく、試聴前の刺激生成と軌道設計に使う。

- 解析数: 2
- 話者数: 1
- 境界信頼度中央値: 1.000

| sample | speaker | activity ms | periodicity ms | stable pitch ms | stable source ms | stable vowel ms | confidence |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| onset-kaneda-modal-a | 金田朋子 | 445.0 | 480.0 | 510.0 | 510.0 | 540.0 | 1.00 |
| onset-kaneda-dark-a | 金田朋子 | 395.0 | 465.0 | 535.0 | 575.0 | 605.0 | 1.00 |

## 制約

- 同一話者の2件は別テイクではなく、UTAUの音源表情差を含む。
- stable vowel境界は初期版の候補であり、formant軌道のcoverageと併記する。
- onset-holdoutはこの解析に含めていない。
