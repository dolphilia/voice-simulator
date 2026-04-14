# 計画書：声道チューブモデル プロトタイプ

## 概要

`web/prototypes/tube-vocal-tract/` に第2プロトタイプを実装する。
声道を複数セグメントの管（チューブ）として2Dで可視化し、ユーザーがその形状をインタラクティブに変形することで、幾何音響シミュレーションによりリアルタイムに母音音声を生成する。

---

## 目標

- 日本語5母音（/a/ /i/ /u/ /e/ /o/）を声道形状から生成できる
- 形状とフォルマントの関係をユーザーが体感的に理解できる
- 第1プロトタイプと同じのこぎり波励振源を流用する
- 幾何音響系（管内の1D波動伝搬モデル）でフォルマントを算出する

---

## 声道モデルの物理的根拠

### ソースフィルター理論

音声 = 声帯音源 × 声道伝達関数 × 放射特性

本プロトタイプでは：
- **音源**：のこぎり波オシレーター（第1プロトタイプと共通）
- **声道伝達関数**：多管チューブモデルにより算出
- **放射**：簡易的な口端放射係数を適用

### 多管チューブモデル（Kelly–Lochbaum モデル）

声道を N 本の等長の管（セクション）に分割し、各セクションに断面積 $A_k$ を割り当てる。隣接するセクション間での反射・透過は：

$$k_k = \frac{A_{k+1} - A_k}{A_{k+1} + A_k}$$

この反射係数を使った散乱行列で圧力波・体積速度波を時間領域で伝搬させる（デジタル波動管）。N = 16〜20 セクション、声道長 17cm を想定。

### 日本語母音の断面積プロファイル

参考文献（Chiba & Kajiyama 1942、splab.net モデル）をもとにした目安値：

| 母音 | 特徴 |
|------|------|
| /a/ | 全体的に広い、口腔中央が最大 |
| /i/ | 前方が狭く後方が広い（高前舌） |
| /u/ | 全体的に狭い（高後舌・唇音） |
| /e/ | /i/ に近いが中程度の開口 |
| /o/ | 後方が狭く前方が広い（後舌・円唇） |

---

## UI 設計

### レイアウト

```
┌──────────────────────────────────────────────┐
│  ヘッダー：タイトル ＋ Start/Stop ボタン     │
├──────────────────────────────────────────────┤
│                                              │
│   声道エディタ（Canvas）                     │
│                                              │
│   ←グロッタル側（声帯）   口側→            │
│                                              │
│   ████████░░░░░░░░████████                  │
│   ████████░░░░░░░░████████  ← 穴（管腔）    │
│   ████████░░░░░░░░████████                  │
│      ●       ●       ●   ← 制御点          │
│                                              │
├──────────────────────────────────────────────┤
│  母音プリセット：[あ] [い] [う] [え] [お]   │
├──────────────────────────────────────────────┤
│  ピッチ：  [────●────────] 80〜400 Hz       │
│  ゲイン：  [──────●──────] スライダー       │
├──────────────────────────────────────────────┤
│  スペクトラム表示（Canvas）                  │
│  ─────────────────────────────              │
└──────────────────────────────────────────────┘
```

### 声道エディタの操作

- 声道は水平方向の長方形として描画される
- 管腔（空洞）は中央の白い領域、壁（肉）は上下の灰色領域で表現
- **N個の制御点**（デフォルト8〜10点）が管腔の幅（＝断面積に比例）を定義
- 制御点をドラッグすることで、その位置の管腔幅を変更できる
- 制御点間はスプライン補間でなめらかに連結
- 上下対称のモデル（管腔幅のみ制御、非対称は将来対応）

### 母音プリセット

各母音ボタンを押すと、対応する断面積プロファイルへアニメーション補間しながら遷移する。プリセット値は物理測定値に基づく。

### スペクトラム表示

- リアルタイムに AnalyserNode から FFT を取得し Canvas に描画
- フォルマント周波数（F1〜F3）をピーク検出してオーバーレイ表示
- 横軸 0〜4000 Hz、縦軸 dB

---

## 技術スタック

