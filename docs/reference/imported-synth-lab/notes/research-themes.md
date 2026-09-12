# 研究テーマ

シンセサイザーに関わることであれば何でも研究テーマとすることができる。以下は主要なテーマの一覧。

## 音の生成

音合成の手法を幅広く扱う。詳細な調査結果は以下のノートにまとめてある。

→ **[synthesis-overview.md](synthesis-overview.md)** — 全手法の概要・索引・比較表

| カテゴリ | 手法 | 詳細ノート |
|---|---|---|
| クラシカルなデジタル音源 | PSG音源、FM音源（DX7/OPL）、PCM/サンプリング | [synthesis-classic.md](synthesis-classic.md) |
| サブトラクティブ合成 | VCO（波形4種）、VCFフィルター各種、ADSR、LFO | [synthesis-subtractive.md](synthesis-subtractive.md) |
| ウェーブテーブル合成 | テーブルスキャン・モーフィング（PPG Wave, Serum） | [synthesis-subtractive.md](synthesis-subtractive.md) |
| アディティブ・変調系 | アディティブ、FM/PM、AM/RM、Phase Distortion、PWM、Vector | [synthesis-additive-modulation.md](synthesis-additive-modulation.md) |
| 物理モデリング | Karplus-Strong、DWG、Modal合成、FDTD、WDF | [synthesis-physical-spectral.md](synthesis-physical-spectral.md) |
| スペクトル合成 | 位相ボコーダー、SMS、PSOLA | [synthesis-physical-spectral.md](synthesis-physical-spectral.md) |
| 粒子ベース | グラニュラー合成（同期・非同期） | [synthesis-physical-spectral.md](synthesis-physical-spectral.md) |
| 高度・現代的手法 | Formant（FOF）、Concatenative、Feedback FM、DDSP、WaveNet | [synthesis-advanced.md](synthesis-advanced.md) |

## フィルターとエフェクト

| カテゴリ | テーマ例 |
|---|---|
| フィルター | ローパス・ハイパス・バンドパス、Moogラダーフィルター、SVFフィルター |
| 空間系エフェクト | リバーブ（畳み込み・アルゴリズム）、ディレイ |
| ダイナミクス系 | コンプレッサー、リミッター、エンベロープ整形 |
| ピッチ・変調系 | コーラス、フランジャー、フェイザー、ビブラート |
| 歪み系 | オーバードライブ、ビットクラッシャー、ウェーブシェイパー |

## 音の解析

生成した音を多角的に解析し、結果を画像や表として出力する。

| 手法 | 出力例 |
|---|---|
| 波形表示 | 時間領域の波形グラフ |
| スペクトル解析 | FFT スペクトル（周波数 vs 振幅） |
| スペクトログラム | 時間 × 周波数 × 強度のヒートマップ |
| エンベロープ解析 | ADSR カーブ、RMS エンベロープ |
| 知覚的特徴量 | MFCCなど |

## 参考資料の収集

役立つ論文・研究成果を定期的に調査してまとめる。収集した資料は `docs/notes/` に随時追加する。
