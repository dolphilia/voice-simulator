# 計画書: 比較評価基盤の強化

作成日: 2026-08-13

## 実施状況（2026-08-13）

| フェーズ | 状態 | 記録 |
| --- | --- | --- |
| 0 仕様固定 | 完了 | metric catalog、schema version、旧CLI自己比較回帰 |
| 1 fixture・テスト | 完了 | 既知F0/formant、gain、delay、polarity、noise、tilt、stretch、異常入力を含む28テスト |
| 2 特徴抽出 | 完了 | multi-resolution、log-mel、MFCC、F0 contour、LPC formant/Bark/bandwidth、H1-H2/CPP/HNR、時間変化、signal integrity |
| 3 manifest・split | 完了 | UTAU 128件、話者単位 development 58 / calibration 49 / holdout 21、漏洩validator、権利台帳 |
| 4 人間基準分布 | 完了 | calibration限定のmedian/MAD/percentile、層化ペア、ラベル分離、Spearman重複監査 |
| 5 スコアカード | 完了 | Target similarity / Human-likeness、カテゴリcoverage/confidence、Paretoレポート |
| 6 holdout・反復接続 | 完了 | `/a/` 旧方式 / spectral-match のdevelopment・holdout比較、5母音task雛形 |
| 7 回帰評価 | 完了 | 通常テスト、gate終了コード、benchmark差分、入力hash付き特徴と任意cache |
| 8 試聴準備 | 完了 | gate/Pareto絞り込み、音量正規化、匿名化、順序固定、重複提示、回答schema |
| 9 試聴 | 完了 | `/a/`評定、5母音・`し/す`識別、属性順序、A/B、校正アンカーを1評価者で実施。重複3組は完全一致 |
| 10 総合判断校正 | 完了（棄却） | 14対象で校正後、未提示6候補で独立検証。全軸が採用基準を満たさず暫定重みを棄却、`aggregate=null`を確定 |

実装と再現コマンドは `research/experiments/comparison-evaluation/README.md`、データ上の制約は同実験の `results/utau-audit.md` に記録した。

## 1. 目的

この計画は、Voice Simulator の生成音が人間の音声へどの程度近づいたかを、複数の尺度から再現可能かつ説明可能に評価できる基盤へ発展させるためのものである。

評価基盤は、次の用途に使う。

- 合成モデル、パラメータ、プリセットの比較
- 反復調整や自動最適化の目的関数
- 変更前後の回帰評価
- 方式ごとの強みと弱みの診断
- 研究仮説の採否判断
- 後に行う試聴評価の対象選別

目標は「人間らしさ」を一つの数値で断定することではない。音声のどの側面が近く、どこが離れ、評価自体をどの程度信頼できるかを分けて示す。

ユーザーによる試聴は重要だが、まず自動的に検証・校正できる部分を完成させる。試聴が必要な作業は計画の後半へ置き、それ以前のフェーズは原則として CLI、テスト、保存済みデータだけで完了できるようにする。

## 2. 背景と現在地

既存の比較基盤には、すでに次が実装されている。

- WAV 読み込み、mono 化、DC 除去、リサンプリング
- 無音トリム、安定中央区間・先頭区間の切り出し
- RMS 正規化、相互相関による整列
- 波形 RMSE、正規化相互相関、SNR
- log spectral distance、spectral convergence
- スペクトル重心、ロールオフ、傾斜、帯域別比率
- F0 と cents 差
- LPC による F1/F2/F3 と formant MAE
- peak frequency、spectral flatness、zero crossing rate
- フレーム単位スペクトル距離、簡易 DTW
- onset、stable、RMS rise time
- 単一ペア比較、一括比較、CSV/JSON/PNG 出力

自己比較では、距離が 0、相関が 1 になることを確認している。`/a/` の反復実験では、これらの一部を使って複合スコアを改善し、Web プロトタイプへ調整値を渡せた。

一方、現在の基盤には次の不足がある。

- 自己比較以外の正しさを検証するテストがない
- 指標が既知の変化へ期待どおり反応するか校正されていない
- 単一の参照録音への距離が中心である
- 人間音声同士にも存在する差を基準化していない
- 同一話者への類似と、一般的な人間音声らしさを分離していない
- 指標間の重複や相関を考慮していない
- 欠損、推定信頼度、不確実性をスコアへ十分反映していない
- 学習・調整データと検証データが分離されていない
- 自動指標と人の判断の対応が未検証である
- 自然さ、音素同一性、話者類似性を一つの「近さ」として混同しやすい

この計画では、既存ツールを捨てず、検証、特徴抽出、複数参照、統計的基準化、レポート、知覚評価の順に積み上げる。

