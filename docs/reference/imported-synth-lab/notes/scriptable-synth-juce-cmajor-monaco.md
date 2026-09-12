# JUCE + Cmajor + Monaco によるスクリプタブルシンセ 実装詳細

コードエディタ内蔵 VST3 スクリプタブルシンセを、JUCE + Cmajor + WebView (Monaco) で構築する際の技術詳細と作業計画。

---

## 構成の全体像

```
[DAW]
  │  MIDI / オーディオ / パラメータ自動化
  ▼
[JUCE AudioProcessor (C++)]
  │  processBlock() ← オーディオスレッド
  │       └── cmaj::AudioMIDIPerformer (Cmajor JIT 実行)
  │
  │  PluginEditor ← GUI スレッド
  │       └── juce::WebBrowserComponent
  │                 └── Monaco Editor (HTML/JS)
  │                       ↕ withNativeFunction / emitEvent
  │                 [コンパイル要求 → バックグラウンドスレッド]
  │                       └── cmaj::Engine → 新 Performer 生成
  │                             └── processLock でスワップ
```

---

## コンポーネント 1: Cmajor C++ API

### 主要クラスと役割

| クラス | 役割 |
|---|---|
| `cmaj::Program` | Cmajor ソースコードのパース・保持 |
| `cmaj::Engine` | JIT コンパイラ本体。LLVM を内包 |
| `cmaj::Performer` | DSP 処理の実行インスタンス |
| `cmaj::AudioMIDIPerformer` | JUCE の AudioBuffer / MidiBuffer と直接接続する高レベルラッパー |
| `cmaj::Patch` | ファイルベースのホットリロード管理。内部でビルドスレッドを持つ |
| `cmaj::SinglePatchJITPlugin` | `juce::AudioPluginInstance` を継承。JUCE プラグインとして直接使える |

ヘッダはすべて `include/cmajor/` 以下にヘッダオンリーで提供される。JIT 実行は配布バイナリ `libCmajPerformer.dylib`（macOS）/ `CmajPerformer.dll`（Windows）が担い、LLVM の直接ビルドは不要。

### ソースコード文字列からのコンパイルフロー

```cpp
// バックグラウンドスレッドで実行する
bool recompile(const std::string& source) {
    cmaj::DiagnosticMessageList diags;
    cmaj::Program program;

    // 文字列からパース（第2引数はエラー表示用のファイル名）
    if (!program.parse(diags, "patch.cmajor", source))
        return reportError(diags);

    cmaj::Engine engine = cmaj::Engine::create();
    cmaj::BuildSettings settings;
    settings.setFrequency(sampleRate);
    settings.setMaxBlockSize(blockSize);
    settings.setOptimisationLevel(3);
    engine.setBuildSettings(settings);

    if (!engine.load(diags, program, {}, {}))
        return reportError(diags);

    if (!engine.link(diags))
        return reportError(diags);

    // 高レベルラッパーでビルド
    cmaj::AudioMIDIPerformer::Builder builder(engine, /*fifoSize=*/1024);
    builder.connectAudioOutputTo(outputEndpoint, {0, 1}, {0, 1});
    builder.connectMIDIInputTo(midiEndpoint);

    auto newPerformer = builder.createPerformer();
    newPerformer->prepareToStart();

    // オーディオスレッドと安全に交換
    {
        std::scoped_lock lock(processLock);
        std::swap(currentPerformer, newPerformer);
        // 旧パフォーマーは lock 解放後のデストラクタで破棄（非オーディオスレッド）
    }
    return true;
}
```

### パラメータの宣言（Cmajor 側）

```cmajor
processor MySynth {
    input value float gain
        [[ name: "Gain", min: 0.0, max: 1.0, init: 0.7, automatable: true ]];
    input value float cutoff
        [[ name: "Cutoff", min: 20, max: 20000, mid: 1000, unit: "Hz" ]];
    input event std::midi::Message midiIn;
    output stream float<2> audioOut;
    // ...
}
```

`cmaj::EndpointDetails::isParameter()` で name アノテーション付き value エンドポイントを自動検出できる。`cmaj_JUCEPlugin.h` の `Parameter` クラスがこれを `juce::HostedAudioProcessorParameter` にラップする。

### オーディオスレッドでの使用

```cpp
// processBlock() 内（JUCE の AudioProcessor から呼ばれる）
void processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi) {
    std::scoped_lock lock(processLock);  // 通常は無競合
    if (currentPerformer)
        currentPerformer->process(buffer, midi, /*replaceOutput=*/true);
}
```

