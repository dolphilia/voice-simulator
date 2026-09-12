# `synth-lab` から移管した資料

このディレクトリは、旧リポジトリ [`dolphilia/synth-lab`](https://github.com/dolphilia/synth-lab) で作成された調査メモを、Voice Simulator の参考資料として保存する領域である。

## 出典と状態

- 移管元: `/Users/dolphilia/github/synth-lab`
- 移管元コミット: `a6c5a5ef7908973f09ade4e3405f03aa6eb21691`（2026-04-14）
- 移管日: 2026-08-25
- 対象: 移管元で Git 管理されていた `docs/notes/*.md` 全 24 ファイル
- 編集: Notebook への相対リンクだけを新しい配置へ合わせた。本文は原則として移管時点の内容を保持している

これらは探索段階の調査メモであり、Voice Simulator の正式な設計判断や検証済みの結論ではない。記載された仕様、比較、コード、外部リンクは、採用前に一次資料と再現実験で確認すること。移管元にライセンス文書はなかったため、外部由来の記述・コード・図表を再利用する場合は、各出典の権利条件も改めて確認する。

Voice Simulator への適用範囲と優先度は [`docs/note/synth-lab-research-integration.md`](../../note/synth-lab-research-integration.md) にまとめている。

## 移管しなかったもの

- 旧ルート README、ディレクトリ方針、ローカル設定: 旧音楽アプリの運用情報であり、現リポジトリの方針と競合するため。必要な内容は旧方針資料として `notes/` 内に残っている
- `.venv/`、`.DS_Store`: 環境固有または生成物のため
- `research/data/` の WAV・PNG: 移管元で Git 管理されておらず、Notebook から再生成できる派生物のため。主要な図と数値は Notebook 出力に埋め込まれている
- 空のプレースホルダー: 現リポジトリの既存構成を使用するため

移管元にはアプリ実装やプロトタイプの Git 管理ファイルはなく、取り込むべき実装コードはなかった。

## 資料の分類

### 音声生成へ直接つながる資料

- [`synthesis-overview.md`](notes/synthesis-overview.md): 合成方式の索引と比較
- [`synthesis-classic.md`](notes/synthesis-classic.md): PSG、FM、PCM
- [`synthesis-subtractive.md`](notes/synthesis-subtractive.md): オシレーター、フィルター、エンベロープ、ウェーブテーブル
- [`synthesis-additive-modulation.md`](notes/synthesis-additive-modulation.md): 加算、FM/PM、AM/RM、PD、PWM
- [`synthesis-physical-spectral.md`](notes/synthesis-physical-spectral.md): DWG、Modal、FDTD、WDF、SMS、PSOLA など
- [`synthesis-advanced.md`](notes/synthesis-advanced.md): FOF/CHANT、連結、カオス、ニューラル方式など

### 生成音の解析・評価へ直接つながる資料

- [`audio-analysis-overview.md`](notes/audio-analysis-overview.md): 解析手法の索引
- [`audio-analysis-time-domain.md`](notes/audio-analysis-time-domain.md): RMS、ZCR、エンベロープなど
- [`audio-analysis-spectral.md`](notes/audio-analysis-spectral.md): FFT、STFT、LPC、MFCC など
- [`audio-analysis-pitch-rhythm.md`](notes/audio-analysis-pitch-rhythm.md): F0 推定、オンセット、リズム
- [`audio-analysis-advanced.md`](notes/audio-analysis-advanced.md): ラフネス、非調和性、位相、非線形解析など

### 候補モデルを広げる資料

- [`sound-from-physics-overview.md`](notes/sound-from-physics-overview.md): 物理・数学系手法の索引
- [`sound-from-fluid-dynamics.md`](notes/sound-from-fluid-dynamics.md): 流体音響、渦音、LBM
- [`sound-from-mechanics.md`](notes/sound-from-mechanics.md): 弾性体、非線形振動子、確率過程
- [`sound-from-mathematics.md`](notes/sound-from-mathematics.md): 変換理論、スパース表現、音色空間など
- [`sound-from-other-sciences.md`](notes/sound-from-other-sciences.md): WDF、蝸牛、Two-Mass Model など

### 周辺資料・旧アプリ固有資料

- [`pcm-sound-module-capacity.md`](notes/pcm-sound-module-capacity.md): PCM 音源モジュールの歴史的仕様調査。比較資料として保持するが、サンプル再生方式を最終音源へ採用する根拠にはしない
- [`overview.md`](notes/overview.md)、[`directory-structure.md`](notes/directory-structure.md)、[`research-themes.md`](notes/research-themes.md)、[`tech-stack.md`](notes/tech-stack.md): 旧プロジェクトの方針と構成。現プロジェクトの方針としては扱わない
- [`plugin-development-juce.md`](notes/plugin-development-juce.md)、[`scriptable-synth-architecture.md`](notes/scriptable-synth-architecture.md)、[`scriptable-synth-juce-cmajor-monaco.md`](notes/scriptable-synth-juce-cmajor-monaco.md): 中断した音楽アプリの設計資料。将来ネイティブ UI や DSP 実行基盤を検討する場合の参考に限定する

## Notebook

調査に対応する探索 Notebook は [`research/notebooks/imported-synth-lab/`](../../../research/notebooks/imported-synth-lab/) に分離して保存している。正式な実験へ利用する場合は、必要な処理を `research/experiments/` または再利用可能な CLI へ移し、入力・評価方法・結果を改めて記録する。