## 3. 「近い」の定義

### 3.1 一つの近さではない

生成音と人間音声の近さは、少なくとも次の問いに分ける。

1. 同じ音素または音節として成立しているか
2. 声道共鳴やスペクトル包絡が人間音声の範囲にあるか
3. 声門音源、周期性、声質が人間音声の範囲にあるか
4. ノイズ成分と有声・無声の構成が適切か
5. onset、遷移、持続時間などの時間構造が適切か
6. 特定の参照話者・発話条件へ似ているか
7. 特定話者に似ていなくても、人間が発した音として自然か

これらは一致しない場合がある。たとえば、特定の `/a/` の F1/F2 に近くても機械的な周期性が残ることがあり、自然な別話者の `/a/` は単一参照から遠くても人間音声として妥当である。

### 3.2 二つの評価目的

評価結果は、次の二系統に分ける。

#### Target similarity

特定の話者、録音、音響目標への近さを測る。

用途:

- 同じ参照を使った反復調整
- プリセットの再現
- 同一条件での方式比較

#### Human-likeness envelope

複数の人間音声から得た分布の中に、生成音の特徴が入っているかを測る。

用途:

- 単一話者への過適合の検出
- 未知話者への一般化
- 人間音声として外れた特徴の診断

この二つを混ぜない。Target similarity が高く Human-likeness envelope から外れる場合は、参照固有の録音特性や推定誤差へ過適合した可能性がある。

### 3.3 自動評価で断定しないもの

次は、自動指標だけでは最終判断しない。

- 自然さ
- 聞き取りやすさ
- 声としての好ましさ
- 感情や表現の妥当性
- 長い発話全体の一貫性

自動評価は候補の絞り込み、問題の診断、変化の追跡に使う。最終的な知覚上の妥当性は後半の試聴評価で確認する。

## 4. 評価原則

### 4.1 生の測定値を失わない

正規化スコアだけでなく、Hz、cent、dB、ms、比率などの元の値を必ず保存する。スコア関数を変更しても過去の実験を再解釈できるようにする。

### 4.2 差の符号を保存する

絶対誤差だけでなく、生成音が高い、低い、明るい、暗い、速い、遅いといった方向を残す。最適化で次にどのパラメータを動かすか判断できるためである。

### 4.3 不変であるべき変化と、評価すべき変化を区別する

例:

- ファイル先頭の無音は、安定母音の音色評価へ影響させない
- 符号反転は、知覚的音色評価へ影響させない
- 音量正規化後のフォルマント評価は、単純ゲインへ反応させない
- timing 評価は、onset や duration の差へ反応させる
- target similarity の F0 評価は音高差へ反応させる
- F0 を条件として分離した声道評価は、音高差へ過度に反応させない

どの指標が何に不変であるべきかをテスト仕様として記録する。

### 4.4 人間音声同士の差を基準にする

生成音と参照音の距離だけでは尺度の大小を解釈しにくい。人間音声同士の次の距離を基準分布として計算する。

- 同一話者・同一音素・別テイク
- 別話者・同一音素
- 同一話者・別音素
- 別話者・別音素

理想的には、良い生成音は「同一音素の人間同士」の範囲へ近づき、「別音素」の範囲から分離される。

### 4.5 データ漏洩を避ける

参照データを次に分割する。

- `development`: 指標実装とパラメータ調整に使う
- `calibration`: 正規化範囲、分布、閾値の推定に使う
- `holdout`: 最終比較にだけ使う

同じ録音から切り出した区間や、同一 UTAU 連続音の近接セグメントが別 split に入らないよう、話者・元ファイル単位で分ける。

### 4.6 欠損を良い値として扱わない

F0 やフォルマントが推定できない場合、誤差 0 として扱わない。次を別に出す。

- `available`: 指標を計算できたか
- `confidence`: 推定の信頼度
- `reason`: 欠損理由
- `coverage`: カテゴリ内で有効だった指標の割合

総合表示には、スコアと信頼度を併記する。

### 4.7 再現可能性を評価結果の一部にする

レポートには次を含める。

- 入力ファイルの識別子とハッシュ
- 評価設定のバージョン
- サンプルレート、区間選択、正規化方法
- 指標実装のバージョン
- 乱数 seed
- 実行時の依存関係

## 5. 評価尺度の体系

### 5.1 信号健全性

合成器の不具合を検出する層であり、人間らしさの主スコアには直接混ぜない。

