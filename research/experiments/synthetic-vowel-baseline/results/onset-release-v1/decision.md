# onsetベースラインv1の確定

G40-b9-gain-attackをonsetベースラインv1として確定する。

確定構成:

- 持続部: B9-corrected-subtle-variation
- 開始部: 40 msの正弦二乗gain attack
- aspiration: 不使用
- F0安定化: 不使用

根拠:

- O0対G40の2/2提示でG40の開始がより自然
- O0対G40の隠し重複一貫性100%
- G40対G80でG40が優位
- G40の全提示で `/a/` yes・人声yes・artifactなし
- aspirationはseed再現性の事前条件を不通過
- F0安定化は追加効果が`SAME`

H1の反証は維持する。G40は人声性の成立要因ではなく、合格済みB9に対する開始自然さの副次改善である。
