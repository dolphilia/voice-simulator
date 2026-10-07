# 計画書: B9+G40母音合成系の一般化

作成日: 2026-08-25

状態: 実行中（採用確認系）。開発探索系は[試聴待ちで停止しない母音自動探索 v1](autonomous-vowel-search-plan.md)へ分離

## 0. 計画の位置付け

本計画は、B9/G40の知覚的な再確認と一般化を順に行う**採用確認系**である。既存の凍結音、hash、回答、24時間規則、試聴順序、合否条件は維持する。

一方、新しい生成候補の調査・生成・測定・感度解析を、本計画の試聴完了待ちにはしない。それらは独立した[開発探索系](autonomous-vowel-search-plan.md)で進める。開発探索系の音響結果だけで、本計画の `listener-qualified` や `release` へ昇格させない。

## 1. 確定済み基準

- 定常 `/a/`: B9-corrected-subtle-variation
- onset: G40-b9-gain-attack
- F0: 220 Hz
- スペクトル傾斜: 600 Hz一次low-pass
- F0変動: 6 Hz以下、標準偏差0.64%
- 振幅変動: 標準偏差0.67 dB
- F0・振幅相関: 0.5
- gain attack: 40 ms、正弦二乗

この40 msは合成音の開始自然さに関する当該試聴者内の局所アンカーである。人間録音の別系統再監査では開始文脈を残すことによる人間らしさ向上は反証されているため、立ち上がりを人声性の主要因へ一般化しない。

## 2. 採用確認系の順序

1. 単一試聴者の別日反復でB9・G40の個人内再現性を確認する
2. `/a/` のF0を160、220、300 Hzに広げる（事前生成・信号検査まで完了）
3. `/i/ /u/ /e/ /o/` のformant設定へ広げる
4. gain attackを固定40 msとF0周期比例で比較する（事前生成・信号検査まで完了）
5. 合格後にWebプロトタイプへ統合する

## 3. 合格と停止

- 各条件で母音同一性yes・人声同一性yesを必須とする
- onsetは共通端点処理より開始自然さで劣らないことを必須とする
- 一般化で失敗した場合、既存 `/a/` 220 Hzの確定を取り消さず、適用範囲を限定する
- パラメータを調整する場合は、一般化用の新バージョンとし、v1のhashを変更しない

## 4. 次の実行単位

利用可能な試聴者が1名であるため、複数試聴者による外部妥当化は将来課題として保留する。現在のB9・G40凍結音を使い、同じ1名が別日に3回回答する個人内反復を先に行う。各回はB6対B9とO0対G40を各2提示し、提示順と左右をrunごとに変える。

### 4.1 実行規則

- runは3回で、前回完了から原則24時間以上あける
- 各runで音量確認をやり直し、条件名と重複位置は表示しない
- 同一run内の重複は2位置以上離す
- B9は2提示ともB6より人間らしく、母音yes、人声yes、artifactなしをrun合格とする
- G40は2提示ともO0より開始自然さで劣らず、母音yes、人声yes、artifactなしをrun合格とする
- 各対象が3 run中2 run以上合格し、run内重複一致率の平均が90%以上なら次へ進む
- 回答数を人数として扱わず、結論は「1名の個人内安定性」に限定する

設定は `research/experiments/synthetic-vowel-baseline/config/single-listener-longitudinal.json` に凍結する。

```bash
# 初回
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-longitudinal --run 1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen-longitudinal --run 1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-longitudinal

# 24時間以上あけてrun 2、さらに24時間以上あけてrun 3を同様に実行
```

集計結果は `results/generalization/single-listener-longitudinal-v1/aggregate.json` に保存する。3 run完了前の集計は途中経過であり、ゲート合格にはしない。

### 4.2 反復進捗

- run 1完了: 2026-08-26
- B9: 2/2でB6より人間らしい、母音yes、人声yes、artifactなし
- G40: 2/2でO0より開始が自然、母音yes、人声yes、artifactなし
- run内重複一致率: 100%
- run 1判定: B9・G40とも合格
- 累積: 1/3 run完了。最終ゲートは未確定
- run 2: 凍結準備済み。run 1完了から24時間後に実施可能

