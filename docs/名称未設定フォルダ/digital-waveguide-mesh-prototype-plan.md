# 計画書：デジタルウェーブガイドメッシュ・プロトタイプ（第4候補）

## 概要

第4プロトタイプ候補として、**デジタルウェーブガイドメッシュ（Digital Waveguide Mesh; DWM）** を用いた声道音響モデルを検討する。

ここでは、これまでの

- 第1プロトタイプ: フォルマントフィルタ
- 第2プロトタイプ: 多管チューブ
- 第3プロトタイプ: 改良版波動管

に続く次の候補として、**1D の管モデルを 2D の波動伝搬へ拡張する** ことを狙う。

ただし、第4プロトタイプ以降はリアルタイム性を必須としない方針であるため、最初から AudioWorklet ベースでは進めない。まずは **オフライン生成前提** で、

1. `research/` 側で数値モデルを成立させる
2. 音響的な妥当性を確認する
3. 必要なら `web/` 側へオフライン再生 UI として移植する

という順で進める。

## この方式を選ぶ理由

デジタルウェーブガイドメッシュは、現在の 1D 波動管よりも以下の点で拡張性がある。

- 2D 形状を直接扱える
- 分岐や局所的な広がりを入れやすい
- 側枝共鳴や空間的な偏りを表現しやすい
- FDTD / FEM よりは軽量で、探索段階の試作に向く

一方で、FDTD / FEM より実装が比較的軽く、1D 波動管から段階的に発展させやすい。

そのため、本プロジェクトにおける位置づけとしては、

- **1D モデルの次の段階**
- **3D 高忠実度計算へ進む前の中間層**

として自然である。

## 目標

このプロトタイプでまず目指すのは、次の状態である。

1. 2D メッシュ上で音波が安定に伝搬する
2. 声道形状の違いによって共鳴特性が変わる
3. 日本語 5 母音に相当する形状差で、スペクトル差またはフォルマント差が観察できる
4. オフライン生成された波形を再生・保存できる
5. 1D 波動管と比較して、どこが改善し、どこが重くなるかを判断できる

## 最初に採用する前提

### 1. まずは 2D に限定する

最初から 3D へは進まない。

理由:

- 3D は計算量とデータ準備コストが大きい
- 2D でも形状依存の共鳴差を確認するには十分
- まずは数値安定性と音響差の有無を確認したい

### 2. まずは三角メッシュを第一候補にする

メッシュトポロジーにはいくつかの選択肢があるが、最初の検証では **三角メッシュ** を第一候補とする。

理由:

- 方向依存性が矩形格子より比較的小さくなりやすい
- 文献上でも声道音響での採用例がある
- 2D 形状との整合を取りやすい

ただし、実装難度を下げるために最初の最小実験だけは矩形格子で始めてもよい。その場合でも、早い段階で三角メッシュへ移行する。

### 3. オフライン生成前提にする

UX は以下を想定する。

```
形状またはプリセットを選ぶ → 生成ボタン → 数秒計算 → 再生 / WAV 保存
```

リアルタイム更新は必須にしない。

### 4. 音源は最初は簡易でよい

最初の段階では、音源に高度な非線形声帯モデルを入れない。

候補:

- インパルス
- 短いパルス列
- Rosenberg 系の簡易グロッタル波形

まずは **共鳴の確認** を優先し、その後 LF や 2 質量モデルへの接続を検討する。

## 実装場所の方針

### フェーズ1は `research/` で行う

最初の DWM 実装は `research/` 側で行う。

理由:

- NumPy 配列演算で実装しやすい
- スペクトル確認、安定性確認、可視化がしやすい
- デバッグや式の検証が Web より速い

想定配置:

```text
research/
├── notebooks/
│   └── digital-waveguide-mesh-prototype.ipynb
└── scripts/
    ├── dwm_mesh.py
    ├── dwm_solver.py
    ├── dwm_shapes.py
    └── dwm_analysis.py
```

### フェーズ2で `web/` へ移すか判断する

研究側で有望と判断できた場合のみ、`web/prototypes/` にオフライン生成型 UI を作る。

想定候補:

```text
web/prototypes/digital-waveguide-mesh/
```

## モデルの最小構成

### 幾何

最初のモデルでは、声道を 2D の閉領域として表現する。

最低限必要な要素:

- グロッタル端
- 口唇開口
- 壁境界
- 形状プリセット

最初は単純化して、

- 上下対称
- 断面の厚みは一定
- 鼻腔なし

とする。

### 音響

各メッシュ点または各接続辺で散乱を行い、時間更新で圧力波を伝搬させる。

最初に必要な機能:

- 1 サンプルごとの更新
- 壁境界条件
- 開口端放射の簡易近似
- 数値損失または物理損失の導入

### 解析

