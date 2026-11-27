# 実時間の舌と唇の操作

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `AnatomyView` はポインター位置を体の座標に戻し、舌体にはテンプレート上のX・Y、唇には開度・突き出しを渡す。Zustandの `setArtic` を通り、`AudioEngine.setArtic` と `scheduleFlush` が同じ画面フレームの部分変更をまとめる。Workletは調音軸の順に数値を並べ、未指定をNaNにして、WASMの `engine_set_artic` から `Engine::set_artic` と `HumanVoice::set_articulation` に伝える。動かした部位の基準目標だけを変え、音声の現在位置・速度は保持する。[上流のポインター処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView.tsx#L132)・[状態の更新](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L314)・[メッセージの集約](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L383)・[Workletの受信](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L112)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L223)

上流の `ArticulatorBank::step` は自由な舌先の目標を前回姿勢から更新し、目標を可動域内に収める。舌体12 Hz、口唇開度11 Hzを使い、`ω = 2πf` とすると、`v' = v + Δt(ω²(T − x) − 2ωv)`、`x' = x + Δt v'`。座標・開度はcm、速度はcm/s。制御更新で位置を進め、声道断面（cm²）に変換し、必要なら口蓋と衝突した舌を押し戻して断面を計算し直す。気道は次の制御境界まで形状を補間する。上流のE2E `grabTongueFirst` は操作から音声開始と口蓋接触を確認し、Rustの `output_does_not_depend_on_the_host_block_size` は同じサンプル時刻の調音変更を異なる分割で再生する。[調音器の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L89)・[発声の制御順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L458)・[上流のE2E](../../../../docs/reference/chimera-vocal-synth/upstream/tools/e2e.ts#L643)・[分割のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

成人男性の固定 /i/（舌体3.683、7.739 cm、唇1.046 cm）から発声し、舌体Yを7.1 cm、次にXを3.1 cm、最後に開度を0.35 cmへ下げる。操作は各約250 ms間隔、停止は最後の操作から約380 ms後。48 kHzの実時間Workletで適用した出力フレームを使い、96 kHz内部の128サンプルごとに追従を計算する。ホストブロック128の末尾で位置・面積・呼気・声門・放射を取得する。各対象軸は次の操作までに目標の0.015 cm以内へ近づき、閉口方向への操作で口端最小断面積は0.2 cm²以上減ると予測する。接触を避ける方向の舌体移動を選び、独立漸化式と比較する。比較時は乱流の寄与を0とし、CLIとブラウザのPCMはビット一致、固定上流とは最大絶対差を照合する。適用時刻はUIの時計から推定せず、Workletで記録する。[登録ケース](../cases/worklet-manual-articulation.json)・[初期姿勢](../cases/vowel-voice-i.json)・[実時間基準](worklet-realtime-voice.md)・[可動声道の先行検証](voiced-vowel-motion.md)

## 操作と再生の経路

研究画面では3つのスライダーにcm値を直接指定する。各入力で3成分の目標を送り、Workletは次の128フレームブロックの開始までに届いた最後の組を採用する。採用した出力フレームを目標と一緒に保存する。同じ制御境界でRustの `ArticulatorBank` が追従を進め、接触補正と気道断面の補間を適用する。声門、呼気、出力段には既存の `ArticulatedVoice` と `OutputStage` を使う。[ブラウザの操作](../../../../web/prototypes/chimera-research/src/main.tsx)・[Workletの適用時刻](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[WASMの目標設定](../crates/vocal-wasm/src/lib.rs#L239)・[調音と接触](../crates/vocal-core/src/voice.rs)

観測JSONの `articulation[].frame` は出力フレーム番号。再実行用CLIケースではその番号を64で割り、呼気目標や調音目標を `articulators.events[]` に並べる。ブラウザは二つの制御更新を含む128フレームの末尾を観測するため、最初の観測は適用フレームから127フレーム後になる。固定上流プローブにも同じ制御イベントと初期姿勢を渡す。CLIの128・77フレーム分割、固定上流の1・77フレーム分割の出力をそれぞれ照合した。[CLIのイベント適用](../crates/vocal-cli/src/articulation_case/voiced.rs#L54)・[固定上流プローブ](../tools/upstream_articulation_probe.rs)・[保存された再実行ケース](../runs/worklet-manual-articulation-20261119-b/artifacts/replay-case.json)

## 実測結果

Chromium 156.0.8078.4の実時間AudioContextからの保存を2回検証し、各13項目が通過した。初回は102,272フレーム、`/tmp` からの再実行は102,784フレーム。停止の適用時刻は512フレーム異なった。実測された各回の時刻で再生すると、CLIと加工前PCMがビット一致し、ブラウザが採取した内部状態12系列の差も0だった。[初回](../runs/worklet-manual-articulation-20261119-a/manifest.json)・[再実行](../runs/worklet-manual-articulation-20261119-b/manifest.json)

| 部位 | 適用した出力フレーム | 操作直前 → 初回観測 → 目標（cm） |
| --- | ---: | --- |
| 舌体Y | 20,352 | 7.739 → 7.721 → 7.100 |
| 舌体X | 32,640 | 3.683 → 3.667 → 3.100 |
| 口唇開度 | 44,928 | 1.046 → 1.029 → 0.350 |

舌体Yを下げた後、観測した口腔中央セルの最小断面積は0.518から2.454 cm²へ増加した。唇を狭めると口端の最小断面積は3.355から1.247 cm²へ減少した。目標への追従は独立漸化式と最大 `8.89×10⁻¹⁶ cm`、呼気は独立計算と最大 `1.00×10⁻¹⁵` の差に収まった。固定上流との差が最初に見えたのは出力フレーム0に対応する内部サンプル1の放射微分で、差は `−2.00×10⁻¹¹ cm³/s²`。固定上流とのPCM最大絶対差は両実行で最大 `3.73×10⁻⁹`、許容差は `5×10⁻⁷` だった。[追従と断面積](../runs/worklet-manual-articulation-20261119-b/summary.json)・[初回のPCM比較](../runs/worklet-manual-articulation-20261119-a/summary.json)

再実行ではWASM線形メモリが発声前のブロック0で1回増えた。そのブロックは4 ms。発声区間のp99は両実行で2 msだったが、初回はゲートを開いたブロックで20 msを1回記録した。計測時計は `Date.now`。処理時間の分布と線形メモリの履歴は性能調査に使い、今回の調音機構の合否13項目は登録済みの音響・再現条件で判定した。[初回の処理時間](../runs/worklet-manual-articulation-20261119-a/summary.json)・[メモリ増加の時刻](../runs/worklet-manual-articulation-20261119-b/summary.json)

固定母音の実時間発声、ブラウザIPA、ブラウザ歌唱、CLIの有声母音遷移の回帰が通過した。操作の検証は接触を避けた一つの舌体・口唇の軌跡を対象とする。上流の画面にある極端な舌位置のドラッグや、調音部位を増やしたときの負荷は別条件で調べる。[実時間発声](../runs/worklet-realtime-voice-20261119-manual-regression/summary.json)・[IPA](../runs/worklet-ipa-voice-20261119-manual-regression/summary.json)・[歌唱](../runs/worklet-song-voice-20261119-manual-regression/summary.json)・[有声母音遷移](../runs/vowel-motion-voice-vowels-20261119-manual-regression/summary.json)

```bash
python3 tools/measure_worklet_manual_articulation.py worklet-manual-articulation-local-1
```
