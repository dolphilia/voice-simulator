# IPA発話をWASMとAudioWorkletに接続する

## 固定上流の読解

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流では `planUtterance` が構造化音素と計画条件をRustの `plan_utterance` へ渡す。計画は音素区間とジェスチャーの列を返す。UIは `schedule` メッセージでWorkletに渡し、`writeGestures` が秒単位の開始・終了・ランプ、重み、速度、順序付き目標をリトルエンディアンのf64に書く。省略した目標にはNaNを使い、文字ラベルは別領域に載せる。WASM側の `engine_schedule` はレコードをRustの構造へ戻し、相対時刻をエンジンの時計へ配置する。Workletはそのオフセットを計画区間にも適用してUIへ返す。[プランナー呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L150)・[ワイヤ形式](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/wire.ts#L48)・[ABIの読み込み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L193)・[Workletの受信処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)

`plan_utterance` の `/p/` は唇閉鎖の調音と、無声化・有気破裂を作る声門開大に分かれる。保持区間の両側にはランプがあり、複数のジェスチャーは同じ調音軸に重み付きで寄与する。候補の `ArticulatedVoice::step` は64出力フレームごとに目標を合成し、調音器、声道断面、接触補正を更新する。その後、声門と気道を内部サンプルごとに進め、放射とPCMを得る。上流の有気テストはIPAの記号が声門開大の計画に反映されることを確認し、WASMテストは操作時刻を保った分割でネイティブとPCMをビット照合する。[IPA発話プランナー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L320)・[上流の有気テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/aspiration.rs#L21)・[上流のWASMテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/wasm-engine.test.ts#L69)・[候補の発声制御](../crates/vocal-core/src/voice.rs)

## 実装前の登録

CLIの既存 `bilabial-p` における `ɑpɑ` をブラウザのIPA入力から計画する。出力は48 kHz、内部96 kHz、モノラル49,828フレーム。オフラインのContextの先頭と合成器の先頭を一致させ、ジェスチャー時刻はCLIと同じ原点からの秒数を使う。観測は16出力フレームごとの末尾と最終フレームで、フレーム番号 `n` の値は内部サンプル `2(n + 1) − 1` に対応する。

既存のCLIでは唇の最小断面が0.0002 cm²を下回る最初のフレームは11,118、再開口は13,888だった。ブラウザでは同じPCMを予測する。断面の観測は16フレームおきなので、最初の観測値は実イベントから最大15フレーム後となる。音素・ジェスチャーは1×10⁻¹²の数値許容差で、PCMはビット一致で比較する。固定上流との比較は元のケースの許容差を使う。発声に未対応のIPAを入力してエラーを表示した後にも、同じ画面から `ɑpɑ` を合成できることを検査する。[今回のケース](../cases/worklet-ipa-voice.json)・[元の入力](../cases/bilabial-p.json)・[CLIの時系列](../runs/bilabial-p-20261119-b/summary.json)

## 実装

ページは入力したIPAをUTF-8でWASMへ渡す。CLIと同じ `ipa_plan::plan` と `male_speech_gestures` が区間・診断・調音を返す。ラベルを含むJSONは観測用としてページに持ち、実行用のスコアは7値の時刻・強さ・速度と22の目標を並べたf64列としてWorkletに渡す。目標と任意の速度値の欠落はNaNで表す。スコアの復元・検証と初期配置は最初のPCMより前に行う。実行側では固定ケースの原点を0として、時間の移動を加えずにスコアを評価する。CLIとWorkletは成人男性の調音初期化と `OutputStage` を共有する。[共通の区間計画](../crates/vocal-core/src/phonetics/ipa_plan.rs)・[WASMの数値形式と配置](../crates/vocal-wasm/src/planning.rs)・[Workletの入力](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)

ブラウザは同じOfflineAudioContextのPCMと、フレーム番号付きの声門・呼気・放射・唇の観測をWAV・JSONに保存する。スコアによる発声は、この工程では成人男性の既定姿勢でオフライン実行する。最大32,768 UTF-8バイト、4,000ジェスチャーを受け付ける。動的に大きくなったWASMの線形メモリを参照する場合は、PCMや観測のTypedArrayを作り直す。固定発声とIPA発話は同じPCM出力段を共有する。[ページ側の計画](../crates/vocal-wasm/host/planning.ts)・[発声用ホスト](../crates/vocal-wasm/host/fixed-voice.ts)・[ブラウザの入力と出力](../../../../web/prototypes/chimera-research/README.md)

## 検証結果

- Chromiumで `ɑpɑ` を入力すると、音素・ジェスチャーの時刻がCLIと一致した。上流の区間とジェスチャーに対する最大差も0。有気区間は声門開大0.36 cm²、保持区間の終端は `/p/` の終端から20 ms後だった。
- 48 kHzの49,828フレームのPCMと、3,115時点の8観測系列はCLIと完全に一致した。CLI側の有意な最初の閉鎖は11,118、開口は13,888。ブラウザでの最初の観測は11,119と13,903で、差は1と15フレーム。ContextとWASMのフレームは連続していた。線形メモリの拡張は0回だった。
- 固定上流との差はPCMで最大 `1.82×10⁻¹²`。最初のPCMの差はフレーム13,291だった。初回サンプルの口端面積・放射にすでに微小な差があり、面積の差は `2.22×10⁻¹⁶ cm²` だった。音素区間・目標の差は検出していない。上流とCLIでは閉鎖・開口とも同じフレームを検出した。
- 画面の未対応 `/ɹ/` の入力でエラーを確認し、その後の `ɑpɑ` で成功した。先行版のオフライン・実時間の固定母音、IPA時間計画、CLI歌唱の回帰とワークスペースのRustテストも通過した。上流の有気、分割と高速発話の10テストが通過した。[初回](../runs/worklet-ipa-voice-20261119-a/manifest.json)・[再実行](../runs/worklet-ipa-voice-20261119-c/manifest.json)・[オフライン固定母音](../runs/worklet-fixed-voice-20261119-ipa-regression/summary.json)・[実時間固定母音](../runs/worklet-realtime-voice-20261119-ipa-regression/summary.json)・[IPA区間](../runs/speech-timing-20261119-ipa-regression/summary.json)・[CLI歌唱](../runs/song-voice-long-20261119-ipa-regression/summary.json)

研究ワークスペースから再実行する。ブラウザの準備はWeb側のREADMEを参照する。

```bash
python3 tools/measure_worklet_ipa.py worklet-ipa-voice-local-1
```
