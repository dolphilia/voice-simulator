# 有声後部歯茎破擦音 /dʒ/ の閉鎖と摩擦

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。元のTSP登録では確認用 `FK61_02` と `MK61_02` だけが残り、未対応音素は `/dʒ/` だった。`/tʃ/` と同じ閉鎖目標から始まり、声帯の開大目標が区間内の後方に移ることで閉鎖付近の低域成分が増えると予測した。調音、声門面積、歯への圧力注入、PCMを比較する。[先行の入力検査](../runs/tsp-active-duration-inspect-20261121-sh/summary.json)・[登録条件](../cases/postalveolar-affricate-dzh.json)

## 固定上流の処理順序

`chimera-cli/src/main.rs::run` から英語本文は `render::text` → `say`、歌詞と音符は `render::notes` → `plan_song` に入り、どちらも `planner::plan_utterance` に区間を渡す。`EnglishG2P` は辞書の `JH` を `/dʒ/` とし、IPAでは `tokenize_ipa` が結合記号や付加記号を読む。`klatt_durations` の基準長・最短長は `/dʒ/` が100・60 ms、`/tʃ/` が125・88 ms。母音で挟まれた語中では `最短 + (基準 − 最短) × 0.85` から94.00・119.45 msを得る。[発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[辞書変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L34)・[基準長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L54)

音素の区間を `[a,b)`、分割点を `m = a+0.45(b−a)` とする。両破擦音の閉鎖は舌先X/Y `(5.75,10.0)` cm、唇突出0.75 cm、幅0.2を支配軸とし、`a−31 ms` から `max(a+10 ms,m−20 ms)` まで速度2で保持する。解放は `r=max(a,m−15 ms)` を基準に `r−8 ms` から `max(r+10 ms,b)` まで速度1.4で持続する。解放の舌先Xは5.7 cm、顎は0.35 cm。舌先Yは `/dʒ/` が参照する `/ʒ/` の較正では成人男性9.495、成人女性9.505、子ども9.524 cm。`/tʃ/` は `/ʃ/` の9.512、9.521、9.538 cm。同じ体型混合式で端点を補間する。閉鎖と解放の口腔目標は強さ40、立ち上がり30 ms、立ち下がり18 ms、解放保持45 ms。[子音の目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L209)・[口腔計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L473)・[ランプ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L819)

`affricate_folds` には `/dʒ/` では `m`、`/tʃ/` では `a+0.15(b−a)` を開大の目標時刻 `o` として渡す。強さ6で0.36 cm²を加え、立ち上がり35 ms。保持の終端は `max(o,b−30 ms)`、立ち下がりは `min(30 ms,b−o)`。目標時刻より前にランプが始まるので、時刻 `o` は開大が最初に起きる時刻とは異なる。早口では開大と口腔のランプ時間を話速で割る。付加記号 `ʱ` は終端20 ms前から次の音素の終端または80 ms後まで0.10 cm²の開大を重ね、`ʲ` は舌体2軸を `/j/` の位置へ動かす。前の破裂音より奥に閉鎖を作るとき、先々行の `/dʒ/` が舌先を準備できる場合は `/t/` の目標を最大25 ms遅らせる。[声帯のルール](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L507)・[開大の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L683)・[先行配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L779)

`HumanVoice::control` は48 kHzで64出力フレームごとに、ジェスチャーから調音と声帯開大を更新する。口腔の断面積は cm²、枝流量は cm³/s。閉鎖で最小断面を通る流れが止まり、解放で狭い枝から歯の近くへ噴流が届くと `HumanAirway::update_noise` が歯の乱流を登録する。`AirwayNetwork::compute_noise` がレイノルズ数とフィルタ状態から圧力源を計算し、96 kHzの伝搬と放射、間引きを経て48 kHzのfloat32を得る。上流の `affricates.rs` は、1 kHzの一極ローパスを2段通した電力と全電力の比を、10 ms窓で測る。閉鎖前10 msから後30 msまでの最小低域比が `/tʃ/` より3 dBを超えて高いこと、摩擦が30 ms以上で、次の母音まで20 ms以下であることを成人男女で試験する。`sing_fast.rs` は短い歌唱で解放の準備と声帯の戻りが持続時間の制約を満たすことを検査する。[制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[乱流の登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[閉鎖と摩擦の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs#L86)・[短い歌唱の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L98)

## 実装と測定

口腔の閉鎖と解放を既存の破擦音の処理に接続し、`/dʒ/` では `/ʒ/` の較正と有声破擦音の開大規則を選んだ。CLIとWASMの自動乱流も同じ音素から有効になる。IPA8条件・短い歌唱1条件・TSP本文2条件の計761,534フレームで計画、形状、声門、乱流、PCMを比較した。上流側は観測用プローブで初期姿勢、音源、出力段を候補とそろえた。`Ah jaw` の `/dʒ/` は550.0〜562.5 ms。開大目標を555.625 msに置き、保持時間0、立ち下がり6.875 msで第2音の母音が始まる時刻へ収まった。`/dʒpt/` の `/t/` の目標閉鎖は25 ms後ろに移る規則を独立式に照合した。[実装](../crates/vocal-core/src/phonetics/speech.rs#L433)・[全計測](../runs/postalveolar-affricate-dzh-20261121-final/summary.json)

| 母音間の条件 | `/dʒ/` の閉鎖付近の最小低域比 dB | `/tʃ/` の最小低域比 dB | `/dʒ/` の摩擦 ms | 摩擦から母音まで ms |
| --- | ---: | ---: | ---: | ---: |
| 成人男性 | −1.16 | −9.45 | 40 | 10 |
| 成人女性 | −2.01 | −9.11 | 40 | 10 |

上流と候補とも低域比の差は男性8.29 dB、女性7.10 dBだった。女性の `/dʒ/` は162フレームで閉鎖と隣接枝の流量0を観測した。歯の乱流に続いて声門面積の周期が戻った。対照の `/tʃ/` は男性438、女性473フレームで閉鎖し、10 ms窓の摩擦長は両者60 msだった。成人条件で歯の帯域上限を独立計算と照合した誤差は `4×10⁻¹² Hz` 未満だった。[調音・スペクトル・声門の比較](../runs/postalveolar-affricate-dzh-20261121-final/summary.json)

最大PCM差は `breathy` 条件の `2.33×10⁻¹⁰`。男性の標準条件の開大目標は全フレーム一致した。比較した項目ではフレーム0の放射の時間微分に最初の差 `4.75×10⁻¹² cm³/s²` があり、声門面積の最初の数値差はフレーム4,213で `1.73×10⁻¹⁸ cm²`。男性PCMは16,694で初めてビット差があった。観測した初期の放射差は調音準備前にあり、その原因は未分離。WASMホストのIPA・歌唱・TSP本文はCLIと合計247,375フレームがビット一致し、先行 `/ʃ/` の3条件も再びビット一致した。[最初の微小差](../runs/postalveolar-affricate-dzh-20261121-final/summary.json)・[WASM照合](../runs/postalveolar-affricate-dzh-20261121-wasm/summary.json)

## 完全閉鎖の予測を外れた成人男性の条件

最初の計測器は `FK61_02` の体型をケースの表示用項目から読んで停止した。体型を実際のレンダー入力から読むよう変更し、停止時のコマンドと外部成果のパス・ハッシュを残した。第1版の再実行は86判定中、成人男性の `/dʒ/` を完全閉鎖とした1判定だけが通過しなかった。フレーム14,207の最小断面積は候補・上流とも約0.002419 cm²。完全閉鎖のしきい値0.0002 cm²以上で、最小セル10の隣接枝には8.49と8.06 cm³/sの順方向流量があった。男性 `/tʃ/` と女性 `/dʒ/` では閉鎖を観測できた。[停止の記録](../runs/postalveolar-affricate-dzh-20261121-a/failure.json)・[第1版の判定](../runs/postalveolar-affricate-dzh-20261121-b/summary.json)

第2版は男性の開いた狭窄を0.005 cm²未満の区間として追加観測し、完全閉鎖のしきい値と他条件の検査は維持した。444フレームにわたって狭窄が続き、フレーム14,437で0.005 cm²に達した。その後の最初の歯の乱流は14,474、声門の周期復帰は17,839で、両実装の時刻は一致した。組み合わせた入力でどの目標が通路を残すかは未分離。男性 `/dʒ/` の音素長を固定し、解放の舌先Yだけを `/tʃ/` の値に変えると、較正高さの寄与を切り分けられる。[改訂した登録](../cases/postalveolar-affricate-dzh.json)・[第2版の判定](../runs/postalveolar-affricate-dzh-20261121-final/summary.json)

## TSPと実行手順

元の確認用 `FK61_02`、`MK61_02` を各144,727フレームで合成した。4話者240本文の入力ハッシュと既に合成可能だった170件の計画を維持し、新たに28件が合成可能になった。元の登録8件はすべて計画を通過した。残る42本文は別の未対応音素を含む。元の調整用2件と確認用2件は次の発話区間長比較に追加し、録音・合成の音素別比較と試聴は引き続き扱う。[TSP入力の判定](../runs/tsp-active-duration-inspect-20261121-dzh/summary.json)・[先行14録音](tsp-active-duration-after-rhotic.md)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4で実行した。第2版は `/tmp` から絶対パスで実行し、86判定が通過した。固定上流12試験、候補41試験とClippyも通過した。高密度CSV44件の約2.05 GBをRTL9210B-CG上で全件比較し、元のハッシュと、先頭および音素の開始・分割点・終端の周辺を保存した。男性の狭窄では断面積が最小になる前後と枝流量も残した。最終成果は合成WAVなどを含め約13.3 MB。WASM照合で使った第1版のCLIのWAVは、第2版のWAVと一致した。[第1版のマニフェスト](../runs/postalveolar-affricate-dzh-20261121-b/manifest.json)・[第2版のマニフェスト](../runs/postalveolar-affricate-dzh-20261121-final/manifest.json)・[WASMの実行記録](../runs/postalveolar-affricate-dzh-20261121-wasm/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 ../../.venv/bin/python tools/measure_voiced_postalveolar_affricate.py postalveolar-affricate-dzh-local-1
cargo build --locked --offline --release --target wasm32-unknown-unknown -p vocal-wasm
npx --offline --yes --package=bun@1.4.4 bun tools/compare_dental_wasm.ts target/wasm32-unknown-unknown/release/vocal_wasm.wasm runs/postalveolar-affricate-dzh-local-1/artifacts cases/postalveolar-affricate-dzh-wasm.json
../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-active-duration-inspect-dzh-local-1
cargo test --locked --offline --workspace
cargo clippy --locked --offline --workspace --all-targets -- -D warnings
```
