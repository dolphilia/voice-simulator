# TSP確認用4録音の語・音素境界

元の比較の確認用から、`FK61_01`・`MK61_01` の「A plea for funds seems to come again.」と、`FK61_02`・`MK61_02` の「He lent his coat to the tall gaunt stranger.」を選んだ。2本文それぞれに実録音2件、上流合成2件、候補合成2件がある。録音と合成は先行のRMS比較で使ったファイルをハッシュで照合した。MFAの版、辞書、音響モデル、ノイズ床、録音注釈との境界差の上限10.001 msは調整用で固定した値を使う。先行比較と区間長の差の方向が一致するかは、合否に含めず観察する。[登録条件](../cases/tsp-phone-boundaries-held-out.json)・[元のRMS区間](tsp-active-duration-original.md#元の登録8件の主しきい値の結果)

## 上流の呼び出しと観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare::tsp::run` から `load_utts`、`say_all`、`align_synth`、`measure_pair` を追った。入力はTSPの録音と本文、または同じ本文と体型設定から通常の `render::say` が生成したPCM。出力はファイルの先頭を零点とする語と音素の始端・終端（秒）。合成ではまず `said_words` で語の順を決め、`EnglishG2P::word(w, true)` の辞書形を `to_arpa` で変換してMFA辞書を作る。録音側は公開発音辞書のまま整列する。固定上流の `every_engine_phone_goes_to_arpabet_and_back` は母音の強勢番号を含む往復、`a_dictionary_word_keeps_its_reduced_function_word_form` は機能語の弱形、`matching_keeps_only_the_same_phones_in_order` は編集距離に基づく音素の対応を検査する。[比較CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L824)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1512)・[調整用で確認した手順](tsp-phone-boundaries-calibration.md#上流の処理と照合方法)

`EnglishG2P::to_phrases` は弱形の語を連結し、語末フラグを付けてから `apply_allophones` を呼ぶ。今回の `tall` の /l/ はここで /ɫ/ になる。MFAには上流と同じ辞書形の `L` を渡し、候補の `english` と上流の句の発音照合、および計画から音響整列への対応でのみ /ɫ/ を `L` に対応させた。発話計画どうしの比較は元のIPAと時刻を保持する。複数本文は一つの合成用辞書を共有し、各話者に対応する本文、語列、音素列を明示して同じMFA設定で2回ずつ整列した。[上流の語と句](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L132)・[候補の句処理](../crates/vocal-core/src/phonetics/english.rs)・[研究用計測器](../tools/measure_tsp_phone_boundaries.py)

`over_noise_floor` は48 kHzの波形の完全な960フレーム窓で平均二乗を求め、その95パーセンタイルを `P95` とする。xorshift32を `0x2545f491` から順に更新し、一様雑音の振幅を `√(3 × P95 × 10^(−47/10))` 倍して加える。加算後のfloat32をPCM16へ量子化する。整列後は無音ラベルを除いた音素を `match_phones` と同じ編集距離・同点時の順で対応させ、始端、終端、区間長の差をmsで記録する。発話全体は最初の語の始端から最後の語の終端までとし、語ごとの長さと隣接語の間隔をそれぞれ足し合わせて照合する。[上流のノイズ生成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L204)・[上流の音素の対応付け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L761)

## 語と音素の実測

全12波形で語列と音素を取得し、独立したMFA作業領域で再実行して同じ時刻とラベルを得た。録音4件の固定上流注釈との最大境界差は約 `1.14×10⁻⁴ ms` で、小数3桁の秒に丸めると全件一致した。合成では本文1が25音素、本文2が30音素で、すべて辞書どおりだった。発話計画は元のIPAと時刻で固定上流に一致した。[計測結果](../runs/tsp-phone-boundaries-held-out-20261121-a/summary.json)・[独立照合](../runs/tsp-phone-boundaries-held-out-20261121-verified/summary.json)

| 録音ID | 最初の語から最後の語までの長さ ms（録音／上流／候補） | 語の合計 ms（録音／上流／候補） | 語間の合計 ms（録音／上流／候補） | 候補と録音の区間長差 ms（MFA／RMS） |
| --- | ---: | ---: | ---: | ---: |
| FK61_01 | 2,140／2,090／2,090 | 2,140／2,020／2,020 | 0／70／70 | −50／−110 |
| MK61_01 | 2,200／2,070／2,070 | 2,160／1,940／1,920 | 40／130／150 | −130／−85 |
| FK61_02 | 2,570／2,680／2,680 | 2,570／2,590／2,590 | 0／90／90 | +110／+180 |
| MK61_02 | 2,300／2,680／2,680 | 2,300／2,500／2,510 | 0／180／170 | +380／+520 |

本文1では候補の語の合計が短く、`MK61_01` の `funds` は録音より150 ms短かった。本文2では男性候補の380 msの増分を語の合計210 msと語間170 msに分けられた。男性候補の `stranger` は150 ms、`gaunt` は100 ms長く、`to` は150 ms短い。本文2で最大の語間は両話者とも `coat` と `to` の間で、候補の90・110 msをMFAが無音に割り当てた。ここには /t/ の閉鎖を含み得るため、計画の休止や聞こえ方を評価する際は閉鎖を別途観測する必要がある。[語別・音素別の時刻](../runs/tsp-phone-boundaries-held-out-20261121-a/summary.json)

実録音との音素対応は本文1が22／25、本文2が27／30で、各本文で2話者と両合成の件数が一致した。全録音の `to` は `AH0`、両合成は `UW0`。本文1の `for` は録音の `F R ER0` と合成の `F AH0 R` で順序が変わり、既定の編集距離と同点時の経路では `F` が対応した。本文2の `tall` と `gaunt` では録音の `AA1` と合成の `AO1` を別のラベルとして記録した。これらは登録した辞書と整列結果の比較で、別ラベルに対応を広げる場合は独立したケースで評価する。[不対応の前後を含む結果](../runs/tsp-phone-boundaries-held-out-20261121-a/summary.json)

両合成へのMFA適用後、各録音IDの最初の音素境界差は、登録順に `again` の `EH1` 終端が +20 ms、`plea` の `IY1` 終端が −10 ms、`coat` の `OW1` 終端が +10 ms、`the` の `DH` 終端が +10 msだった。最大差は女性の本文2で `to` の `UW0` 終端の50 ms。比較前の保存済みfloat32は4組ともフレーム0ですでにビット差があり、MFA入力のPCM16にもフレーム0・1・0・3から差があった。計画の音素・時刻と同一のノイズ生成を照合しているため、波形側の差がアラインメント入力に既に存在するところまで確認できた。個々の境界を動かす波形の区間の特定は残る。[合成計画と音響境界](../runs/tsp-phone-boundaries-held-out-20261121-a/summary.json)・[先行する波形差の調査](tsp-active-duration-original.md#発話前の放射と終端のしきい値)

## 実行と保存

macOS 15.6.1 arm64、MFA 3.4.3、`english_us_arpa` v3.0.0。固定RustのTSP試験6件、計測7判定、調整用の回帰7判定、独立検証3判定が通過した。固定上流のRustプローブとMFA入力のPCM16は8波形・1,043,436フレームすべて一致し、調整用の再実行は先行要約の全項目を再現した。確認用のマニフェストに記載した63成果は計4,386,354バイト。4つのMFA作業領域はRTL9210B-CGの各実行の `tmp` にあり、確認用で約1.0 GiBだった。PythonとRustの版、合成に使ったWAV・モデル・辞書のSHA-256、各コマンドは実行記録から追える。[確認用の実行記録](../runs/tsp-phone-boundaries-held-out-20261121-a/manifest.json)・[調整用の回帰](../runs/tsp-phone-boundaries-calibration-20261121-regression/manifest.json)・[独立照合の実行記録](../runs/tsp-phone-boundaries-held-out-20261121-verified/manifest.json)

固定上流のディレクトリで `cargo test --locked --offline -p chimera-cli compare::tsp::tests` を実行した。確認用、調整用の回帰、独立検証のマニフェストに載る計103成果のサイズとSHA-256を照合した。

最初の起動では `diskutil info -plist /Volumes/RTL9210B-CG` が90秒を超えて応答せず、作業ディレクトリ作成前に中止した。同じ確認を10秒で打ち切り、macOSの `getattrlist` と `statvfs` からボリュームUUIDと書き込み可否を取得できるようにした。元のマウント先、UUID、書き込み可否の条件はこの経路でも照合する。実ディスク2件の正例と、誤UUID・マウント外のディレクトリ・別ディスク・存在しないパスの拒否を検証してから再実行した。[作業ディスクの確認処理](../tools/run_storage.py)

`research/experiments/chimera-rebuild` で実行する。各実行IDは再実行時に未使用の値を指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=3221225472 ../../.venv/bin/python tools/measure_tsp_phone_boundaries.py tsp-phone-boundaries-held-out-20261121-a --case cases/tsp-phone-boundaries-held-out.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python tools/measure_tsp_phone_boundaries.py tsp-phone-boundaries-calibration-20261121-regression
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=16777216 ../../.venv/bin/python tools/verify_tsp_phone_boundaries.py tsp-phone-boundaries-held-out-20261121-verified tsp-phone-boundaries-held-out-20261121-a tsp-phone-boundaries-calibration-20261121-regression
```