| 指標 | 主な目的 |
| --- | --- |
| clipping sample ratio | クリッピング検出 |
| DC offset | バイアス検出 |
| peak / true-peak 近似 | 出力余裕の確認 |
| RMS / loudness 近似 | 音量条件の確認 |
| silence ratio | 無音・途切れの検出 |
| NaN / Inf / denormal | 数値異常の検出 |
| high-frequency alias ratio | エイリアシング候補の検出 |

### 5.2 ピッチと有声性

| 指標 | 内容 |
| --- | --- |
| median F0 delta cents | 中央 F0 の差 |
| F0 contour RMSE cents | 時系列 F0 差 |
| F0 contour correlation | 抑揚形状の一致 |
| voiced/unvoiced precision・recall・F1 | 有声区間判定の一致 |
| pitch-period stability | 周期の安定性 |
| jitter 差 | 周期揺らぎの差 |

持続母音では中央値と安定性、遷移・発話では輪郭と有声境界を重視する。

### 5.3 声道共鳴と音素同一性

| 指標 | 内容 |
| --- | --- |
| F1/F2/F3 absolute delta Hz | 物理周波数差 |
| F1/F2/F3 relative error | 話者スケールを考慮しやすい差 |
| formant delta Bark | 知覚周波数軸上の差 |
| bandwidth delta | 共鳴の鋭さの差 |
| formant trajectory distance | 遷移中の軌跡差 |
| vowel-space position | F1/F2 空間内の位置 |
| vowel classification margin | 同一母音群と別母音群の分離余裕 |

F1/F2/F3 の点推定だけでなく、推定信頼度と時間的な連続性を評価する。複数の解析設定で一致しないフォルマントは低信頼とする。

### 5.4 スペクトル包絡と音色

| 指標 | 内容 |
| --- | --- |
| multi-resolution log spectral distance | 複数 FFT 窓長での包絡差 |
| multi-resolution STFT distance | 時間・周波数分解能を変えた差 |
| log-mel spectral distance | 聴覚帯域に近いスペクトル差 |
| MFCC / mel-cepstral distance | 包絡の低次元差 |
| spectral convergence | 全体形状差 |
| centroid / rolloff / slope delta | 明るさと高域傾向 |
| band-energy vector distance | 低・中・高・air 帯域の構成差 |

単一 FFT サイズだけでなく、短い窓と長い窓を併用する。F0 の倍音位置に過敏な距離と、包絡を平滑化した距離を分けて出す。

### 5.5 声門音源と声質

| 指標 | 内容 |
| --- | --- |
| H1-H2、H1-A1/A2/A3 | 開口・閉鎖特性の近似 |
| harmonic spectral slope | 倍音減衰 |
| CPP | 周期性・声質の安定度 |
| HNR | 調波とノイズの比 |
| shimmer | 振幅周期変動 |
| nonharmonic energy ratio | 非周期成分の近似 |
| RMS / F0 local variability | 局所安定性 |

F0 とフォルマントの影響を受けるため、可能な指標には補正条件と信頼度を付ける。将来的な声門逆フィルタリングは別実験とし、初期強化では H1-H2、CPP、HNR を優先する。

### 5.6 ノイズ・摩擦音

| 指標 | 内容 |
| --- | --- |
| spectral centroid / peak / moments | ノイズ中心と分布形状 |
| flatness | 狭帯域・広帯域性 |
| 3–8 kHz / 8–12 kHz ratio | sibilant と air 成分 |
| low-frequency voicing ratio | 有声成分の混入 |
| noise envelope distance | attack、hold、decay の差 |
| time-varying centroid distance | 子音から母音への変化 |
| zero crossing rate | 補助的な無声性指標 |

### 5.7 時間構造と遷移

| 指標 | 内容 |
| --- | --- |
| duration delta | 全体長の差 |
| onset / offset delta | 境界時刻の差 |
| RMS rise / fall delta | エンベロープ時間差 |
| DTW log-mel distance | 時間伸縮を許した特徴差 |
| formant transition duration | 共鳴遷移時間 |
| spectral-stability arrival time | 安定音へ到達する時刻 |
| event-order violations | 閉鎖・ノイズ・有声開始の順序異常 |

### 5.8 波形・位相

波形 RMSE、相互相関、SNR は残すが、人間音声参照への主評価には使わない。次に限定する。

- 同一合成器の決定論的回帰テスト
- 同じ F0、位相、長さを持つ人工 fixture
- フィルタやアルゴリズム変更の局所比較

### 5.9 識別性

人間音声のラベルを使い、生成音が目的音素の人間分布へ近いかを評価する。

初期は透明性を保つため、F1/F2、log-mel、MFCC など明示特徴量上の最近傍・重心距離を用いる。大規模学習済み音声モデルによる埋め込みは、必要になった場合の補助診断に留め、初期総合スコアには入れない。

