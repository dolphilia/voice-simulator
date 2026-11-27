# 英語の接近音 /ɹ/ の調音と時間配分

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行するTSP本文の入力検査で、元の確認用 `FK61_01` と `MK61_01` は `/ɹ/` だけが未対応だった。今回は音素の姿勢と時間配分を、単独のIPA、英語歌詞、TSP本文で照合する。[事前登録](../cases/english-rhotic.json)・[先行する入力検査](../runs/tsp-active-duration-inspect-20261121-dental/summary.json)

## 固定上流での処理順序

`chimera-cli/src/main.rs::run` から英語発話では `render::text` → `say`、歌詞付き音符では `render::notes` → `plan_song` に進む。`english.rs::arpabet_to_segments` が辞書の `R` を `/ɹ/` に変換し、語境界を保って区間計画へ送る。発話の `planner.rs::plan_utterance` は `durations.rs::klatt_durations` を使い、語末側の `/ɹ/` が母音と同じ語にある場合は、母音の通常長から `/ɹ/` の長さを差し引いて40 msを下限とする。`/ɹ/` の基準長は80 ms、最短値は30 ms。同じ語で直後が母音なら通常のオンセット、次の語が母音で始まる場合は前の語の韻尾として時間を配分する。長さが明示指定されている場合は、この差し引きを適用しない。[英語の辞書変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L239)・[語末の時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L204)

`inventory.rs::phoneme` から受け取る `/ɹ/` の支配軸は舌先X/Y `(5.35, 9.35)` cm、反り0.85、唇の突出0.5 cm・幅0.3、舌根−0.6 cm。舌体 `(2.3, 7.1)` cmは補助軸。選んだ固定版にはこの音素の体型別の較正上書きがなく、体型差は声道形状と音響への適用に現れる。`/ɻ/` の支配軸は舌先 `(5.4, 9.55)` cmと反り1.0。`oral_gestures_into` が発話・歌唱の秒単位の区間 `[a,b)` から、支配軸を `a−8 ms` から `max(a+10 ms,b)` まで、強さ40・速度1.3で計画する。立ち上がり30 ms、解除18 ms、解除保持45 ms。補助軸は `a` から `b`、強さ2.2、両側50 ms。口蓋化の指定は自由な舌体軸へ `/j/` の目標を重ねる。話速が1より大きいときはランプと保持を話速で割る。[調音目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L225)・[軸の分割とランプ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L809)

`pre_placed_behind_closure` は後続の破裂音が調音位置の前方にある閉鎖の後に来て、さらに先々行音が必要な軸を既に動かすかを確認する。`/ɹpt/` では先々行音 `/ɹ/` が舌先、`/ɹpk/` では舌体の軸を持つ。該当すると閉鎖の狙いを `min(0.025,max(0,t1−t0−0.030))` 秒だけ遅らせる。短い音符でも次の音素へはみ出さず、接近音で終わる発話の呼気終端には一般の共鳴音の規則を使う。[先行配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L779)・[歌唱の短い閉鎖の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L78)

