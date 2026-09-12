# 計画書: 母音立ち上がり音源モデルの研究と統合

作成日: 2026-08-25

状態: 停止条件成立・H1反証・S系列中止

実施メモ（2026-08-25）:

- `checkpoint-wizard-v1` の17/17提示を完了し、hashと回答validatorに合格
- `UNSURE` 0、外乱0、隠し重複の評価軸一貫性87.5%
- H1は現刺激では不支持だが、0.55秒対0.8秒の長さと終端処理が交絡
- 長さ・端点・定常部音量を統制した再監査は、人間らしさ8/8で `SAME`、開始自然さ4/8でonset文脈ありが選択された
- H1は「データ不足を伴う不支持」、開始自然さへの限定効果は残ると判定
- JVS 2話者の追試でもonset文脈が人間らしさで選ばれた例は0/4
- 統制比較合計12件はonset文脈0、定常部のみ1、`SAME` 11でH1を反証
- 停止規則に従いS系列を中止。holdoutは未開封のまま維持
- 次工程を [`完全生成母音ベースラインの成立回復`](./synthetic-vowel-baseline-recovery-plan.md) へ移行

関連資料:

- [`発声開始と非定常性の研究計画`](./phonation-onset-and-nonstationarity-research-plan.md)
- [`人間らしい母音立ち上がりの合成方針`](../note/phonation-onset-synthesis-direction-review.md)
- [`ブラインド試聴CLIウィザード`](./listening-wizard-plan.md)
- [`phonation-onset-nonstationarity 実験`](../../research/experiments/phonation-onset-nonstationarity/README.md)

## 1. 当初決定（停止済み）

以下はH1判定前に固定した当初案である。2026-08-25に停止条件が成立したため、四状態モデルとS系列は実装しない。

発声開始を、単一のゲイン包絡ではなく、呼気、声門内転、周期振動の成立、母音調音の成立が時間差を伴って進む過程としてモデル化する。

主方式は、周期単位で動作する四状態のパラメトリック状態遷移モデルとする。

```text
airflow
  -> adduction
  -> coherence
  -> source-quality establishment
  -> articulation
```

声門音源は、現行倍音音源、時変LF音源、必要な場合のみ自励振動モデルの順で比較する。物理モデルは既定解にせず、簡易方式で人間開始部の効果を移せない場合、または少数の物理パラメータで複数の観測軌道を説明できる場合にだけ採用候補とする。

既存の `phonation-onset-nonstationarity` 実験は上書きも置換もしない。既存の候補音声と13ユニーク比較を維持したまま、未回答段階で試聴CLIウィザード用セッションへ移行する。ウィザードで第1試聴を完了し、その知覚結果を後継研究の開始条件とする。

## 2. 目的

最終目的は、人間音声断片や学習済み音声生成モデルを最終音源に使わず、人間の発声に近いと判断される立ち上がりを持つ母音音声を生成することである。

この計画では、次を達成する。

1. 人間音声の開始部が知覚上寄与するかを、既存の凍結刺激で判定する
2. 発声開始中の時間変化を、フレーム単位と周期単位で測定する
3. 複数の観測軌道を四状態の低次元モデルへ写像する
4. 現行C6、四状態モデル、時変LF、周期成立、結合aspirationを段階的に比較する
5. 必要な場合だけ自励振動モデルを比較する
6. `/a/` で選択した規則を `/i/ /u/` と未使用話者へ移す
7. onsetモデルを固定した後、持続部非定常モデルとWeb waveguideへ統合する

## 3. 対象外

初期実行では次を対象外とする。

- 録音音素、開始波形、声門波形の再生・連結
- granular合成を最終音源にすること
- neural vocoderや生成AIを最終生成器にすること
- 特定話者の声紋や話者同一性の再現
- 子音を含む一般発話
- 感情、歌唱、声区遷移の包括的再現
- 3D流体構造連成を最初から実装すること
- 自動指標だけで自然さを採否すること

人間音声と逆フィルタリング結果は、区間切除による仮説検証、特徴測定、パラメータ範囲の推定に使用できる。ただし、完全生成候補へ波形断片を残さない。

## 4. 現在地

### 4.1 完了済み

既存研究では次が完了している。

