# 日本語非ニューラル知覚資料の適用性監査

固定6経路で現日本語非ニューラル発話を校正できる公開対応資料は確認できず。未知を通過に扱わない。

|候補|結果と不足|一次資料|
|---|---|---|
|VoiceMOS2026|現HTS日本語発話/劣化と対応する公開音声評点・利用条件を検証できない。登録や連絡は実施しない。|[資料1](https://arxiv.org/html/2609.13792v1), [資料2](https://sites.google.com/view/voicemos-challenge/resources)|
|MOS-Bench-SHEET|多言語という表記やコードライセンスを、現在の日本語非ニューラル発話の資格/全資料の利用条件へ転用しない。|[資料1](https://arxiv.org/html/2411.03715v2), [資料2](https://github.com/unilight/sheet), [資料3](https://wenchinhuang.com/sheet/)|
|SingMOS|日本語歌声を日本語発話へ、ニューラル歌唱を非ニューラル発話へ拡張しない。|[資料1](https://arxiv.org/html/2406.10911v2)|
|BVCC|日本語の聴取者属性と音声言語を区別。英語の非ニューラル先例は日本語校正を代替しない。今回原音声取得0。|[資料1](https://zenodo.org/records/10691660), [資料2](https://arxiv.org/html/2411.03715v2), [資料3](https://www.cstr.ed.ac.uk/projects/blizzard/data.html)|
|SOMOS|対応評点があっても英語ニューラル資料であり現在の資格に不足。取得しない。|[資料1](https://zenodo.org/records/7378801)|
|Japanese-HTS-ITTS2018|論文内MOS設定は先例。現在の波形判定器の校正に必要な公開刺激と個別評点の対応、利用条件を確認できない。|[資料1](https://www.isca-archive.org/interspeech_2018/yanagita18_interspeech.pdf)|

新版MOS-Bench/SHEETと2026年資料も照合した。資料の名称・多言語対応・日本語聴取者・別領域の高相関を、日本語非ニューラル発話の資格に置き換えない。これは適用性監査であり、音声hash/評点/判定器を固定した実校正ではない。一次本文のcopy/hashは保存していないため、その限界も残す。

既存未資格MOSの採択利用と同じ資料だけの再探索を凍結。新しい対応公開資料がある時に別契約。現在は独立な非ニューラル生成/音響/内容比較を継続。
