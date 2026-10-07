# ニューラル支援研究：残る評価条件の再検証

2026-10-02。[pilot報告](neural-assisted-non-neural-speech-pilot-result-2026-10-02.md)の後続調査。元の品質条件を変更せず、生成・AI評価を追加しない範囲で、公開資料と局所測定を点検した。無人方針は維持している。

**新しい品質資格は取得できなかった。一方、局所測定に採用してはいけない方法を外部音声で特定し、次の機構研究に必要な資料を具体化した。** ファイルの存在だけで完了扱いしない[22項目の要件監査](../../research/experiments/neural-control-distillation/results/nas-pilot-20261002-v1/post-pilot/requirements-audit-v2.json)も保存した。

## 知覚評価の資料

[TTSDS2の聴取評点資料](https://huggingface.co/datasets/ttsds/listening_test)は英語である。[MOS-Benchの公式一覧](https://wenchinhuang.com/sheet/mos-bench/)でも、日本語を含むSingMOSは歌声として分類される。これらを日本語のHMM/VTL発話にそのまま適用する根拠は確認できなかった。

日本語の主観実験も点検した。[Kurihara・Sano（2024）](https://www.isca-archive.org/interspeech_2024/kurihara24_interspeech.pdf)のOpen JTalk比較は前段の比較で、音響側はFastSpeech2とParallel WaveGANである。比較名だけから古典HMM音源のMOSと解釈できない。[Yanagitaら（2018）](https://www.isca-archive.org/interspeech_2018/yanagita18_interspeech.pdf)は日本語HMM系の増分合成と人手評点を報告するが、今回確認した本文では、発話別の音声と個票の対応付き配布を確認できなかった。条件平均MOSを個別音声へ転記したり、今回のMei音源の正解点にしたりしない。

対象方式・日本語・入力範囲・推定器との独立性を満たす資料が不足している。これは調べた候補についての結論であり、適格資料が世界中に存在しないという主張ではない。取得状況と出典は[公開資料監査](../../research/experiments/neural-control-distillation/results/nas-pilot-20261002-v1/post-pilot/public-evidence-review.json)にある。

## VOTの外部信号検証

[Haskins Laboratoriesが公開するVOT連続体](https://www.haskinslaboratories.org/vot)のWAV 30件を取得した。音声は10 kHzの人工的な唇音系列で、公称VOTは−150〜+150 ms。+140 msが欠け、複数ファイルに約5 msの録音差の注記がある。再配布許諾の明記は未確認のため、研究比較に限定し、最終bundleには含めない。生成した候補音声でも、日本語の自然音声評点資料でもない。

測定器のコードと条件を結果閲覧前に固定した。25 ms窓・1 ms刻みで、70〜450 Hz相当の正規化自己相関と高域エネルギー変化から周期性開始・放出候補を取り、その時差を公称値と比べた。15 msは窓幅と資料注記に基づく工学診断用の幅で、知覚上の許容幅ではない。

|外部系列|件数|絶対誤差の平均|最大誤差|15 ms以内|
|---|---:|---:|---:|---:|
|正のVOT|14|63.9 ms|136.0 ms|3/14|
|0 ms|1|16.0 ms|16.0 ms|0/1|
|負のVOT|15|26.1 ms|37.0 ms|0/15|

**この候補測定器は不通過であり、生成器の採否には使わない。** エネルギー立上りを口腔の放出と同一視できず、周期性の窓にも境界のぼけがある。ファイル名の公称値も人手で再測定した正解境界とは異なる。同じ30件を見ながら閾値を調整して資格を得たことにはしない。[固定条件と詳細結果](../../research/experiments/neural-control-distillation/results/nas-pilot-20261002-v1/post-pilot/local-events/summary.json)を保存した。

[AutoVOT公式説明](https://github.com/mlml/autovot)は正のVOTのみの対応とし、対象資料の注釈での学習を推奨する。付属の英語系モデルを日本語の正負VOTの資格へ転用しない。[日本語Paidologos資料](https://talkbank.org/phon/access/Japanese/PaidoJapanese.html)は関連する音声と注釈へのリンクを持つが、実取得先は認証UI用の319 byteのHTMLを返した。成功した音声・注釈ダウンロードとして数えていない。ログインや外部への連絡はしていない。

[Kongら（2012）](https://talkbank.org/phon/access/0docs/kong2012.pdf)は、日本語では有声・無声のVOT分布が重なり、発声開始付近のF0やH1−H2等も区別に関与することを報告している。本研究への示唆は、VOTだけで子音の良否を最適化せず、正負の境界、発声開始時F0、スペクトル傾斜、閉鎖中の振幅を別々に測定・点検することである。既存の教師内部durationやVTL指令時刻は、これらの独立した正解境界として使わない。

## 完了監査と費用

既存pilotの封印1,264ファイルを再ハッシュし、変更がないことを確認した。教師5資産・選択済みモデル・最終bundleのハッシュ、分割24文の非重複、学習完了と監査レンダー開始の時系列、比較120条件・ASR144件、HMM利得修正16条件のE0、各bundleの隔離実行4組も点検した。

達成済みなのは、限定した時間/F0の移行比較、非ニューラル単独実行、再現・来歴・費用の記録である。残る条件は、知覚資格、VOT/局所遷移の測定資格、日本語調音・声質制御の拡張、速度・複数声への一般化、未使用条件による最終品質確認。人工fixtureの判定器テストを、実音声の合格証拠へ昇格していない。

同じcampaignの追記台帳を `post-pilot/ledger.jsonl` に分離し、既存台帳との合算で上限を検査する。旧台帳・旧封印は変更していない。今回の追加候補生成・AI評価は0件で、累計は教師32、レンダー307、AI評価299のまま。追加取得WAVは約0.3 MBの圧縮資料で、全体容量・経過時間は[費用スナップショット](../../research/experiments/neural-control-distillation/results/nas-pilot-20261002-v1/post-pilot/cost-snapshot.json)に記録した。

目標は未達のまま保持する。新しい比較や資格校正を一式実施するには、対象に対応する評点/境界資料と追加の評価枠が必要である。現在の残り1 AI枠で十分な確認ができたとは扱わず、上限・campaign数を自動的に増やさない。