- H1〜H6の事前契約
- onset-development 6件、checkpoint 2件の解析
- onset-holdoutの未開封維持
- 人間音声内A0〜A6刺激
- 完全生成C1〜C7とformant除去対照
- signal / splice gate
- 13比較と重複2比較、計15提示の凍結
- 回答validatorと分析器

### 4.2 未完了

- 第1試聴の回答
- H1、H3〜H6の知覚的分類
- onset-holdoutの開封
- 通常発声等の別系統リファレンス追加
- 周期単位解析v2
- S系列の後継合成器
- onsetモデルと持続部モデルの統合

### 4.3 現行結果の扱い

developmentで得たonset duration中央値110 ms、F0、周期性、HNR、formant等の探索値は、候補範囲とfixtureにだけ使う。人間一般の既定値や採用モデルの正解値にはしない。

現行 `stable_vowel_onset` は `stable_source_onset` の30 ms後に置いた候補である。後継モデルのformant軌道を決める前に、実際のformant安定化に基づく境界へ更新する。

## 5. 証拠の優先順位

| レベル | 証拠 | 用途 |
| --- | --- | --- |
| E0 | signal integrity、再現性、操作成立 | 試聴へ出せるか判断 |
| E1 | 人間音声内の切除・ループ比較 | onset仮説の因果的確認 |
| E2 | 完全生成音のablation試聴 | 生成要因の採否 |
| E3 | 未使用話者・母音のholdout | 一般化確認 |
| E4 | 複数評価者の知覚結果 | 人間一般への主張 |

自動特徴距離、波形相関、スペクトル距離はE0に属する。自然さや人間らしさの代理にはしない。

## 6. 仮説

既存H1〜H6を変更せず、後継研究では次を追加する。

| ID | 仮説 | 主比較 | 反証条件 |
| --- | --- | --- | --- |
| N1 | 複数時定数の四状態モデルは単一smoothstepより自然な開始を作る | S1対S0 | S1が複数刺激でS0を上回らない |
| N2 | 時変声門パルス形状は静的倍音音源より寄与する | S2対S1 | S2がS1を上回らない |
| N3 | 周期単位の振動成立は付加ノイズ近似より寄与する | S3対対応対照 | 開始自然さ・発声らしさに差がない |
| N4 | 声門状態と結合したaspirationは独立ノイズより寄与する | S4対独立ノイズ対照 | S4が上回らない、またはartifactが増える |
| N5 | 自励振動モデルは簡易モデルより知覚または一般化で優れる | S5対S4 | 品質が上がらず複雑さだけ増える |

各仮説は支持、限定支持、反証、未判定のいずれかに分類する。1評価者の結果はプロジェクト内の実装判断に限定する。

## 7. 合成条件

| 条件 | 内容 | 導入時期 |
| --- | --- | --- |
| S0 | 現行C6を後継rendererで再現 | 必須 |
| S1 | 四状態、複数時定数、現行に近い倍音音源 | 必須 |
| S2 | S1に時変LF音源を追加 | 必須 |
| S3 | S2に周期単位のcoherence成立を追加 | N2評価後 |
| S4 | S3にadduction連動aspirationを追加 | N3評価後 |
| S5 | 二質量または簡易body-cover音源 | 条件付き |

S1〜S4は、追加順の比較だけでなく、一要因除去と対応対照を作る。S5はS4までの結果が着手条件を満たした場合だけ実装する。

## 8. 四状態モデル

### 8.1 状態

| 状態 | 範囲 | 意味 |
| --- | ---: | --- |
| `airflow(t)` | 0〜1 | 呼気駆動の成立度 |
| `adduction(t)` | 0〜1 | 声門閉鎖姿勢の成立度 |
| `coherence(t)` | 0〜1 | 周期振動の成立度 |
| `articulation(t)` | 0〜1 | 母音調音目標への到達度 |

状態ごとに開始時刻、10/50/90%到達時間、曲線形状、overshootを持つ。全状態を同じ補間曲線へ固定しない。

### 8.2 出力パラメータへの写像

```text
airflow
  -> 駆動エネルギー、aspiration可能量

adduction
  -> 声門開口率、閉鎖強度、LF形状、残留息漏れ

coherence
  -> 周期長分散、周期脱落、周期間波形類似度

articulation
  -> F1/F2/F3、bandwidth、声道損失

airflow × adduction × coherence
  -> 有声音振幅

airflow × residual_gap(adduction)
  -> aspiration振幅
```

