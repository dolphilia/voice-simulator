# 英語計画ABIの割り当てを工程別に測る

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のWASM APIは `State::g2p` に `EnglishG2P` を置き、辞書をロードする要求で `load_dict()` を呼ぶ。辞書の単語とARPABETを所有するハッシュ表に格納し、発話要求では `to_phrases()` が同じ辞書を参照して句ごとの音素、強勢、イントネーションを返す。`plan_phrases()` は句ごとに `plan_utterance()` で継続時間と調音ジェスチャーを計算する。句の開始・終了・休止は秒で、次の句の開始は直前の終了に休止を加えた時刻。発音試験は `Hello world` の強勢と `water` の弾き音、句読点に応じた句の分割と疑問イントネーションを確かめる。[上流の辞書・発音API](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L125)・[上流の索引と発音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L119)・[句の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L880)・[上流の発音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/english.rs#L26)

研究版の `PlanBuffers` はUTF-8の入力と辞書の生バイト、戻り値の報告と数値スコアを保持する。`vocal_english_plan_with_body()` が体型と基準音高（Hz）を解決し、`dictionary_lexicon()` が辞書バイトをUTF-8として検証して `English::with_dictionary()` に渡す。この索引は辞書から借りた `&str` をキーと値に持ち、発話ごとに作り直す。`plan_voice_with_body()` は発音、継続時間、体型に応じたジェスチャーを返す。`PlanBuffers::store()` は秒単位の開始・終了や調音目標をF64のスコアに書き、計画とジェスチャーをJSONで返す。スコアは容量を保持して長さだけをリセットし、報告の文字列は読み直すたびに生成する。[研究版の英語ABI](../crates/vocal-wasm/src/planning.rs#L105)・[研究版の辞書索引](../crates/vocal-core/src/phonetics/english.rs#L47)・[研究版の句とジェスチャー](../crates/vocal-core/src/phonetics/english.rs#L373)

確認用07の44.1 kHzケースで計数した3,555回の内訳を、索引、発音と句の計画、計画の報告値、数値スコア、ジェスチャー入り報告値、JSON文字列化の順に記録する。辞書は借用文字列のハッシュ表で、報告値は各ノードを所有するため、割り当ての回数は報告側が大きいと予測する。二回目も索引と報告を作り、数値スコアの容量を保持するので、割り当ては1回減る見込み。計数の合計、同じ辞書を単独で構築した結果、保存済みの計画・音声・内部観測を照合する。[事前登録](../cases/worklet-live-tsp-planner-allocation-44100.json)・[前回の計数](../runs/worklet-live-tsp-allocation-44100-20261122-b/summary.json)

## 初回と繰り返しの計測

ネイティブの診断テストでだけ、英語計画ABIの六つの重ならない区間にカウンターを置いた。ABIの全体件数は別の読み取りで求め、合計が一致することを確認した。同じ入力と辞書でもう一度ABIを呼び、各回の計画JSONとF64スコアを保存した。辞書単体の計数は `English::with_dictionary()` を別に実行して照合し、TSVのタブ区切り前の異なる単語をPythonで数えた。[計数点の実装](../crates/vocal-wasm/src/planning.rs#L191)・[診断テスト](../crates/vocal-wasm/src/tests/speech_allocation.rs#L19)・[比較手順](../tools/measure_worklet_live_tsp_allocation.py)

| 英語計画ABI内の工程 | 通常の初回 | 同じ入力の再計画 | コア計画を先に実行した後の初回ABI |
| --- | ---: | ---: | ---: |
| 辞書索引の構築 | 17 | 17 | 17 |
| 発音と句の計画 | 1,715 | 171 | 171 |
| 計画の報告値を構築 | 527 | 527 | 527 |
| 数値スコアを格納 | 1 | 0 | 1 |
| ジェスチャー入り報告値を構築 | 1,282 | 1,282 | 1,282 |
| 報告をJSON文字列化 | 13 | 13 | 13 |
| 合計 | 3,555 | 2,010 | 2,011 |

辞書の単独構築は17回で、126,052語の索引を作った。JSON関連は1,822回で、初回の51.3%、再計画の90.6%を占めた。計画JSONと数値スコアは初回と再計画でバイト一致した。事前の「再計画では1回だけ減る」という予測に対し、観測された減少は1,545回。うち1,544回の差は発音と句の計画、残る1回は数値スコアだった。初回3,555回と再計画2,010回は、研究ワークスペースと `/tmp` から合計3回再現した。[初回の集計](../runs/worklet-live-tsp-planner-allocation-44100-20261122-a/summary.json)・[再実行](../runs/worklet-live-tsp-planner-allocation-44100-20261122-c/summary.json)

## コア計画だけを先行させる比較

差を確認してから先行処理のケースを別に登録した。新しいプロセスで `vocal_core` の辞書索引と `plan_voice_with_body()` だけを実行し、その後に最初の英語計画ABIを呼んだ。先行処理での件数は索引17回、発音と句の計画1,715回。その後の最初のABIでは発音と句の計画が171回となり、数値スコアの最初の確保1回を含め、合計2,011回を2実行で再現した。計画JSONと数値スコアは通常の初回とバイト一致した。コアでは音素・継続時間・母音と子音の較正表を遅延初期化している。今回の比較で1,544回の差はコア計画の先行処理に帰属し、各表の件数は未計測。[先行処理の事前登録](../cases/worklet-live-tsp-planner-prewarm-44100.json)・[対照の集計](../runs/worklet-live-tsp-planner-prewarm-44100-20261122-b/summary.json)・[音素と継続時間の表](../crates/vocal-core/src/phonetics/catalog.rs#L50)・[母音の較正表](../crates/vocal-core/src/phonetics/vowels.rs#L28)

五つのネイティブ実行でPCM全98,790標本、ABI観測、声門2系列、声道断面・圧力・流量が基準とバイト一致した。772量子のネイティブ描画の割り当ては引き続きゼロで、固定上流とのPCM最大差は1.16×10⁻¹⁰。通常のFirefox再計測では11判定を通過し、CLIと実時間・オフラインWorkletのPCMがビット一致した。Firefoxの描画時間は全量子のp99が2 ms、約2.90 msの予算を越えた量子が3件、WASMメモリ成長は0回。計時は1 ms刻みで1実行。標準のコアとABIの44試験、およびFirefox比較で固定上流の英語とエンジンの11試験が通過した。6実行の954入力・127出力をサイズとSHA-256で照合し、実体59,858,240バイトをRTL9210B-CGに保存した。[通常のFirefox・CLI比較](../runs/worklet-live-tsp-44100-planner-regression-20261122/summary.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-planner-allocation-44100.py)

## 実行コマンド

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、Firefox 157.0。以下は研究ワークスペースから実行した。通常計数の `b` と `c`、先行処理の `b` は `/tmp` からPythonと計測ツールを絶対パスで指定した。再計測では新しい実行IDを使う。[候補のマニフェスト](../runs/worklet-live-tsp-planner-allocation-44100-20261122-c/manifest.json)・[先行処理のマニフェスト](../runs/worklet-live-tsp-planner-prewarm-44100-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_allocation.py worklet-live-tsp-planner-allocation-44100-20261122-a --planner-phases
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_allocation.py worklet-live-tsp-planner-prewarm-44100-20261122-a --prewarm-planner
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-44100-20261122-a/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-44100-planner-regression-20261122 "$firefox"
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
```

次は `PlanBuffers::store()` がジェスチャー入り報告を中間の `serde_json::Value` に組み立てる工程の1,282回を対象にする。数値スコアと既存のJSONを基準に、同じ報告を直接バイト列にシリアライズする候補を比較する。辞書索引の初期化は別の比較で扱う。[報告の生成](../crates/vocal-wasm/src/planning.rs#L191)
