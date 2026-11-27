# 歌唱予約時の声門周期ジッター

## 読んだ経路と更新順序

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`Engine::set_source()` から `HumanVoice::apply_source()` へ粗さを渡す。粗さ0.1のとき、周期長の揺らぎ係数は `0.0021 + 0.0245 × 0.1 = 0.00455`、面積パルスの振幅の揺らぎ係数は `0.02 + 0.22 × 0.1 = 0.042`。今回はピッチドリフトを0にした前回の上流出力を基準にした。通常の歌唱CLIに追加した `song_voice.voice.period_jitter` は、描画前に研究版の周期長の係数だけを設定する。係数の単位は無次元で、省略時は従来の0を使う。[上流の音源設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L115)・[粗さからの変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)・[研究版の歌唱入力](../crates/vocal-cli/src/timing_case/speech_voice.rs#L113)・[声門の設定](../crates/vocal-core/src/glottis.rs#L147)

内部96 kHzの1ステップで、声門上下圧の差（dyn/cm²）を平滑化し、制御されたF0（Hz）から `F0 / 96,000 / 周期倍率` 周期だけ位相を進める。折り返すステップの増分には旧周期の倍率を使う。続いてシード777の乱数から、次の周期倍率を `clamp(1 + ジッター係数 × g, 0.55, 1.8)` として決める。ここで `g` は一様乱数4個の和から2を引き、1.7320508を掛けた値。振幅用の乱数を同じ境界でさらに4個引く。係数0の条件もこの順序で乱数を消費する。声門面積（cm²）は現在の位相のパルスを用いて更新し、面積を気道へ渡して流量（cm³/s）と放射を計算する。放射の差分は間引きと出力処理を経て48 kHzのPCMに届く。[上流の位相と面積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L187)・[気道と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[研究版の位相と面積](../crates/vocal-core/src/glottis.rs#L211)

上流の既存試験は、ホストのブロック長で波形が変わらないこと、短い音が拍に着地すること、声帯の開大で接触区間が変わることを調べている。既存の研究ケースには固定圧と一定ピッチで周期倍率を推定する検証がある。今回はその乱数と周期倍率の独立計算を再利用し、歌唱の全区間を積分した。F0の滑走が更新される128内部サンプルとビブラートが更新される32内部サンプルはどちらも出力2内部サンプルの境界に乗る。予備描画は110 Hz、予約後は保存F0を各出力サンプル内の2ステップへ展開した。[ブロック長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短い歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[声帯開大](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)・[固定圧の事前登録](../cases/glottal-cycle-jitter.json)・[独立積分](../tools/measure_song_schedule_jitter.py#L24)

## 比較と実測

事前登録した「Pop Dee」の2音を240 BPMで描画した。予備描画16,384・16,512フレームと、乱流注入量1・0の4条件を使った。予約を渡した次の48 kHzサンプルを譜面相対−1,440とし、31,200点の物理量を比較した。PCM差の有声区間は譜面相対21,000〜21,599サンプルとした。[事前登録](../cases/song-voice-schedule-jitter.json)

ジッター0の研究版で予約直後に残っていた位相差は0.04189、0.04261周期。ジッターを0.00455にすると、予約直後の位相は固定上流と同じ0.590847464、0.884899179周期になった。全4条件で、予約後31,200点の位相とF0も上流と保存された浮動小数点のビットまで一致した。位相を独立に積分すると、予備描画を含む149または150回の周回を経た計測値を全区間で再現できた。[結果要約](../runs/song-voice-schedule-jitter-20261121-a/summary.json)

| 上流との比較 | ジッター0の研究版 | ジッター0.00455の研究版 |
| --- | ---: | ---: |
| 有声区間のPCMの誤差RMS、4条件の範囲 | 0.04488〜0.04913 | 0.00621〜0.00734 |
| PCMの全区間の最大絶対差、4条件の範囲 | 0.21044〜0.21956 | 0.03113〜0.03195 |

有声区間のRMS誤差は各条件で83.7〜87.4%減った。位相をそろえた後も、声門上下圧は20,878、声門面積と声門流量と放射は20,878または20,879サンプルに実装間の差が閾値を超えた。PCM差が閾値10⁻⁶を超えた位置は20,915または20,916サンプル。上流ではシマー0.042が面積パルスの振幅に掛かり、研究版では0を使う。残る差に対する振幅揺らぎの寄与は別の対照で確かめる。[物理量とPCMの初回閾値](../runs/song-voice-schedule-jitter-20261121-a/summary.json)

予約前の描画量だけを128フレーム変える比較では、乱流注入量0のPCMの初回閾値超過が、ジッターをそろえた研究版と固定上流で20,910サンプルにそろった。ジッター0の研究版は20,908サンプルだった。通常の乱流量1では3条件とも14,330サンプルで差が現れた。[予約位置を組にした比較](../runs/song-voice-schedule-jitter-20261121-a/summary.json)

### 口端面積の照合位置

継承した要約の `lip_area_cm2` は上流の最小断面 `net.amin[airway.oral.last_node()]` と研究版の有効断面 `lip.area_cm2` の比較で、予約直後から約0.16 cm²の開きが見える。研究版の `lip_minimum_cm2` を上流の列に対応させ、元のCSVの予約直前1行を外して比較し直した。全4条件・各31,200点で、最大差は5.7×10⁻¹⁴ cm²だった。口端の比較には以後、対応する最小断面どうしを使う。[上流の列](../tools/upstream_song_schedule_state_probe.rs#L56)・[研究版の列](../crates/vocal-cli/src/timing_case/speech_voice.rs#L775)・[元の上流CSV](../runs/song-voice-schedule-drift-20261121-repeat/artifacts/upstream/frame-16384-noise-0.csv)・[元の研究版CSV](../runs/song-voice-schedule-jitter-20261121-a/artifacts/frame-16384-noise-0/voicing.csv)

## 実行と保存

研究ワークスペースで次を実行した。再実行は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。固定上流と研究版の既存テストは各15件通過した。従来の短音ケースの一条件を現在のCLIから再描画し、ジッターを省略した場合と明示的に0とした場合のPCM・声門CSV・出力段CSVがそれぞれ以前の保存出力と一致した。負の値の `inspect` は入力エラーになった。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。両実行で42判定（予測14件を含む）が通過し、各156入力・30出力のサイズとSHA-256を照合した。PCMとCSVと要約の21件、および抜粋前のCSVのSHA-256は両実行で一致した。PCMと声門の全時系列をRTL9210B-CGに残し、ブロック長比較用の出力段CSV8件は照合後に指定区間を抽出した。各回の出力段CSVは15,872,084バイトから881,208バイトになった。外部への実体保存は2回で185,151,372バイトだった。[初回](../runs/song-voice-schedule-jitter-20261121-a/manifest.json)・[再実行](../runs/song-voice-schedule-jitter-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 \
  ../../.venv/bin/python tools/measure_song_schedule_jitter.py song-voice-schedule-jitter-20261121-a
```

次は研究版のジッター0.00455とドリフト0を使い、面積パルスのシマーだけを上流と同じ0.042にする。シードから独立計算した振幅倍率を、声門面積、流量、放射、PCMの順に照合する。
