# 無人非ニューラル音声研究 実行報告

campaign: `ans-pilot-v1`。判定: **inconclusive（品質目標未達）**。

母音・VV・主要子音・短文を共有規則から生成し、別プロセスで未知のかな文を再生成した。信号が成立することを、自然な日本語音声が完成したことへ読み替えない。

## 実行結果

| 工程 | 結果 |
|---|---|
| P0 | implemented |
| P1 | numerical-qualified-perception-inconclusive |
| P2 | pilot-completed |
| P3 | engineering-only |
| P4 | engineering-only |
| P5 | engineering-isolation-only-quality-confirmation-unopened |

台帳の完了試行: 2364、E0失敗または実行失敗: 0。失敗も予算に含む。

## 評価と限界

E0は非有限値・clipping・DC・全体無音・継続長・端点を検査する。F0は既知周期信号で資格を点検した。帯域残差は診断に限定し、MOS/CERへ換算していない。

JVSは保存済み履歴を走査し、話者と文IDの双方を分割した。リポジトリ外の既知/未知は証明できない。自動alignmentは±10msで摂動し、短すぎる/不安定な母音を除外して率を残した。声道長の厳密整合とラベルの独立確認は未実施。

P2は音源→声道→共同の共有制御探索と同数の無作為対照。設定を条件ごとに取り替えた非共有oracleも保存したが、波形自由適合の上限を測ったとは主張しない。seedとフレームを独立話者として数えていない。

P3/P4では鼻腔結合近似、閉鎖、摩擦、破裂、促音、撥音、長音、無声化、アクセント核、句内F0を実装した。音素ごとの明瞭性・VOT/調音妥当性・混同行列・ASRのCER・TTSDS2は未資格または未実施であり、工程の品質通過は認定していない。

かな前段の助詞表記は発音通りに入力する。漢字解析・辞書アクセントは未接続。外部未知入力も拒否を結果に残し、任意文章対応とはしない。

## 選別候補

- `dsp-adaptive-05`: 診断残差 2.513197、coverage 1.000。共有係数 `{"tract_scale": 1.0208214585779376, "bandwidth_scale": 1.1820053618381068, "ta": 0.03}`。
- `vtl-random-06`: 診断残差 0.497717、coverage 1.000。共有係数 `{"tongue_x_cm": -0.06362595528478213, "lip_protrusion_cm": -0.14725783500861803, "pressure_scale": 1.1429534334685656}`。

## 生成単独実行

監査フックと生成モジュール静的検査: `True`。同じ入力でfloat64出力ハッシュを比較した。OSのアクセス拒否確認は `os-isolation.json` があれば併読する。

移出内容は `bundle/`、共有設定は `voice-config.json`。録音・重み・発話辞書・保存済み制御軌跡を含まない。WAVと制御ログは実行時に生成する。VTLは研究比較のみで、移出bundleに含めていない。

## 実測コスト

| backend | 完了試行数 | 中央値RTF（評価を含む） |
|---|---:|---:|
| B9 | 45 | 0.1066 |
| G40 | 45 | 0.2150 |
| dsp | 1509 | 0.0430 |
| vtl | 765 | 1.7325 |

## 再現

リポジトリルートで実行。DSPは既存の `research/.venv`、AI評価は実験専用の `.venv-eval` に分離する。

```bash
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py status --campaign ans-pilot-v1
research/.venv/bin/python -m unittest discover -s research/experiments/autonomous-speech-synthesis/tests -v
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py run --campaign ans-pilot-v1
```

同一IDの再実行は保存済み試行を検証して再利用する。コード・設定・環境が違う場合は同じIDで再開しない。新規の再現は別IDを使い、確認データの使用履歴は引き継ぐ。

## 残る完了条件

- 日本語の物理/規則合成に対する自然さ代理評価器の資格が不足
- 音素認識・短文CERと自然参照分布の必須ゲートが未達
- かな入力を超える任意日本語テキスト品質は対象外

計画の完了条件は達成していない。試聴回答を待つ工程は追加していない。