## 6. 前処理と比較条件

同じ音声ペアに対して、目的別に複数の比較 view を作る。

### 6.1 Raw-condition view

元の音量、F0、長さを保つ。発話条件全体の target similarity に使う。

### 6.2 Level-normalized view

RMS または将来の loudness で音量を揃える。音色、共鳴、声質を比較する。

### 6.3 F0-conditioned view

F0 差を別指標として扱い、平滑スペクトル包絡やフォルマントを中心に比較する。初期段階では音声を pitch-shift せず、包絡抽出と調波位置に頑健な尺度を使う。

### 6.4 Time-aligned view

全体遅延だけを整列する view と、DTW で局所伸縮を許す view を分ける。DTW 後の距離だけでは timing の悪さが隠れるため、warp 量も指標として保存する。

### 6.5 Segment views

- stable vowel
- consonant/noise
- onset
- transition
- offset
- whole event

自動区間検出の結果と信頼度を保存し、必要なら manifest で手動境界を与えられるようにする。ただし初期計画では自動境界を優先する。

## 7. 複数参照と統計的基準化

### 7.1 参照セット

1 つの生成音に対し、次の参照集合を持てる形式にする。

- 同一話者・同一音素
- 同一条件の複数テイク
- 複数話者の同一音素
- 声質や F0 帯を揃えた部分集合

### 7.2 基準分布

参照音声同士の全ペアまたは層化サンプルから、指標ごとに次を求める。

- median
- MAD または robust scale
- 5 / 25 / 50 / 75 / 95 percentile
- 有効サンプル数
- 話者内分布と話者間分布

生成音の距離は、生値に加えて robust z-distance と percentile として表す。

例:

```text
F1 absolute delta: 84 Hz
human same-vowel median: 62 Hz
human same-vowel 95 percentile: 148 Hz
generated percentile: 68
status: within human reference range
```

### 7.3 多変量距離

個別指標を主としつつ、同じカテゴリ内では多変量距離も検討する。

- robust standardized Euclidean distance
- covariance shrinkage を用いた Mahalanobis 距離
- 人間分布の最近傍距離と重心距離

サンプル数が少ない場合は Mahalanobis 距離を使わず、独立した robust z-distance の集合を表示する。

### 7.4 参照への集約

複数参照に対して、最小距離だけを使わない。最小値は偶然近い録音へ過適合しやすいため、次を併記する。

- nearest reference distance
- median reference distance
- trimmed mean distance
- within-range ratio

## 8. スコア設計

### 8.1 最初はスコアカードを使う

初期出力は、次のカテゴリ別スコアカードとする。

| カテゴリ | 主な問い |
| --- | --- |
| signal integrity | 数値・信号上の異常がないか |
| pitch / voicing | 音高と有声性が近いか |
| resonance / phonetic identity | 音素を決める共鳴が近いか |
| spectral envelope / timbre | 音色と帯域構成が近いか |
| source / voice quality | 周期性と声質が近いか |
| noise / frication | ノイズの帯域・量・時間形状が近いか |
| timing / transition | 発音イベントの時間構造が近いか |

各カテゴリに次を出す。

- 生の主要指標
- 人間基準分布上の percentile
- 0〜100 の暫定カテゴリスコア
- coverage
- confidence
- 主な外れ値と方向

### 8.2 総合スコアは後から導入する

総合スコアは、次を満たすまで正式な最適化目的にしない。

- 各指標の既知変形テストが通る
- 人間同士の基準分布がある
- development / calibration / holdout が分かれている
- 指標間相関が確認されている
- 少人数試聴との対応が確認されている

それ以前は、カテゴリ別改善、Pareto 改善、重大な悪化の有無で判断する。

### 8.3 暫定カテゴリスコア

カテゴリスコアが必要な場合は、各指標の robust z-distance を上限付きで変換する。

```text
distance = abs(value - human_center) / robust_scale
metric_score = 100 * exp(-k * distance)
```

ただし `k` は calibration データで定め、未校正の固定値を正式評価には使わない。強く相関する指標を重複加算せず、カテゴリ内で代表指標を選ぶ。

### 8.4 ゲート条件

重大な異常は平均点で相殺させない。

例:

- clipping が閾値以上
- F0 未検出率が高い
- 目的母音とは別の母音群に近い
- 有声・無声順序が逆
- 数値異常がある

これらはカテゴリスコアとは別に `fail / warn / pass` として出す。

## 9. テスト戦略

### 9.1 自己同一性テスト

既存の自己比較を自動テスト化する。

