# TSPの `coat to` で語間と破裂音の閉鎖を比較する

確認用 `FK61_02` に対応する女性設定の本文全体を、上流と再実装の通常CLIで合成する。MFAの語境界は先行比較で保存した2つの整列JSONから読み、話者の録音と合成の対応関係は既登録のままとした。作業前に、`coat` の語末と `to` の語頭の /t/ が舌先を同じ位置へ動かし、90 msの語間の半分以上が0.005 cm²以下の口腔狭窄に重なると予測した。清浄PCMの電力が直前の母音に対して−10 dB以下の時間も、語間の半分以上と予測した。断面積0.0002と0.05 cm²も感度を確認する観測点に登録した。[事前条件](../cases/tsp-coat-to-closure.json)・[先行するMFAの比較](tsp-phone-boundaries-held-out.md#語と音素の実測)

## 上流の呼び出しと観測値

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `render::text` と `compare::tsp::say_all` は `render::say` に本文と体型を渡す。英語辞書で語を音素へ変換し、句の抑揚と休止を添えて `plan_phrases` を呼ぶ。女性の基準音高は205 Hz、計画はファイル先頭の50 ms後に始まり、末尾へ300 msを加える。上流の `render::say` と同じ声道・声源の初期状態で動かす観測用Rustプローブを用意し、通常CLIのPCMと全フレームで照合する。候補は先行比較に使ったJSONを `vocal-cli inspect`・`render`・`render-pcm` の通常入口に渡す。[上流の発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[観測用Rustプローブ](../tools/upstream_tsp_closure_probe.rs)・[候補の発話経路](../crates/vocal-cli/src/timing_case/speech_voice.rs)

`plan_utterance` は /t/ を舌先が主となる無声歯茎破裂音として扱う。音素計画の区間を `[t0,t1]` とすると、閉鎖の目標時刻 `a` は `t0 + min(d, max(0, t1−t0−0.030))`。母音後の歯茎音で `d = 0.019` 秒、直前が /t/ のときは0秒。独立計算では、主ジェスチャーの時間を `[a−0.031, max(a+0.010,t1−0.020)]` として両版の計画と比較する。主ジェスチャーは舌先を固定の座標へ強さ40で動かし、舌体を前寄りにする補助ジェスチャーの強さは1.2。上流の `stop_spans.rs` は母音後と /s/ 後の音圧降下を調べ、`engine.rs` は描画ブロックによらず同じ波形を返すことを調べる。[破裂音の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L444)・[舌先の先行と解放](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[固定上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/stop_spans.rs)

`HumanVoice::control` は出力64フレームごとにジェスチャーを混合し、舌の位置と速度を更新して接触を処理する。 `HumanAirway::apply` による口腔形状を節点の断面積へ変換し、次の制御点まで内部サンプルごとに補間する。 `AirwayNetwork::step` は断面の最小値も閉鎖判定に使う。口端と鼻端の放射には並列R–L負荷を使い、合計の体積流量と1内部サンプル前との差に96 kHzを掛けて放射信号（cm³/s²）を得る。 `HumanVoice::render` は間引きと出力処理の後に48 kHzのfloat32を返す。各CSV行は内部2サンプルを進めた後の状態で、PCMフレーム `k` の区間を `[k,k+1)` フレームとした。最小断面（cm²）、セル番号、唇と鼻の流量（cm³/s）、放射流量の時間差分を同じ行に保存する。[制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[声道への反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[気道と放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1079)

## フレームへの写像

MFAの `coat` 終端と `to` 始端をサンプルレートで整数フレームに丸め、その半開区間と面積しきい値以下の区間の共通部分を数える。計測対象は900〜1,330 ms。清浄PCMの二乗を5 ms窓で平均し、1 ms間隔で求める。窓電力を `coat` の二重母音内930〜1,010 msの平均電力で割り、 `10 log₁₀` でdBに換算する。窓の判定は中心の左右0.5 msに割り当てる。マスクの直接計数と区間の交差、各窓の直接平均と矩形畳み込みを照合する。MFA側の時刻は先行計測のノイズを加えたPCM16に由来する。[計測器](../tools/measure_tsp_coat_to.py)・[先行する整列用PCM16の検証](../runs/tsp-phone-boundaries-held-out-20261121-verified/summary.json)

## 比較結果

両版の舌先ジェスチャーは1,021.724〜1,078.599 msと1,067.599〜1,146.099 msで、独立式に一致した。主区間どうしは11 ms重なった。MFAが語間とした1,060〜1,150 msの4,320フレームでは、すべて口腔セル8の最小断面積が0 cm²だった。唇端の最小面積は約0.292 cm²。モデルの閉鎖しきい値0.0002 cm²では、両版とも1,057.146〜1,165.875 msに連続した閉鎖があり、2音素の計画境界を越えた。0.005と0.05 cm²の観測点でも語間の全フレームが範囲内だった。清浄PCMが前の母音より−10 dB以下の窓は語間全体と重なり、その連続区間は1,027.5〜1,230.5 msだった。この1条件では、MFAの語間は連続した歯茎閉鎖の中に含まれる。[全観測値](../runs/tsp-coat-to-closure-20261121-final/summary.json)・[時系列図](../runs/tsp-coat-to-closure-20261121-final/artifacts/coat-to.png)

完全に0へ達する最初のフレームは固定上流50,879、再実装50,815で、制御1回分の64フレーム差があった。0.0002 cm²を最初に下回る時刻は一致した。語間の放射流量の時間差分には両版で最大約5,440 cm³/s²が残った。ファイル先頭の観測では口腔の最小セルと面積が一致し、舌先Yが固定上流6.810460 cm、再実装7.294194 cmで、口端流量と放射の時間差分にも最初のフレームから差があった。通常の初期舌先が異なることは先行実験と整合する。個々の有声波形やMFAの境界差への寄与は引き続き条件を絞って比較できる。[再実装の状態](../runs/tsp-coat-to-closure-20261121-final/artifacts/candidate-state.retained.csv)・[固定上流の状態](../runs/tsp-coat-to-closure-20261121-final/artifacts/upstream-state.csv)・[初期舌先の先行対照](tsp-active-duration-original.md#発話前の放射と終端のしきい値)

図の灰色はMFAの語間、縦の点線は2つの /t/ の計画境界、横の破線は面積0.005 cm²と電力−10 dB。放射は間引き前の各出力フレーム末尾で採った値を表示する。

## 実行と保存

初回は電力の独立照合だけが不合格だった。発話先頭からの累積電力の差を取る方法では、閉鎖中の小さな値に桁落ちが生じ、矩形畳み込みとの差が最大 `1.28×10⁻⁴ dB` になった。窓内で直接平均する方法に変更すると最大差は `1.42×10⁻¹⁴ dB` となり、許容差 `1×10⁻⁸ dB` を通過した。語間との重複フレームは変更前後で一致し、事前に登録した判定と許容差を維持した。初回の全系列と不合格の要約を保存した。[初回の判定](../runs/tsp-coat-to-closure-20261121-a/summary.json)・[修正後の判定](../runs/tsp-coat-to-closure-20261121-final/summary.json)

macOS 15.6.1 arm64で通常の上流と候補のPCMは各144,727フレームが対応する先行WAVとバイト一致し、観測用上流プローブも通常PCMと全点一致した。正式実行の8判定、固定上流の `stop_spans`・`engine` 12試験、候補 `vocal-core` 15試験を通過した。Python・Rustの版、入力とソースのSHA-256、コマンドはマニフェストにあり、図はMatplotlib 3.10.8で作成した。正式実行では外部ディスクに書いた候補のCSV約209.3 MBを全フレーム検査し、指定区間と元のハッシュを保持した。保存成果は約26.8 MB。初回の約231.5 MBは失敗の検証用にRTL9210B-CGで保持する。[初回の保存記録](../runs/tsp-coat-to-closure-20261121-a/manifest.json)・[正式実行の保存記録](../runs/tsp-coat-to-closure-20261121-final/manifest.json)

`research/experiments/chimera-rebuild` から再実行する。実行IDは未使用の値を指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_tsp_coat_to.py tsp-coat-to-closure-local-1
cargo test --locked --offline -p vocal-core
```