出力波形に対して最低限以下を確認する。

- 波形
- FFT スペクトル
- スペクトログラム
- 主要ピーク周波数
- 1D 波動管との比較

## 形状表現の方針

最初の DWM では、連続的な自由描画よりも **プリセット + 少数パラメータ変形** を優先する。

候補:

- 5 母音の 2D 近似形状
- 前舌 / 後舌
- 狭窄位置
- 開口度
- 唇開口

最初から複雑な UI 編集は作らず、まずは形状差が音響差になることを確認する。

## 最初の成功判定

このプロトタイプは、少なくとも次の条件を満たしたら「次に進む価値あり」とみなす。

1. 数値発散せず、安定して数百 ms 以上の波形を生成できる
2. `/a/` と `/i/` の差がスペクトル上ではっきり見える
3. 1D 波動管と比べて、少なくとも一部の形状で別のピーク / ディップ構造が現れる
4. 生成時間が研究用途として許容範囲にある

## 非目標

この段階では以下をやらない。

- 3D メッシュ
- フル生体力学モデル
- 鼻腔結合
- 摩擦音・乱流の本格導入
- リアルタイム音声生成
- 最終 UI の作り込み

## 実装フェーズ

### フェーズ1：最小の数値実験

目的:

- DWM 自体の安定性と基礎特性を確認する

作るもの:

- 単純な直管または矩形共鳴器
- インパルス応答生成
- FFT による共鳴ピーク確認

完了条件:

- 既知の単純共鳴器で、おおまかな共鳴位置が理論値と整合する

### フェーズ2：2D 声道形状プリセット

目的:

- 声道らしい形状差が音響差になるかを見る

作るもの:

- 5 母音相当の簡易 2D 形状
- グロッタル入力からの応答生成
- 出力波形の保存

完了条件:

- 少なくとも `/a/` と `/i/` の差がスペクトル上で安定に確認できる

### フェーズ3：損失と境界条件の改善

目的:

- 不自然なリンギングや反射を減らし、比較に耐える応答へ近づける

作るもの:

- 壁損失の簡易モデル
- 開口端放射の近似
- 必要なら吸音境界または損失層

完了条件:

- 出力スペクトルが極端に人工的でなくなり、形状差がより安定に見える

### フェーズ4：1D 波動管との比較

目的:

- DWM を採用する意味を確認する

作るもの:

- 同じ母音プリセットに対応する 1D / 2D モデル比較
- フォルマント / スペクトルピーク / ディップ構造の比較
- 計算時間比較

完了条件:

- DWM の利点とコストを文章で説明できる

### フェーズ5：Web 移植判断

目的:

- 次段階の実装先を決める

判断基準:

- 研究側で差が十分見えるか
- 計算時間が許容範囲か
- UI を作る価値があるか

分岐:

- 有望なら `web/prototypes/digital-waveguide-mesh/` を作る
- 重すぎる / 効果が薄いなら、FDTD / FEM 検証へ進む

## 技術的な論点

実装前に整理しておくべき論点は次の通り。

### 1. 格子依存性

矩形格子では方向依存の分散誤差が出やすい。三角メッシュや改良散乱則をどう扱うかは重要な論点になる。

### 2. サンプルレートと空間解像度

時間刻みと空間刻みの関係が安定性と計算量を大きく左右する。最初に現実的な分解能を決める必要がある。

### 3. 境界条件

壁を完全反射にするか、損失を入れるか、口端放射をどう近似するかで結果が大きく変わる。

### 4. 形状データの粒度

最初の段階では高精度 MRI 形状ではなく、母音差を見るための簡易形状で十分かどうかを見極める必要がある。

### 5. 励振源の複雑さ

最初はインパルスや簡易グロッタル波でよいが、最終的には音源側の改善が必要になる可能性が高い。

## 推奨する最初の具体案

現時点で最も妥当な最初の具体案は次の通り。

### 案 A

- 実装場所: `research/`
- 言語: Python + NumPy
- 形状: 2D、上下対称、母音プリセット 5 種
- 格子: まず単純格子で検証、その後三角メッシュへ移行
- 音源: インパルス → 簡易グロッタル波
- 出力: WAV 保存、FFT とスペクトログラム確認

### この案の利点

- 実装が最も速い
- 失敗しても知見が残る
- 数値安定性と音響差を先に検証できる
- Web 移植の是非を後から判断できる

## この段階で想定する成果物

最低限の成果物は次の 4 つである。

1. `digital-waveguide-mesh-prototype.ipynb`
2. DWM コアスクリプト
3. 5 母音プリセットの 2D 形状定義
4. 比較メモ（1D 波動管 vs DWM）

## `research/` に置く最初のファイル設計

ここでは、最初に作るノートブックとスクリプトを、責務ごとに分解して定義する。

