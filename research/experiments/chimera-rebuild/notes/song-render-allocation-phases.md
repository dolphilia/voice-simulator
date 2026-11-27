# 48 kHz歌唱で声道更新が割り当てる領域を調べる

## 上流の歌唱と調音更新

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `playTune()` はMIDIと歌詞を拍・秒に変換し、ジェスチャー列をWeb Audioへ予約する。Workletが `engine_schedule()` でジェスチャーを渡し、`engine_render()` で出力フレーム数を要求する。`Engine::render()` はホストの要求を内部ブロック境界で区切る。人の `HumanVoice::render()` は制御カウンタが尽きたサンプルで `control()` を呼ぶ。制御関数は内部標本レート `fs` から `dt = ctrl_every / fs` 秒を求め、現在時刻でスコアを混合し、調音器を進めてから時計を更新する。新しい姿勢に `airway.apply()` を適用し、接触補正で姿勢が変わった場合だけ `reapply()` して気道グラフの補間を開始する。各内部サンプルでは肺圧、声門開口と圧力伝搬を進め、間引き後の出力をFloat32へ書く。上流の歌唱計画試験はTypeScriptの既定計画との一致を、エンジン試験は異なるホスト分割で同じ波形になることを確認する。[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts:330)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs:176)・[人の調音更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs:457)・[計画試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_planning.rs:168)・[ブロック分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs:78)

研究版は `vocal_render()` → `OutputStage::render_frame()` → `ArticulatedVoice::step_with_glottal_pressure()` を通る。出力は48 kHzで、内部96 kHzの2標本に対応する。64出力フレームごとの制御では、輪郭と接触から目標断面を求め、咽頭・口腔を等長セルに再標本化する。`HumanTractControl::apply()` は前周期の確定断面を今回の変化率制限に用い、`reapply()` も同じ基準断面と秒単位の周期を用いる。面積はcm²、管長はcm。再計算した場合は乱流源を更新してから声道補間を開始する。[ネイティブABI](../crates/vocal-wasm/src/lib.rs:967)・[接触補正の呼び出し](../crates/vocal-core/src/voice.rs:591)・[声道更新](../crates/vocal-core/src/airway/tract_control.rs:155)

## 事前登録

現行の通常入口で旧記録を再現した。48 kHzの `Pop Dee` は出力91,200フレーム・713量子、量子ごとの描画割り当てと再割り当ては旧計測と全件一致し計11,809回。出力44,672〜47,744フレームで始まる25量子が各32回だった。通常は各16回で、この区間の直前の1量子は24回だった。2つの制御周期が1量子に入るため、接触補正による声道の再計算で更新回数が倍になった仮説を登録する。`resample()` は咽頭・口腔のセル列をそれぞれ生成し、`raw.clone()` は両セル列を複製する。この2段だけでも更新1回につき4回の割り当てを予測する。計測モードを切り替えてPCMと観測値を照合し、ABIの全件数と段階内訳を分けて保存する。[事前登録](../cases/song-render-allocation-phases.json)・[現行のブラウザ・CLI・上流比較](../runs/worklet-live-song-allocation-current-20261122-a/summary.json)・[旧計数](../runs/worklet-live-song-20261120-a/manifest.json)・[等長セル](../crates/vocal-core/src/anatomy/resample.rs:37)

## 計測の実装と結果

ネイティブの診断機能 `render-allocation-probe` で、既存のテスト用アロケーターのカウンターを同じスレッドから読む。対象関数へ入ったときと抜けたときの件数の差を取り、128出力フレームごとに集計する。PCMと観測値は描画前に確保した領域へ記録した。声道更新の総件数とその内訳は入れ子なので、内訳は親の値の検算に使う。最初の試験コマンドは完全一致のフィルターにモジュール名を付けておらず0件で終了した。正式な計測では `tests::song_render_allocation_profile` を指定し、各記録で1試験の実行を確認した。[計数器](../crates/vocal-core/src/render_allocation_probe.rs)・[計測と照合](../tools/measure_song_render_allocation_phases.py)・[正式なマニフェスト](../runs/song-render-allocation-phases-20261122-b/manifest.json)

| 処理 | 呼び出し | 割り当て・再割り当て |
| --- | ---: | ---: |
| 声道の初回更新 `apply()` | 1,425 | 11,400 |
| 接触補正後の `reapply()` | 51 | 408 |
| 乱流源登録 | 1,476 | 1 |
| 気道補間の準備 | 1,425 | 0 |

出力44,672〜47,744フレームの25量子は、すべて `apply()` が2回で16件、`reapply()` が2回で16件。直前の44,544フレームの量子には再計算が1回あり、追加の8件を説明できた。初回量子の17件目は乱流源登録の範囲に入った。制御更新の外側と段階の内訳に計数残差はゼロだった。[量子別の計数](../runs/song-render-allocation-phases-20261122-b/artifacts/allocations-by-quantum.csv)・[全体の集約](../runs/song-render-allocation-phases-20261122-b/summary.json)

声道更新1回の8件の内訳は輪郭0、接触グリッド3、面積プロファイル1、等長セルへの再標本化2、解析用の `raw` を制限用の `limited` に複製する処理2。接触グリッドには屋根沿い距離、測定格子、接触付きの標本列の確保が含まれる。次は `raw` と `limited` の観測値を維持したまま、複製先の咽頭・口腔セル領域を再利用できるかを別ケースで調べる。計測された複製の2,952件を消せれば、全体の割り当ては11,809回から8,857回に減る見込み。今回の計測はネイティブでの回数を示す。ブラウザの時間予算に対する効果には別の実測が要る。[断面目標と複製](../crates/vocal-core/src/airway/tract_control.rs)・[計測点の実装](../crates/vocal-core/src/anatomy/contact.rs)

観測を有効・無効にした出力91,200標本と、1,425観測点のABI全23値はビット一致した。通常のブラウザの出力全体と保存対象の12観測列も一致した。独立検算では、生のFloat32・Float64とCSVから件数を再計算した。診断の2回はPCM、観測値、量子別の内訳、要約がバイト一致した。計測機能を指定しないブラウザ・CLI・固定上流との回帰は25判定を通過し、候補と固定上流のPCMの最大差は2.33×10⁻¹⁰。上流エンジン・計画15試験と再実装のコア・ABI38試験も通過した。4実行の809入力・68出力をサイズとSHA-256で照合し、成果の実体343,437,813バイトをRTL9210B-CGに保存した。[ブラウザの回帰](../runs/worklet-live-song-allocation-probe-regression-20261122/summary.json)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-song-render-allocation-phases.py)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-allocation-current-20261122-a --live
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" ../../.venv/bin/python tools/measure_song_render_allocation_phases.py song-render-allocation-phases-20261122-b
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-allocation-probe-regression-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
```