- 同一音声の距離は 0 または許容誤差内
- 相関は 1 に近い
- 前処理後の長さと指標が決定論的

### 9.2 不変性テスト

同じ fixture に既知変形を加える。

| 変形 | 不変であるべき主評価 | 反応すべき評価 |
| --- | --- | --- |
| 先頭無音追加 | stable vowel timbre | onset / duration |
| 単純ゲイン | level-normalized timbre | raw RMS |
| 符号反転 | spectrum / formant | raw waveform |
| 全体遅延 | aligned timbre | alignment lag |
| 微小位相変更 | envelope | waveform RMSE |

### 9.3 感度・単調性テスト

| 変形 | 期待する反応 |
| --- | --- |
| F0 を cents 単位で変更 | F0 差がほぼ同量で単調増加 |
| formant を既知 Hz 移動 | 対応 formant 差が単調増加 |
| spectral tilt 変更 | slope、H1-H2、brightness 系が反応 |
| noise mix 増加 | HNR、CPP、flatness、nonharmonic 系が反応 |
| bandpass 中心移動 | centroid、peak、band ratio が反応 |
| time stretch | timing と DTW warp が反応 |
| attack 変更 | onset / RMS rise が反応 |

### 9.4 識別テスト

人間参照データを使い、同一母音ペアの距離が別母音ペアより統計的に小さいか確認する。

初期完了条件:

- F1/F2 または包絡カテゴリで同一母音と別母音を分離できる
- leave-one-speaker-out でも傾向が維持される
- どの指標が分離へ寄与したか説明できる

### 9.5 回帰 fixture

小さく再配布可能な fixture を用意する。

- 合成正弦波・調波音
- 既知フォルマントを持つ source-filter 音
- 既知帯域のノイズ
- onset と transition を持つ人工イベント
- 権利条件が明確な小規模人間音声

大規模 UTAU データがなくても、基本テストを実行できるようにする。

## 10. データ設計

### 10.1 評価 manifest

CSV または JSONL で次を管理する。

```text
sample_id
path
kind: human | generated | analytic
label
mode
speaker_id
source_recording_id
take_id
style
f0_range
split: development | calibration | holdout
license
generator
generator_version
parameter_file
random_seed
notes
```

### 10.2 比較 task

評価目的を task として定義する。

```text
task_id
generated_selector
reference_selector
target_type: target_similarity | human_likeness
segment_view
normalization_view
metric_profile
```

これにより、同じ WAV を別の目的・前処理で評価できる。

### 10.3 初期参照セット

ユーザーの新規収録を待たず、既存 UTAU データから自動的に次を作る。

- 5 母音の development / calibration / holdout
- 話者単位で分離した同一母音参照
- `し/す` と breath の小規模参照
- 可能な範囲で同一話者・別サブセットのテイク

UTAU 固有の偏りは manifest に明記する。後のフェーズで自前録音や別コーパスを追加する。

## 11. 実装構成案

既存の `research/scripts/` を直ちに大規模移動せず、比較評価基盤を自己完結した実験として追加する。

```text
research/experiments/comparison-evaluation/
├── README.md
├── config/
│   ├── metric-profiles.json
│   ├── thresholds.json
│   └── splits.json
├── fixtures/
│   ├── manifests/
│   └── expected/
├── src/
│   ├── features/
│   ├── metrics/
│   ├── baselines/
│   ├── reports/
│   └── cli/
├── tests/
└── results/
```

既存の `audio_utils.py` と `compare_waveforms.py` は当面互換性を維持する。新基盤の安定後に、共通機能をライブラリ化し、旧 CLI を薄い互換ラッパーにする。

### 11.1 内部データモデル

評価処理を次の段階に分ける。

```text
audio input
  -> validated waveform
  -> segment views
  -> feature bundle
  -> pairwise raw metrics
  -> reference-distribution normalization
  -> category scorecard
  -> report
```

特徴量と距離計算を分ける。同じ特徴量を一括比較で再利用し、キャッシュできるようにする。

### 11.2 CLI 案

```bash
# fixture と既知変形の検証
python -m comparison_eval test

# manifest の特徴抽出
python -m comparison_eval extract --manifest samples.csv

# 人間同士の基準分布生成
python -m comparison_eval baseline --manifest samples.csv --split calibration

# 単一生成音のスコアカード
python -m comparison_eval evaluate \
  --generated generated.wav \
  --references references.csv \
  --profile sustained-vowel

# 複数モデルの比較レポート
python -m comparison_eval benchmark --tasks tasks.csv
```

## 12. 実施フェーズ

### フェーズ 0: 評価仕様と既存挙動の固定

