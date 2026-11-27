# 歌唱中の声門面積パルスの振幅揺らぎ

## 上流の式と実装した入口

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`Engine::set_source()` から受け取った粗さを `HumanVoice::apply_source()` が声門に渡す。粗さ0.1でシマー係数は `0.02 + 0.22 × 0.1 = 0.042`。この係数は作ったパルスの面積を周期ごとに変える。周期ジッターは位相の歩進に掛かり、別の乱数を使う。[上流の音源設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L115)・[粗さとシマーの対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)

`ParametricGlottis::next()` は、96 kHzの各内部ステップで声門上下圧の差（dyn/cm²）から振動量を更新し、F0（Hz）と周期倍率で位相を進める。位相が折り返すと、シード777の乱数列の最初の4個を周期倍率に、次の4個を振幅倍率に使う。2番目の4個の一様乱数の和から2を引いて1.7320508倍した値を `g` とすると、このケースの振幅倍率は `max(0.12, 1 + 0.042 × g)`。係数が0でも乱数を同じ順で消費する。新しい振幅倍率は折り返したサンプルの振動面積から適用する。平滑化した面積振幅、振幅倍率、振動量、位相で決まるパルスを掛け、静的開口を足して声門面積（cm²）を得る。次に気道の流量（cm³/s）と圧力を更新し、放射の時間差分を48 kHzへ間引いてPCMを作る。[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L187)・[気道と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

研究版の通常の歌唱入力に `song_voice.voice.amplitude_shimmer` を加えた。予備描画の前に係数を既存モデルへ渡し、指定したケースのトレースに `glottal_cycle_amplitude_scale` を出力する。省略時は従来どおり係数0で描画する。上流の既存試験はホストブロック長の独立性、短音の拍、声帯を開いたときの周期内閉鎖を検証する。研究版では既存の固定圧のシマーケースも再実行し、周期、振幅、圧駆動の独立計算を確認した。[CLIで設定する位置](../crates/vocal-cli/src/timing_case/speech_voice.rs#L614)・[声門への適用](../crates/vocal-core/src/glottis.rs#L157)・[ブロック長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短い歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[声帯開大](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)・[固定圧の再実行](../runs/glottal-cycle-shimmer-20261122-song-regression/summary.json)

## 4条件での比較

ドリフト0とジッター0.00455を固定し、シマー0の研究版に0.042の条件を加えた。240 BPMの「Pop Dee」2音で、予備描画16,384・16,512フレームと乱流注入量0・1の組合せを使った。予約直後から各31,200点の声門状態を、譜面開始から各29,760点のPCMを照合した。物理量とPCMの閾値は前回と同じで、有声区間は譜面相対21,000〜21,599サンプル。口端は上流・研究版とも最小断面を比較し、前回確認した列の定義差を解消した。[事前登録](../cases/song-voice-schedule-shimmer.json)・[計測器](../tools/measure_song_schedule_shimmer.py)

観測した振幅倍率は全4条件で独立計算と一致し、31,200点中の最小・最大は0.89358、1.11722だった。予備描画中の110 Hzと予約後の観測F0から96 kHzで独立に位相を積分して周期番号を求め、振幅用乱数を別に計算した。研究版のシマー0・0.042と固定上流の全点で、位相とF0はビット一致した。口端最小断面の上流との最大差は5.7×10⁻¹⁴ cm²だった。[独立計算](../tools/measure_song_schedule_shimmer.py#L24)・[結果要約](../runs/song-voice-schedule-shimmer-20261122-a/summary.json)

| 上流との比較 | シマー0の研究版 | シマー0.042の研究版 |
| --- | ---: | ---: |
| 声門面積の最大絶対差（cm²）、4条件の最大 | 9.76×10⁻³ | 1.18×10⁻¹⁵ |
| 声門流量の最大絶対差（cm³/s）、4条件の最大 | 11.99 | 5.15×10⁻¹¹ |
| 放射差分の最大絶対差（cm³/s²）、4条件の最大 | 59,165.98 | 2.13×10⁻⁷ |
| 有声窓のPCM誤差RMS、4条件の範囲 | 0.00621〜0.00734 | 0 |
| 全PCMの最大絶対差、4条件の最大 | 0.03195 | 1.46×10⁻¹¹ |

シマーをそろえた場合、登録した声門面積・流量・放射・PCMの全閾値内に収まった。研究版でシマーだけを変えると、声門面積と放射は20,878または20,879サンプルから差が見え、PCM差は20,915または20,916で閾値を超えた。この位置は、各予約フレームで乱流注入の有無に共通だった。予備描画を128フレーム変えた組同士では、従来の通常乱流14,330・乱流注入量0の20,910サンプルに今回もPCM差が見えた。[4条件の物理量とPCM](../runs/song-voice-schedule-shimmer-20261122-a/summary.json)

### 閾値を下回る残差

生の保存PCMをビットで比較すると、29,760サンプル中、条件ごとに5〜11点が異なった。いずれも最初の差は譜面相対11,692で、振幅約6.34×10⁻⁹の1 ULP差だった。保存した内部物理量のうち、放射差分には11,104で約4.7×10⁻¹² cm³/s²、声門上下圧と流量には11,113で差が見えた。この位置では声門面積は一致しており、シマーに由来する有声化後の差より早い。48 kHzでは各出力サンプルに対応する96 kHzの2ステップを別々に観測していないため、これらの差が始まる演算の位置は未確定。[上流の保存系列](../runs/song-voice-schedule-drift-20261121-repeat/artifacts/upstream/frame-16384-noise-0.csv)・[研究版の保存系列](../runs/song-voice-schedule-shimmer-20261122-a/artifacts/frame-16384-noise-0/voicing.csv)

## 実行と保存

次を研究ワークスペースから実行した。再実行は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。固定上流の `engine`、`sing_fast`、`lung_port` の15テストと、研究版の `cargo test --locked -p vocal-core -p vocal-cli -p vocal-wasm` の41テストが通過した。研究版は `cargo check --locked --target wasm32-unknown-unknown -p vocal-wasm` にも通過した。シマーを省略したPCM・声門CSV、および明示的に0としたPCMと従来の観測列は、保存済みの研究版とビット一致した。負のシマーを渡したCLIは入力エラーを返した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 \
  ../../.venv/bin/python tools/measure_song_schedule_shimmer.py song-voice-schedule-shimmer-20261122-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 \
  ../../.venv/bin/python tools/measure_glottal_cycle.py glottal-cycle-shimmer-20261122-song-regression glottal-cycle-shimmer
```

歌唱比較は各34判定（予測14件を含む）を通過。各157入力・30出力をハッシュとサイズで照合し、PCM・CSV・要約の21件と、出力段CSV8件の抜粋前ハッシュが再実行間で一致した。出力段CSVは全区間をビット照合した後、事前指定した区間を保存した。初回の8件は15,869,982バイトから878,886バイトになった。外部ディスクRTL9210B-CGに比較2回で189,854,466バイト、固定圧の回帰で20,054,332バイトを保存した。[初回](../runs/song-voice-schedule-shimmer-20261122-a/manifest.json)・[再実行](../runs/song-voice-schedule-shimmer-20261122-repeat/manifest.json)・[固定圧の回帰](../runs/glottal-cycle-shimmer-20261122-song-regression/manifest.json)

次は、通常の上流音源のドリフト5セントも研究版に指定し、予約位置を固定したSafariの既存の加工前PCMと両版を同じ条件で照合する。今回のドリフト0の数値を、音源設定とブラウザ経路の両方を確かめる対照にする。
