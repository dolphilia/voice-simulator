# 有声歯摩擦音 /ð/ の閉鎖と摩擦

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。以前のTSP入力検査では、事前登録の8録音すべてが候補で停止し、そのうち6件に `/ð/`、2件に `/ð/` だけが未対応として出た。今回は `/ð/` の調音を、固定上流との比較で単独に追加した。[以前の入力検査](../runs/tsp-active-duration-inspect-20261121-a/summary.json)・[事前登録](../cases/dental-dh.json)

## 上流の呼び出しと調音

英語の入口は `chimera-cli/src/main.rs::run` → `render.rs::text` → `say`。単純なIPAの場合は `render::speech` を使う。`say` の辞書で `english.rs::arpabet_to_segments` が `arpa` を呼び、`DH` が `/ð/` になる。句境界と強勢を得て `planner.rs::plan_phrases` から `plan_utterance` へ渡る。`durations.rs::klatt_durations` は `/ð/` の長さを有声摩擦音として配分し、基準50 ms、最短30 msを使う。発話では句の基準時刻に対し、呼気の立ち上がりの中心を40 ms、最初の音素区間を60 msに置く。調音のモードは、長さの決定と展開の後に決まる。[CLIの発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs)・[英語の音素変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs)・[長さの配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs)

`inventory.rs::phoneme` は歯音の舌先Xを6.85 cm、Yを体型別の較正値にする。成人男性8.190 cm、成人女性8.208 cm、子ども8.244 cm。補間体型は体型重みに従う。`plan_utterance` は発話頭・明示休止 `_` の後と、破裂音・破擦音・摩擦音の後では `/ð/` を閉鎖として扱い、`dental_closure` の `(6.85, 9.0)` cmを使う。舌先だけに強い目標を与え、歯茎系の子音に使う舌体の補助目標は加わらない。[音素目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L153)・[音素の文脈判定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L350)

音素区間を `[t0,t1)` 秒とする。閉鎖を狙う `aim` は `t0 + min(delay, max(0,t1−t0−0.030))`。遅延は通常0、歯擦音後は0.030 s。次に閉じる位置より手前の両唇閉鎖があり、その前の音が舌先を既に扱う場合は0.025 s。`oral_gestures_into` の舌先目標は `aim−0.031` から `max(aim+0.010,t1−0.020)`、速度倍率1.55。摩擦音の場合は `t0−0.008` から `max(t0+0.010,t1)`、速度倍率1.3。いずれも強さ40、立ち上がり30 ms、解除18 ms、解除保持45 ms。話速が1を超えるとランプと保持の時間を話速で割る。[閉鎖の遅れ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L700)・[舌先の先行位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L784)・[調音目標の時間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L819)

声門開大の目標は `t0−0.015` から `t1` まで。閉鎖の強さは6、摩擦音の強さは3。追加開大の値は通常0.09 cm²で、鼻音後の摩擦音だけ0.035 cm²。これは制御の目標値で、実測開大にはスコアの重み、体型の面積スケール、同時に有効なジェスチャーが反映される。制御更新は出力64フレームごとにスコアを評価し、調音器を進め、接触を補正した形状を断面へ写す。`HumanAirway::update_noise` は正の最小狭窄を探し、その面積と体型スケールに応じて流れから圧力注入する乱流源の位置と利得を更新する。時系列では舌先、最小断面、枝への圧力注入、声門と放射を出力フレーム末尾に揃えた。[開大の分岐](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L535)・[声道側の配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L325)

上流の `stop_spans.rs::dh_after_a_pause_is_a_silent_closure` は非発声に近い128フレーム平均二乗を発話頭の前半で測り、強勢母音との差を−30 dB未満とする。`dh_after_an_explicit_pause_is_a_closure_too` は発話頭、明示休止後、母音間で調音様式の違いを確認する。今回は同じ比較に、鼻音後、歯擦音後の速い条件、両唇閉鎖前から舌先が置かれる条件、口蓋化を加えた。候補と上流の音源は既存の比較プローブで初期姿勢・揺らぎ・出力ゲインを揃えた。[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/stop_spans.rs)・[比較プローブ](../tools/upstream_bilabial_probe.rs)

## 実装と結果

