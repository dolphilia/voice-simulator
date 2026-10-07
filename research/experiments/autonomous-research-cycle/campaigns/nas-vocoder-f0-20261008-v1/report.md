# 同一3streamのvocoder×LF0比較結果

新16文×2条件×6方式の192比較を完了。
全192通常/隔離組とCLI4件の波形hashが一致。二ASRは各192件。
最終音源は文章から計算する非ニューラルHTS/WORLD。

- native: 指定F0・支持通過 0/32、E0 32/32、研究資格 False。
  whisper: 誤り50/712、native誤り50。悪化/欠測群: なし。
  reazon: 誤り35/712、native誤り35。悪化/欠測群: なし。
- calibrated: 指定F0・支持通過 12/32、E0 32/32、研究資格 False。
  whisper: 誤り41/712、native誤り50。悪化/欠測群: both/group5, both/group6, neutral/group6, higher/group5。
  reazon: 誤り32/712、native誤り35。悪化/欠測群: both/long, both/group2, both/group3, both/group6, neutral/long, neutral/group6, higher/all, higher/long, higher/group2, higher/group3, higher/group5。
- voicing: 指定F0・支持通過 24/32、E0 32/32、研究資格 False。
  whisper: 誤り47/712、native誤り50。悪化/欠測群: both/short, both/group0, both/group5, both/group6, neutral/all, neutral/short, neutral/group6, higher/short, higher/group0, higher/group5。
  reazon: 誤り28/712、native誤り35。悪化/欠測群: both/long, both/group3, both/group6, neutral/long, neutral/group3, neutral/group6, higher/long, higher/group3, higher/group5。
- hts_native: 指定F0・支持通過 0/32、E0 32/32、研究資格 False。
  whisper: 誤り49/712、native誤り50。悪化/欠測群: both/short, both/group5, both/group6, neutral/all, neutral/short, neutral/group2, neutral/group5, higher/group5, higher/group6。
  reazon: 誤り39/712、native誤り35。悪化/欠測群: both/all, both/long, both/group3, both/group5, both/group7, neutral/all, neutral/long, neutral/group3, higher/all, higher/long, higher/group3, higher/group5, higher/group7。
- hts_calibrated: 指定F0・支持通過 11/32、E0 32/32、研究資格 False。
  whisper: 誤り44/712、native誤り50。悪化/欠測群: both/short, both/group0, both/group5, both/group6, neutral/short, neutral/group5, neutral/group6, higher/short, higher/group0, higher/group5, higher/group6。
  reazon: 誤り42/712、native誤り35。悪化/欠測群: both/all, both/long, both/group2, both/group3, both/group6, neutral/long, neutral/group3, neutral/group6, higher/all, higher/short, higher/long, higher/group2, higher/group3, higher/group5, higher/group6。
- hts_voicing: 指定F0・支持通過 25/32、E0 32/32、研究資格 False。
  whisper: 誤り52/712、native誤り50。悪化/欠測群: both/all, both/short, both/group5, both/group6, both/group7, neutral/all, neutral/short, neutral/group5, neutral/group6, higher/short, higher/group5, higher/group6, higher/group7。
  reazon: 誤り35/712、native誤り35。悪化/欠測群: both/long, both/group1, both/group3, both/group6, neutral/long, neutral/group3, higher/all, higher/long, higher/group1, higher/group3, higher/group5, higher/group6。

未達: 日本語非ニューラル知覚資格、独立P5確認。保護最終確認は未開封。
一時領域は自分の所有manifestだけを削除し、不存在を確認。時間・回数・累積書込は返却しない。
支持欠測: WORLDの校正26区間→補完5区間、HTSの校正24区間→補完2区間。全候補は不採択。
実生成584・DSP968・二ASR384。推論前のASR開始拒否を含む技術再試行3件を保持。
詳細個票は外部、全33群・要因差・資格はaggregate-summary.json。
次: pitch-measurement-v1を生成前登録し、周期既知の短区間・基本波欠損・母音共鳴・雑音の固定256条件と16否定条件でDIO/Harvest/ACFの支持欠測を検証する。旧192比較へ同じ測定器を診断として適用し、旧判定は変更しない。
個別実験の終了を全体品質達成へ読み替えない。