## 5. 推論範囲と後続判断

合格した場合は、B9・G40をこの試聴者内で安定した固定基準としてF0一般化へ進む。失敗した場合はv1を取り消さず、どの軸が揺れたかを記録して比較設計または判定規則を見直す。いずれの場合も、他者にも同じ知覚が成立するとは主張しない。将来試聴者を確保できた時点で、複数人検証を独立した外部妥当化として再開する。

## 6. 待機で止めない並行作業

試聴結果が必要なのは候補の「昇格」であって、生成、信号検査、実験実装、測定の準備ではない。以後は次の作業列を並行して進める。

| 作業列 | 待機中に進める範囲 | 試聴ゲート完了まで禁止する範囲 |
|---|---|---|
| A 個人内アンカー | 予定時刻でrun 1〜3を実施・集計 | 3回未完了での最終判定 |
| B F0一般化 | 候補生成、hash、信号gate、測定、試聴CLI準備 | 候補の採用・release化 |
| C 他母音 | formant設定の出典整理、生成器のパラメータ化、自動テスト | 知覚的な微調整、最終formantの確定 |
| D 実装基盤 | manifest、回帰検査、比較・集計ツール、Web統合境界 | 未合格候補を既定音として公開 |
| E 代替モデル | 物理音源・声道モデルの独立実験と客観測定 | B9/G40より優れるという知覚的結論 |
| F 自動探索 | B9近傍の台帳、目標仕様、回帰、感度、有限探索、頑健性、試聴候補凍結 | 音響指標だけによる人声性の認定・release化 |

候補の採用状態は `draft` → `signal-qualified` → `listener-qualified` → `release` の4段階に分ける。これとは別に、`engineering_checks`、`proxy_results`、`robustness_results`、`listening_status` を保存する。音響測定や頑健性で前進しても採用状態を先取りしない。

### 6.1 F0一般化の先行作業

160、220、300 HzについてB9持続部とG40開始部を生成し、自動信号gateを通過させた。220 Hzは既存v1とsha256が一致することも確認済みである。160/300 Hzは `signal-qualified` であり、まだ知覚的には未承認とする。

- 設定: `research/experiments/synthetic-vowel-baseline/config/f0-generalization.json`
- manifest: `research/experiments/synthetic-vowel-baseline/results/f0-generalization-candidates/manifest.json`
- 候補数: 6
- 人間音声・録音断片・生成AI音声: 不使用
- 試聴セッション: 160 Hzと300 Hzを各2提示、計4提示として準備済み
- 実行ロック: 単一試聴者の別日反復ゲート合格まで開始不可

### 6.2 5母音一般化の先行作業

220 Hzで `/a/ /i/ /u/ /e/ /o/` のB9持続部とG40開始部を計10音生成し、信号gateを通過させた。`/a/` は既存v1とsha256が一致する。`/i/ /u/ /e/ /o/` は既存Web `reference` プリセットを暫定初期値とした `signal-qualified` 候補で、まだ母音知覚・人声性は未承認である。

- 設定: `research/experiments/synthetic-vowel-baseline/config/vowel-generalization.json`
- manifest: `research/experiments/synthetic-vowel-baseline/results/vowel-generalization-candidates/manifest.json`
- 候補数: 10
- 変更対象: F1〜F3と帯域幅のみ
- 固定対象: F0、B9微細変動、スペクトル傾斜、40 ms gain attack
- 試聴質問: 目的母音名は明示し、候補条件名・左右・重複位置は隠す
- 試聴セッション: `/i/ /u/ /e/ /o/` を各2提示、計8提示として準備済み
- 実行ロック: F0一般化試聴合格まで開始不可

### 6.3 準備済み試聴の順序保証

後続試聴は先に凍結しておくが、CLIが前提結果を確認してから開始する。

