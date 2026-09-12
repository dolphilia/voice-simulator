# 音合成手法 — 概要と索引

## 手法マップ

```
音合成手法
│
├── クラシカルなデジタル音源             → synthesis-classic.md
│   ├── PSG音源（矩形波・LFSR ノイズ）
│   ├── FM音源（DX7, OPL）
│   └── PCM / サンプリング音源
│
├── サブトラクティブ合成                 → synthesis-subtractive.md
│   ├── VCO（サイン・矩形・鋸歯・三角）
│   ├── VCF（Moog ラダー・SVF・Sallen-Key）
│   ├── VCA + ADSR エンベロープ
│   ├── LFO による変調
│   └── ウェーブテーブル合成
│
├── アディティブ・変調系合成             → synthesis-additive-modulation.md
│   ├── アディティブ合成（ハモンドオルガン等）
│   ├── FM / PM 合成
│   ├── AM 合成 / リングモジュレーション
│   ├── Phase Distortion（Casio CZ）
│   ├── PWM（パルス幅変調）
│   └── ベクターシンセシス
│
├── 物理モデリング・スペクトル・グラニュラー → synthesis-physical-spectral.md
│   ├── Karplus-Strong（弦）
│   ├── DWG（Digital Waveguide）
│   ├── FDTD・WDF
│   ├── Modal 合成（共鳴モード）
│   ├── 位相ボコーダー（Phase Vocoder）
│   ├── SMS（Spectral Modeling Synthesis）
│   ├── PSOLA
│   └── グラニュラー合成
│
└── 高度・現代的な合成手法              → synthesis-advanced.md
    ├── Formant 合成（FOF / CHANT）
    ├── Concatenative 合成（コーパスベース）
    ├── Feedback FM / カオティックオシレーター
    └── ニューラル合成（WaveNet・NSynth・DDSP）
```

---

## 6 つの設計哲学による分類

| 設計哲学 | 手法 |
|---|---|
| **減算**（豊富な倍音から削る） | サブトラクティブ（VCO+VCF）、PCM+フィルター |
| **加算**（正弦波を積み重ねる） | アディティブ合成、ハモンドオルガン |
| **変調**（オシレーター同士を掛け合わせる） | FM/PM、AM/RM、PD、PWM |
| **断片の組み合わせ** | グラニュラー、Concatenative、PCM ループ |
| **物理現象のモデル化** | Karplus-Strong、DWG、Modal、FDTD |
| **スペクトル直接操作** | 位相ボコーダー、SMS、DDSP |

---

## 手法の特性比較表

| 合成手法 | 計算コスト | 音色多様性 | 制御しやすさ | 代表的な用途 |
|---|---|---|---|---|
| PSG | 極低 | 低 | 高 | チップチューン、レトロゲーム |
| FM | 低〜中 | 高 | 中（習熟要） | ブラス、EP、ベル、デジタル系 |
| PCM | 中 | 中（素材依存） | 高 | リアルな楽器音 |
| サブトラクティブ | 低〜中 | 中 | 高 | アナログ系リード・パッド |
| ウェーブテーブル | 低 | 高 | 高 | モーフィング系、モダンシンセ |
| アディティブ | 中〜高 | 非常に高 | 中 | 精密な音色設計、オルガン |
| グラニュラー | 中〜高 | 非常に高 | 中 | テクスチャー、タイムストレッチ |
| Karplus-Strong / DWG | 中 | 中 | 中 | 弦楽器・管楽器モデル |
| Modal | 低〜中 | 中 | 高 | 打楽器・打鍵楽器 |
| 位相ボコーダー | 高 | 非常に高 | 中 | タイムストレッチ、モーフィング |
| SMS | 高 | 高 | 高 | 音声変換、楽器モデリング |
| AM / RM | 極低 | 中 | 高 | 金属・ベル系、特殊効果 |
| Phase Distortion | 低 | 中〜高 | 中 | アナログライクなデジタル音 |
| Formant（FOF） | 中 | 中 | 高 | 音声合成、歌声 |
| DDSP | 中 | 高 | 高 | ティンバー変換、新楽器 |
| WaveNet | 非常に高 | 非常に高 | 低 | 高品質 TTS |

---

## Python ライブラリ一覧

| ライブラリ | 用途 |
|---|---|
| numpy / scipy | 基本的な DSP 演算、フィルター設計 |
| scipy.signal | 窓関数・フィルター・信号生成 |
| soundfile / sounddevice | 音声 I/O、リアルタイム再生 |
| librosa | 音響分析・位相ボコーダー・特徴量抽出 |
| pedalboard（Spotify） | 高速 DSP 処理 |
| ddsp（Google Magenta） | 微分可能 DSP フレームワーク |
| sms-tools（MTG UPF） | SMS スペクトルモデリング |
| mido / python-rtmidi | MIDI I/O |

---

## 関連ノート

- [クラシカルなデジタル音源（PSG・FM・PCM）](synthesis-classic.md)
- [サブトラクティブ合成・ウェーブテーブル](synthesis-subtractive.md)
- [アディティブ合成・変調系合成](synthesis-additive-modulation.md)
- [物理モデリング・スペクトル・グラニュラー](synthesis-physical-spectral.md)
- [高度・現代的な合成手法](synthesis-advanced.md)
- [研究テーマ一覧](research-themes.md)
