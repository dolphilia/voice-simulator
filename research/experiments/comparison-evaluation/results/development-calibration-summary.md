# Development知覚校正の固定記録

固定日: 2026-08-13

初回生成候補6件と校正アンカー8件、合計14ユニーク対象の人間評価をdevelopment benchmarkへ対応させた。各軸は1〜5のうち4段階以上を使用し、2つのアンカー重複と1つの初回重複は全軸で完全一致した。

## 暫定対応

| 知覚軸 | 採用候補 | Spearman | p値 |
| --- | --- | ---: | ---: |
| naturalness | source_voice_quality Target | 0.745 | 0.0023 |
| naturalness | pitch_voicing Target | 0.700 | 0.0053 |
| phoneme_identity | source_voice_quality Target | 0.727 | 0.0032 |
| phoneme_identity | resonance Target | 0.537 | 0.0474 |
| target_similarity | source_voice_quality Target | 0.733 | 0.0029 |
| target_similarity | pitch_voicing Target | 0.671 | 0.0087 |
| voice_quality | pitch_voicing Target | 0.766 | 0.0014 |
| voice_quality | source_voice_quality Target | 0.733 | 0.0029 |
| voice_quality | spectral_timbre Human-likeness | 0.533 | 0.0496 |

clarityは校正gateを通る対応がなく、総合化対象にしない。

## 解釈上の注意

- 相関は1評価者・14対象の探索結果であり、因果関係を示さない。
- 人間referenceと加工アンカーが尺度の端点を作っているため、近い生成候補内の細かな順位性能とは別である。
- pitch/voicing得点が自然さと対応したのは、人間録音と単純周期音を分離した影響を含む。
- Human-likeness envelopeよりTarget得点が多く残ったため、現在の人間分布正規化が知覚自然さを十分表しているとは言えない。
- 暫定重みはholdout検証前には採用しない。正式なscorecardは引き続き`aggregate=null`とする。

入力・出力ハッシュは`listening-sessions/development-calibration-lock.json`へ固定した。holdoutの結果が悪くてもdevelopmentへ戻って重みを変更しない。
