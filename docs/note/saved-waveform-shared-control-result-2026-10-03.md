# 保存済み実波形から共有制御へ移す比較：部分結果と容量超過

2026-10-03。承認済み[比較案](../plans/saved-waveform-target-shared-control-proposal-2026-10-03.md)を新ID `nas-saved-wave-shared-20261003-v1` で実施した。**17文の目標を再検証して3方式を学習し160波形を生成したが、保存実装の不備で容量350MBを超過したため、単独実行・ASR前に停止した。比較も品質目標も完了していない。**

## 成立した部分と未実施

保存済み63条件のWAV hash、有限性、E0、状態不変、DIO列、固定支持域、MSE、正則化目的を再検証した。逆推定や教師を再生成せず、短10・長7の17文を固定規則で選んだ。訓練は209対象音素区間、16特徴の中心化後rank14。全対象有声音素で中心化・一様縮尺を行い、訓練と実行の集合を一致させた。

直接回帰16係数・ridge10、研究NN（16幅tanh2層・固定500step）、学生回帰16係数・ridge10の3fitを実施した。旧12診断文と新8文、通常／変更、既定／直接／NN／学生の160波形はすべて有限・E0・内部不変を通過した。160生成後、独立実行のsetup予約が容量上限で拒否され、その後の生成・fit・AIは0。単独実行32件と認識320件は未実施である。

## 保存実装の不備と証拠の保全

個別記録の全状態snapshotを集約manifestにも複製し、最後の集約235,490,836 bytesを容量予約せず保存した。実保存量は485,850,405 bytesとなり350,000,000 bytesを超えた。予算確認は次のsetup予約を拒否したが、集約書込そのものを事前に防げなかった。私の実装不備であり、上限内実行とは扱わない。

個別記録・WAV・モデルは保持した。集約をgzipに可逆圧縮し、復元した原文のSHA-256・バイト数が完全一致することを検査してから重複原文を除去した。圧縮集約は51,430,979 bytes、原文SHA-256は `43401db872ae3bfeec9b9e3308136132a10d0887bebd19d7502f51a5ffa7db76`。保全中は原文と圧縮版が共存し、観測ピーク537,281,384 bytesを記録した。圧縮後の容量が上限未満になっても、超過事実を取り消さず追加実行を停止した。

次案用に、保存予定JSONの実バイト数と余裕を先に点検し、状態列を複製せず個別記録のpath/hashを残す検査を用意した。生成器の保存経路へ接続・実行したとは扱わない。

## 得られた音響診断

制御残差の訓練MSEは既定0.804912に対し直接0.445620、NN0.064886、学生0.447843。NNの訓練上の改善は学生へ大部分を移せていない。これだけで波形品質や汎化を認定しない。

次表の旧12文MSEは中心化実波形F0の半音²。欠損のある平均は観測できた文だけの値であり、合格判定には使わない。

|方式|訓練制御MSE|旧12文 通常MSE|旧12文 変更MSE|全40条件の支持域欠損|全体F0／活動長の保護不通過|
|---|---:|---:|---:|---:|---:|
|direct_non_neural|0.445620|8.237943（欠損0）|9.218255（欠損0）|3|1|
|neural|0.064886|6.288359（欠損2）|7.484827（欠損0）|5|15|
|distilled_non_neural|0.447843|8.305410（欠損0）|9.259400（欠損0）|3|0|

既定の旧12文MSEは通常10.232302、変更11.968529。直接と学生は通常／変更それぞれの全体・短・長で低下し、旧12文のMSE計測欠損は0。しかし、新8文には両方式で各3条件の支持域欠損があり、直接は旧1条件でDIO全体F0差5%を超えた。NNは旧通常2文を含む計5条件で支持域欠損があり、15条件で全体指令の保護に不通過だった。

支持域欠損を信号生成失敗と混ぜず、E0が通る実波形でも局所測定条件が通らないことを別記した。区間を削除・補間してMSEを改善せず、全方式を採択・品質認定していない。内容保持・かなCER・ニューラル除去後の単独一致は未評価で、成功とも失敗とも推定しない。

## 終了監査と残る作業

監査時3278.124秒、保全後301,870,254 bytes。台帳はsetup4・fit3・render160・audit2、AI0・教師0・取得0。予約済みジョブはすべて終了した。独立実行setupの容量拒否は予約前なので、台帳の失敗ジョブと分けて拒否記録を保存した。容量遵守は明示的にfalseとした。

旧15封印・7,549ファイル、現160個別記録とWAV、3モデルのhash・内部不変を検証した。旧資産を変更せず、未終了プロセス0で封印する。封印後の追加処理拒否も検査する。

[未完評価の次案](../plans/saved-shared-control-evaluation-followup-2026-10-03.md)は、現モデル・160波形を再利用し、単独32生成と最大320AIだけを新枠1時間・100MBで実行する案。fit・逆推定・診断波形再生成・教師・取得は0。保存形式を修正して先に容量を予約し、超過防止を実行前に検査する。現在のcampaignを再開していない。

日本語非ニューラルの知覚資格、局所閉鎖・開放・摩擦・声質、未知文の一般品質、独立最終確認は引き続き未達である。

- [目標検証](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/saved-wave-audit.json)・[固定訓練](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/training-contract.json)
- [3モデル比較](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/model-comparison.json)・[部分音響集計](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/partial-summary.json)
- [可逆圧縮の証跡](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/lossless-archive.json)・[圧縮集約](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/render-manifest.json.gz)
- [終了監査](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/completion-audit-v2.json)・[費用と超過記録](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/cost-audit-v2.json)・[成果封印](../../research/experiments/saved-waveform-shared-control/results/nas-saved-wave-shared-20261003-v1/artifact-seal.json)
