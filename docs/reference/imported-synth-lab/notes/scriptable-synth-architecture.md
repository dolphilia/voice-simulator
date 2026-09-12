# スクリプタブルシンセの設計

コードエディタを UI 内に持ち、ユーザーが書いたスクリプトで発音・エフェクト処理を制御する VST3 ソフトシンセの設計についてのまとめ。

## 目標とする機能

- プラグイン UI 内にコードエディタを持つ
- エディタに書いたスクリプトが DAW からの MIDI・オーディオ信号を受け取る
- スクリプトに記述したロジックに従って発音・フィルター処理を行う

**結論：技術的に実現可能。同様のコンセプトのプロジェクトが複数存在する。**

---

## 実在する参照実装

| プロジェクト | スクリプト言語 | 概要 |
|---|---|---|
| **Protoplug** | LuaJIT | JUCE 製 VST/AU。UI 内エディタで書いた Lua スクリプトが DSP 処理を担う |
| **Amati** | Faust | JUCE 製 VST/CLAP。Faust コードを書いて Compile ボタンで即座に DSP が切り替わる |
| **Blue Cat's Plug'n Script** | AngelScript | 商用 VST。スクリプトで音声処理・MIDI 処理・UI を完全制御 |
| **HISE** | HiseScript (JS 派生) | JUCE 製サンプラー開発フレームワーク。スクリプトで MIDI イベントを処理 |
| **nih-faust-jit** | Faust | Rust + NIH-plug。libfaust JIT で .dsp ファイルをロード・実行 |
| **FaustVst** | Faust | Faust コードを動的ロード・コンパイル・編集できる VST3 |

---

## コンポーネント 1：コードエディタ UI

### JUCE 標準：`CodeEditorComponent`

- シンタックスハイライト対応（カスタムトークナイザー実装可能）
- `LuaTokeniser` が JUCE に標準内蔵
- DAW 互換性が高い
- UI の洗練度は基本的（オートコンプリート・複数カーソルなし）

### WebView + Monaco / CodeMirror（JUCE 8 以降）

- VSCode 相当の編集体験が実現できる
- JUCE 8 の `WebBrowserComponent` で C++ バックエンドと双方向通信可能
- **課題：** キーイベントが WebView に吸収され、DAW のキーボードショートカット（スペースバーなど）が効かなくなる問題あり。FL Studio on macOS でのバグも報告されている

| アプローチ | UI 品質 | DAW 互換性 | 実装コスト |
|---|---|---|---|
| `CodeEditorComponent` | 基本的 | 高 | 低 |
| WebView + Monaco | VSCode 相当 | 中（要対処） | 中〜高 |
| WebView + CodeMirror | 良好 | 中（要対処） | 中 |

---

## コンポーネント 2：スクリプトのコンパイル・実行

### コンパイル戦略の比較

| 方式 | 適用例 | コンパイル待ち | 性能 |
|---|---|---|---|
| **JIT（libfaust + LLVM）** | Amati、FaustVst | 数十〜数百 ms | 最高（C++ 相当） |
| **JIT（Cmajor）** | cmaj::SinglePatchJITPlugin | 数十〜数百 ms | 最高 |
| **トレース JIT（LuaJIT）** | Protoplug | なし（ウォームアップ） | 高 |
| **インタープリタ（Faust FBC）** | faust2clap ホットリロードモード | なし | 中 |

### スクリプト適用のタイミング

- **明示的なコンパイルボタン**（Amati 方式）— シンプルで安全
- **保存時に自動コンパイル**（Blue Cat 方式、Cmajor）
- **入力しながらライブコンパイル**（Protoplug の Live Mode）

---

## コンポーネント 3：オーディオスレッドとの安全な統合

スクリプトの再コンパイル中もオーディオを途切れさせないための仕組みが最大の技術的課題。

### アトミックポインタスワップによる解決