目的:

現在のツールが何を計算しているかを仕様化し、強化中の意図しない変更を検出できるようにする。

作業:

- 現行 CSV の列、単位、前処理、欠損条件を一覧化する
- 指標ごとに「用途」「避ける用途」「不変条件」を記述する
- 既存自己比較出力を regression fixture にする
- 現行 `/a/` 実験を再評価できる task を作る
- 評価設定に schema version を付ける

成果物:

- `research/experiments/comparison-evaluation/README.md`
- metric catalog
- legacy regression fixtures

完了条件:

- 現行比較結果を同じ条件で再生成できる
- 各列の意味と単位が文書化されている
- 新基盤と旧 CLI の差を追跡できる

ユーザーチェック: 不要。

### フェーズ 1: 解析 fixture と自動テスト

目的:

自己比較だけでなく、既知の変化に対する指標の正しさを検証する。

作業:

- 調波音、source-filter 母音、帯域ノイズ、transition fixture を生成する
- 遅延、ゲイン、符号、F0、formant、tilt、noise、time stretch の変形器を作る
- 不変性、感度、単調性テストを実装する
- NaN、無音、短すぎる音声、stereo、異なる sample rate の異常系を追加する
- 許容誤差を fixture ごとに明示する

成果物:

- 小規模 fixture generator
- 自動テスト群
- expected metrics

完了条件:

- 既知 F0 変更を cents で許容誤差内に測れる
- 既知 formant 変更を対応する方向へ検出できる
- level-normalized 指標が単純ゲインへほぼ不変である
- timing 指標が既知遅延・伸縮へ単調に反応する
- 異常入力が黙って有効スコアにならない

ユーザーチェック: 不要。

### フェーズ 2: 特徴抽出の強化

目的:

既存指標の弱点を補い、声の構成要素を分けて測れる特徴量を追加する。

優先実装:

1. multi-resolution STFT / log spectrum
2. log-mel spectrum と MFCC
3. F0 contour と voiced/unvoiced
4. Bark 上の formant 差と bandwidth
5. H1-H2、CPP、HNR
6. time-varying centroid と noise envelope
7. clipping、silence、alias 候補などの signal integrity

作業:

- feature bundle の schema を定義する
- フレーム特徴量と集約値を分けて保存する
- 推定器ごとの confidence と欠損理由を出す
- 特徴抽出結果を入力ハッシュと設定でキャッシュする
- 既存指標との重複を確認する

完了条件:

- 持続母音、ノイズ、transition の profile ごとに必要特徴が揃う
- fixture テストが追加特徴でも通る
- 同一入力の再実行で同じ結果になる
- 推定不能値が明示的に欠損となる

ユーザーチェック: 不要。

### フェーズ 3: 参照 manifest とデータ分割

目的:

単一参照への依存をやめ、評価用データを漏洩なく管理する。

作業:

- manifest schema と validator を実装する
- 既存 UTAU 台帳から評価 manifest を生成する
- 話者・元録音単位で development / calibration / holdout に分割する
- 5 母音、`し/す`、breath の初期セットを作る
- ライセンス、由来、利用範囲を manifest に保持する
- 分割後の件数と偏りをレポートする

完了条件:

- 同じ話者または元録音の漏洩を検査できる
- 各 split に必要なラベルがある
- holdout は通常の反復調整から参照されない
- UTAU 偏重がレポート上で明示される

ユーザーチェック: 不要。新しい外部音声の取得はこのフェーズでは行わない。

### フェーズ 4: 人間音声の基準分布

目的:

「人間音声同士ならどの程度違うか」を尺度の基準にする。

作業:

- calibration split 内で層化ペアを生成する
- 話者内・話者間、同音素・別音素の距離分布を計算する
- median、MAD、percentile、coverage を保存する
- leave-one-speaker-out で識別性を検証する
- 推定失敗率を話者、ラベル、F0 帯ごとに集計する
- 指標間の Spearman 相関と冗長性を調べる

完了条件:

- 同一母音と別母音を分離する指標が特定される
- 各主要指標を人間分布の percentile で表現できる
- サンプル不足で使えない多変量尺度を自動的に避けられる
- 強く重複する指標が総合カテゴリへ二重計上されない

ユーザーチェック: 不要。

### フェーズ 5: 評価 profile とスコアカード

目的:

比較対象ごとに適切な尺度を選び、診断可能なレポートを出す。

初期 profile:

- `sustained-vowel`
- `fricative-noise`
- `vowel-transition`
- `cv-syllable`
- `deterministic-regression`

作業:

- profile ごとの segment、normalization、metric、gate を設定化する
- target similarity と human-likeness を別に出す
- 主要外れ値と方向を文章化する
- coverage と confidence をカテゴリごとに出す
- CSV/JSON に加えて Markdown または HTML レポートを生成する
- モデル間の Pareto 比較を出す

完了条件:

- 1 つの生成音についてカテゴリ別の強み・弱みを読める
- 単一総合点がなくてもモデル比較の判断材料が揃う
- 欠損が多い評価は低 confidence と表示される
- target similarity と human-likeness が混同されない

ユーザーチェック: 不要。

### フェーズ 6: holdout ベンチマークと反復調整への接続

目的:

評価基盤を実際のモデル選択と最適化へ使い、過適合を検出する。

作業:

- 既存 `/a/` の 10 試行を新スコアカードで再評価する
- `spectral_match` の有無を target / human-likeness の両方で比較する
- development で調整したパラメータを holdout 話者で評価する
- 5 母音へ実験を拡張できる task を用意する
- 反復調整はカテゴリ別目的と gate を使う
- 1 カテゴリ改善の代わりに別カテゴリが悪化した場合を検出する

完了条件:

- `/a/` の旧複合スコア改善を多面的に再解釈できる
- development 改善が holdout でも維持されるか判定できる
- 過適合または指標ハックの例を検出できる
- 新しい実験が同じ task 形式で追加できる

ユーザーチェック: 不要。音声候補は保存するが、この時点では試聴を完了条件にしない。

### フェーズ 7: レポートと継続的回帰評価

目的:

評価を一度限りの解析ではなく、実装変更ごとに再利用できるようにする。

作業:

- 小規模 fixture を通常テストへ組み込む
- 代表的な生成音を benchmark set にする
- 前回結果との差分レポートを作る
- gate failure とカテゴリ悪化を終了コードで返せるようにする
- 実行時間とキャッシュを最適化する
- 重要な基準値とレポートだけを Git 管理する

完了条件:

- 小規模テストが通常環境で短時間に実行できる
- 音響コア変更による予期しない悪化を検出できる
- 基準更新には理由と評価バージョンが必要になる

ユーザーチェック: 不要。

### フェーズ 8: 試聴評価の準備

目的:

ユーザーの時間を使う前に、自動評価で候補を絞り、再現可能な試聴手順を用意する。

作業:

- 明らかな gate failure と劣後候補を除外する
- 同等または Pareto 関係にある少数候補を選ぶ
- 音量正規化、順序ランダム化、匿名 ID を自動化する
- 評価項目を音素同一性、自然さ、明瞭さ、声質、参照類似へ分ける
- A/B、ABX、カテゴリ識別、MOS 風評価の使い分けを定義する
- 回答を CSV/JSON へ保存する
- 同一候補の重複提示で回答内一貫性を測る

完了条件:

- 1 セッションの候補数と所要時間が過大でない
- 評価者がモデル名や調整条件を知らずに回答できる
- 自動指標と結合可能な回答形式になっている
- ユーザーは生成・整列・音量調整を手作業で行わなくてよい

ユーザーチェック: 原則不要。試聴 UI または音声セットの最終動作確認だけを依頼する可能性がある。

### フェーズ 9: 少人数の試聴評価

目的:

自動指標が人の判断とどの程度対応するかを確認する。

最初の評価:

1. 5 母音の識別
2. 参照音声との A/B 類似比較
3. 自然さと明瞭さの独立評価
4. brightness / breathiness の順序評価
5. `し/す + 母音` の音節識別とつながり

作業:

- 少数候補をブラインド提示する
- 回答時間、再回答一致、自由記述を保存する
- 自動カテゴリスコアとの順位相関を計算する
- 評価者内・評価者間の一致度を確認する
- 自動評価と食い違う例を重点的に診断する

完了条件:

- 自動指標のうち、どれが各知覚軸と対応するか分かる
- 対応しないカテゴリを総合スコアへ入れない判断ができる
- 試聴評価の再現手順と制約が文書化される

ユーザーチェック: 必要。この計画で最初に本格的な試聴判断を求めるフェーズとする。

### フェーズ 10: 総合判断モデルの校正

目的:

自動指標と試聴結果をもとに、用途別の総合判断を導入する。

作業:

- 自然さ、音素同一性、target similarity を別目的として校正する
- 指標間相関を考慮して代表指標を選ぶ
- 単純で説明可能な重み付けを優先する
- calibration で重みを決め、holdout で検証する
- 総合点とカテゴリスコアの両方を残す
- バージョンごとのスコア互換性を管理する

完了条件:

