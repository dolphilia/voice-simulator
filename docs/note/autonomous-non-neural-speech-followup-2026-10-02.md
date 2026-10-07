# 非ニューラル音声合成：評価再現性と日本語制御の追加検証

2026-10-02。[初回実行報告](autonomous-non-neural-speech-execution-report-2026-10-02.md)に続き、計画の全体完了条件へ向けて実装と実測を追加した。**状態は引き続きinconclusive、品質目標は未達**。4 campaign、台帳レンダー合計2,596。以下の追加処理に最終確認用の人間参照録音は使用していない。

## 進んだ点

- UTMOSv2の推論時の無作為区間抽出を特定し、入力ごとにPython/NumPy/PyTorchの乱数を固定。同一自然音声3件の再評価差がすべて0になった。
- Open JTalkの辞書・規則から12文の読み、モーラ、アクセント句を抽出し、VTLの実行時制御へ接続した。HTS音響生成とニューラルアクセント推定は呼んでいない。
- 4条件×12文×2seed＝96レンダーを実施。すべてE0検査を通過。明瞭性をASRで調べ、悪化する拡張を採用しなかった。
- VTLの共有物理モデルと生成規則を独立bundleへ移出。研究実装・通常bundle・OS制限下bundleの未知文波形が一致した。
- 新campaign用の課題数上限制御と初期化失敗時のロック解放を追加。追加6テストを含む23テストが通過した。

[追加結果の集計](../../research/experiments/autonomous-speech-synthesis/results/ans-vtl-japanese-v2/followup-summary.json)と[テスト記録](../../research/experiments/autonomous-speech-synthesis/results/test-results-23.log)を保存した。既存campaignの凍結コアと結果は変更せず、追加スクリプトのhashを別manifestで記録した。

## 評価器の測定手順を修正

