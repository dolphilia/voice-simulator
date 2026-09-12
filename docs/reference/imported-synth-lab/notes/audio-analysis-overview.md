# 音の解析手法 — 概要と索引

## 手法マップ

```
音の解析手法
│
├── 時間領域                         → audio-analysis-time-domain.md
│   ├── RMS（実効音量）
│   ├── ZCR（ゼロ交差率）
│   ├── 振幅エンベロープ
│   └── その他（AMDF、尖度 等）
│
├── 周波数領域・時間-周波数領域       → audio-analysis-spectral.md
│   ├── FFT / DFT
│   ├── スペクトル特徴量
│   │   └── 重心・帯域幅・フラックス・ロールオフ・フラットネス
│   ├── STFT / スペクトログラム
│   ├── Mel スペクトログラム
│   ├── CQT（定Q変換）
│   ├── ウェーブレット変換（CWT）
│   ├── ガボール変換
│   ├── Wigner-Ville 分布
│   └── EMD / HHT（経験的モード分解）
│
├── 知覚・音色特徴量                  → audio-analysis-spectral.md
│   ├── MFCC
│   ├── LPC
│   ├── クロマ特徴量（Chroma）
│   └── Tonnetz
│
├── ピッチ・基本周波数推定            → audio-analysis-pitch-rhythm.md
│   ├── ACF（自己相関）
│   ├── YIN
│   ├── PYIN
│   ├── HPS（高調波積スペクトル）
│   ├── ケプストラム法
│   └── CREPE（深層学習）
│
├── リズム・テンポ解析                → audio-analysis-pitch-rhythm.md
│   ├── オンセット検出
│   ├── BPM推定
│   ├── ビートトラッキング
│   └── ダウンビート・小節解析
│
└── 高度・特殊な手法                  → audio-analysis-advanced.md
    ├── ラフネス（Roughness）
    ├── スペクトルエントロピー
    ├── 非調和性（Inharmonicity）
    ├── 位相スペクトル・グループ遅延
    ├── バイスペクトル
    └── 非線形解析（リアプノフ指数、フラクタル次元 等）
```

---

## 用途別・手法の選択指針

| 目的 | 推奨手法 |
|---|---|
| 音量・ダイナミクス解析 | RMS + 振幅エンベロープ |
| 音色の素早い特徴把握 | スペクトル重心・帯域幅・ロールオフ |
| 音色分類（機械学習） | MFCC（13〜40係数）+ Δ + ΔΔ |
| 音楽のキー・コード解析 | Chroma-CQT + Tonnetz |
| ピッチ推定（単音） | PYIN / CREPE |
| テンポ・ビート解析 | librosa.beat + madmom（高精度） |
| スペクトル詳細解析 | STFT（線形）/ CQT（音楽的） |
| 非定常・過渡現象の解析 | CWT（Morlet）/ EMD |
| 倍音構造・シンセ音色解析 | HPS + Inharmonicity + ラフネス |
| 協和・不協和の定量化 | Roughness（Sethares モデル） |
| リアルタイム処理 | ZCR + RMS + STFT（小窓） |
| 深層学習の入力 | Mel スペクトログラム / MFCC |
| 非線形系（FM・ウェーブシェーパー等）の解析 | バイスペクトル / リアプノフ指数 |

---

## 主要ライブラリ一覧

| ライブラリ | 主な用途 | 備考 |
|---|---|---|
| **numpy.fft / scipy.fft** | FFT計算 | 標準。scipy版は高速 |
| **scipy.signal** | 汎用信号処理 | STFT、フィルタ、Hilbert変換 |
| **librosa** | 音楽・音声解析全般 | 最も包括的。音楽向け機能が豊富 |
| **pywavelets (PyWt)** | ウェーブレット変換 | DWT/CWT |
| **ssqueezepy** | 高精度CWT / WVD | スクイーズ変換 |
| **madmom** | リズム解析 | ビート・オンセット検出（RNN系） |
| **crepe** | ピッチ推定 | 深層学習F0推定 |
| **nolds** | 非線形解析 | リアプノフ指数、フラクタル次元 |
| **emd-signal** | EMD/HHT | 非定常信号分解 |
| **essentia** | MIR全般 | C++ベースで高速。TensorFlow統合 |
| **aubio** | リアルタイム処理 | オンセット・ピッチ・テンポ |

> 研究環境（`.venv`）には numpy / scipy / matplotlib / soundfile が導入済み。  
> librosa 以降は必要になったタイミングで追加インストールする。

---

## 関連ノート

- [時間領域の解析手法](audio-analysis-time-domain.md)
- [スペクトル・時間周波数・知覚特徴量](audio-analysis-spectral.md)
- [ピッチ推定・リズム解析](audio-analysis-pitch-rhythm.md)
- [高度・特殊な解析手法](audio-analysis-advanced.md)
- [音の解析 実践ノートブック](../../../../research/notebooks/imported-synth-lab/01_audio_analysis.ipynb)