| 項目 | 選択 |
|------|------|
| 言語 | TypeScript |
| ビルド | Vite |
| 音声 | Web Audio API（AudioWorkletProcessor） |
| 描画 | Canvas 2D API（ライブラリ不使用） |
| 依存関係 | なし（ゼロ依存） |

---

## モジュール構成

```
tube-vocal-tract/
├── package.json
├── tsconfig.json
├── index.html
└── src/
    ├── main.ts                  # エントリーポイント
    ├── styles.css
    ├── audio/
    │   ├── engine.ts            # TubeVoiceEngine：AudioContext管理・パラメータ制御
    │   ├── tube-model.ts        # Kelly–Lochbaum モデル：断面積→フィルター係数算出
    │   ├── vowel-presets.ts     # 5母音の断面積プロファイル定義
    │   └── worklet/
    │       └── tube-processor.ts  # AudioWorkletProcessor：リアルタイム波動伝搬
    └── ui/
        ├── app.ts               # UIルート・コンポーネント組み立て
        ├── tract-editor.ts      # 声道エディタ Canvas コンポーネント
        └── spectrum-view.ts     # スペクトラム表示 Canvas コンポーネント
```

### 主要クラス・責務

#### `tube-model.ts` — `TubeModel`
- 断面積配列 `areas: number[]` を受け取り、Kelly–Lochbaum 反射係数列を算出
- `computeReflectionCoefficients(areas) → k[]`
- `getFormantFrequencies(areas, sampleRate) → [F1, F2, F3]`（行列法またはパワースペクトル推定）

#### `audio/worklet/tube-processor.ts` — `TubeProcessor`（AudioWorkletProcessor）
- メインスレッドから反射係数を SharedArrayBuffer または postMessage で受信
- のこぎり波をソースとして時間領域で波動伝搬を計算
- 各サンプルごとに N 段の散乱を実行し出力信号を生成

#### `engine.ts` — `TubeVoiceEngine`
- AudioContext、AudioWorklet、AnalyserNode、GainNode を管理
- `setAreas(areas: number[])` → TubeModel 経由で係数を更新しワークレットへ送信
- `setFrequency(hz)` / `setGain(v)` でソースパラメータを制御

#### `ui/tract-editor.ts` — `TractEditor`
- Canvas 上に声道形状を描画（壁・管腔・制御点）
- ドラッグイベントで制御点の Y 位置を更新
- 変更時に `onAreasChange(areas: number[])` コールバックを呼び出す
- `setAreas(areas)` でプリセット遷移アニメーションを実行

#### `ui/spectrum-view.ts` — `SpectrumView`
- AnalyserNode の FFT データを requestAnimationFrame で取得・描画
- フォルマント位置をマーキング

---

## 実装フェーズ

### フェーズ1：音響コア
1. `tube-model.ts` の実装とユニットテスト（Node.js で算出値を検証）
2. `TubeProcessor`（AudioWorklet）の実装：のこぎり波 → 多管散乱 → 出力
3. `TubeVoiceEngine` の実装：基本的な start/stop、areas 更新

### フェーズ2：UI基盤
4. `TractEditor` Canvas の描画ロジック（静的な声道形状の描画）
5. 制御点のドラッグ操作の実装
6. `SpectrumView` の実装

### フェーズ3：統合と母音プリセット
7. `vowel-presets.ts` に5母音の断面積プロファイルを定義・調整
8. 母音プリセットボタンとアニメーション補間の実装
9. ピッチ・ゲインスライダーの接続

### フェーズ4：調整とチューニング
10. 各母音が自然に聞こえるよう断面積プロファイルを微調整
11. フォルマント周波数のオーバーレイ表示で視覚的フィードバックを確認
12. モバイルタッチ対応

---

## 参考資料

- Kelly, J. L., & Lochbaum, C. C. (1962). Speech synthesis. Proc. 4th ICA.
- Chiba, T., & Kajiyama, M. (1942). The Vowel: Its Nature and Structure.
- [声道モデル実物展示 - splab.net](https://splab.net/vocal_tract_model/ja/)
- Pink Trombone（Neil Thapen）のソース実装
- 第1プロトタイプ: `web/prototypes/vowel-formant-prototype/`