[UTMOSv2 v1.3.0の実装](https://github.com/sarulab-speech/UTMOSv2/tree/v1.3.0)の `dataset/ssl.py` と `dataset/multi_spec.py` は、推論時にも `select_random_start` で区間を選ぶ。前回はこの乱数状態を各入力で固定していなかったため、入力変換への感度と無作為区間の違いが混ざっていた。

同じseedを各入力の直前に再設定し、CPU決定的演算を要求して31推論を行った。自然音声3件×7条件に、別seedでの自然音声6件、DSP/VTLの短文4件を加えた構成である。

| 同一seedでの変換 | 自然音声3件での変化 |
|---|---|
| 同一波形の再評価 | 全件0 |
| 半振幅 | ほぼ0 |
| 5msのずれ | +0.024〜+0.089 |
| 再サンプリング | −0.018〜−0.107 |
| 強いclipping | −2.63〜−3.49 |
| 部分欠落 | −0.63〜−1.62 |

別seedでは自然音声の値に最大約0.49の幅が残った。乱数を固定して再現できることと、抽出区間によらず安定することは別である。また日本語物理合成の人間評点との独立校正はないため、資格は `diagnostic-only` のままとした。以前の値は消さず、測定手順の限界を明記して保持した。

証拠: [固定seed評価](../../research/experiments/autonomous-speech-synthesis/results/evaluator-seeded-v1/evaluation.json)、[事前固定した入力一覧](../../research/experiments/autonomous-speech-synthesis/results/evaluator-seeded-v1/frozen-manifest.json)。上流実装のhashも記録している。

## 日本語前段・時間・アクセント・接触の比較

`japanese_frontend.py` は `run_frontend` / `make_label` のfull-contextラベルをモーラと句へ変換する。12文すべてで解析できたが、未知語を含む任意日本語文の正答率を測ったわけではない。句末アクセント位置のラベルだけでは平板と尾高の区別を完全には検証できず、ここでは句内の高低制御に限定する。辞書の読み・アクセントを人手による正解とは扱わない。

`ans-vtl-japanese-v2` ではF0基準160Hzを固定し、次の4条件を事前登録した。新規文脈4文は最終人間参照群とは別であり、その認識結果も開発診断として扱う。

| 条件 | 変更 | かなCER・全12文 | 既存8文 | 新規4文 |
|---|---|---:|---:|---:|
| baseline | 辞書音素、従来の時間配分、速度0.85 | 51.1% | 44.2% | 56.9% |
| mora | 1モーラ0.20秒、子音/母音へ配分 | 47.9% | 55.8% | 41.2% |
| accent | moraに辞書の句内高低±1.5半音を追加 | 62.8% | 72.1% | 54.9% |
| accent-tap | accentの側音指令を短い舌尖閉鎖へ置換 | 73.4% | 86.0% | 62.7% |

faster-whisper baseに正解文のヒントを渡していない。漢字表記差を減らすため、読み正規化後のCERを併記した。自然参照3文のかなCERは10.0%。別文集合・少数文であり、自然参照への非劣性が成立したという結果ではない。

moraは全体値では改善したが既存8文で悪化したため、保護条件を満たす改善とは判断しない。accentとaccent-tapも採用しない。後から閾値や文集合を変えて合格にしていない。前回の39.5%は異なる入力表記・音素列を使った8文の値であり、今回の51.1%と直接差を取らない。

[音響診断](../../research/experiments/autonomous-speech-synthesis/results/ans-vtl-japanese-v2/prosody-diagnostic.json)では、184区間中176区間でF0を比較でき、標的からの相対誤差中央値は4.03%、5%以内は126区間だった。これは知覚的なアクセント正答率ではない。残る8区間は欠測/不確実として分母から消していない。

## 「接触指令」と実際の閉鎖の差

28ms・時定数7msの舌尖閉鎖指令を8か所に入れたが、同時刻の音量が親条件より下がったのは4か所だけだった。そこで、VTL公式API `vtlGesturalScoreToTractSequence` と `vtlTractToTube` を使い、保存したジェスチャから約2.49ms刻みの声道断面を再計算した。

切歯の0〜3cm後方の管区間で、診断上のほぼ閉鎖を0.01cm²以下とすると、親の側音条件は0/8、短い閉鎖指令は1/8だった。指令にclosureと書いただけでは、短い時間内にモデルが閉鎖へ到達しないことが分かった。閾値は幾何診断であり、日本語弾音の正解境界ではない。

次は指令継続長・時定数・開始時刻を**音声探索の前に幾何で校正**する。閉鎖へ到達する条件が確認できるまでは、音量やASR点数だけを使って接触モデルの完成を宣言しない。[断面診断の全結果](../../research/experiments/autonomous-speech-synthesis/results/ans-vtl-japanese-v2/tap-geometry-diagnostic.json)を保存した。

## VTLの独立生成

[研究用bundle](../../research/experiments/autonomous-speech-synthesis/results/vtl-bundle-v2/README.md)には、生成コード、VTLのarm64 dylib、全発話で共有するJD3声道/音素標的、来歴とライセンスだけを含める。参照録音、AI重み、発話辞書、保存済み発話軌跡は含めない。辞書前段は研究側にあり、bundleはかな/明示音素と明示アクセントを受ける。現版は160Hz・0.20秒/モーラの限定された研究実装である。

未知入力「あたらしいちずをひろげる」について、研究実装・通常bundle・OS隔離bundleのfloat64波形hashがすべて `e2171a48907d538a712693f52d6e0496ecee81333a264f80776ce9abfe0aafdb` で一致。参照ファイル・AI重み・ネットワークの拒否probeも3件すべて通過。OS側のネットワーク拒否はCライブラリにも適用される。通常実行RTFは1.67、隔離時は2.39で、現在の条件ではリアルタイムより遅い。

初回は外側sandboxから追加sandboxを起動できず、`sandbox_apply: Operation not permitted` で失敗した。必要な起動権限で同じ拒否プロファイルを適用し直し、成功した。これは自動承認レビューによる却下ではない。

[一致検証](../../research/experiments/autonomous-speech-synthesis/results/vtl-isolation-v2/verification.json)、[拒否probe](../../research/experiments/autonomous-speech-synthesis/results/vtl-isolation-v2/denial-probes.json)、bundle内manifestとGPLライセンスを保存した。品質未資格のため、既定音や完成版には採用しない。

## 運用修正と残る条件

`campaign_v2.py` は、開始前と試行ごとの両方で異なるP3/P4課題数を制限する。失敗や中断の予約も残すため、再開して課題数を増やす抜け道を作らない。新campaignは12/40課題で予算内。初期化中に版不一致が起きたときのロックファイルも解放する。初回campaignの116課題という逸脱は消していない。

4 campaignのうち今回の96レンダーを追加し、累計2,596。P1、テスト、31回のUTMOS、ASR、幾何診断、bundle再生成は別証拠であり、この台帳数には含めない。6 campaign・48時間・40GBの上限を引き上げていない。

残る主要条件は、P2の実際の自由適合と共有制御の差、日本語子音の成立、保護条件を含めた明瞭性の改善、独立したE1/E2資格、条件が整ってから一度だけ行う最終確認である。今回はこれらの条件を完了扱いにしていない。

再現コマンドは[実験READMEの追加検証](../../research/experiments/autonomous-speech-synthesis/README.md#追加検証v2)を参照。既存の結果を上書きせず、旧結果と新しい測定手順を区別して残す。
