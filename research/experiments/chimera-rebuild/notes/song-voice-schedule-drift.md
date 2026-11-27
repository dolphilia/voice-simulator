# 歌唱予約前のピッチドリフトと声門位相

## 読んだ経路と式

固定上流の `Engine::set_source()` は `HumanVoice::set_source()` に部分更新を渡し、`apply_source()` が各値を声門のパラメータへ反映する。今回の対照では描画前に `SourcePatch.drift` を5から0セントへ変えた。粗さ0.1から計算するジッター0.00455とシマー0.042は両条件で同じ。基準F0と歌唱のビブラートは調音・呼気と一緒に制御フレームごとに更新される。予約は所定のフレームまで描画したエンジン時計に30 msを足して行う。[予約と音源設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L115)・[sourceから声門への反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)・[調音と音高の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)

`ParametricGlottis::next()` は声門上下圧の差を平滑化した後、96 kHzの内部32サンプルごとに低周波の乱数ドリフトを更新する。シード4,242から得た乱数をカットオフ0.3、0.9、2.7 Hzの一次フィルタに通し、出力を重み1、1/2、1/3で足して1.4で割る。この値とドリフト量の積をビブラートのセント値に足す。合計を `c` セントとすると、F0に掛ける倍率は `2^(c/1200)`。ドリフト量0でも乱数は進み、その値はビブラートの位相歩進に残る。独立計算に使う予約直後の30 msはビブラートの深さ0である。[ドリフト用状態と乱数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L238)・[ピッチ変調](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)

声門の位相は1内部サンプルにつき `F0 / 内部レート / 周期倍率` 進む。周期の折り返しで、シード777から得るジッターで次の周期倍率を、シマーで面積パルスの振幅を変える。圧差に応じた振動量とパルスから声門面積（cm²）を求め、気道のポートに設定して流量（cm³/s）と圧力（dyn/cm²）を更新する。口・鼻の放射の時間差分を間引き、直流除去と制限を経てPCMにする。上流ではホストブロック長で波形が変わらないこと、短い音が拍に合うこと、声帯を離したときに閉鎖区間が変わることを試験している。[周期倍率と振幅](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L187)・[声門からPCM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ブロック長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[声帯を離す試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)

研究版では通常の `song_voice.voice.pitch_drift_cents` から既存の声門変調器に係数を渡す。実験の0セントは設定を省略した従来の入力、5セントは新しい設定を指定した入力を使った。指定した値は予備描画の前に適用する。ジッター、シマー、PCMの出力処理は各実装の従来条件で各々そろえた。[歌唱CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs#L254)・[適用位置](../crates/vocal-cli/src/timing_case/speech_voice.rs#L595)・[変調器](../crates/vocal-core/src/glottis.rs#L305)

## 比較と実測

事前登録した240 BPMの「Pop Dee」2音で、予約前の16,384・16,512フレームと乱流注入量1・0を組み合わせた。両版とも48 kHzの出力サンプル末尾で状態をそろえた。譜面時刻0の前の1,440サンプルでピッチを照合し、0以降の29,760サンプルで最初のPCM差を走査した。有声部の誤差は21,000〜21,599サンプルの同じ窓で測った。[事前登録](../cases/song-voice-schedule-drift.json)・[比較コード](../tools/measure_song_schedule_drift.py)

5セントの予約直後のF0は、両版とも16,384フレームで109.891759704 Hz、16,512フレームで109.889694350 Hzだった。0セントでは110 Hz。0と5のF0比をセントに戻すと、予約後の1,440点すべてが独立したIIR計算と保存された数値で一致した。ドリフト量をそろえた場合の実装間F0差は、測定全区間で閾値10⁻⁹ Hz以下だった。いずれの実装でも、0と5の間で声門の位相は予約直後の第1サンプルに分かれ、声門面積・流量・放射は20,878サンプルに、PCMの閾値超過は20,902または20,904サンプルに現れた。乱流注入量0と1で、この初回位置は同じだった。[詳細](../runs/song-voice-schedule-drift-20261121-a/summary.json)・[独立ピッチ計算](../tools/measure_glottal_pitch.py#L26)

| 同じ予約位置での両実装のPCM比較 | 21,000〜21,599サンプルの誤差RMS、4条件の範囲 |
| --- | ---: |
| 上流5セント・研究版0セント | 0.10884〜0.11786 |
| 両方0セント | 0.04488〜0.04913 |
| 両方5セント | 0.04658〜0.05037 |

ドリフト量をそろえると、有声区間のRMS誤差は各条件で57〜59%減った。上流のドリフトを0とした場合、予約時の絶対位相は研究版より0.04189または0.04261周期進んでいた。研究版の直接積分は一定周期で、上流の直接積分はシード777から独立に計算した周期倍率を使った。これで0セントの実測位相を両版・全先行区間で4.5×10⁻¹⁶周期以内に説明できた。シマーは位相の式に入らず、声門面積に掛かる。ドリフトをそろえた後の波形差のうち、周期と面積の揺らぎがそれぞれ何割を説明するかは未測定。[独立周期倍率](../tools/measure_glottal_cycle.py#L41)・[実測](../runs/song-voice-schedule-drift-20261121-a/summary.json)

同じ実装で予約前の描画量だけを128フレーム変える前回の比較も、保存PCMから読み直した。通常乱流の初回閾値超過は、上流と研究版の0・5セントすべてで14,330サンプル。注入量0では上流0セント20,910、研究版0セント20,908、上流5セント20,903、研究版5セント20,902サンプルだった。乱流注入を止めたときに前回残った5サンプル差は、同じ係数での比較では0セントで2、5セントで1サンプルになった。[研究版の0セント](../runs/song-voice-schedule-state-20261121-repeat/manifest.json)・[上流の5セント](../runs/upstream-song-schedule-state-20261121-repeat-b/manifest.json)・[追加した2条件](../runs/song-voice-schedule-drift-20261121-a/manifest.json)

## 実行と保存

研究ワークスペースから次を実行した。別ディレクトリの再実行は `/private/tmp` から、Pythonとスクリプトを絶対パスにして実行した。固定上流の `engine`、`sing_fast`、`lung_port` の15テストと、研究版の `cargo test --locked -p vocal-core -p vocal-cli` の15テストが通過した。負のドリフト量を指定したCLIの `inspect` はエラーを返した。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。比較2回は各53判定を通過し、各160入力・43出力をサイズとSHA-256で確認した。29件のPCM・CSV・要約が両回でバイト一致した。設定省略時の回帰は既存の16判定と5予測を通過し、123入力・30出力をハッシュ照合した。設定追加前と同じPCM・CSV・要約21件もバイト一致だった。実体はRTL9210B-CGに比較2回で276,598,178バイト、回帰で107,566,776バイト保存した。[初回](../runs/song-voice-schedule-drift-20261121-a/manifest.json)・[再実行](../runs/song-voice-schedule-drift-20261121-repeat/manifest.json)・[設定を省略した回帰](../runs/song-voice-schedule-state-20261121-drift-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 \
  ../../.venv/bin/python tools/measure_song_schedule_drift.py song-voice-schedule-drift-20261121-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=160000000 \
  ../../.venv/bin/python tools/measure_song_schedule_state.py song-voice-schedule-state-20261121-drift-regression
```

次はドリフト0を固定し、研究版のジッターだけを上流の0.00455にする。先行区間で絶対位相がそろうか、有声区間の面積・放射・PCMの残差がどう変わるかを測る。
