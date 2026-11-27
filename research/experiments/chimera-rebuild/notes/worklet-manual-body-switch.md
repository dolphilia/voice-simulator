# 手動発声中の体型切り替え

## 上流の読解

- ストアの `setBody` は歌唱や発話を止め、Workletへ成人内女性比と子ども比を送る。Workletが `engine_set_body` を呼び、`Engine::set_body` は新しい `HumanVoice` と気道網を作る。中立姿勢の位置、調音速度、圧力・流量、声門位相、呼気の現在値、出力フィルタの履歴は初期化される。古い全調音目標と舌先の自由設定、音高以外の音源設定、演奏者の呼気目標を新しい声に渡す。音高目標は新体型の既定値に更新し、声の局所時計は0に戻す。外側の出力サンプル時計は維持する。上流にはビートの時刻を引き継ぐ処理もある。今回は手動発声の切り替えを記録する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L299)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L108)・[切り替え](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L88)・[声道と出力段の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L223)
- 96 kHzの内部計算を128サンプル進めるごとに調音・呼気・音高を更新する。成長側の無次元呼気ゲートは `g ← g + (G−g)(1−exp(−Δt/0.025))`。音高（Hz）は `f ← f(F/f)^(1−exp(−Δt/0.06))`。調音位置（cm）は `a=ω²(目標−位置)−2ωv`、続けて `v←v+aΔt`、`位置←位置+vΔt` で更新する。唇の `ω=2π×11` rad/s。形状と圧力を更新してから、声門流量・放射・PCMを得る。上流の `engine` テストは絶対サンプル位置の体型変更を含むセッションがホスト分割で変わらないこと、`body_mix` は端点と混合を確認する。[呼気とF0](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L511)・[調音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)・[ホスト分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)

## 事前登録

既存の固定母音 /i/ から始め、口唇開度を0.35 cmへ設定して保持し、成人女性へ切り替える。実際に操作を適用した128フレーム量子を保存する。切り替え後の位置は中立の0.7 cmから同じ0.35 cmへ追従し、呼気目標1のままゲートが立ち上がる。直後の量子末尾で制御2回分を独立計算し、停止前のF0が205 Hzに近いことを確かめる。上流は既存の手動計測と同様に比較用ゲインを揃え、乱流・声門の微小変動を0にした条件で計測する。[登録ケース](../cases/worklet-manual-body-switch.json)・[先行のケース保存](../cases/worklet-manual-case-export.json)

## 実装と初回の差

Workletは次のレンダー量子で調音目標を渡してから体型を切り替え、適用した出力フレーム、体型、咽頭・口腔のセル数を `bodyChanges` に記録する。保存ケースの `articulators.events[].body` には同じ時刻を制御フレーム番号に直して書く。CLIの `render` と `render-pcm` はその時刻で作り直した声に切り替える。出力段はフィルタの係数を保ったまま履歴を初期化する。[手動Worklet](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[ケースの保存](../../../../web/prototypes/chimera-research/src/manual-replay.ts)・[発声器の切り替え](../crates/vocal-core/src/voice.rs)・[CLIの再現](../crates/vocal-cli/src/articulation_case/voiced.rs)

初回 `a` は収録とCLIによる出力まで進み、比較プログラムが列名をキーとする辞書にスライスを適用して停止した。列ごとに内部サンプルを出力フレームへ対応させ、同じ登録条件で `b` を計測した。CLI・ブラウザ間のPCMと内部状態は一致した。固定上流とは切り替えの28032フレームで口腔中央の最小断面積に −0.03866 cm² の差が出て、13フレーム後にPCMが許容差を超えた。調音の初期化を読み直すと、上流は声道を作る前に中立姿勢の舌先を顎の回転から求めた `(6.24141, 6.81046)` cm に置き直す。既存の自由舌先の計算を初期化でも共有するよう候補を修正し、登録条件と閾値を維持した。[初回の失敗記録](../runs/manual-bodyswitch-20261120-a/manifest.json)・[修正前の判定と最初の差](../runs/manual-bodyswitch-20261120-b/summary.json)・[上流の舌先初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L79)・[修正後の初期姿勢](../crates/vocal-core/src/anatomy.rs#L83)

## 実測結果

```bash
python3 tools/measure_worklet_manual_body_switch.py manual-bodyswitch-local-1
```

- `c` は12項目すべて通過した。27776出力フレームで咽頭・口腔は18・18セルから15・16セルになった。ブラウザの加工前PCM全88,960フレームは保存ケースを入力したCLIとビット一致し、量子末尾695点の12観測系列も一致した。CLIを128・77フレームで分けてもWAVと出力CSVのハッシュは一致した。[実行記録](../runs/manual-bodyswitch-20261120-c/manifest.json)・[判定と測定値](../runs/manual-bodyswitch-20261120-c/summary.json)
- 切り替え直後の量子末尾で、唇の開度は0.691656 cm、呼気ゲートは0.101175、F0は113.0175 Hzだった。位置・呼気・F0の独立計算との差はそれぞれ0 cm、`5.56×10⁻¹⁷`以下、`2.85×10⁻¹⁴` Hz以下だった。停止直前の2400フレームで観測値の中央値は0.350000 cm、F0は204.9302 Hzとなった。固定上流との最大PCM絶対差は `7.28×10⁻¹²`、断面積の最大絶対差は `5.38×10⁻¹⁴` cm²以内だった。[上流照合と独立計算](../runs/manual-bodyswitch-20261120-c/summary.json)
- 切り替えを実行したサンプルで生のPCMはほぼ0に戻った。直前の値は `c` で −0.17585、直後は `−7.47×10⁻¹²` だった。操作が当たる位相によって生のPCMに段差が生じる。再生時の知覚とスコア再生中の体型変更は今後の比較対象とする。[切り替え前後の観測](../runs/manual-bodyswitch-20261120-c/summary.json)
- `/tmp` からの `repeat` も全12項目を通過した。切り替えフレームは `c` の27776に対して27520だった。両方の `browser.json` から取得した適用フレームを起点に、停止までの `browser.wav` を切り出して32ビットの値を比較すると、22,784フレームすべてで一致した。[再実行記録](../runs/manual-bodyswitch-20261120-repeat/manifest.json)・[再実行の測定値](../runs/manual-bodyswitch-20261120-repeat/summary.json)
- 体型変更を含まない従来の操作・ケース保存は20項目、英語歌詞による実時間歌唱は25項目の回帰比較を通過した。`cargo test --workspace --locked`、`cargo clippy --workspace --all-targets --locked -- -D warnings`、Webの型検査とビルドも通過した。[手動発声の回帰](../runs/manual-bodyswitch-20261120-manual-regression/manifest.json)・[歌唱の回帰](../runs/manual-bodyswitch-20261120-song-regression/manifest.json)
