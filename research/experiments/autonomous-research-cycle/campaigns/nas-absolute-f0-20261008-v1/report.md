# 絶対F0校正の比較結果

新16文×2条件×2方式の64比較を完了。
全64通常/隔離組とCLI4件の波形hashが一致。二ASRは各64件。
最終音源は文章から計算する非ニューラルHTS/WORLD。

- native: 指定F0・支持通過 0/32、E0 32/32、研究資格 False。
  whisper: 誤り52/730、native誤り52。悪化/欠測群: なし。
  reazon: 誤り32/730、native誤り32。悪化/欠測群: なし。
- calibrated: 指定F0・支持通過 20/32、E0 32/32、研究資格 False。
  whisper: 誤り58/730、native誤り52。悪化/欠測群: both/all, both/short, both/group1, both/group3, both/group6, both/group7, neutral/all, neutral/short, neutral/group3, neutral/group4, higher/all, higher/short, higher/long, higher/group1, higher/group6, higher/group7。
  reazon: 誤り32/730、native誤り32。悪化/欠測群: both/short, both/group5, both/group6, neutral/all, neutral/short, neutral/group3, neutral/group6, higher/group5。

未達: 日本語非ニューラル知覚資格、独立P5確認。保護最終確認は未開封。
一時領域は自分の所有manifestだけを削除し、不存在を確認。時間・回数・累積書込は返却しない。
個別実験の終了を全体品質達成へ読み替えない。
