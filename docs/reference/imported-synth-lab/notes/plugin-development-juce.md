# JUCE による VST3 プラグイン開発

## JUCE とは

C++ でのオーディオプラグイン開発における業界標準フレームワーク。VST3・AU・AUv3・AAX・LV2 など主要プラグインフォーマットをすべて単一コードベースからビルドできる。Native Instruments・iZotope・Ableton など業界大手が採用。

### ライセンス

- **AGPLv3**（オープンソース準拠なら無償）
- **商用ライセンス**（クローズドソース配布には月額サブスクリプション）
- VST3 配布には Steinberg の無償 Distribution License が別途必要

### ビルドシステム

| ツール | 概要 |
|---|---|
| **CMake**（推奨） | 2020 年以降 JUCE 公式サポート。`juce_add_plugin()` で宣言的にプラグイン設定を記述 |
| **Projucer** | JUCE 独自の IDE/ビルドファイル生成ツール。現在は CMake が主流 |

```cmake
juce_add_plugin(MySynth
    PLUGIN_MANUFACTURER_CODE Manu
    PLUGIN_CODE Syn1
    FORMATS VST3 AU Standalone
    PRODUCT_NAME "My Synth"
)
```

---

## JUCE + スクリプト言語の組み合わせ

### 技術的実現可能性

**実現可能。実証済みの前例が複数存在する。**

| プロジェクト | スクリプト言語 | 概要 |
|---|---|---|
| **Surge XT** | Lua | 本番品質シンセ。フォーミュラモジュレーターに Lua を採用 |
| **Protoplug** | LuaJIT | リアルタイム DSP 処理を Lua スクリプトで記述できる VST/AU |
| **Amati** | Faust | Faust コードをエディタで書いて動的コンパイルする VST/CLAP |
| **HISE** | HiseScript (JS 派生) | サンプル音源開発フレームワーク。MIDI 処理をスクリプトで制御 |

### バインディングライブラリ（Lua の場合）

| ライブラリ | 特徴 |
|---|---|
| **sol2 (sol3)** | ヘッダオンリー・型安全・高パフォーマンス（C++14 以上） |
| **LuaBridge3** | ヘッダオンリー・依存なし。一部ベンチマークで sol2 を上回る |
| **Lua C API（生）** | 最低レベル・最高パフォーマンス。RT 安全設計に最も適合 |

---

## スクリプト言語の選択肢と比較

| 言語 | 実行性能 | DSP 特化 | 組み込み容易性 | RT 安全性 | サイズ |
|---|---|---|---|---|---|
| **LuaJIT** | 高 | なし | 高 | 要注意（GC 管理で対応可） | 小 |
| **Faust + libfaust** | 最高（C++ 相当） | 最高 | 中 | 高（コンパイル後は純 C++） | 大 |
| **Cmajor** | 最高 | 高 | 中 | 高 | 中 |
| **AngelScript** | 高 | なし | 高 | 高（VM サンドボックス） | 小 |
| **WebAssembly** | 中（約 2.5 倍オーバーヘッド） | なし | 低 | 最高 | 中 |

### 各言語の詳細

**Faust**
- 関数型 DSP 言語。libfaust + LLVM JIT により生成コードは C++ 相当の性能
- JUCE 統合モジュール: [juce_faustllvm (olilarkin)](https://github.com/olilarkin/juce_faustllvm)
- デプロイ課題: libfaust + LLVM でバイナリサイズが 100MB 超になる

**Cmajor**
- JUCE 作者 Julian Storer が設計した DSP 専用言語
- LLVM 18 ベース JIT。コンパイル後は JUCE C++ プロジェクトにエクスポート可能
- JUCE との親和性を公式サポート
- 前身の SOUL は ROLI 経営問題で廃止。Cmajor はその後継

**LuaJIT**
- Apple Silicon（AArch64）のネイティブ対応は 2.1 beta で改善中
- JUCE には `LuaTokeniser` が標準内蔵

---

## 最大の技術的課題：オーディオスレッド安全性

### 禁止事項（リアルタイムオーディオスレッド内）

- メモリアロケーション / デアロケーション
- ロック（mutex）
- I/O・システムコール
- **ガベージコレクション**

### Lua の GC ポーズ問題

標準 Lua 5.x のインクリメンタル GC は 1〜数ミリ秒のポーズが発生する可能性がある。44.1kHz / 256 サンプルのバッファは約 5.8 ミリ秒しか許容時間がないため致命的。

**対処策:**
1. **Lua をオーディオスレッドに置かない**（最も確実）
2. GC を手動制御: `lua_gc(L, LUA_GCSTOP, 0)` でオーディオ中は停止し、アイドル時に分割実行
3. **LuaJIT を採用**（GC ステップが短い）
4. ホットパス内でのオブジェクト生成を禁じるスクリプティング規約を設ける

---

## 推奨アーキテクチャ

```
[GUI スレッド]
  └── Lua（モジュール接続定義・GUI イベント・パラメータ設定）
        └── ロックフリーキューで通知
               ↓
[オーディオスレッド]
  └── C++ DSP エンジン（JUCE）← スクリプトは介入しない
```

**Lua はコントロール層・設定層に使い、DSP ループは C++ で動かす**のが安全で実績のある設計。

---

## 参考プロジェクト

| プロジェクト | URL |
|---|---|
| JUCE | https://github.com/juce-framework/JUCE |
| Surge XT | https://github.com/surge-synthesizer/surge |
| Protoplug | https://github.com/pac-dev/protoplug |
| Protoplug fork | https://github.com/Sin-tel/protoplug |
| Amati | https://github.com/glocq/Amati |
| juce_faustllvm | https://github.com/olilarkin/juce_faustllvm |
| pMix2 | https://github.com/olilarkin/pMix2 |
| Cmajor | https://cmajor.dev |
| sol2 | https://github.com/ThePhD/sol2 |
| LuaBridge3 | https://kunitoki.github.io/LuaBridge3/Manual.html |

---

## 関連ノート

- [スクリプタブルシンセの設計](scriptable-synth-architecture.md)
- [技術スタック](tech-stack.md)
- [プロジェクト概要](overview.md)