### ホットリロード時の状態について

新しい Performer は初期状態から始まる（フィルタ係数・ディレイバッファはリセット）。`performer.reset()` メソッド（v1.0.2616 以降）で明示的なリセットも可能。ホットリロード時の音切れは仕様として受け入れる設計が現実的。

---

## コンポーネント 2: JUCE 8 WebBrowserComponent + Monaco

### C++ 側の設定

```cpp
// PluginEditor のコンストラクタ
webBrowser = juce::WebBrowserComponent(
    juce::WebBrowserComponent::Options{}
        .withNativeIntegrationEnabled()       // window.__JUCE__.backend を JS に注入
        .withResourceProvider([this](const auto& url) {
            return serveFile(url);            // BinaryData からファイルを返す
        })
        .withKeepPageLoadedWhenBrowserIsHidden()  // FL Studio バグ対策（必須）
        .withNativeFunction("compileCode", [this](auto& args, auto complete) {
            // JS から呼ばれる。args[0] が Cmajor ソースコード文字列
            std::string code = args[0].toString().toStdString();
            juce::Thread::launch([this, code, complete]() mutable {
                bool ok = proc.recompilePatch(code);
                complete(ok ? juce::var("OK") : juce::var("ERROR"));
            });
        })
        .withNativeFunction("getParameters", [this](auto& args, auto complete) {
            complete(buildParameterJSON());
        })
);
addAndMakeVisible(webBrowser);
webBrowser.goToURL(webBrowser.getResourceProviderRoot());
```

### BinaryData からファイルを返す ResourceProvider

```cpp
std::optional<juce::WebBrowserComponent::Resource>
serveFile(const juce::String& url) {
    // URL を相対パスに変換
    auto path = url.fromFirstOccurrenceOf("/", false, false);
    if (path.isEmpty()) path = "index.html";

    // BinaryData の命名規則: "index.html" → BinaryData::index_html
    // Monaco の ZIP を展開して返すパターン（ファイル数が多いため）
    if (auto entry = monacoZip->getEntry(path.toStdString())) {
        auto stream = monacoZip->createStreamForEntry(*entry);
        juce::MemoryBlock data;
        stream->readIntoMemoryBlock(data);
        return juce::WebBrowserComponent::Resource{data, getMimeType(path)};
    }
    return std::nullopt;
}
```

### JavaScript 側（Monaco エディタの設定）

```javascript
// window.__JUCE__.backend から C++ 関数を取得
const compileCode   = window.__JUCE__.backend.getNativeFunction("compileCode");
const getParameters = window.__JUCE__.backend.getNativeFunction("getParameters");

// C++ → JS イベントのリスン
window.__JUCE__.backend.addEventListener("compileResult", (msg) => {
    showStatus(msg);
});

// Monaco のセットアップ（AMD ローダー、オフライン）
require.config({ paths: { vs: 'vs' } });
require(['vs/editor/editor.main'], function () {
    const editor = monaco.editor.create(document.getElementById('editor'), {
        value: defaultCode,
        language: 'cpp',     // Cmajor は C-like なので cpp で代用
        theme: 'vs-dark',
        automaticLayout: true,
    });

    // Ctrl+Enter でコンパイル
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
        compileCode(editor.getValue())
            .then(result => showStatus(result));
    });
});
```

### C++ → JS へのイベント送信

```cpp
// コンパイル結果を Monaco に送る（PluginEditor から）
void notifyCompileResult(bool success, const std::string& message) {
    webBrowser.emitEventIfBrowserIsVisible(
        "compileResult",
        juce::var(juce::String(success ? "[OK] " : "[ERROR] ") + message)
    );
}
```

### Monaco のオフラインバンドル

```
ui/
  index.html
  vs/                      # npm install monaco-editor の min/vs/ をコピー
    loader.js
    editor/
      editor.main.js
      editor.main.css
    base/worker/workerMain.js
    language/typescript/ts.worker.js
```

ファイル数が多い（345 ファイル制限を超える可能性）ため、`vs/` を ZIP 圧縮して単一 BinaryData にし、ResourceProvider 内で `juce::ZipFile` を使って展開するパターンが現実的。

---

## コンポーネント 3: CMake ビルド設定

### 依存関係の配置

```
project/
  libs/
    juce/               # git submodule or FetchContent
    cmajor/             # GitHub Releases からダウンロード・展開
      include/
      cmake/
      lib/              # libCmajPerformer.dylib / CmajPerformer.dll
  ui/
    index.html
    vs/                 # Monaco Editor (or monaco.zip)
  src/
    PluginProcessor.h / .cpp
    PluginEditor.h / .cpp
  CMakeLists.txt
```

### CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.22)
project(ScriptableSynth VERSION 0.1.0)

# --- JUCE ---
add_subdirectory(libs/juce)

# --- Cmajor ---
set(CMAJOR_PATH "${CMAKE_CURRENT_SOURCE_DIR}/libs/cmajor")
include("${CMAJOR_PATH}/cmake/CmajorMacros.cmake")
MAKE_CMAJ_LIBRARY(cmaj_lib ENABLE_PERFORMER_LLVM)

# --- WebUI アセット（BinaryData に埋め込む） ---
juce_add_binary_data(WebUI_Data SOURCES
    ui/index.html
    ui/monaco.zip        # Monaco を ZIP 圧縮した場合
)

# --- プラグインターゲット ---
juce_add_plugin(ScriptableSynth
    PLUGIN_MANUFACTURER_CODE Manu
    PLUGIN_CODE Sscr
    FORMATS VST3 AU Standalone
    PRODUCT_NAME "Scriptable Synth"
    IS_SYNTH TRUE
    NEEDS_MIDI_INPUT TRUE
    NEEDS_WEBVIEW2 TRUE
)

target_sources(ScriptableSynth PRIVATE
    src/PluginProcessor.cpp
    src/PluginEditor.cpp
)

target_include_directories(ScriptableSynth PRIVATE
    "${CMAJOR_PATH}/include"
)

target_link_libraries(ScriptableSynth
    PRIVATE
        juce::juce_audio_processors
        juce::juce_gui_extra
        cmaj_lib
        WebUI_Data
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags
)

if(APPLE)
    target_link_libraries(ScriptableSynth PRIVATE
        "-framework WebKit"
        "-framework CoreAudio"
        "-framework CoreMIDI"
    )
endif()
```

---

## Cmajor 言語の基礎

### エンドポイントの 3 種類

```cmajor
processor Example {
    input  stream float  audioIn;   // サンプル精度、毎フレーム
    output stream float  audioOut;

    input  value  float  gain       // パラメータ向き（変化時のみ更新）
        [[ name: "Gain", min: 0.0, max: 1.0, init: 0.5 ]];

    input  event  std::midi::Message midiIn;  // MIDI・トリガー向き
}
```

### 最小サイン波シンセサイザー（8 ボイス）

```cmajor
graph SineSynth  [[main]]
{
    input  event std::midi::Message midiIn;
    output stream float<2> audioOut;

    input value float masterGain
        [[ name: "Master Gain", min: 0.0, max: 1.0, init: 0.7 ]];

    let voiceCount = 8;
    node {
        voices       = Voice[voiceCount];
        voiceAllocator = std::voices::VoiceAllocator (voiceCount);
    }
    connection {
        midiIn -> std::midi::MPEConverter -> voiceAllocator;
        voiceAllocator.voiceEventOut -> voices.eventIn;
        (voices * masterGain) -> audioOut;
    }
}

graph Voice
{
    input event (std::notes::NoteOn, std::notes::NoteOff) eventIn;
    output stream float out;
    node {
        noteToFreq = NoteToFrequency;
        envelope   = std::envelopes::FixedASR (0.005f, 0.15f);
        oscillator = std::oscillators::Sine (float32);
    }
    connection {
        eventIn -> noteToFreq -> oscillator.frequencyIn;
        eventIn -> envelope.eventIn;
        (oscillator.out * envelope.gainOut) -> out;
    }
}

processor NoteToFrequency
{
    input  event std::notes::NoteOn noteOn;
    output event float32 frequencyOut;
    event noteOn (std::notes::NoteOn e) {
        frequencyOut <- std::notes::noteToFrequency (e.pitch);
    }
}
```

### MIDI フローの全体像

```
DAW MIDI In
  → JUCE MidiBuffer
    → cmaj::AudioMIDIPerformer（内部で MIDI イベントを Cmajor に渡す）
      → input event std::midi::Message midiIn
        → std::midi::MPEConverter
          → std::voices::VoiceAllocator（8 ボイス）
            → Voice[8]（各ボイスが Oscillator + Envelope）
              → 合算 → output stream float<2> audioOut
