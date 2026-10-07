# 有声補完・非周期成分2×2の比較結果

新16文×2条件×5方式の160比較を完了。
全160通常/隔離組とCLI4件の波形hashが一致。二ASRは各160件。
最終音源は文章から計算する非ニューラルHTS/WORLD。

- native: 指定F0・支持通過 0/32、E0 32/32、研究資格 False。
  whisper: 誤り52/644、native誤り52。悪化/欠測群: なし。
  reazon: 誤り14/644、native誤り14。悪化/欠測群: なし。
- calibrated: 指定F0・支持通過 18/32、E0 32/32、研究資格 False。
  whisper: 誤り43/644、native誤り52。悪化/欠測群: both/group6, neutral/group4, neutral/group6, higher/group6。
  reazon: 誤り23/644、native誤り14。悪化/欠測群: both/all, both/short, both/long, both/group0, both/group2, neutral/group0, higher/all, higher/short, higher/long, higher/group0, higher/group2。
- voicing: 指定F0・支持通過 26/32、E0 32/32、研究資格 False。
  whisper: 誤り49/644、native誤り52。悪化/欠測群: both/group4, both/group6, neutral/group4, neutral/group6, higher/group5, higher/group6。
  reazon: 誤り21/644、native誤り14。悪化/欠測群: both/all, both/short, both/long, both/group0, both/group2, both/group4, neutral/group0, higher/all, higher/short, higher/long, higher/group0, higher/group2, higher/group4。
- aperiodicity: 指定F0・支持通過 18/32、E0 32/32、研究資格 False。
  whisper: 誤り46/644、native誤り52。悪化/欠測群: both/group4, both/group6, neutral/short, neutral/group4, neutral/group6, higher/group6。
  reazon: 誤り22/644、native誤り14。悪化/欠測群: both/all, both/short, both/group0, both/group2, neutral/group0, higher/all, higher/short, higher/group0, higher/group2。
- combined: 指定F0・支持通過 26/32、E0 32/32、研究資格 False。
  whisper: 誤り51/644、native誤り52。悪化/欠測群: both/group0, both/group4, both/group6, neutral/group0, neutral/group4, higher/group0, higher/group5, higher/group6。
  reazon: 誤り21/644、native誤り14。悪化/欠測群: both/all, both/short, both/long, both/group0, both/group2, both/group4, neutral/group0, higher/all, higher/short, higher/long, higher/group0, higher/group2, higher/group4。

未達: 日本語非ニューラル知覚資格、独立P5確認。保護最終確認は未開封。
一時領域は自分の所有manifestだけを削除し、不存在を確認。時間・回数・累積書込は返却しない。
有声補完: 支持欠損16→1区間、AP半減: 支持回復0。全候補は内容/ピッチの保護条件不通過で不採択。
実生成attempt646、保守予約課金806。生成前停止1回・生成後受渡停止1回・監査保存前拒否1回を保持。
詳細JSONは外部、全33群と判定はaggregate-summary.json。
個別実験の終了を全体品質達成へ読み替えない。
