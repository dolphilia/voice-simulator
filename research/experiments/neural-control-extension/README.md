# 非ニューラル移行の追加検証

旧pilotの固定HMM・回帰モデルとニューラル教師を読み取り再利用し、未知16文とF0・速度の変更を調べる。既存の学習・選別結果は変更しない。仕様と上限は[追加計画](../../../docs/plans/neural-assisted-extension-plan-2026-10-02.md)を参照。

実施結果は[追加比較の報告](../../../docs/note/neural-assisted-extension-result-2026-10-02.md)。AI評価枠300回を使用済み。移植した制御の品質を認定しておらず、既定HMMより内容が悪化したため採択していない。以下のコマンドは再現手順の記録であり、既存IDで予算を自動更新しない。

リポジトリ直下から既存環境のPythonで順番に実行する。台帳は同時に一つの予約のみを許容する。

```bash
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/render.py
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/evaluate.py --engine whisper
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/evaluate.py --engine reazon
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/teacher_compare.py
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/evaluate.py --engine whisper --source teacher
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/evaluate.py --engine reazon --source teacher
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/neural-control-extension/summarize.py
```

`prepare.py`は初期固定専用で再実行しない。生成・評価は既存成果物のハッシュを検査して再開できる。集計は既存summaryを上書きしない。教師の声ファイル取得以外は既存資産をオフラインで使用する。教師出力は研究用であり、最終HMM実行時には使わない。別声jf_gongitsuneはKokoro公式VOICES.mdのCC BY欄が示す[koniwa / tnc ごん狐](https://github.com/koniwa/koniwa/blob/master/source/tnc/tnc__gongitsune.txt)に由来する。来歴を保存し、最終bundleへ同梱しない。

後続処理は`relative.py`（別8文の相対移植）、`evaluate.py --source relative --engine whisper/reazon`、`pitch_audit.py`（非学習F0解析）、`bounded.py`（別2文の特徴外挿制限）、`evaluate.py --source bounded --engine whisper/reazon`、`finalize.py`の順で実施した。スラッシュ付きengine表記は二つの別実行を意味する。各プロトコルと失敗例を結果ディレクトリに保存している。工学比較と自然さの認定を混同しない。

生成とAI評価を追加せずに成果物と旧封印を検査するには、同じPythonで`verify.py`を実行する。