1. `listen-longitudinal --run N`: run間を24時間以上あける
2. `listen-f0-generalization`: 反復ゲート合格時のみ許可
3. `listen-vowel-generalization`: F0試聴合格時のみ許可

F0試聴は160/300 HzについてB9持続部とG40開始部を比較し、両方の `/a/` 同一性・人声同一性・artifactなしと、G40が開始自然さで劣らないことを各2提示で要求する。5母音試聴も同じ規則を `/i/ /u/ /e/ /o/` に適用する。回答回数を人数として扱わない。

### 6.4 gain attackスケーリングの先行作業

固定40 msと、220 Hz・40 msを8.8周期として他F0へ比例させる方式を生成した。比例時間は160 Hzで55 ms、220 Hzで40 ms、300 Hzで約29.33 msである。

- 設定: `research/experiments/synthetic-vowel-baseline/config/gain-attack-scaling.json`
- manifest: `research/experiments/synthetic-vowel-baseline/results/gain-attack-scaling-candidates/manifest.json`
- 候補数: 6
- 固定40 ms候補: F0一般化候補とhash一致
- 220 Hz: 両方式が完全同一
- 160/300 Hz: 比較可能な波形差あり
- 状態: `signal-qualified`、知覚的優劣は未評価
- 試聴セッション: 160/300 Hzを各2提示、計4提示として準備済み
- 選択規則: 両F0の各2提示で周期比例が優位な場合のみ周期比例を全体採用。F0間で固定・比例に分かれればpitch-dependent、重複不一致またはidentity/artifact失敗はinconclusive
- 実行ロック: 5母音一般化試聴合格まで開始不可

### 6.5 Web統合監査

現行Webはparallel bandpass、単純saw、微細変動なし、通常開始用40 ms attackなしであり、研究B9+G40とは生成構造が異なる。値の差し替えではなく、既存エンジンを残した明示DSP別経路が必要と判断した。

- 監査: `docs/note/web-generalization-integration-audit.md`
- 契約: `research/experiments/synthetic-vowel-baseline/config/web-integration-contract.json`
- 実装方針: release manifest駆動、opt-in導入、TypeScriptによる手続き的DSP
- 回帰方針: ブラウザsample rate差を考慮し、PCM hashではなくパラメータ・音響指標を照合
- 公開制約: listener-qualified範囲だけをWebで利用可能にする

## 7. 基準ドリフトの監視

頻繁に同じ基準を聞くと記憶・学習・疲労が増えるため、追加の無計画な再試聴は行わない。次の規則で隠しアンカーを入れる。

1. 現在のrun 1〜3自体を最初のドリフト基準とする。
2. 完了後は、新規試聴3セッションごと、または14日経過時の遅い方でアンカーを1回入れる。
3. B6対B9とO0対G40を交互に使い、条件名を表示しない。
4. アンカー結果は新候補の優劣集計に混ぜず、基準安定性として別集計する。
5. 直近3アンカー中2回で既定判定が崩れた場合、releaseを削除せず、新候補の昇格だけを停止して再確認する。

これにより、基準の変化を見逃さず、同時に検査そのものが試聴者を過度に訓練することを避ける。

## 8. 開発探索系との同期規則

1. 本計画の試聴待ちは、自動探索campaignの開始を妨げない。
2. 自動探索は独立した `campaign_id`、`candidate_id`、探索seedを使い、凍結済み試聴音を変更しない。
3. 自動探索から試聴へ送るのは最大4候補とし、有効な探索用試聴キューは同時に一つまでとする。
4. 探索用回答は仮説と評価器の更新に使い、本計画の別日反復や一般化回答へ合算しない。
5. 自動探索候補を本計画へ取り込む場合は、未使用seedによる独立確認を先に行い、一般化用の新versionとして扱う。
6. 既存B9/G40が再確認で不安定でも、自動探索の工学結果は保持する。ただし知覚候補の昇格は停止して原因を診断する。
