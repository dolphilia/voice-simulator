# CSDの確認曲 en005a で全曲の丸め前とPCMを照合する

調整曲 `en001a` の2句では、設定を揃えたときの丸め前とPCMの最大誤差が同じフレームにあった。確認曲 `en005a` は既に先頭20 msの同設定対照がある。今回はそこで使った録音長73.846秒の譜面を保持し、発声器を句ごとに作り直さず全36句106音符を一度の描画で処理する。録音は時刻の基準に使い、ここで測る量は合成器どうしの数値差。 [事前登録](../cases/csd-en005a-full-pcm-rounding.json)・[確認曲の先頭20 ms](csd-acoustic-f0-en005a.md#pcmの最初の差を調べた対照)・[調整曲の比較](csd-en001a-two-phrase-pcm-rounding.md)

## 入力から出力まで

固定上流の `compare_song` は録音長を計り、`render_notes` で歌詞・音高・音符長を句単位にまとめる。音符間隔は秒を60 BPMの拍として渡す。`plan_song` が調音・呼気・音高のジェスチャーを返し、同じ `HumanVoice` に全句を予約する。研究用の上流プローブの `matched` は、通常の予約と描画を使いながら、初期姿勢・声源変動・息成分・出力ゲインを研究版に合わせる。研究版は保存済み譜面を通常の `vocal-cli render-pcm` に渡す。 [上流の全曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[上流の句ごとの計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L259)・[同設定のプローブ](../tools/upstream_csd_continuous_probe.rs#L61)・[研究版の歌唱](../crates/vocal-cli/src/timing_case/speech_voice.rs)

`HumanVoice::render` は各内部標本で声門と気道を更新し、口・鼻・壁の放射体積速度（cm³/s）の合計差分（cm³/s²）を間引き器へ渡す。FIRは最古の入力から係数を一項ずつ加え、96 kHzの2標本ごとに48 kHzの値を出す。出力ゲインの後に `y[n] = x[n] − x[n−1] + a y[n−1]` でDCを除去し、ピーク包絡・保持カウンタを更新してfloat32へ変換する。上流は制御更新で一部の微小履歴をゼロにするので、その位置を再計算でも反映する。 [上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[FIRの加算順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[弱音の微小履歴](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L68)・[歌い終わりの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L48)

## 全曲の再計算

独立計算のFIRを、係数1個ずつ全フレームへ掛けてから加える実装へ変更した。各フレームの加算順は旧計算と同じで、全標本をPythonオブジェクトのリストへ変換する処理と、フレームごとのタプルの保持を省いた。入力の精度に依存しないようにfloat64へ変換してからFIRを計算する。DC除去と包絡の再帰は従来どおり1フレームずつ更新する。間引き率1・2・3、float32・float64の入力と微小履歴のゼロ化の有無を組み合わせた12条件で旧計算とビット一致し、調整曲の保存済み201,600フレームでも両版の放射と出力段の全列が一致した。 [独立計算](../tools/measure_tsp_fk61_pcm_first_difference.py#L29)

最初の二つの描画はすべての放射・出力・PCMを採取した後、リミッターの作動を検出した検算で停止した。従来の検算はDC除去直後の値がfloat32の変換に入る場合を扱っていた。今回はピーク包絡が0.75を超えるフレームで `0.75 / 包絡` を掛け、次に絶対値0.85を超える場合のソフトクリップも判定する。両版とも利得抑制の対象は1,103,539フレームで、作動したフレーム集合も一致した。最初の作動は177,754、最後は3,342,093。ソフトクリップは両方0フレームだった。再計算したPCMはそれぞれの採取PCMと全点でビット一致した。 [初回の停止](../runs/csd-en005a-full-pcm-rounding-20261124-registered/manifest.json)・[別ディレクトリからの停止](../runs/csd-en005a-full-pcm-rounding-20261124-repeat/manifest.json)・[修正後の全曲の照合](../runs/csd-en005a-full-pcm-rounding-20261124-verified-repeat/summary.json)

## 全曲の測定結果

固定上流の先頭960 PCMフレームと全歌唱計画は既存の同設定対照に一致した。研究版は保存済みの全曲PCMとジェスチャーを再現した。最初に差が出たのは内部標本0の口端流量と放射差分だった。 [計測と全比較値](../runs/csd-en005a-full-pcm-rounding-20261124-verified-repeat/summary.json)

| 観測量 | 最大絶対差 | 出力フレーム | 場所 |
| --- | ---: | ---: | --- |
| float32変換直前 | 1.413×10⁻¹¹ | 20,363 | 第1拍より前 |
| float32 PCM | 1.490×10⁻⁸ | 3,214,976 | 第36句、66.979秒 |

調整曲と確認曲で最初の111,872 PCMフレームが各版内でビット一致した。両曲の丸め前の最大差が共通する20,363は、この出力の共通区間の約0.424秒にある。確認曲の譜面区間だけの丸め前最大差は1.620×10⁻¹³だった。全曲でも丸め前後の最大誤差位置が同じという事前予測は不成立だった。

第36句のPCM最大差は1 ULP。丸め前の二値は隣接float32値の中点からそれぞれ +4.441×10⁻¹⁶、−4.136×10⁻¹⁵だけ離れていた。このフレームのピーク包絡は両版で約0.588で、利得抑制は発動していない。PCM差の二乗和の87.16%がこの1フレームに集中した。全581,157相違フレームのうち、複数ULP差の548,670フレームすべてで、両版のPCM絶対値は10⁻⁶以下だった。リミッター作動中にPCMが分かれたのは18フレームだった。 [丸め中点と振幅別の集計](../runs/csd-en005a-full-pcm-rounding-20261124-verified-repeat/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。事前登録のSHA-256は `f537402ec07b3e5620eec9cb3c8417d34da78f20f1e9ab2ddc9fe9a469a0b0b7`。同じ密度の調整曲では圧縮済みの観測が53 MiBだったので、全曲の圧縮済み観測をおよそ1 GiBと見積もった。追加の未圧縮観測、CSV、ビルド領域を含め各実行の見積もりを8 GiBとし、書き込み可能で空き343 GiBのRTL9210B-CGへ直接出力した。

二つの独立した描画の観測は各1.1 GiBで、観測、PCMハッシュ、歌唱計画、採取パッチはバイト一致した。修正後の二つの検算では、元の停止記録を残し、それぞれが照合済みの採取物を同じ外部ボリューム上でハードリンクした。検算側で新たに書き出した要約もバイト一致し、各7判定に通過した。 [初回の検算](../runs/csd-en005a-full-pcm-rounding-20261124-verified/manifest.json)・[再実行の検算](../runs/csd-en005a-full-pcm-rounding-20261124-verified-repeat/manifest.json)

第7段階の初回監査では、検算時に保存したケースと採取時の同名ケースがどちらも入力にあり、件数だけでケースを同定する処理が停止した。二つのSHA-256が同じ場合に、検算した実行自身の保存ケースを採るよう修正した。既存166実行のケース同定結果も照合した。 [修正前の監査](../runs/stage7-evidence-update-20261124-csd-en005a-full-pcm-rounding/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=8589934592 \
  ../../.venv/bin/python tools/measure_csd_en005a_full_pcm_rounding.py csd-en005a-full-pcm-new
```

保存済みの採取物から検算し直す場合は、新しい実行IDと `--capture-run` を指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_csd_en005a_full_pcm_rounding.py csd-en005a-full-pcm-reanalysis \
  --capture-run csd-en005a-full-pcm-rounding-20261124-repeat
```
