# Holdout知覚検証と総合判断

検証日: 2026-08-13

Developmentで未提示だった6候補を、2つのholdout話者のreferenceに対して匿名評価した。重複1件を加えた7提示の回答は完全で、重複の5軸平均絶対差は0.0だった。Developmentの入力、暫定重み、holdout benchmark、提示keyは回答前にSHA-256で固定し、結果を見た後に変更していない。

## 人間評価

| 軸 | 結果 |
| --- | --- |
| 音素同一性 | 全6候補が1 |
| 自然さ | 全6候補が1 |
| 明瞭さ | 4〜5 |
| 声質 | 全6候補が1 |
| 参照類似性 | spectral-match 3件はすべて2、original 3件はすべて3 |

自由記述は一貫して「楽器音に聞こえる」とした。候補は明瞭だが、母音または人間音声としては成立していない。originalはreferenceのニュアンスや成分に近いという弱い手掛かりがあり、spectral-matchより参照類似性が1段高かった。

## 固定モデルの独立検証

| 軸 | Holdout Spearman | 1〜5換算MAE | 判定 |
| --- | ---: | ---: | --- |
| naturalness | 算出不能（全回答1） | 2.700 | 不合格 |
| phoneme_identity | 算出不能（全回答1） | 2.766 | 不合格 |
| target_similarity | 0.293 | 1.218 | 不合格 |
| voice_quality | 算出不能（全回答1） | 2.611 | 不合格 |
| clarity | 校正対応なし | — | 総合化対象外 |

採用基準は、順位相関0.3以上かつ1〜5換算MAE 1.0以下だった。どの校正軸も基準を満たさなかった。

## 採否判断

暫定総合判断モデルは棄却する。`activated=false`、`eligible_for_adoption=false`を確定し、正式な`aggregate`は`null`のまま維持する。

これはカテゴリ別自動評価を無効にする判断ではない。次は引き続き有用である。

- signal integrity gate
- F0、formant、スペクトル、時間差などの生測定値
- Target similarityのカテゴリ別診断
- 既知変形fixtureと回帰検査
- candidateのPareto絞り込み

一方、現在のHuman-likeness envelopeと暫定重みを自然さ・声質の代理には使わない。

## 得られた研究上の結論

1. フォルマントやスペクトル包絡の近さだけでは、人間の発声らしさを表現できない。
2. 現行の音源品質指標は、生成音を人間評価より約2.6〜2.8段階も高く見積もった。
3. spectral-matchは数値上のスペクトルTargetを改善しても、holdoutでは参照類似性がoriginalより低かった。指標ハックまたは単一参照への過適合の実例である。
4. 人間音声は強いノイズが加わっても人間由来と認識された一方、定常的な調波・formant合成は明瞭でも楽器音に聞こえた。
5. 今後の最優先診断は、短時間スペクトル重心、RMS包絡、F0、周期性の微細変動と、ノイズが周期音へ結合する構造である。
6. 次版の評価器は、同じholdout回答で再調整せず、新しいdevelopment試聴で校正し、別の未使用holdoutで検証する必要がある。

## 再現証拠

- responses SHA-256: `f9e6f66b976405bcbef1fa168f39a597e02c7ed6ba685c3c91b1727cced20496`
- analysis SHA-256: `bf6f3f4fd3be64c64340c1970a9fb23e4ab025cef6b372c54df94b420ccc7c32`
- validation SHA-256: `4612d9bfb1e7afce826283e66ada73f0596ac6db70311ad08ebffc10278b404a`