```
[GUI スレッド / バックグラウンドスレッド]
  スクリプト編集 → バックグラウンドでコンパイル
  → 新 DSP オブジェクトを生成
  → atomic_ptr.store(new_dsp, memory_order_release)

[オーディオスレッド]
  processBlock() {
    DSPObject* dsp = atomic_ptr.load(memory_order_acquire);
    dsp->process(buffer, midiEvents);  // 旧コードで継続、切り替えは瞬時
  }
```

旧オブジェクトの解放は GUI スレッドが担う。切り替えはアトミック 1 命令なので音切れが起きない。

### ノード状態の保持（synfx-dsp-jit のアプローチ）

DSP ノードにユニーク ID を付与し、再コンパイル時にフィルター係数やバッファなどの状態を引き継ぐことで、リロード時の音切れ・パラメータ消失を防ぐことができる。

---

## 推奨スタック（目的別）

### 手軽に始める → JUCE + LuaJIT + `CodeEditorComponent`

- Protoplug をそのまま参照できる
- LuaJIT ランタイムが小さくデプロイが容易
- Apple Silicon（AArch64）の対応状況に注意

### 高品質な DSP → JUCE + Faust（libfaust） + `CodeEditorComponent`

- 生成コードの実行性能が最高水準
- `juce_faustllvm` モジュールで主要インフラが揃っている
- バイナリサイズが大きい（LLVM 含め 100MB 超）

### モダンな開発体験 → JUCE + Cmajor + WebView（Monaco）

- Cmajor は JUCE 作者設計の DSP 言語。C に近い構文で学習コストが低い
- `cmaj::SinglePatchJITPlugin` でライブリロードを公式サポート
- Monaco により VSCode 相当のエディタ体験
- エコシステムはまだ発展途上

---

## 主な技術的課題と対処策

| 課題 | 対処策 |
|---|---|
| コンパイル中のオーディオ中断 | バックグラウンドコンパイル + アトミックスワップ |
| スクリプトのバグで DAW ごとクラッシュ | AngelScript / Wasm の VM サンドボックスを採用 |
| WebView のキーイベントが DAW に届かない | `CodeEditorComponent` で回避、または個別対処 |
| Faust + LLVM のバイナリサイズ（100MB 超） | インタープリタバックエンドのみ使用、または Cmajor / LuaJIT で代替 |
| LuaJIT の GC ポーズ | GC 手動制御・ホットパスでのアロケーション禁止 |

---

## ライブコーディング環境からの設計教訓

| 環境 | 設計の参考点 |
|---|---|
| **SuperCollider** | scsynth（オーディオサーバー）と sclang（クライアント）を分離し OSC で通信。スクリプト変更がオーディオスレッドに直接触れない |
| **Extempore** | Scheme（制御）と xtlang（LLVM JIT 型低レベル言語）の 2 言語統合。オーディオレートコードを動的変更可能 |
| **TidalCycles** | パターン変更を OSC メッセージで伝達。UI と DSP の明確な分離 |

---

## 参考プロジェクト

| プロジェクト | URL |
|---|---|
| Protoplug | https://github.com/pac-dev/protoplug |
| Protoplug fork | https://github.com/Sin-tel/protoplug |
| Amati | https://github.com/glocq/Amati |
| juce_faustllvm | https://github.com/olilarkin/juce_faustllvm |
| pMix2 | https://github.com/olilarkin/pMix2 |
| nih-faust-jit | https://github.com/YPares/nih-faust-jit |
| FaustVst | https://github.com/mikeoliphant/FaustVst |
| faust2clap | https://github.com/cucuwritescode/faust2clap |
| Blue Cat's Plug'n Script | https://www.bluecataudio.com/Products/Product_PlugNScript/ |
| synfx-dsp-jit | https://github.com/WeirdConstructor/synfx-dsp-jit |
| Cmajor | https://cmajor.dev |
| HISE | https://hise.dev |

---

## 関連ノート

- [JUCE による VST3 プラグイン開発](plugin-development-juce.md)
- [技術スタック](tech-stack.md)
- [プロジェクト概要](overview.md)