F0は独立LFOにせず、基準張力、衝突・閉鎖状態、低周波ドリフトから導く候補を比較する。

### 8.3 開始様式

初期対象はmodalとbreathyとする。

- modal: airflowとadductionが近接して発振域へ入る
- breathy: airflowが先行し、adductionが遅れ、安定後にも残留声門間隙を持つ

hard/pressed onsetは、modal/breathyでモデル構造が成立した後の拡張とする。

## 9. データとsplit

### 9.1 既存データ

既存UTAUリファレンスは次に使用する。

- CLIと特徴抽出器の開発
- 既存結果の再現
- S系列の初期パラメータ範囲
- checkpointとの接続

UTAUだけから人間一般の分布を決めない。

### 9.2 追加データ

一般化段階では最低限、次を追加する。

- 5話者以上
- `/a/ /i/ /u/`
- modalとbreathy
- 各条件3反復以上
- 発声前300〜500 msを含む
- 同一マイク距離、無加工、低残響
- 可能ならEGG同時計測

### 9.3 split規則

- 話者単位でdevelopment、checkpoint、holdoutを分ける
- 同じ連続収録、同一テイク、同一話者をsplit間で共有しない
- checkpoint回答は候補選択に使用できる
- holdout回答は最終判断にだけ使用する
- holdout開封後にパラメータ規則を変更した場合、新しいholdoutを作る

### 9.4 台帳

入力と派生物に次を保存する。

- sample ID、話者、母音、開始様式、テイク
- 収録条件、権利、利用制限
- split
- ファイルhash
- 境界と信頼度
- 使用した特徴抽出器のversion
- 生成条件、パラメータ、seed
- 人間音声断片を含むか
- export可否

## 10. 解析v2の仕様

### 10.1 境界

次を別々に保存する。

| 境界 | 定義 |
| --- | --- |
| `acoustic_activity_onset` | 背景からエネルギーが持続的に上昇した時刻 |
| `first_oscillation` | 最初の振動候補 |
| `reliable_periodicity_onset` | 信頼できる周期が連続して得られる時刻 |
| `stable_pitch_onset` | F0が安定域へ滞在し始める時刻 |
| `stable_source_onset` | 周期性、周期間類似度、音源声質が安定する時刻 |
| `stable_vowel_onset` | formantが安定域へ滞在し始める時刻 |

ファイル先頭時刻に加え、`acoustic_activity_onset`からの相対時刻と、`first_oscillation`後の周期番号を保存する。

### 10.2 複数解像度

- 活動・過渡検出: 5〜10 ms相当
- F0・周期性: 2〜4周期を確保する可変窓
- formant・スペクトル: 20〜40 ms相当
- 周期単位特徴: pitch-synchronous segment

一つの40 ms窓ですべてを推定しない。

### 10.3 周期単位特徴

- 周期長、周期振幅
- 隣接周期波形相関
- 周期ごとの最大下降速度proxy
- 開口率・閉鎖率候補
- 局所jitter / shimmer
- 周期脱落・弱周期
- 安定域へ入るまでの周期数

### 10.4 逆フィルタリング

逆フィルタリングは任意の補助解析とする。

- 少なくとも二方式を比較する
- 高F0、breathy、soft onsetの合成fixtureで既知誤差を測る
- 方式間不一致と信頼度を保存する
- 推定波形を直接生成物へ使用しない
- open quotient、NAQ、MFDR等は音響的推定値として扱う

### 10.5 解析テスト

既知信号fixtureを作り、次を検証する。

- amplitude ramp
- F0 rampとovershoot
- 減衰するjitter / shimmer
- 周期脱落
- static / moving formant
- static LF / time-varying LF
- aspiration比率の減衰
- 境界の数ms perturbation

## 11. 正規化と自動gate

### 11.1 正規化

- 安定部のRMSまたは知覚ラウドネスを条件間で合わせる
- onsetと安定部の相対エネルギーは維持する
- peak制限は全条件で同じ規則を使う
- 自動正規化後に操作意図が保たれたか再測定する

### 11.2 signal gate

- clippingなし
- DC offset許容範囲内
- NaN / Infなし
- onset前の意図しない発振なし
- click、単一sample peak、明瞭な不連続なし
- aliasing候補が許容範囲内