基本方針は次の通り。

- ノートブックは「実験の入口・可視化・比較」に集中させる
- 数値計算ロジックは `research/scripts/` に切り出す
- 最初から巨大なモジュールにせず、小さく責務分離する
- 将来 Web 側へ移植しやすいよう、I/O を単純な配列中心にする

### 1. 最初のノートブック

#### `research/notebooks/digital-waveguide-mesh-prototype.ipynb`

このノートブックを、DWM 研究の最初の入口にする。

役割:

- DWM 実験全体のランナー
- 形状プリセットの選択
- ソルバ実行
- 波形 / スペクトル / スペクトログラム表示
- 1D 波動管との比較表示
- 生成 WAV の保存

このノートブックでは、重い実装を書き込まない。計算ロジックはすべて `research/scripts/` から import する。

#### ノートブックの想定セクション

1. 目的と前提
2. 依存ライブラリの import
3. 実験パラメータ設定
4. 形状プリセットの読み込み
5. メッシュ生成
6. 音源生成
7. ソルバ実行
8. 出力波形の可視化
9. FFT / スペクトログラム表示
10. 1D 波動管との比較
11. WAV 保存
12. 所感メモ

### 2. 最初のスクリプト群

最初の段階では、以下の 5 ファイル構成を推奨する。

```text
research/scripts/
├── dwm_config.py
├── dwm_shapes.py
├── dwm_mesh.py
├── dwm_sources.py
├── dwm_solver.py
└── dwm_analysis.py
```

### `research/scripts/dwm_config.py`

役割:

- 実験で共通に使う定数定義
- デフォルトパラメータの一元管理

最初に持つもの:

- サンプルレート
- 音速
- 空間刻み `dx`
- 時間刻み `dt`
- 生成秒数
- デフォルト F0
- 損失係数の初期値
- 出力サンプル位置の既定値

想定 API:

```python
DEFAULT_SAMPLE_RATE
DEFAULT_DURATION_SEC
DEFAULT_SOUND_SPEED
DEFAULT_GRID_STEP_M
DEFAULT_F0
DEFAULT_LOSS

def make_default_config() -> dict: ...
```

### `research/scripts/dwm_shapes.py`

役割:

- 2D 声道形状プリセットの定義
- パラメトリックな簡易変形

最初に持つもの:

- `/a/ /i/ /u/ /e/ /o/` の 2D 近似輪郭
- 直管や単純共鳴器などの検証用形状
- 形状をグロッタル端・口端付きのポリゴンとして返す関数

最初の段階では、輪郭は「少数制御点の 2D ポリライン」または「ポリゴン頂点列」でよい。

想定 API:

```python
def make_uniform_tube_shape(length_m: float, width_m: float) -> dict: ...
def make_vowel_shape(vowel: str) -> dict: ...
def list_available_shapes() -> list[str]: ...
```

返り値の最小仕様:

- `polygon`
- `glottal_port`
- `lip_port`
- `metadata`

### `research/scripts/dwm_mesh.py`

役割:

- 2D 形状から計算格子を作る
- 内部点・境界点・開口端を分類する
- 将来の三角メッシュ移行の受け皿を作る

最初は実装簡易化のため、内部表現は矩形格子でもよい。ただし API 名は格子方式に依存しすぎないようにする。

最初に持つもの:

- ポリゴン内外判定
- 格子点生成
- 隣接関係の構築
- 壁 / 開口 / 音源位置の分類

想定 API:

```python
def build_rect_mesh(shape: dict, dx: float) -> dict: ...
def get_probe_index(mesh: dict, which: str = "lip") -> int: ...
def summarize_mesh(mesh: dict) -> dict: ...
```

将来追加候補:

- `build_tri_mesh(...)`
- 格子依存誤差比較

### `research/scripts/dwm_sources.py`

役割:

- 励振源波形の生成

最初に持つもの:

- インパルス
- パルス列
- 簡易グロッタル波

ここは既存の `glottal-source-models.ipynb` で扱っている知見を後で移植できるように、波形生成を独立させる。

想定 API:

```python
def make_impulse(n_samples: int, index: int = 0, amplitude: float = 1.0) -> np.ndarray: ...
def make_pulse_train(n_samples: int, fs: int, f0: float, amplitude: float = 1.0) -> np.ndarray: ...
def make_simple_glottal_source(n_samples: int, fs: int, f0: float, amplitude: float = 1.0) -> np.ndarray: ...
```

### `research/scripts/dwm_solver.py`

役割:

- DWM の時間更新本体
- 圧力状態の保持
- 境界条件・損失の適用

このファイルが最初の数値コアになる。

最初に持つもの:

- 初期状態生成
- 1 ステップ更新
- N サンプル分の波形生成
- 口端または任意プローブ位置での観測