- 総合点の高低を構成指標へ分解して説明できる
- holdout の人の順位と一定の対応がある
- 特定指標だけを最適化して総合点を不正に上げにくい
- 用途の異なる総合点を一つに混ぜない

ユーザーチェック: 試聴結果の解釈と重みの採否判断で必要。

## 13. 実施順序と依存関係

```text
Phase 0 仕様固定
   ↓
Phase 1 fixture・テスト
   ↓
Phase 2 特徴抽出
   ↓
Phase 3 manifest・split
   ↓
Phase 4 人間基準分布
   ↓
Phase 5 スコアカード
   ↓
Phase 6 holdout・反復接続
   ↓
Phase 7 回帰評価
   ↓
Phase 8 試聴準備
   ↓
Phase 9 試聴
   ↓
Phase 10 総合判断校正
```

フェーズ 0〜7 は、現在の保存済みデータと自動生成 fixture で進める。ユーザーの試聴を待たずに実施可能である。

## 14. 優先順位

### 最優先

1. 既知変形による指標テスト
2. multi-resolution / log-mel 系の包絡評価
3. 複数参照 manifest と話者単位 split
4. 人間音声同士の基準分布
5. target similarity と human-likeness の分離
6. カテゴリ別スコアカード

### 次点

7. F0 contour、有声・無声、CPP、HNR、H1-H2
8. transition の時間変化評価
9. holdout ベンチマーク
10. 継続的回帰評価

### 後半

11. ブラインド試聴基盤
12. 自動指標と知覚評価の相関
13. 用途別総合スコア

## 15. 成功条件

比較評価基盤の強化は、次を満たしたときに初期完成とみなす。

- 指標が既知変形へ期待どおり反応することを自動テストできる
- 同一音素の人間音声同士の差を基準として表示できる
- 単一参照と複数参照の両方を扱える
- target similarity と human-likeness を別に評価できる
- 音源、共鳴、音色、ノイズ、時間構造をカテゴリ別に診断できる
- development / calibration / holdout が分離されている
- 欠損、coverage、confidence が表示される
- 反復調整で一側面だけ改善した場合の副作用を検出できる
- Web または他の合成器の出力を同じ形式で評価できる
- 試聴前に候補を自動的に絞り込める

総合スコアの完成は、初期完成条件には含めない。総合スコアは試聴評価との対応が確認できた後の成果とする。

## 16. リスクと対策

### 指標が多すぎて判断できない

対策:

- カテゴリごとに主指標と診断指標を分ける
- 相関の高い指標を代表指標へ縮約する
- 外れ値の方向と推奨調整対象をレポートする

### 単一参照へ過適合する

対策:

- 複数参照の中央値と human-likeness envelope を使う
- holdout 話者で評価する
- nearest reference だけで判断しない

### F0 差がすべてのスペクトル指標を支配する

対策:

- F0 を独立カテゴリにする
- 平滑包絡、log-mel、MFCC を併用する
- raw-condition と F0-conditioned view を分ける

### 自動指標が知覚と対応しない

対策:

- 総合スコアを早期導入しない
- 後半でブラインド試聴との順位相関を測る
- 対応しない指標を診断専用に下げる

### 参照データの偏りを人間一般と誤認する

対策:

- UTAU baseline と明記する
- 話者・F0・サブセット別の分布を出す
- 後に別コーパス、自前録音、物理ベンチマークを追加する

### 推定失敗がモデルの改善を誤誘導する

対策:

- confidence と coverage を必須にする
- 複数設定または補助指標で整合性を確認する
- 欠損を 0 距離に変換しない

### スコアを上げるだけの不自然な最適化が起きる

対策:

- gate、カテゴリ別スコア、Pareto 比較を使う
- holdout と複数参照を使う
- 後半で知覚評価を行う
- 波形やスペクトルの代表例をレポートへ残す

## 17. この計画で当面行わないこと

- 大規模な聴取実験
- 不透明な単一 AI 評価器への全面依存
- 話者認証モデルのスコアを人間らしさと同一視すること
- 自然さを自動指標だけで断定すること
- 初期段階から全音素・文章発話を扱うこと
- 校正前の重み付き総合点を正式な研究結論に使うこと
- 評価のために参照音声を合成出力へ混ぜること

## 18. 関連文書

- [既存の波形比較ツール計画](waveform-comparison-tool-plan.md)
- [調査・研究・解析の総括](../note/research-review-2026-08-13.md)
- [UTAU 音声サンプル分析計画](utau-samples-research-plan.md)
- [UTAU 分析後の実装計画](utau-informed-next-implementation-plan.md)
- [母音 `/a/` 反復実験](../note/vowel-matching-experiment-summary.md)