### 11.3 experiment gate

- 安定部F0、母音、長さ、ラウドネスが比較意図に沿って統制されている
- 操作対象の軌道が意図した方向へ変化している
- 対応対照で非対象パラメータ差が記録されている
- 条件間でseed由来の偶然差だけを比較していない
- 完全生成候補に人間音声断片がない

### 11.4 complexity gate

新しい方式は、追加した状態・曲線・物理パラメータ数を報告する。同等の知覚結果なら、規則が少なく母音やF0へ一般化しやすい方式を選ぶ。

## 12. 試聴設計

試聴の詳細仕様は [`ブラインド試聴CLIウィザード`](./listening-wizard-plan.md) に従う。手作業で音声ファイルを開いたり、`responses.csv`を直接編集したりしない。

### 12.1 評価軸

- 人間の声として聞こえるか
- 実際に発声している感じがあるか
- 開始が自然か
- 持続部が自然か
- 目的母音として聞こえるか
- ノイズ、クリック、楽器音、加工音などのartifactがあるか

### 12.2 形式

- 主比較はA/B対比較
- 質問は原則yes/noへ分解する
- 差を感じた場合だけA/Bを選ぶ
- `SAME`（同程度）と`UNSURE`（判断不能）を分ける
- 5段階confidenceは使用しない
- 質問中にA/Bを何度でも再生できる
- artifactはAとBを別々のyes/noで聞く
- 左右と提示順をseed固定で均衡化する
- 同一比較の非隣接・左右再ランダム化した隠し重複を含める
- 人間原音、既存C1/C6、S0を尺度アンカーにする
- 開始前に音量校正と非採点の操作練習を行う
- 一問ごとに自動保存し、中断・再開できる
- 5提示または10分ごとに休憩を提案する
- 試聴前に候補、hash、分析規則を凍結する

既存の13ユニーク比較と候補音声は維持する。未回答の旧15提示セッションは変更せず保存し、同じ候補から `checkpoint-wizard-v1` を新たに凍結する。

### 12.3 採用条件

候補は次をすべて満たした場合に採用する。

1. onset自然さまたは発声らしさがベースラインより改善する
2. 母音同一性を下げない
3. artifact増加で改善を説明できない
4. 複数話者または複数seedで方向が一致する
5. holdoutで同じ規則の効果が再現する

1評価者での結果は内部設計判断とする。一般化した知覚主張が必要な段階で複数評価者を導入する。

## 13. 実施フェーズ

### フェーズ0: 計画固定

目的:

- 後継研究の範囲、仮説、着手条件、証拠区分を固定する

作業:

- 本計画を保存する
- 既存凍結刺激とlockを変更・削除しないことを確認する
- 現行holdoutが未開封であることを確認する
- 新規S系列のIDと証拠契約を予約する
- 試聴ウィザード計画とquestion routingを固定する

完了条件:

- 本計画が既存研究と相互参照される
- 既存チェックポイントに変更がなく、ウィザード用移行方針が記録される

ユーザーチェック: 不要。

### フェーズ0W: 試聴ウィザード実装と移行

目的:

- 第1試聴を、手入力なしで安全・簡単・再現可能に完了できるようにする

作業:

1. player preflight、音量校正、練習を実装する
2. A/B再生とyes/noへ分解した質問を実装する
3. `SAME`と`UNSURE`を分ける
4. 一問ごとのatomic save、中断、再開を実装する
5. artifact左右yes/no、外乱確認、理由タグを実装する
6. 隠し重複の最低間隔と左右再ランダム化を実装する
7. 旧13比較と同じ音声hashから `checkpoint-wizard-v1` を生成する
8. fake playerテストとmacOS `afplay`スモークを行う

完了条件:

- 音声ファイルやCSVを手動で開かずダミーセッションを完了できる
- 強制中断後に回答を失わず再開できる
- condition、hypothesis、duplicate情報が画面へ出ない
- 旧候補音声と13ユニーク比較が変わっていない
- 重複提示が連続せず、最低4提示離れている

ユーザーチェック: 校正・練習・再生の技術スモークのみ必要。本番回答はまだ行わない。

### フェーズ1: ウィザードによる第1試聴

目的:

