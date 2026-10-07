# 独立音声合成: E0とP1接続

根拠は[実行計画](../../../docs/plans/independent-voice-synthesis-execution-plan.md)と[v3](../../../docs/note/independent-voice-synthesis-proposal-v3.md)。過去の音声・候補・プリセットは使用していない。

## 結果

E0はS1・S2の既知応答自己回復が不通過となり、規則に従って終了した。測定データの取得・適合は行っていない。公開測定についての結論はなく、合格解が存在しないという意味でもない。

点検探索29,268回、直接評価24回。追加開始点・追加モデル・公開測定への探索は0回。詳細は `results/e0/qualification/summary.json` と各適合の全評価履歴に保存している。

P1は既知K1のP5と解析LF音源による接続を実装し、固定3秒の音声を生成した。知覚回答は未収集であり、人声品質や改善を認定していない。

## 実行環境と操作

リポジトリルートで、既存環境 `research/.venv/bin/python` を使用した。Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1。独立環境を作る場合は本ディレクトリの `requirements.txt` を使う。

```bash
research/.venv/bin/python research/experiments/independent-voice-synthesis/run.py test
research/.venv/bin/python research/experiments/independent-voice-synthesis/run.py status
```

`qualify` はS1→S2の正式実験であり、既存結果があると再実行を拒否する。削除してやり直さない。`prepare-p1` も既存刺激を上書きしない。

`prepare-data`、`fit-e0`、`evaluate-e0` は点検不通過を検出し、終了コード2で拒否する。点検通過時の測定取得・適合・判定経路は未実装である。今回の結果からその経路を動かすことは許されない。CLI名が存在することを全分岐の実装完了とは扱わない。

WAV・画像・生入力はGit除外対象だが、音声hash・数値結果・回答は保持する。刺激の再現にはmanifestに保存した設定とコードを使い、既存の正式結果を変更しない。

## LFと信号の意味

LF式は[Fant・Liljencrants・Lin (1985)](https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf)の指数正弦と指数回帰の形式を用いる。周期で正規化した時間uについて、前半は `E0 exp(alpha u) sin(pi u/tp)`、後半は `-[exp(-epsilon(u-te))-exp(-epsilon(1-te))]/(epsilon ta)` とする。epsilonは終了時の接続、alphaは1周期の積分ゼロから解く。

倍音係数はこの式を解析積分する。実時間の微分係数へ `U0*F0` を掛け、非ゼロ周波数で `j2πf` を除して交流流量へ戻す。流量の原始関数の数値積分との一致を別途検証している。定数は `config/p1-connection.json` で試聴前に固定し、録音や耳による調整はしていない。原論文の式の確認には[COVAREP作者のLFスペクトル実装](https://github.com/covarep/covarep/blob/master/glottalsource/glottal_models/gfm_spec_lf.m)も参照したが、コードは移植せず区間指数積分から実装した。

P5の流量比の後で、一度だけ音圧変換を行う。帯域窓、フェード、レベル係数、有限長の帯域外漏れはmanifestに記録する。絶対SPLや発声開始・終了の自然さは評価していない。

探索オプションの意味は[SciPyの公式Powell仕様](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-powell.html)に従う。停止成功は回復精度の保証ではない。

## 成果物の用途

- `models.py`、`objective.py`、`p1_connection.py`: 数値検証済みの明示的な機構。最終方式への採用には別途要件確認が必要。
- `optimization.py`、`qualification.py`: この固定E0だけの探索・判定。汎用的な最適化性能は保証しない。
- `config/p1-listening-contract.md`: 1名・1刺激の印象確認。対照がないため改善やモデル間優劣は判定しない。
- `results/p1/fixed-k1/response-template.json`: 未回答の雛形。回答済み証拠ではない。

完了と未完了の対応は[実行報告](../../../docs/note/independent-voice-synthesis-execution-report.md)を参照する。