最小限の設計としては、まず「関数型」で十分である。クラス化は必要になってからでよい。

想定 API:

```python
def initialize_state(mesh: dict) -> dict: ...
def step_dwm(state: dict, mesh: dict, source_value: float, config: dict) -> dict: ...
def run_dwm(mesh: dict, source: np.ndarray, config: dict, probe: str = "lip") -> dict: ...
```

`run_dwm(...)` の返り値の最小仕様:

- `output`
- `pressure_history` または省略可能な内部状態ログ
- `meta`

### `research/scripts/dwm_analysis.py`

役割:

- 生成波形の評価と可視化補助

最初に持つもの:

- 波形プロット
- FFT スペクトル
- スペクトログラム
- 主要ピーク検出
- WAV 保存

想定 API:

```python
def compute_spectrum(audio: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]: ...
def compute_spectrogram(audio: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
def find_major_peaks(audio: np.ndarray, fs: int, n_peaks: int = 5) -> np.ndarray: ...
def save_wav(path, audio: np.ndarray, fs: int) -> None: ...
```

## 最初のノートブックで使う import イメージ

最初のノートブックから見た使い方は、概ね次のような形を想定する。

```python
from pathlib import Path

import numpy as np

from scripts.dwm_config import make_default_config
from scripts.dwm_shapes import make_vowel_shape
from scripts.dwm_mesh import build_rect_mesh, get_probe_index
from scripts.dwm_sources import make_impulse, make_simple_glottal_source
from scripts.dwm_solver import run_dwm
from scripts.dwm_analysis import compute_spectrum, compute_spectrogram, save_wav
```

## ノートブックの最初の実験シナリオ

最初のノートブックでは、機能を欲張らず、次の順で確認する。

### 実験 1: 直管

目的:

- ソルバが安定して動くか
- 理論共鳴と大きく外れていないか

入力:

- `make_uniform_tube_shape(...)`
- インパルス入力

確認:

- インパルス応答
- 主要ピーク

### 実験 2: 母音 2 種

目的:

- `/a/` と `/i/` のスペクトル差を見る

入力:

- `make_vowel_shape("a")`
- `make_vowel_shape("i")`

確認:

- FFT の差
- 主要ピーク位置の差

### 実験 3: 母音 5 種

目的:

- 5 母音に広げたときに差が安定するかを見る

確認:

- ピーク比較表
- WAV 保存と聴感確認

## 追加しないもの

最初のファイル設計では、以下はまだ切り出さない。

- 三角メッシュ専用ソルバ
- 高度な境界条件専用モジュール
- 1D 波動管比較専用モジュール
- 複雑なクラス階層

必要になったら後で増やす。

## 次段階で増える可能性のあるファイル

進展した場合、次のような分割を検討する。

```text
research/scripts/
├── dwm_boundary.py        # 放射・損失・吸音境界
├── dwm_tri_mesh.py        # 三角メッシュ構築
├── dwm_compare_1d.py      # 1D 波動管との比較
├── dwm_formants.py        # フォルマント / ピーク推定
└── dwm_export.py          # WAV / JSON / 図保存
```

## 最初の実装順

ファイル設計まで含めた、最初の着手順は次の通り。

1. `dwm_config.py`
2. `dwm_shapes.py`
3. `dwm_mesh.py`
4. `dwm_sources.py`
5. `dwm_solver.py`
6. `dwm_analysis.py`
7. `digital-waveguide-mesh-prototype.ipynb`

この順にすると、ノートブックは最後に薄く組み立てるだけで済む。

## 参考資料

- [Mullen, Howard, Murphy 2003, Digital waveguide mesh modelling of the vocal tract acoustics](https://pure.royalholloway.ac.uk/en/publications/digital-waveguide-mesh-modelling-of-the-vocal-tract-acoustics/)
- [Speed, Murphy, Howard 2013, Three-Dimensional Digital Waveguide Mesh Simulation of Cylindrical Vocal Tract Analogs](https://pure.royalholloway.ac.uk/en/publications/three-dimensional-digital-waveguide-mesh-simulation-of-cylindrica)
- [Gully et al. 2017, Articulatory text-to-speech synthesis using the digital waveguide mesh](https://pure.york.ac.uk/en/publications/articulatory-text-to-speech-synthesis-using-the-digital-waveguide)
- [Kröger 2022, Computer-Implemented Articulatory Models for Speech Production: A Review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9040071/)
- [プロトタイプ開発方針](../notes/prototype-direction.md)
- [フォルマントフィルタ / 波動管以外の手法メモ](../notes/alternative-synthesis-methods.md)

## 備考

この計画書は、第4プロトタイプ候補として DWM を検討するための具体化メモであり、実装中に

- 格子方式
- 形状表現
- 実装場所

を必要に応じて見直す前提の草稿である。