```

---

## DAW 互換性の既知問題

| 問題 | 対象 | 状況 | 回避策 |
|---|---|---|---|
| WebView がタブ切り替えで消える | FL Studio / macOS | 未修正 | `.withKeepPageLoadedWhenBrowserIsHidden()` を必ず指定 |
| キーボード入力が DAW に届かない | Logic Pro / Ableton ほか | 未修正 | macOS `.mm` で `keyDown:` / `keyUp:` を `nextResponder` へ転送（JUCE アップデートのたびに再確認要） |
| スペースキーが DAW に届かない | 全 DAW | WebView の仕様 | JS 側で個別に `preventDefault` を制御 |
| WebView2 ランタイム未インストール | 古い Windows 10 | — | `JUCE_USE_WIN_WEBVIEW2_WITH_STATIC_LINKING=1` で静的リンク（+30MB） |
| Monaco Web Worker が動作しない | `file://` URL | — | JUCE ResourceProvider 経由（事実上 http://）で解決済み |

---

## 本番配布時の注意

- **バイナリサイズ**: `libCmajPerformer.dylib` は LLVM を含み 70〜100 MB 程度。プラグインバンドルに同梱する必要がある
- **JIT なし配布の選択肢**: `cmaj generate --target=cppcode` で純粋 C++ を生成し、LLVM 不要のバイナリを作ることも可能（ただしホットリロードは不可）
- **コード署名（macOS）**: WebBrowserComponent には `com.apple.security.cs.allow-jit` エンタイトルメントが必要になる場合がある

---

## 作業計画（推奨順序）

### フェーズ 1: 環境構築と疎通確認

1. JUCE 8 をサブモジュールとして追加 (`libs/juce/`)
2. Cmajor の最新バイナリを GitHub Releases からダウンロードし `libs/cmajor/` に配置
3. `MAKE_CMAJ_LIBRARY` マクロと JUCE の `juce_add_plugin` を組み合わせた CMakeLists.txt を作成
4. Cmajor の C++ API（`cmaj::Engine` / `cmaj::AudioMIDIPerformer`）でサイン波シンセを JUCE Standalone として動作させる

### フェーズ 2: ホットリロード実装

5. `PluginProcessor` に `recompilePatch(std::string)` を実装（バックグラウンドスレッドでコンパイル → `processLock` でスワップ）
6. デフォルトの Cmajor コード（サイン波シンセ）をハードコードして起動時にコンパイル
7. スワップ前後でオーディオが途切れないことを確認

### フェーズ 3: Monaco エディタ UI の接続

8. Monaco Editor を `node_modules/monaco-editor/min/vs/` からコピーし ZIP 化
9. `PluginEditor` に `juce::WebBrowserComponent` を追加
   - `withNativeIntegrationEnabled()` / `withResourceProvider()` を設定
   - `withNativeFunction("compileCode", ...)` で C++ 側のコンパイル関数に接続
10. `index.html` + Monaco の JS を実装（Ctrl+Enter でコンパイル、結果表示）
11. `emitEventIfBrowserIsVisible("compileResult", ...)` でコンパイル結果を Monaco に返す

### フェーズ 4: VST3 動作確認

12. VST3 としてビルドし、DAW（Reaper / Ableton 等）に読み込む
13. DAW 互換性の問題（キーボードイベント・FL Studio バグ等）を確認・対処
14. `libCmajPerformer.dylib` の同梱と配布パッケージの構成を確認

---

## 参考リソース

| リソース | URL |
|---|---|
| Cmajor 公式サイト | https://cmajor.dev |
| Cmajor C++ API リファレンス | https://cmajor.dev/docs/Tools/C++API |
| Cmajor 言語リファレンス | https://cmajor.dev/docs/LanguageReference |
| Cmajor 標準ライブラリ | https://cmajor.dev/docs/StandardLibrary |
| Cmajor GitHub | https://github.com/cmajor-lang/cmajor |
| Cmajor Releases | https://github.com/cmajor-lang/cmajor/releases |
| JUCE WebView 解説（公式ブログ） | https://juce.com/blog/juce-8-feature-overview-webview-uis/ |
| JUCE WebView チュートリアル | https://github.com/JanWilczek/juce-webview-tutorial |
| JUCE WebViewPluginDemo | https://github.com/juce-framework/JUCE/blob/master/examples/Plugins/WebViewPluginDemo.h |
| Monaco Editor 統合ガイド | https://github.com/microsoft/monaco-editor/blob/main/docs/integrate-esm.md |

---

## 関連ノート

- [スクリプタブルシンセの設計](scriptable-synth-architecture.md)
- [JUCE による VST3 プラグイン開発](plugin-development-juce.md)
- [技術スタック](tech-stack.md)
