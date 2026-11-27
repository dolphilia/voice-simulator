# ブラウザの英語発話で体型を選ぶ

## 上流の読解

- 上流の画面で体型を確定すると、ストアの `setBody` は発話・歌唱を停止し、新しい基準F0を取り、メッセージをAudioWorkletへ送る。Workletは `engine_set_body` の成人内女性比と子ども比（各0〜1、無次元）をRustに渡す。 `BodyMix::weights` は成人男性・成人女性・子どもの重みを `(1 − c)(1 − f)`、`(1 − c)f`、`c` とする。[ストア](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L299)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L108)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L276)・[体型の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L330)
- `Engine::make_voice` は選択体型で物理モデルと気道網を作り、基準音高（Hz）を設定する。動作中の `set_body` では、新しい声道と声門に切り替えてから、音高以外の音源設定、調音目標（長さはcm）、演奏者の呼気ゲートを復元する。新しい音響状態と時計は初期化し、ビートの位相は引き継ぐ。出力には体型と咽頭・口腔のセル数が含まれる。 `body_mix` は端点、重み、較正目標、共鳴、混合体型の発声を検査し、 `engine` は途中の体型変更を含むブロック分割不変性を検査する。[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L68)・[体型のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)・[分割不変性テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)
- `speakText` は辞書で句を作り、 `speakPhrases` が同じ体型・発話速度・基準F0を `planPhrases` に渡してスコアを予約する。上流の対話画面の基準は110・205・260 Hz。今回の比較では、既存の研究CLIの英語ケースと相互に再現できるよう、CLIの英語用端点112・205・250 Hzを両経路で共有する。体型の間は `exp(Σ wᵢ ln(Fᵢ))` で補間し、入力された基準F0を優先する。研究画面のレンダーでは開始前に体型を確定し、発声ごとに音響状態を初期化する。[上流の発話予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L52)・[上流画面の基準F0](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/body.ts#L54)・[研究CLIの基準F0](human-body-english.md)

## 事前登録

固定した英文 `Mom, pop. Is it so?` を3端点と混合体型でレンダーし、混合体型では180 Hz指定も比較する。気道の初期化から、64出力フレームごとの調音・呼気・F0の更新、気道と声門の内部計算、出力段を経たモノラルf32 PCMまで追う。最初の声門F0は110 Hz。PCMは48 kHzで118,748フレーム、気道と声門は96 kHz。加工前PCMを保存し、32出力フレームごとに声門面積と流量、放射、口唇、鼻端流量、軟口蓋などの10系列を照合する。各体型のセル数は固定気道の先行計測に照合する。ケースを画面から取得し、その実体をCLIの `inspect`、`render`、`render-pcm` へ渡す。上流の波形と内部状態は、同じ入力で保存済みの固定上流プローブの結果を使う。[登録ケース](../cases/worklet-english-body.json)・[英語の比較条件](../cases/human-body-english.json)・[先行の上流計測](../runs/bodyenglish-20261120-repeat/manifest.json)・[先行のセル数](../runs/airbody-20261120-repeat/summary.json)

## 体型を計画と音響へ渡す

ページ側WASMの `vocal_english_plan_with_body` は調音スコアを作り、選ばれた基準F0を返す。ホストは同じ2つの比率をWorklet側の `vocal_start_score_with_body` へ渡す。ここで体型別の咽頭・口腔・鼻腔と声門を持つ `ArticulatedVoice` を準備し、出力前にジェスチャーを適用する。Workletの声道観測バッファは声道を作った後に実際のセル数で確保する。これにより、計画と音響を構成するWASMの2インスタンスに体型が届く。[ページ側のWASM計画](../crates/vocal-wasm/src/planning.rs#L87)・[Worklet側のスコア初期化](../crates/vocal-wasm/src/lib.rs#L204)・[ブラウザのレンダーとケース生成](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L135)

保存する入力には、体型、テキスト、発話速度と開始時刻、中立姿勢、レート、音源設定を含める。基準F0を空欄にした場合は `voice.f0_hz` を省略してCLIの既定値を使う。入力された場合はその値を保存する。観測JSONでは実際に使った基準F0を確認できる。[画面](../../../../web/prototypes/chimera-research/src/main.tsx#L194)

## 計測時の失敗

最初のブラウザ実行は発声前に停止した。計測器がラベル文字列を直接検索したとき、選択肢を含む `select` の「体型」に完全一致しなかった。その間に辞書取得の待機が30秒で切れた。アクセシビリティツリーでは「体型」のコンボボックスが一つ存在することを確認し、ロールとアクセシブルネームで指定した。辞書の応答待機はフォーム操作の後に開始する。最初の実行は保存し、ケースの閾値は同じ値で再試行した。[初回の実行記録](../runs/worklet-bodyenglish-20261120-a/manifest.json)

ビルドの試行時は、BunがPATHに見つからなかったため既存の計測手順に従って固定のBun 1.4.4を `npx` から使った。Rustでは体型型の定義モジュールが非公開なので `vocal_core::anatomy` の再エクスポートを使う。

## 実測結果

Chromium 156.0.8078.4で5条件を画面から生成した。発音表示は全条件で `mˈɑm | pˈɑp | ɪzɪtsoʊ?`。保存したJSONをそのままCLIへ渡すと発音計画とジェスチャーが一致し、各条件のPCM 118,748フレームもビット一致した。3,711点の内部状態10系列にも差がなかった。上流の `body_mix` と `engine` の合計10テストも通過した。[ブラウザ計測結果](../runs/worklet-bodyenglish-20261120-repeat/summary.json)・[混合体型の保存ケース](../runs/worklet-bodyenglish-20261120-repeat/artifacts/three-way-explicit-180-case.json)

| 体型 | 基準F0（Hz） | 咽頭・口腔のセル数 | 疑問句末の計画F0（Hz） |
| --- | ---: | --- | ---: |
| 成人男性 | 112.00 | 18、18 | 151.20 |
| 成人女性 | 205.00 | 15、16 | 276.75 |
| 子ども | 250.00 | 11、13 | 337.50 |
| 混合 | 168.79 | 15、16 | 227.87 |
| 混合・180 Hz指定 | 180.00 | 15、16 | 243.00 |

上流とのPCMの最大絶対差は混合・180 Hz指定で `3.73×10⁻⁹`。最初のビット差は条件により1963〜20492番フレームで現れた。上流との内部系列には、ブラウザの最初の観測点である31番フレームですでに声門流量の差があり、成人男性では `4.70×10⁻¹⁷ cm³/s` だった。上流の計画とジェスチャーも許容差内で一致している。前回の全フレーム計測では0番フレームの幾何にも差があった。[ブラウザの差分](../runs/worklet-bodyenglish-20261120-repeat/summary.json)・[全フレーム計測](../runs/bodyenglish-20261120-repeat/summary.json)

ブラウザの疎な観測から求めた閉鎖は、同じ波形の全フレーム計測より最大0.583 ms遅れて検出された。子どもの鼻端流量ピークは全フレームの170.26 cm³/sから167.18 cm³/sへ約1.81%小さく測定された。発音の生成や時刻の比較では、観測間隔の選び方がこの差に関係する。[32フレーム間隔の計測](../runs/worklet-bodyenglish-20261120-repeat/summary.json)・[1フレーム間隔の計測](../runs/bodyenglish-20261120-repeat/summary.json)

修正後の初回と `/tmp` からの再実行で各86項目を満たした。保存ケース・観測・PCM・CLIの出力・WASM・要約を含む38ファイルのSHA-256が一致した。[修正後の初回](../runs/worklet-bodyenglish-20261120-b/manifest.json)・[再実行](../runs/worklet-bodyenglish-20261120-repeat/manifest.json)・[混合体型の画面](../runs/worklet-bodyenglish-20261120-repeat/artifacts/three-way-explicit-180.png)

既存のブラウザ計測は英語15項目、IPA12項目、歌唱15項目が通過した。CargoのワークスペーステストとClippyも通過した。[英語の回帰](../runs/worklet-bodyenglish-20261120-english-regression/summary.json)・[IPAの回帰](../runs/worklet-bodyenglish-20261120-ipa-regression/summary.json)・[歌唱の回帰](../runs/worklet-bodyenglish-20261120-song-regression/summary.json)

```bash
python3 tools/measure_worklet_english_body.py worklet-english-body-local-1
```
