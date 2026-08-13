# 発声開始 development 自動解析

この結果は知覚自然さの判定ではなく、試聴前の刺激生成と軌道設計に使う。

- 解析数: 6
- 話者数: 3
- 境界信頼度中央値: 1.000

| sample | speaker | activity ms | periodicity ms | stable pitch ms | stable source ms | stable vowel ms | confidence |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| onset-maoto-modal-a | maoto | 395.0 | 410.0 | 425.0 | 425.0 | 455.0 | 1.00 |
| onset-maoto-soft-a | maoto | 410.0 | 410.0 | 420.0 | 440.0 | 470.0 | 1.00 |
| onset-mizuhara-modal-a | 水原薫 | 395.0 | 420.0 | 455.0 | 455.0 | 485.0 | 0.82 |
| onset-mizuhara-light-a | 水原薫 | 365.0 | 390.0 | 390.0 | 845.0 | 875.0 | 1.00 |
| onset-sanada-modal-a | 真田アサミ | 405.0 | 445.0 | 565.0 | 565.0 | 595.0 | 1.00 |
| onset-sanada-boyish-a | 真田アサミ | 405.0 | 435.0 | 505.0 | 505.0 | 535.0 | 1.00 |

## 制約

- 同一話者の2件は別テイクではなく、UTAUの音源表情差を含む。
- stable vowel境界は初期版の候補であり、formant軌道のcoverageと併記する。
- onset-holdoutはこの解析に含めていない。