`timing::plan` にあった文脈判定を利用し、`speech.rs::dental_gestures` で舌先と声門の既存ジェスチャーへつないだ。`TraceFeatures::from_symbols` で口腔の断面を観測し、CLIとWASMで自動乱流を起動する。閉鎖時の解析は上流の128出力フレームのブロック末尾を時間座標として、別のNumPy計算から平均二乗を求めた。狭いセルが同じ最小面積を持つ場合は、独立して全セルを走査し、違うセルを選んでも面積と閉鎖の判定が揃うかを調べた。[発話スコア](../crates/vocal-core/src/phonetics/speech.rs)・[観測口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L1067)・[WASMの計画](../crates/vocal-wasm/src/planning.rs#L250)・[計測器](../tools/measure_dental_dh.py)

| 条件 | 中央区間の口腔最小断面の中央値 | 中央区間の声門開大の中央値 | 主な観測 |
| --- | ---: | ---: | --- |
| 男性の発話頭 | 0 cm² | 0.09225 cm² | 閉鎖前半のレベルは強勢母音に対して−32.59 dB |
| 女性の発話頭 | 0 cm² | 0.07472 cm² | 閉鎖前半は−38.31 dB |
| 明示休止の後 | 0 cm² | 0.09225 cm² | 中央1,056フレームが全件閉鎖 |
| 男性の母音間 | 0.23467 cm² | 0.09225 cm² | 狭窄乱流の前向き圧力RMSは5.590 dyn/cm² |
| 女性の鼻音後 | 0.14086 cm² | 0.03017 cm² | 中央区間で閉鎖せず、有声状態を維持 |

国際音声記号による8条件と英語本文2件について、独立に算出した舌先と開大の目標、固定上流との計画・時間軸・波形・内部状態、ホスト分割77と128での再現を確認し、64判定が両実行で通過した。PCM差の最大は女性のTSP本文の `3.73×10⁻⁹`。その本文では比較プローブ間の放射差分の最初の差は出力フレーム0の `8.31×10⁻¹² cm³/s²`、声門流量の最初の差は3、断面の最初の差は3,065、PCMのビット差の最初は1,963だった。先頭の差は歯音の調音区間より前に生じている。すべての代表条件の内部系列は登録許容差を満たした。[64判定の結果](../runs/dental-dh-20261121-repeat/summary.json)

英語のTSP調整用 `FA01_01` と `MA01_01` は `/ð/` の追加によって発話計画が通り、女性・男性の各129,024フレームを通常のCLIで合成した。4話者240件を再検査し、計画可能な本文が6件から32件に増えた。元の登録の残る6件では `/ɹ/`、`/ʃ/`、`/dʒ/` のいずれかが未対応。前回の3文・6録音を用いた発話区間長の回帰では、各出力と計測値が一致した。[入力の再検査](../runs/tsp-active-duration-inspect-20261121-dental/summary.json)・[録音比較の回帰](../runs/tsp-active-duration-20261121-dental-regression/summary.json)

破擦音を含む条件を第3版に追加した。`ɑtɕðɑ` は遅延0 msで `/ð/` を閉鎖として計画し、`ɑdʑpðɑ` は両唇閉鎖の前に舌先が置かれるため、閉鎖を狙う遅延の上限25 msを適用した。音素区間が41.9 msなので実際に使った遅延は11.9 ms。追加の2条件とも中央で完全閉鎖し、先行10条件の要約と一致したまま全76判定を通過した。[破擦音を含む最終結果](../runs/dental-dh-20261121-affricates/summary.json)

## 保存と再実行

研究ワークスペースから初回を実行し、`/tmp` ではPythonと計測器を絶対パスで指定して再実行。初回見積もり1 GiBに対し、全成果は1,487,885,358バイトだった。再実行では2 GiBを確保。判定を全フレームで行った後、CSV40件の列と区間を絞り、実体を約11.9 MBへ減らした。再実行の要約は初回とバイト一致し、元CSV40件のSHA-256も初回と一致した。再実行の115成果は参照先とハッシュを照合した。初回の全系列は作業用のRTL9210B-CGに残した。[初回の全成果](../runs/dental-dh-20261121-a/manifest.json)・[再実行の成果](../runs/dental-dh-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2684354560 ../../.venv/bin/python tools/measure_dental_dh.py dental-dh-local-1
../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-active-duration-inspect-local-2
cargo test --locked --offline --workspace
cargo clippy --locked --offline --workspace --all-targets -- -D warnings
```

WASMはリリースモジュールをBun 1.4.4で起動し、ブラウザと共用する `planIpa`・`planEnglish` と `FixedVoiceEngine` を通した。発話頭、母音間、英語本文の計234,197フレームはCLIとビット一致。最初の試行はWAVの `fact` チャンクを考慮せず停止し、RIFFチャンクを走査するよう修正した。次の試行ではPCMが一致した後に音響ケースのCSV保存規則が適用されて停止したため、WASM確認用のケースを用意した。変更箇所の整形とClippyは通過。ワークスペース整形の検査では既存の `phonetics.rs` のモジュール順だけに差があった。[第1試行](../runs/dental-dh-20261121-wasm/manifest.json)・[第2試行](../runs/dental-dh-20261121-wasm-verified/manifest.json)・[WASMの条件](../cases/dental-dh-wasm.json)・[WASMの結果](../runs/dental-dh-20261121-wasm-final/summary.json)

```bash
cargo build --locked --offline --release --target wasm32-unknown-unknown -p vocal-wasm
npx --offline --yes --package=bun@1.4.4 bun tools/compare_dental_wasm.ts target/wasm32-unknown-unknown/release/vocal_wasm.wasm runs/dental-dh-20261121-a/artifacts cases/dental-dh-wasm.json
```

第3版では2.5 GiBを確保し、従来条件の40 CSVの抜粋に加えて、追加2条件の全系列を作業用ディスクに残した。135成果、312,504,349バイトのハッシュとリンク先を再照合した。Rustのワークスペース41試験と固定上流の `stop_spans` 6試験が通過し、第3版のWASMを再ビルドして同じ234,197フレームのビット一致も得た。[第3版のマニフェスト](../runs/dental-dh-20261121-affricates/manifest.json)
