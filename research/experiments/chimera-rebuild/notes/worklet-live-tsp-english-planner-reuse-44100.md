# 英語発話のWASM計画器をページで共有する

## 固定上流と再実装の呼び出し順

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `src/wasm/chimera.ts` の `initChimera` は読み込み中のPromiseと、準備済みのWASMエクスポートをページ内に保持する。`call` はJSONリクエストを書き込み、`chimera_call` の後で最新のポインタとバイト長を取得して結果を解釈する。失敗した初期化は次回に再試行できる。`src/wasm/engine.ts` の `EnglishG2P.load` は辞書を読み、`src/ui/speech.ts` の `speakText` と `speakPhrases` は句と計画オプションをWASMへ渡してWorklet側に予定を登録する。固定版の `tests/words.test.ts` は単一ページ側の呼び出し経路で語境界を検証し、`crates/chimera/tests/english.rs` は辞書・強勢と異音・句境界を検証する。

再実装の `web/prototypes/chimera-research/src/main.tsx` の英語発話パネルは `renderEnglishVoice` と `renderRealtimeEnglishVoice` を呼ぶ。従来は両関数とも `loadFixedModule` でWASMを取得・コンパイルし、`crates/vocal-wasm/host/planning.ts` の `planEnglish` の内部で毎回 `WebAssembly.Instance` を生成していた。Rustの `PlanBuffers` はインスタンスごとの入力バイト列・辞書バイト列・報告JSON・調音スコアを持つ。`planEnglish` は入力と辞書をコピーし、開始秒、話速倍率、F0のHz、体型の重みを渡す。WASMは報告のUTF-8バイト長を返し、`readResult` はこの長さと最新のメモリ参照からJSONをデコードし、直後に `Float64Array.slice()` で数値スコアをコピーして返す。発話フレーム数は報告の終了秒と出力Hzの積を丸めた値。描画側は `FixedVoiceEngine` の別のインスタンスでスコアを消費する。

英語の通常経路でコンパイル済みモジュールを共有し、モジュールごとに計画器を保持すれば、オフライン発話から実時間発話への切り替えでページ側のコンパイルと計画器の生成が各2回から1回になると予測した。辞書のデータを毎回上書きし、結果を同期的にコピーするため、辞書の差し替えと以前のスコアの保持を個別に確認できる。[事前登録](../cases/worklet-live-tsp-english-planner-reuse-44100.json)・[領域再利用の基準](../runs/worklet-live-tsp-planner-report-buffer-44100-20261122-c/summary.json)

## 実装

`loadEnglishModule` は英語のオフライン発話と実時間発話で同じ読み込みPromiseを使う。個別の実時間発話を止めると、その呼び出しのContextを閉じる。共有の読み込みはほかの呼び出しも待てる状態で続け、取得に失敗したときにPromiseを消す。`planEnglish` は `WeakMap` にモジュールと計画インスタンスを対応付け、入力と辞書は各呼び出しで書き込む。英語以外の入口と描画側のインスタンス生成は従来の経路を使う。既存の英語発話計測でコンパイル数を照合する2箇所は、計画器を共有する条件の1回に更新した。[ページ側の読み込み](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L76)・[計画の呼び出しとコピー](../crates/vocal-wasm/host/planning.ts#L139)

## 実行と照合

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Node 24.19.0、Firefox 157.0。確認用07（FK64_08）、女性体型、話速1、出力44,100 Hz、内部88,200 Hz。以下は研究ワークスペースから実行したコマンド。再計測は `/tmp` からPythonとスクリプトを絶対パスで指定し、実行ID末尾を `-b` とした。

```bash
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-44100-report-buffer-final-20261122/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-english-planner-reuse-44100-20261122-a "$firefox" --reuse-english-planner
CHIMERA_FIREFOX="$firefox" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-english-planner-reuse-48000-20261122
```

確認用07のオフライン発話と実時間発話を同一ページで続けると、基準で2回だったコンパイルは1回になり、計画インスタンスの生成もページ側で1回だった。2実行で18判定が通過し、どちらも保存済み基準と98,790フレームのPCM、内部観測、調音計画が一致した。固定上流とのPCM最大絶対差は1.1641532182693481×10⁻¹⁰だった。実時間計時のp99は2〜3 ms、予算超過は1〜12量子で、前回の単回測定は2 ms、6量子だった。[通常経路の再実行](../runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/summary.json)

同じページで計画器1個を共有した結果を、毎回コンパイルした5個の場合と比べた。`Map, map. Map?` から `Map.` へ切り替え、同じバイト長の辞書を同じ配列に上書きすると、実際に計画された `[m, æ, p]` が `[m, ʌ, p]` へ変わった。不正な辞書のエラーを挟んで元の辞書と入力に戻すと、計画とスコアが元に戻った。最初に返した値も、後続の呼び出し後にスコアの全バイトが一致した。別ページでWASMの初回取得をHTTP 503にすると、次の発話で再取得し、98,790フレームを出力できた。独立検算ではジェスチャーの7フィールドと22調音目標からスコアを復元し、長い報告754要素、短い報告と辞書差し替えは各261要素を照合した。音素区間も各音素長÷話速から再計算した。[辞書と取得エラーの比較出力](../runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/artifacts/english-planner-reuse.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-english-planner-reuse-44100.py)

48 kHzではChromium 156.0.8078.4とFirefox 157.0で、オフライン発話から実時間発話、停止後の操作可能状態までの21判定が通過した。両ブラウザでコンパイルと計画器の生成は各1回。全107,527フレームのWAVが両ブラウザでバイト一致し、固定上流とのPCM最大絶対差は両方1.1641532182693481×10⁻¹⁰だった。再実装のWASM31試験、固定上流の英語とエンジン11試験、TSの型検査も通過。3実行の846入力と64出力をサイズ・SHA-256で照合し、実体78,707,854バイトをRTL9210B-CGに保存した。ネイティブの時計追跡を行う別の計測スクリプトはコンパイル数の判定を更新した段階で、今回のOSトレースは収録していない。[48 kHzの照合](../runs/worklet-live-tsp-english-planner-reuse-48000-20261122/summary.json)
