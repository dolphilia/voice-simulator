# CSDのもう一つの確認曲 en035a で全曲の丸めを照合する

`en035a` は、長い音符を持つ曲の事前選定で確定した確認曲。録音長と譜面を保存済みの全76句・109音符の実行に揃える。`en005a` では第1拍前に丸め前の最大差、第36句にPCMの最大差があった。この曲でも第1拍前・譜面区間・終端以降の最大差、RMS、利得抑制の時間を取り、調整曲と共通する冒頭と、歌唱に入ってから現れる差を照合する。 [事前登録](../cases/csd-en035a-full-pcm-rounding.json)・[長音による選定](csd-long-note-vibrato.md#注釈による選定)・[en005aの全曲の測定](csd-en005a-full-pcm-rounding.md)

## 入力、観測点と計算順

固定上流の `compare_song` は録音と注釈を読み、`render_notes` が1音符の長さを次の音符までの秒で決める。句内の音符長を60 BPMの拍として `plan_song` に渡し、返されたジェスチャーを1つの `HumanVoice` に絶対時刻で予約する。通常設定の上流描画は保存済みの公式CLIの全曲PCMと比較する。同設定の対照では研究用プローブの `matched` で初期姿勢、息成分、声源変動、出力ゲインを研究版に合わせ、予約とレンダーは同じ順で行う。研究版は既存の `vocal-cli render-pcm` と `inspect` を使う。上流の歌唱試験は音符の先行子音と拍の一致、句末の母音の放し方を扱う。 [曲の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[句の予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L259)・[プローブの設定](../tools/upstream_csd_continuous_probe.rs#L61)・[拍の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L29)・[母音の放し方の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L48)

`HumanVoice::render` は96 kHzの内部標本で声門・気道を進める。口、鼻、壁の放射体積速度（cm³/s）を足した合計の差分（cm³/s²）をFIRへ渡す。FIRは最古の入力から一項ずつ加え、内部標本を2対1で間引く。48 kHzではゲイン、DC除去、ピーク包絡の更新、利得抑制、必要時のソフトクリップ、float32変換の順に通す。ピーク包絡は最新の絶対振幅と比較して更新し、ピークより小さい区間では保持標本数が0になるまで減衰を待つ。利得抑制が作動すると、DC除去後の値に `0.75 / 包絡` を掛ける。検算は `en005a` の放射・間引き・利得抑制の独立計算を再利用し、上流の制御境界の微小履歴のゼロ化も再現する。 [上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[FIRの加算順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[研究版の出力処理](../crates/vocal-core/src/output.rs#L107)・[微小履歴の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L68)

## 全曲の測定結果

通常設定の固定上流と研究版のPCMは、長音の既存比較の各5,590,588フレームにビット一致した。同設定での描画も、観測を入れる前後のPCMと全歌唱計画が各版で一致した。両版とも11,181,176内部標本の放射合算・差分と、全出力のFIR・DC除去・リミッター・PCMを独立計算に照合した。最初の版間差は内部標本0の口端流量と放射差分だった。 [結果要約](../runs/csd-en035a-full-pcm-rounding-20261124-registered/summary.json)

| 区間 | 丸め前の最大絶対差 | PCMの最大絶対差 | PCMの相違フレーム数 |
| --- | ---: | ---: | ---: |
| 第1拍前 | 1.413×10⁻¹¹ | 1.413×10⁻¹¹ | 117,931 |
| 譜面区間 | 1.256×10⁻¹³ | 2.980×10⁻⁸ | 359,822 |
| 譜面の終端以降 | 5.485×10⁻¹⁴ | 1.455×10⁻¹¹ | 30,873 |

丸め前の全曲最大差は `en005a` と同じフレーム20,363だった。両曲のPCMは同じ版内で冒頭154,496フレーム（約3.219秒）が一致し、この最大差は共通区間にある。PCMの最大差は第18句のフレーム1,637,779（34.120秒）の1 ULP。変換前の値は丸め中点からそれぞれ +1.499×10⁻¹⁵、−7.661×10⁻¹⁵の位置にあり、この1フレームがPCM差の二乗和の89.44%を占めた。全曲のPCM差のRMSは1.333×10⁻¹¹、そのフレームを外すと4.332×10⁻¹²だった。 [区間・丸め中点・RMSの結果](../runs/csd-en035a-full-pcm-rounding-20261124-registered/summary.json)

利得抑制は両版で同じ618,105フレームに作動し、すべて譜面区間内だった。そのうちPCMが分かれたのはフレーム640,407と1,279,830で、どちらも1 ULPだった。PCMの最大差が出たフレームの包絡は両版で約0.726で、作動しきい値0.75を下回った。ソフトクリップは0フレームだった。複数ULP差の469,321フレームでは、すべて両版のPCM絶対値が10⁻⁶以下だった。 [リミッターと振幅別の集計](../runs/csd-en035a-full-pcm-rounding-20261124-repeat/summary.json)・[出力段とPCMの採取物](../runs/csd-en035a-full-pcm-rounding-20261124-repeat/artifacts/output-trace.npz)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用。事前登録のSHA-256は `b51e353ed7ee1b0a8275bf4a7a1efc48825ac96d88a2d7c8a95d264a3f4ead1b`。観測の密度を確認曲 `en005a` と同じとすると圧縮済み観測は1.8 GiB程度。二重の一時描画、未圧縮系列、試験ビルドのため、各実行の領域を12 GiBと見積もった。空き340 GiBを確認したRTL9210B-CGに直接保存した。区間別のULP数と利得抑制中の差を数える処理は、先行する `en005a` の保存データでも再計算し、既知の全曲集計に一致した。 [比較CLI](../tools/measure_csd_en035a_full_pcm_rounding.py)

異なる作業ディレクトリから独立に描画・検算した2実行では、約1.9 GiBの圧縮観測、PCMハッシュ、譜面計画、観測パッチ、要約の7出力が一致した。各実行では、上流の歌唱と微小履歴の16試験、研究版の一様管3試験を実行し、計測の7判定に通過した。 [初回のマニフェスト](../runs/csd-en035a-full-pcm-rounding-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/csd-en035a-full-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=12884901888 \
  ../../.venv/bin/python tools/measure_csd_en035a_full_pcm_rounding.py csd-en035a-full-pcm-new
```
