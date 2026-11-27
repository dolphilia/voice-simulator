# 計画JSONの出力領域を再利用する

## 固定上流から再実装の報告まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `src/ui/speech.ts` で `speakPhrases` が句列・体型・話速・F0を `src/wasm/engine.ts` の `planPhrases` に渡す。さらに `src/wasm/chimera.ts` の `call` がJSONをWASMへ渡す。`crates/chimera-wasm/src/api.rs` の `chimera_call` はJSONを解釈して `dispatch` に渡し、`planPhrases` 分岐は `planner::plan_phrases` の戻り値を `to_json` でJSON値にする。成功の状態コードは0、失敗は1。結果は毎回新しいバイト列にして `State.result` に代入する。TS側は `chimera_result_ptr` と `chimera_result_len` で現在のメモリから指定バイトを読み取る。`tests/words.test.ts` は二重母音を含む語の区間、句をまたぐ休止、発音を持たない入力に続く語の対応を、`crates/chimera/tests/english.rs` は辞書と句切りを検証する。

再実装の `crates/vocal-wasm/host/planning.ts` の `planEnglish` は `vocal_english_plan_with_body` に開始秒、話速の倍率、基準F0のHz、体型の重みを渡す。`PlanBuffers::store` は数値スコアを書いた後、`serde_json::to_vec` で報告を書き、得たバイト列で `report` を置き換えて長さを返す。各ジェスチャーの数値スコアは秒単位の開始・終了とランプ時間、強度、速度、解放保持、各調音成分の順で並ぶ。省略値はNaN。入力エラーと上限超過はエラー文字列のJSONを出し、スコアを空にする。TSの `readResult` はその長さでUTF-8を読み、スコアをコピーする。通常のTSの各計画関数は呼び出しごとにWASMインスタンスを作る。

`serde_json` 1.0.154の `src/ser.rs` の `to_vec` は128バイトから書き始める。今回は最初の出力先を同じ容量で確保し、次回は長さをゼロにした既存バッファへ書く。短い報告への切り替えとシリアライズ途中のエラー時に、前回の内容や書きかけの内容を公開範囲から除く。最初の英語計画は9回のまま、同一インスタンスへの再計画は0回と予測した。[事前登録](../cases/worklet-live-tsp-planner-report-buffer-44100.json)・[直前の基準](../runs/worklet-live-tsp-planner-direct-text-plan-44100-20261122-b/summary.json)

## 実装と計数範囲

`PlanBuffers::write_report` は `Vec<u8>` の長さをゼロにして `serde_json::to_writer` で同じ領域へ書く。JSON書き込み中にエラーが出た場合はスコアを空にし、もう一度出力長をゼロにしてエラーを出す。試験では一部のフィールドを書き終えた後にエラーを返し、エラーJSONと空のスコア、その次の正常報告を照合した。[報告の格納](../crates/vocal-wasm/src/planning.rs)・[異常系の試験](../crates/vocal-wasm/src/planning/report.rs)

初回の計測 `-a` では報告の比較と割り当て削減の予測が成立した。一方、不正UTF-8のABI全体は1回なのに工程合計は0回だった。英語入力のUTF-8検証が早期にエラー文字列を所有化する処理を、どの工程にも含めていなかった。文字列の所有化までを既存の `speech_plan` 区間に入れ、正常入力の件数とJSON出力の範囲を保った。条件と判定式を維持し、失敗した要約を残した。[初回の判定](../runs/worklet-live-tsp-planner-report-buffer-44100-20261122-a/summary.json)

## 実行と照合

確認用07（FK64_08）、女性体型、話速1、出力44,100 Hz、内部88,200 Hz。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4。以下は研究ワークスペースから実行したコマンド。再実行は `/tmp` からPythonとスクリプトを絶対パスで指定し、計数の実行ID末尾を `-c` とした。

```bash
CARGO_TARGET_DIR=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-rebuild-debug cargo test --locked --offline -p vocal-core -p vocal-wasm --lib --quiet
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 CARGO_TARGET_DIR=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-rebuild-debug ../../.venv/bin/python tools/measure_worklet_live_tsp_allocation.py worklet-live-tsp-planner-report-buffer-44100-20261122-b --reuse-report-buffer
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-44100-20261122-a/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-44100-report-buffer-final-20261122 "$firefox"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-report-buffer-final-20261122 --live
```

| 計画ABIの工程 | 初回の基準 → 今回 | 再計画の基準 → 今回 |
| --- | ---: | ---: |
| 辞書索引 | 17 → 17 | 17 → 17 |
| 入力検証・発音と句の計画 | 1,715 → 1,715 | 171 → 171 |
| 中間の英語計画値 | 0 → 0 | 0 → 0 |
| 数値スコアの格納 | 1 → 1 | 0 → 0 |
| 中間の報告値 | 0 → 0 | 0 → 0 |
| JSON出力 | 9 → 9 | 9 → 0 |
| 合計 | 1,742 → 1,742 | 197 → 188 |

描画後の切り替えで、出力の長さは短い `A.` で1,432バイト、不正UTF-8で59バイト、元の入力に戻したとき17,014バイトだった。数値スコアの `f64` の個数は順に116、0、1,653。最後のJSON・スコアは最初とバイト一致し、3回のJSON出力の割り当ては全て0回だった。不正入力の割り当て1回はエラー文字列の所有化に帰属した。独立検算では各報告のUTF-8長、キーの辞書順、不正入力のJSON、短い報告のジェスチャー数×29、六工程とABIの件数、および22音素区間を照合した。[切り替え時の報告と計数](../runs/worklet-live-tsp-planner-report-buffer-44100-20261122-c/artifacts/planner-report-transitions.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-planner-report-buffer-44100.py)

2回の計数で36判定と削減予測5項目が成立した。英語発話の全98,790フレームのPCM、ABI・声門・声道観測は基準に一致し、全772量子の描画中は割り当てゼロ。固定上流に対する全PCMの最大絶対差は1.1641532182693481×10⁻¹⁰だった。[再実行の結果](../runs/worklet-live-tsp-planner-report-buffer-44100-20261122-c/summary.json)

通常のFirefox発話11判定とChromium歌唱25判定、再実装48試験、固定上流の発話・歌唱の対応試験が通過した。両ブラウザのPCMと内部観測は保存済みの同条件の出力と一致した。UTF-8計数範囲の修正前にもブラウザで両条件が合格していたが、修正後の再ビルドでWASMのハッシュが変わったため、両ブラウザを新しいビルドで再実行した。最終WASMのSHA-256 `550b9b169189e9cfa5d7b5528186df26aa9af8765da605d868b778d4271ababc` は両ブラウザが記録した値と一致した。今回の単回計時ではp99は両方2 msで、予算超過はFirefoxで6量子、Chromiumで1量子だった。確認した最終版4実行の854入力と88出力をサイズ・SHA-256で照合し、成果の実体211,741,056バイトをRTL9210B-CGに保存した。[Firefox](../runs/worklet-live-tsp-44100-report-buffer-final-20261122/summary.json)・[Chromium](../runs/worklet-live-song-report-buffer-final-20261122/summary.json)