`HumanVoice::control` は出力64フレームごとに目標を重ね、速度と位置を更新して形状と断面を作る。舌根の変位は、舌体の相対移動と合わせて喉頭前方の点のX座標に体型倍率 `k` を掛けて入る。放射量を内部96 kHzで計算し、間引き・出力段を経て48 kHzのPCMにする。上流の `nasal_spans.rs::a_vowel_and_its_coda_r_share_the_vowels_span` は `/pɑɹk/` の核の長さ、次語母音への連結、同語内のオンセットを比較する。`sing_fast.rs::a_delayed_cluster_closure_stays_inside_a_short_sung_stop` と `sound_marks.rs` は短い閉鎖と実音響での時刻の観測を確かめる。今回はこの順序を踏まえ、発話時刻、全フレームの内部状態、PCM、舌根と反りの独立したばね計算を照合する。[形状での舌根の扱い](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L829)・[時間配分の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/nasal_spans.rs#L68)・[計測器](../tools/measure_english_rhotic.py)

## 実装と実測

既存の発話・歌唱共用の調音計画で `/ɹ/` を受け付け、支配軸と補助軸のジェスチャーを生成した。語末母音の時間配分は既存の処理を用いた。実行前に調音の方向、母音間の開口と発声、閉鎖の遅延、歌唱の核との境界を登録した。候補のIPA7条件、英語歌唱1条件、TSP本文2条件は通常のCLIを使い、固定上流の計画と観測用プローブで、初期姿勢を同じにして比較した。舌先の反りと舌根は9 Hzの臨界減衰ばねの独立計算にも照合した。[再実装](../crates/vocal-core/src/phonetics/speech.rs#L744)・[事前登録](../cases/english-rhotic.json)・[全条件の結果](../runs/english-rhotic-20261121-final/summary.json)

母音間の `/ɹ/` の中央30〜70%では舌根変位の中央値が−0.585 cm、唇の突出が0.483 cm、幅が0.324、口腔の最小断面積が1.137 cm²だった。同じ入力の `/ɻ/` では唇の突出0.012 cm、幅0.971、口腔の最小断面積0.532 cm²で、両条件で口腔の開口と発声を保った。`/ɹpt/` と `/ɹpk/` の目標閉鎖はともに25 ms遅れ、`/pɑɹ/` の終端の呼気目標は `/ɹ/` の末尾から45 ms後だった。2音の `Run car` はそれぞれの母音核を0.500〜0.880秒、1.000〜1.398秒に置き、最初の `/ɹ/` は第1音の核の手前、末尾の `/ɹ/` は第2音の核の後に置いた。[時間配分と中央区間の測定](../runs/english-rhotic-20261121-final/summary.json)

全体の最大PCM差は `/ɹpk/` を含む条件の `3.73×10⁻⁹`。母音間の条件では舌根と反りが全フレーム一致し、最初の口腔面積差はフレーム11,458で `2.66×10⁻¹⁵ cm²`。放射量の時間微分にはフレーム0から `4.75×10⁻¹² cm³/s²` の差があり、同条件の最初のPCMビット差はフレーム31,739だった。フレーム0は `/ɹ/` の制御開始より前で、放射の微小差がここで生じることまでを確認した。CLIの128・77フレーム分割は全条件で同じ時系列とPCMを返した。WASMホストのIPA・歌唱・TSPの合計259,584フレームはCLIとビット一致し、IPAの母音間条件は自動乱流を起動しなかった。[上流との差の観測点](../runs/english-rhotic-20261121-final/summary.json)・[WASMの結果](../runs/english-rhotic-20261121-wasm/summary.json)

## 最初の不合格と時間配分の改訂

最初の計測器はCLIの `inspect` の設定JSONから `entries` を読もうとして停止した。タイミング一覧を返す `render` に切り替え、停止時のコマンドと出力ハッシュを残した。次の実行は82判定中81件が通過した。上流の6条件との時刻差はすべて0秒だったが、第1版は `/ɑɹ/` と `/ɑl/` の子音長にも共通値を要求して不合格になった。両条件とも基準長80 msで、当該文脈で共通の倍率は `1.4 × 0.85 × 0.7`。第2版では `最短長 + (80 ms − 最短長) × 倍率` を使い、最短長30 msの `/ɹ/` と40 msの `/l/` を個別に検査した。核の合計時間、PCMと各物理量の許容差は維持した。[計測器の失敗](../runs/english-rhotic-20261121-a/failure.json)・[第1版の不合格](../runs/english-rhotic-20261121-b/summary.json)・[第2版の条件](../cases/english-rhotic.json)

| 時間配分の対照 | 前の母音 ms | 接近音 ms |
| --- | ---: | ---: |
| 語末側の `/pɑɹk/` | 164.55 | 71.65 |
| `/pɑlk/` | 236.20 | 73.32 |
| 次語の母音に続く `/pɑɹ/ + /ɑ/` | 57.30 | 72.50 |
| 同じ語に次の母音がある `/pɑɹɑ/` | 104.264 | 72.50 |
| 同じ語に次の母音がある `/pɑlɑ/` | 104.264 | 74.00 |
| `/pɑɹk/` の長さを明示指定 | 120.00 | 90.00 |

`/pɑɹk/` の母音と接近音の合計236.20 msが、`/pɑlk/` の母音長と一致した。次語の母音への接続では `/ɹ/` の長さが同語内のオンセットと等しく、前の母音の時間が短くなった。[固定上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/nasal_spans.rs#L68)・[6条件の測定値](../runs/english-rhotic-20261121-final/summary.json)

## TSP本文と再現手順

元の確認用 `FK61_01`、`MK61_01` は各116,132フレームを生成し、固定上流との最大PCM差はどちらも `2.91×10⁻¹¹` だった。4話者の240本文について通常入口の入力検査を再実行し、32件から130件に増えた。元の登録8件全件を対象とする判定は、4件が未対応のため不合格として保存した。`FA01_02` と `MA01_02` には `/ʃ/`、`FK61_02` と `MK61_02` には `/dʒ/` が残る。今回合成できた2件は、録音を用いる次の発話区間比較で確認用に追加する。[TSPの再検査](../runs/tsp-active-duration-inspect-20261121-rhotic/summary.json)・[既存の録音比較](tsp-active-duration-after-dh.md)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4で、以下をCHIMERAの研究ワークスペースから実行した。第2版の83判定、固定上流28試験、候補のワークスペース41試験とClippyが通過した。WASMの比較に用いた第1版のCLIのWAVは、第2版の対応するWAVとハッシュが一致した。同じWASM計測器で従来の `/ð/` 3条件のビット一致も確認した。[CLIのマニフェスト](../runs/english-rhotic-20261121-final/manifest.json)・[WASMのマニフェスト](../runs/english-rhotic-20261121-wasm/manifest.json)

高密度CSV40件はRTL9210B-CGで作成し、全フレームを判定した。先頭64フレームと各接近音の始端・中央・終端の前後64フレームから、登録した列を保存した。元CSV約1.35 GBのSHA-256は第1版の全量保存と40件すべて一致する。第2版の合成WAVを含む保存成果は約12.5 MBで、実体は `/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/english-rhotic-20261121-final/artifacts` にある。[保存範囲とハッシュ](../runs/english-rhotic-20261121-final/manifest.json)・[第1版の全量保存](../runs/english-rhotic-20261121-b/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=3221225472 ../../.venv/bin/python tools/measure_english_rhotic.py english-rhotic-local-1
cargo build --locked --offline --release --target wasm32-unknown-unknown -p vocal-wasm
npx --offline --yes --package=bun@1.4.4 bun tools/compare_dental_wasm.ts target/wasm32-unknown-unknown/release/vocal_wasm.wasm runs/english-rhotic-local-1/artifacts cases/english-rhotic-wasm.json
../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-active-duration-inspect-rhotic-local-1
cargo test --locked --offline --workspace
cargo clippy --locked --offline --workspace --all-targets -- -D warnings
```
