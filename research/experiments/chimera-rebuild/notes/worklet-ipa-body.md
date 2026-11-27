# ブラウザのIPA発話で体型を選ぶ

## 上流の読解

- `ipaToPhrases` と `tokenizeIpa` で表記を音素に分け、`speakPhrases` から同じ体型・速度・F0をWASMの `planPhrases` に渡す。 `plan_utterance` は時間範囲（秒）とジェスチャーを決め、 `vowel_artic` と `inventory::phoneme` は体型で較正値を選ぶ。成人内女性比を `f`、子ども比を `c` とすれば、重みは `(1−c)(1−f), (1−c)f, c`。舌先などcm単位の目標は成分ごとの加重平均、F0（Hz）は `exp(Σ wᵢ ln(Fᵢ))`。エンジンの3端点は110、205、260 Hz。[IPAと発話予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L44)・[WASM計画入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L155)・[音素計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L320)・[子音目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L264)・[既定音高](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L26)
- /p/ の唇開き目標は各体型で `−0.25 cm`。 /s z/ では舌先高さを較正表から選ぶ。声道を更新してから、 `update_noise` が最小の正の断面積 `A` と歯までの距離を使って乱流源と圧力注入先を選ぶ。流量を `U` とすると、ジェット速度は `|U|/A`（cm/s）、直径は `2√(A/π)`（cm）。歯に届いた渦径を `δ` として帯域上限は `|U|/A × 直径/δ²`（Hz）。最小断面積、歯への注入枝、励起、注入圧力とPCMを対応させる。 `stop_spans` は閉鎖時刻、 `voiced_fricatives` は狭窄に伴う有声成分低下、 `body_mix` は目標と音響の体型補間を検査する。[乱流の計算順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[閉鎖テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/stop_spans.rs#L72)・[摩擦音テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs#L29)・[体型テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)

## 事前登録

`ˈɑpɑ / ˈɑsɑ / ˈɑzɑ` を4体型で試す。研究CLIのIPA開始0.05秒、発話間休止0.35秒と末尾余白0.20秒を共通にし、96 kHz内部・48 kHz出力で134,454フレームを得る。音素時刻と /p/ の閉鎖目標は一致し、 /s z/ の舌先は体型の重みで変わる。 /p/ の計画区間は約0.262〜0.342秒。 /s z/ の中央50%で正の狭窄と歯への励起を測る。16フレーム間隔の観測では毎フレームのCLIに対して開閉検出が最大15フレーム後に来ると予測する。音高設定を保存し、オフラインと実時間のダウンロードと固定上流PCMを比較する。[登録ケース](../cases/worklet-ipa-body.json)・[CLIの登録条件](../cases/human-body-ipa.json)・[上流とCLIの先行実行](../runs/bodyipa-20261120-repeat/manifest.json)

## ブラウザでの準備と観測

ページ側の `vocal_ipa_plan_with_body` は、英語と同じ体型の2軸を受け取り、IPA用の `speech_gestures` に渡す。F0の入力が空ならIPAの体型別既定音高を使う。成人男性のIPAは指定F0から始める。女性・子ども・混合は声門の初期F0を110 Hzとし、64出力フレームごとに時定数0.06秒の対数補間で基準F0へ近づく。この初回更新の値も別計算で照合する。オフラインと実時間の入口は `prepareIpaVoice` とWorkletの初期化を共有し、実時間では準備した時点から2048フレーム先に発声を予約する。[WASMのIPA計画](../crates/vocal-wasm/src/planning.rs#L79)・[準備とレンダー](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L49)

IPAに乱流源を有効化する音素があれば、通常の声門・口唇系列に最小正断面積、歯への源の枝番号、励起レベル、前方向の注入圧力を加える。レンダー後に実際の気道網から読み、調音計画上のラベルから推定しない。枝の未選択は−1。Workletの量子ごとの処理は音響を進め、発話の出力先頭を基準に16フレームごとに観測を写す。JSONを保存した際は開始待ちの無音を含むブラウザ時計も実時間測定に記録する。CLI用ケースには合成開始後の音響を再現するための入力を保存する。[WASMの観測](../crates/vocal-wasm/src/lib.rs#L560)・[観測列の選択](../crates/vocal-wasm/host/fixed-voice.ts)・[ブラウザの計測器](../tools/measure_worklet_ipa_body.py)

## 実測結果

4体型の両モードで各134,454フレームのPCMが、保存したケースをCLIで再実行したPCMとビット一致した。8,404点の内部状態12系列はCLIと同値で、調音計画とジェスチャーも一致した。実時間は予定フレームで開始し、128フレーム量子が連続した。別の発声を開始してから停止し、入力を再び使えることも4体型で確認した。上流の `stop_spans`、`voiced_fricatives`、`body_mix` の11テストにも通過した。[結果と実行条件](../runs/worklet-bodyipa-20261120-a/summary.json)・[子どもの実時間保存ケース](../runs/worklet-bodyipa-20261120-a/artifacts/child-live-case.json)

| 体型 | 基準F0（Hz） | /s/ の狭窄中央値（cm²） | /z/ の狭窄中央値（cm²） | 歯への注入圧力RMS /s/・/z/（dyn/cm²） |
| --- | ---: | ---: | ---: | ---: |
| 成人男性 | 110.00 | 0.09781 | 0.13527 | 30.45・19.47 |
| 成人女性 | 205.00 | 0.07986 | 0.10995 | 22.50・15.47 |
| 子ども | 260.00 | 0.05520 | 0.07807 | 15.40・6.81 |
| 混合 | 169.50 | 0.07875 | 0.10952 | 22.49・15.27 |

/s/ の147点と /z/ の105点は、いずれも中央50%の窓で全点に歯への乱流励起がある。枝番号は全観測点で上流と一致した。/p/ の開閉検出は毎フレーム計測に対して2〜13出力フレーム後で、0.042〜0.271 msにあたる。例えば成人男性・女性・混合は毎フレームの閉鎖開始がそれぞれ13625・13622・13627番で、ブラウザの16フレーム間隔ではすべて13631番と観測された。[開閉の時刻と乱流の数値](../runs/worklet-bodyipa-20261120-a/summary.json)

PCMの上流との差は最大 `4.66×10⁻¹⁰`。最初のPCMビット差は条件により1963〜16139番で現れた。内部状態では、ブラウザの最初の観測点の15番フレームで成人男性の声門流量に `1.83×10⁻¹⁸ cm³/s` の差がすでにあり、毎フレームの先行照合では0番の歯までの距離にも差があった。乱流の上流差は許容範囲内だった。初回の声門F0と独立計算との差は最大 `2.85×10⁻¹⁴ Hz` だった。[ブラウザの差分](../runs/worklet-bodyipa-20261120-a/summary.json)・[先行の全フレーム比較](human-body-ipa.md#実装と照合)

初回と `/tmp` からの再実行で各136項目が通過した。ケース・波形・CLI出力・オフラインの観測・WASM・要約など39ファイルのSHA-256が一致した。実時間の観測JSON4件では、開始Contextフレームと経過時間などの時計に依存するフィールドに差が出た。出力フレームで整列した内部状態と計画は一致した。[初回](../runs/worklet-bodyipa-20261120-a/manifest.json)・[再実行](../runs/worklet-bodyipa-20261120-repeat/manifest.json)

既存の実時間IPA19項目、体型別英語発話86項目、歌唱15項目も通過した。CargoのワークスペーステストとClippy、WASMとWebのビルドも通過した。[実時間IPAの回帰](../runs/worklet-bodyipa-20261120-ipa-live-regression/summary.json)・[体型別英語の回帰](../runs/worklet-bodyipa-20261120-english-body-regression/summary.json)・[歌唱の回帰](../runs/worklet-bodyipa-20261120-song-regression/summary.json)

```bash
python3 tools/measure_worklet_ipa_body.py worklet-ipa-body-local-1
```
