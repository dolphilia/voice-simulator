# 研究版の歌唱予約と声門の乱流を固定上流へ照合する

## 上流と研究版の描画順

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `Engine::schedule()` は、実際に音声を描画して進んだ時計に先行時間を足して譜面を予約する。 `HumanVoice::render()` は48 kHzの出力1サンプルにつき96 kHzの内部処理を2回進める。先に声門の上下圧から声門面積を求め、その値を気道のポートに渡す。気道の乱流は枝の流量と断面からレイノルズ数を求め、活動した枝に帯域雑音による圧力を加える。圧力と流量の更新を経た放射出力が、間引きと出力処理でPCMになる。ブロック長を変えてもPCMが一致することと、短い母音が拍に合うことは上流のテストで照合する。[予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[発声の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[乱流注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

研究版は通常のCLIで `song_voice` を読むと `run_song()` で音素区間と譜面を計画する。今回追加した `warm_up_frames` を指定すると、譜面を渡す前に `ArticulatedVoice::step()` と `OutputStage::render_frame()` でその数の出力フレームを進める。声門の位相、気道の乱数と帯域フィルタ、間引き器・直流除去などの状態を保持したまま、予備描画の終了時の音源時計をジェスチャーの開始・終了に足して歌唱を始める。保存するPCMとCSVは譜面を渡した位置から始まる。音源の基準F0には `base_pitch_hz` を指定できる。従来のケースは予備描画0フレームで、歌唱の最初の音符を基準F0にする。[CLIの入口](../crates/vocal-cli/src/main.rs#L332)・[歌唱の設定と描画](../crates/vocal-cli/src/timing_case/speech_voice.rs#L253)・[声門と放射の更新](../crates/vocal-core/src/voice.rs#L212)・[PCM出力段](../crates/vocal-core/src/output.rs#L76)

研究版の乱流源は声門のポートを観測し、正の流量では咽頭の先頭から2本目の枝へ、逆流では気管側へ圧力を加える。乱流量0でも乱数とフィルタは進む。出力側に見える最初の差を比較するため、固定上流と同様、48 kHzで1サンプルを出した直後の値を使った。内部の2ステップの区別は残る。[声門乱流の枝](../crates/vocal-core/src/airway/human/frication.rs#L62)・[乱数、フィルタ、注入](../crates/vocal-core/src/airway/network/turbulence.rs#L106)

## 条件と判定

固定上流と同じ男声の中立姿勢、歌詞「Pop Dee」、MIDI 60と64を各0.25拍、240 BPM、肺圧7.2 cmH₂O、呼気ゲート0、基準F0 110 Hz、緊張度0.5で比較した。予約前に16,384または16,512フレームを予備描画する。各条件で乱流量1と0を計測した。譜面の時刻0をそろえるため、保存時刻の先頭から先行時間1,440サンプルを差し引いた。この準備区間と譜面時刻0以降を合わせて31,200フレーム出力する。従来の歌唱CLIの音源設定を使うため、上流の既定の揺らぎまでは合わせていない。[事前登録](../cases/song-voice-schedule-state.json)・[固定上流の基準](upstream-song-schedule-state.md)・[ケース生成と比較](../tools/measure_song_schedule_state.py)

固定上流の各音素区間と、研究版が `inspect` で出す譜面時刻を整数サンプルで照合した。出力の長さ、値の有限性、128・77フレーム単位のPCMと出力段のCSVの一致を取得条件にした。予備描画を変えたときの声門位相、唇・呼気、乱流圧、放射、PCMを既登録の閾値で比較し、固定上流とのPCM差の発生位置の違いは128フレーム以内と予測した。[解析](../tools/measure_song_schedule_state.py)

## 実測

初回と別ディレクトリからの再実行は各16件の取得判定と5件の予測を通過した。音素区間は全条件で固定上流と同じ出力サンプルにあり、唇開きと呼気ゲートは予備描画を変えても許容差内で一致した。[初回](../runs/song-voice-schedule-state-20261121-a/summary.json)・[再実行](../runs/song-voice-schedule-state-20261121-repeat/summary.json)

| 予備描画を128フレーム増やしたときの差 | 固定上流 | 研究版 |
| --- | ---: | ---: |
| 通常の乱流で声門の枝圧に差が出た位置 | 14,256 | 14,256 |
| 通常の乱流で放射に差が出た位置 | 14,256 | 14,256 |
| 通常の乱流でPCM差が0.000001を超えた位置 | 14,330 | 14,330 |
| 乱流注入量0で声門面積・放射に差が出た位置 | 20,878 | 20,878 |
| 乱流注入量0でPCM差が0.000001を超えた位置 | 20,903 | 20,908 |

位置は譜面時刻0から数えた48 kHzの出力サンプル番号。研究版の最初の乱流圧は、上流と同じ咽頭枝13で+0.007235533と−0.003690928 dyn/cm²となった。同じ予約位置どうしで比較した上流との差は、最初の注入で1.5×10⁻¹³ dyn/cm²以下。通常乱流の最初のPCM差が閾値を超えるときの差分の大きさも両実装で1.00133×10⁻⁶だった。[計測済みの枝圧](../runs/song-voice-schedule-state-20261121-repeat/summary.json)・[上流での枝の照合](../runs/upstream-song-schedule-state-20261121-repeat-b/artifacts/probe.json)

乱流を0にすると研究版のPCM差の初回位置は通常条件より6,578サンプル（約137.04 ms）遅れた。上流より5サンプル遅いが、声門面積と放射に最初の差が出る位置は上流とそろった。有声化以降のPCMを実装間で絶対比較した最大差は、±1に正規化したPCMで約0.47〜0.48。通常の歌唱設定で、研究版は周期揺らぎとピッチドリフトを0に初期化し、上流は既定のピッチドリフト5 centsを使う。位相の進みは研究版0.293333周期、上流0.293762周期だった。出力PCMが分かれる要因のうち、既定のピッチドリフトと周期揺らぎそれぞれの寄与は未分離。[研究版の声門初期値](../crates/vocal-core/src/voice.rs#L90)・[上流の声門初期値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L52)・[上流の位相測定](../runs/upstream-song-schedule-state-20261121-repeat-b/summary.json)

## 検証と保存

最初のコンパイルでは、共通の描画設定に予備描画数を追加した際に拍パターンの初期化が漏れた。そこに従来と同じ0を指定してから正式計測した。独立に保存PCMの閾値超過とCSVの枝圧を読み直し、保存した2回のPCM・計測CSV・要約はバイト一致した。既存の短音の声門・狭窄乱流ケースを再実行して各18・16件の取得判定が通過した。狭窄ケースの従来のPCMと物理量CSVもビット・バイト一致だった。声門乱流のフィルタ状態を保つ既存の単体テストも通過した。[声門の回帰](../runs/song-voice-fast-glottis-source-20261121-warm-up-regression/manifest.json)・[狭窄の回帰](../runs/song-voice-fast-constriction-source-20261121-warm-up-regression/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。比較2回の各123入力・30出力をサイズとSHA-256で照合し、PCM・状態CSVを含む計215,132,778バイトをRTL9210B-CGに保存した。再実行は `/private/tmp` からPythonとスクリプトの絶対パスで起動した。[初回マニフェスト](../runs/song-voice-schedule-state-20261121-a/manifest.json)・[再実行マニフェスト](../runs/song-voice-schedule-state-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=160000000 ../../.venv/bin/python \
  tools/measure_song_schedule_state.py <実行ID>
```

次は固定上流側でも、短い譜面・既定の乱流源を使ってピッチドリフトだけを0にする。予備描画2位置で、声門位相、発声後の声門面積と流量、PCMの差が研究版の0設定にどこまで近づくかを確認する。
