# `synth-lab` 由来の探索 Notebook

旧 `synth-lab` の Git 管理下にあった探索 Notebook 6 本を、出力を含む研究記録として移管した。出典はコミット `a6c5a5ef7908973f09ade4e3405f03aa6eb21691`（2026-04-14）である。

移管時に、生成先を旧 `../data/` からこの領域専用の `artifacts/` へ変更し、Notebook のカーネル名を汎用の `python3` に置き換えた。また、既存出力に記録されていたローカル仮想環境の絶対パスはプレースホルダーへ置換した。解析コードと既存の図・数値出力はそれ以外変更していない。

## Notebook 一覧

- `00_environment_check.ipynb`: Python 音響解析環境、波形、FFT の確認
- `01_audio_analysis.ipynb`: Karplus–Strong 音を題材にした波形、FFT、スペクトログラム、RMS、ZCR、ケプストラム
- `02_mfcc.ipynb`: 合成音の MFCC、差分、類似度、PCA 相当の可視化
- `03_roughness.ipynb`: 臨界帯域モデルを使ったラフネスの探索
- `04_cqt_chroma.ipynb`: CQT、クロマ、コード検出の探索
- `05_pyin_pitch.ipynb`: PYIN、ACF、HPS、ケプストラムによる F0 推定の比較

これらは探索記録であり、Voice Simulator の検証済み実験ではない。実行済み出力には、移管元環境での警告や環境依存の表示が残る場合がある。数式、指標の実装、評価条件、ライブラリ API は、再利用前に確認すること。

## 実行

このディレクトリを作業ディレクトリとして Jupyter を起動する。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook
```

Notebook が生成する WAV と画像は `artifacts/` 以下へ保存する。このディレクトリは Git 管理しない。Notebook 内に埋め込まれた既存出力は、移管時点の研究記録として保持する。

正式な実験へ発展させる場合は、処理を `research/experiments/<experiment-name>/` または再利用可能な CLI へ移し、入力・由来・評価方法・結果を記録する。