- H1、H3〜H6を知覚的に分類する

作業:

1. `listen`コマンドを起動する
2. 環境確認、音量校正、非採点の操作練習を行う
3. 各質問中に必要なだけA/Bを再生して回答する
4. 必要に応じて休憩・中断し、同じセッションを再開する
5. 完了時に回答JSONと互換CSVを自動生成・検証する
6. 別の分析コマンドで仮説別結果を生成する

予定コマンド:

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py listen --session checkpoint-wizard-v1
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py analyze-listening --session checkpoint-wizard-v1
```

完了条件:

- 回答validatorを通過する
- `SAME`、`UNSURE`、外乱、再生回数、休憩が記録される
- 重複回答の一貫性がconditionへ戻して報告される
- H1、H3〜H6が支持、限定支持、反証、未判定に分類される

ユーザーチェック: 必須。音の知覚回答が必要。

中止・分岐条件:

- H1不支持: フェーズ2Aへ進む
- H1支持: フェーズ2Bへ進む
- 回答一貫性不足: 同じ候補を差し替えず、UNSURE率、再生回数、外乱、疲労を確認して未判定または再試聴とする

### フェーズ2A: onset仮説の再監査

H1不支持の場合だけ実施する。

目的:

- onset仮説そのものと刺激設計の失敗を分ける

作業:

- A0/A1/A2の長さ、境界、ラウドネスを再監査する
- onset長40/80/160/240 msの感度を調べる
- UTAU以外の少数リファレンスで同じ切除比較を作る
- artifactと発声らしさを分離して再評価する

完了条件:

- H1を再支持、反証、データ不足のいずれかに分類する

停止条件:

- 別系統データでもH1が反証された場合、S系列は実装しない
- 次の研究優先度をonset以外へ戻す

ユーザーチェック: 再試聴時のみ必要。

実施状況（2026-08-25）:

- checkpoint 2音源の統制再監査を完了。10/10提示、hash合格、重複一貫性100%、artifact 0
- 人間らしさは8/8で `SAME`、開始自然さは4/8でonset文脈あり、4/8で `SAME`
- 現分類は「データ不足を伴う不支持」。総合的人間らしさは再支持されず、開始自然さへの限定効果だけが残った
- 非UTAU追試としてJVS 2話者、40/80 ms文脈、120 ms提示を凍結済み
- JVS追試を完了。人間らしさはonset文脈0/4、定常部のみ1/4、`SAME` 3/4
- H1を反証と最終分類し、本計画の停止条件を適用した。S系列フェーズ3〜13は実行しない
- onsetは将来、合格した定常ベースラインに対する開始自然さの副次操作としてのみ再検討できる

### フェーズ2B: 結果固定とamendment

H1支持の場合に実施する。

目的:

- 既存結果を固定し、後継研究の具体的な対象を決める

作業:

- 第1試聴結果と採否を保存する
- 本計画への接続を既存計画へ短いamendmentとして追記する
- H4/H5の結果に応じて共有状態とformant軌道の優先度を決める
- onset-holdoutは未開封のまま維持する

完了条件:

- 結果を見た後に変更できる範囲と、凍結を続ける範囲が明記される

ユーザーチェック: 不要。

### フェーズ3: 後継ワークスペースと解析v2

目的:

- S系列を再現可能に生成・測定する基盤を作る

予定ディレクトリ:

```text
research/experiments/phonation-onset-source-modeling/
├── README.md
├── config/
│   ├── evidence-contract.md
│   ├── experiment.json
│   └── datasets.json
├── src/
│   └── onset_source/
│       ├── boundaries.py
│       ├── cycles.py
│       ├── trajectories.py
│       ├── state_model.py
│       ├── lf_source.py
│       ├── aspiration.py
│       ├── synthesis.py
│       ├── validation.py
│       └── reporting.py
├── tests/
└── results/
    ├── analysis/
    ├── generated/
    ├── stimuli/
    └── listening/
```

作業:

- 解析v2の境界と周期追跡を実装する
- 既知信号fixtureを作る
- 既存解析値との回帰差を報告する
- 入力・派生物manifestを統合する
- 言語中立な状態・パラメータschemaを定義する

完了条件:

- fixtureの既知変形へ正しく反応する
- 低信頼例を無言で採用しない
- 同一入力、設定、seedから同一結果を再生成できる
- `stable_vowel`を固定30 msで捏造しない

ユーザーチェック: 不要。

### フェーズ4: S0ベースライン

目的:

- 現行C6と後継rendererを接続する

作業:

- 現行C6のパラメータとseedを後継側で再現する
- 波形一致ではなく、F0、振幅、周期性、HNR proxy、formant軌道を比較する
- 現行C6とS0の聴感差が大きい場合は原因を記録する

完了条件:

- S0が現行C6と同じ実験条件を表す
- 差分が実装変更、正規化、フィルタのどれに由来するか説明できる
- S0が以後の固定ベースラインになる

ユーザーチェック: 原則不要。大きな聴感差が残る場合だけ技術確認を行う。

### フェーズ5: S1四状態モデル

目的:

- 単一smoothstepと複数時定数の違いを検証する

作業:

- `airflow/adduction/coherence/articulation`を実装する
- modalとbreathyの初期プリセットを作る
- 状態から振幅、F0、ノイズ、formantへの写像を実装する
- S0と安定部条件を一致させる
- 状態を同時化した対照と、時間順序を持つS1を生成する

完了条件:

- 各状態軌道と音響出力軌道をsidecarへ保存できる
- N1に必要な比較が成立する
- signal / experiment gateを通過する

ユーザーチェック: 候補凍結後の小規模試聴で必要。

### フェーズ6: S2時変LF音源

目的:

- 声門パルス形状の成立過程の寄与を検証する

作業:

- 正規LFまたはRd系のオフライン音源を実装する
- 開口率、閉鎖時刻、return phase、spectral tiltを時間変化させる
- 静的LFと時変LFを同じ状態・声道で比較する
- oversamplingとanti-aliasingを検証する
- 逆フィルタリング結果は範囲推定にだけ使用する

完了条件:

- LFパラメータが有効範囲を外れない
- パルス形状とスペクトル傾斜の操作が測定上成立する
- N2に必要な比較が成立する

ユーザーチェック: 候補凍結後の小規模試聴で必要。

分岐:

- S2がS1を上回らない場合、LF複雑化を停止し、S1を基準にS3を試すか判断する
- S2が改善する場合、S2をS3の基礎にする

### フェーズ7: S3周期成立モデル

目的:

- 付加ノイズではない、不規則振動から周期振動への成立を生成する

作業:

- 周期ごとの `T_k/A_k/R_k` を生成する
- 減衰する周期長分散、弱周期、周期間波形差を実装する
- coherence上昇に伴い安定分布へ収束させる
- 同じ非調波エネルギーを持つ付加ノイズ対照を作る

完了条件:

- 最初の周期列と安定化周期数をsidecarへ保存できる
- 対応対照と非調波量を可能な範囲で一致させる
- N3に必要な比較が成立する

ユーザーチェック: 候補凍結後の小規模試聴で必要。

### フェーズ8: S4結合aspiration

目的:

- 息から有声音へ移る過程を声門状態と結合する

作業:

- `airflow × residual_gap(adduction)`を基礎とするaspiration包絡を実装する
- 帯域制限、時間変化、乱数seedを管理する
- 同じノイズエネルギーを持つ独立包絡対照を作る
- modalとbreathyで残留量を変える

完了条件:

- ノイズ量とスペクトルが意図した範囲にある
- 「息」ではなく「付加ノイズ」と聞こえる候補をartifact評価で検出できる
- N4に必要な比較が成立する

ユーザーチェック: 候補凍結後の小規模試聴で必要。

### フェーズ9: S系列checkpoint

目的:

- S0〜S4から採用候補を一つまたは二つへ絞る

作業:

- 仮説ごとの最小比較集合を作る
- signal / experiment / complexity gateを適用する
- 仮説ごとのprimary / secondary質問を事前固定する
- 左右、順序、非隣接重複、question routing、hashを凍結する
- CLIウィザードで音量校正、練習、対比較を実施する
- `SAME`、`UNSURE`、artifact、外乱、再生回数を保存する
- N1〜N4を分類する

完了条件:

- 採用・保留・棄却の理由が知覚結果と操作結果に結び付いている
- 音素同一性とartifactを別に報告する
- 次に残す状態とパラメータを固定する

ユーザーチェック: 必須。

### フェーズ10: S5自励振動モデル

次のいずれかを満たす場合だけ実施する。

- 人間開始部の効果は支持されたがS4までで移植できない
- S4の曲線と例外規則が、自励振動モデルと同程度に複雑になった
- onset typeやF0変更に対して個別曲線では一般化しない

目的:

- 自励振動が簡易音源より知覚または一般化で優れるかを確認する

作業:

- 二質量または簡易body-coverモデルをオフライン実装する
- 声門下圧、初期開大、内転、剛性、減衰、衝突を制御する
- 簡易な声道側圧力フィードバックを比較可能にする
- S4と同じ声道・安定部条件でS5を生成する
- モデル複雑度と計算量を報告する

完了条件:

- 自励発振の閾値と安定化を再現できる
- 無発振、発散、過大衝突をgateできる
- N5を知覚または一般化で判定できる

採用条件:

- S4より知覚評価が改善する、または
- 同等品質で複数開始様式・F0へ少ない規則で一般化する

ユーザーチェック: 候補凍結後に必要。

### フェーズ11: `/i/ /u/` と新規話者への移植

目的:

- `/a/`への過適合を検出する

作業:

- onset状態規則を固定する
- 母音固有値は安定formantと必要最小限のarticulation軌道だけ変更する
- 未使用話者、modal/breathy、複数F0で生成する
- failure caseを分類する

完了条件:

- onsetモデルの構造と係数規則を母音ごとに作り直していない
- `/i/ /u/`の母音同一性を保つ
- 複数話者・F0で開始改善の方向が再現する

ユーザーチェック: checkpoint候補の試聴で必要。

### フェーズ12: holdout

目的:

- 凍結した完全生成モデルを未使用条件で検証する

作業:

- 最終候補、主要ablation、S0、現行方式、人間アンカーを匿名化する
- onset-holdoutを初めて開封する
- パラメータを変更せず刺激を生成する
- 自動gate後に試聴集合、質問、重複、hashを凍結する
- checkpointと同じCLIウィザードで試聴する
- 結果を支持、限定支持、反証に分類する

完了条件:

- holdout結果を見た後にモデルを調整していない
- 開始自然さと母音同一性の両方を報告する
- 完全生成音と人間音声を含む研究刺激を区別する

ユーザーチェック: 必須。

### フェーズ13: 持続部とWebへの統合

目的:

- 固定したonsetモデルを長い非定常母音へ接続する

作業:

- 既存計画フェーズ8の持続部非定常モデルへ戻る
- onset状態からsustain状態へ不連続なく遷移させる
- 言語中立パラメータJSONを定義する
- オフラインrendererとWeb実装の一致fixtureを作る
- 選択した音源をwaveguide AudioWorkletへ移植する
- CPU負荷、aliasing、パラメータ更新の滑らかさを検証する

完了条件:

- Webでリアルタイム生成できる
- オフライン採用候補との主要特徴差が許容範囲内
- Startごとに機械的な完全反復をしない
- seed固定で再現可能、seed変更で許容範囲内の個体差を作れる

ユーザーチェック: 最終試聴で必要。

## 14. 予定CLI

後継ワークスペース実装後は、次の入口を提供する。以下は計画上のインターフェースであり、現時点では未実装である。

```bash
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py test
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py validate-manifest
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py analyze
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py render-s0
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py render-state-model
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py render-lf
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py render-cycle-onset
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py render-aspiration
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py freeze-candidates
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py listen
research/.venv/bin/python research/experiments/phonation-onset-source-modeling/run.py analyze-listening
```

S5は条件付きのため、着手決定前には通常pipelineへ含めない。

## 15. テスト戦略

### 単体テスト

- 状態曲線の範囲、順序、単調性、overshoot
- LFパラメータの有効範囲
- 周期列の長さ、seed再現性、安定化
- aspiration包絡と状態結合
- manifest、hash、split検証
- 正規化とsignal gate

### 性質テスト

- coherence増加で周期長分散が減る
- adduction増加で残留aspirationが減る
- articulation増加でformantが目標へ近づく
- 安定部の条件を変えずonset状態だけをablateできる
- 同じseedと設定で同じ音声を得る

### 回帰テスト

- 既存C6とS0の特徴差
- 既存比較評価の28件
- 現行phonation-onset実験の10件
- Web統合後のオフラインfixtureとの比較

## 16. 成果物

- 第1試聴の仮説別結果
- 既存計画への結果後amendment
- 周期単位を含む解析v2
- 入力・派生物の統合manifest
- 四状態の言語中立schema
- S0〜S4の完全生成rendererとablation
- 条件付きS5自励振動renderer
- 自動gateと複雑度報告
- checkpoint / holdout試聴集合
- `/a/ /i/ /u/`の固定規則による生成候補
- Web waveguide統合
- 仮説N1〜N5の最終報告

## 17. リスクと対策

### 試聴前に既存候補を変更する

対策:

- 既存lockとhashを維持する
- 後継候補は別ワークスペース・別IDにする
- amendmentは第1試聴結果の固定後に行う

### 現行C6の失敗をonset仮説の失敗と誤認する

対策:

- H1の人間音声内比較とH3の完全生成比較を分ける
- C6が表現していない周期成立と時変声門形状を明記する

### ランダムさを増やすほど自然に聞こえると誤認する

対策:

- 同じ分散・非調波量を持つ時間順序違いの対照を作る
- roughness、artifact、自然さを分けて評価する
- 人間参照範囲外の変動量をgateする

### 逆フィルタリング誤差を声帯物理量と誤認する

対策:

- 二方式と合成fixtureで検証する
- 高F0、breathy、soft onsetの信頼度を下げる
- 推定値を音響的候補として命名する

### 物理モデルが目的化する

対策:

- S5に明示的な着手条件と採用条件を置く
- 知覚、一般化、規則数、計算量をS4と比較する
- 同等以下なら研究対照に留める

### `/a/`またはUTAUへの過適合

対策:

- 話者単位splitを守る
- `/i/ /u/`へ固定規則で移す
- 別系統収録とholdoutを使う

### 試聴負担が増える

対策:

- 各フェーズで自動gateと重複候補削減を行う
- 一度にS0〜S5を比較しない
- 小規模checkpointと最終holdoutに集約する
- 仮説ごとに必要な質問だけをroutingし、全提示で全軸を聞かない
- 5段階評定を廃止し、yes/noとA/Bへ分解する
- 休憩提案、中断、resumeを標準化する

### 手入力・記憶・再生操作による試聴ミス

対策:

- 音量校正から完了検証までCLIウィザードで案内する
- 質問中にA/Bを何度でも再生できる
- 一問ごとにatomic saveし、CSVを直接編集しない
- 無効入力をその場で拒否する
- condition名、過去回答、重複情報を表示しない
- 外乱とplayer errorを回答から分離して記録する

## 18. 成功条件

この計画は、次をすべて満たしたとき完了とする。

1. 既存H1の結果に基づいて後継研究の着手可否を決めている
2. 最初の数周期と複数状態の時間差を再現可能に記述できる
3. 少なくともN1〜N4を支持、限定支持、反証、未判定に分類できる
4. 人間音声断片を含まない生成モデルで既存ベースラインとの知覚比較ができる
5. 改善が母音同一性低下やartifact増加によるものではない
6. `/i/ /u/`と未使用話者で固定規則を検証している
7. holdoutを候補調整に再利用していない
8. 物理モデルを採用または不採用にした理由が証拠と複雑度で説明できる
9. 採用onsetモデルを持続部とWeb waveguideへ統合できる
10. すべての主要試聴が、音量校正、再生ログ、自動保存、隠し重複を持つウィザードで実施される

「人間と完全に区別できない」ことは必須完了条件にしない。まず、人間らしさへ寄与する開始要因を再現可能なablationで特定し、その効果を完全生成音へ移せることを成功とする。

## 19. 最初の実行単位

計画採用後の最初の作業範囲は、次に限定する。

1. CLI試聴ウィザードの最小実装
2. 旧checkpointから `checkpoint-wizard-v1` への未回答移行
3. 音量校正、練習、再生、中断・再開の技術スモーク
4. ウィザードによる第1試聴
5. `analyze-listening`によるH1、H3〜H6の分類
6. 結果に応じたフェーズ2Aまたは2Bへの分岐

S系列の実装は、この判断が終わるまで開始しない。これにより、開始部仮説が支持される前に新しい合成器へ過剰投資することを避ける。
