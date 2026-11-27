# 子ども声部の出力ゲインとPCM

前回の初期舌先をそろえた計測では、無発声時の過渡が消え、音源変動をそろえた歌唱の全区間に最大0.0472802のPCM差が残った。今回は同じ歌唱の研究版で `song_voice.voice.output_gain` だけを変更する。固定上流はドリフト・ジッター・シマーを0にそろえ、体型ゲインは既定値を使う。[事前登録](../cases/duet-child-output-gain.json)・[初期舌先の計測](duet-child-initial-tip.md)

## 読解と予測

- 上流の `render::notes` は体型から `HumanVoice::new(48000, body, 2)` を作り、音源を設定してからジェスチャーを登録する。描画前の状態には入力と出力のDC履歴、ピーク包絡、保持残数があり、全て0から始める。初期化時に基準ゲイン `5.5×10⁻⁷` へ体型の長さ比に応じた係数を掛ける。比0.9以下で0.875、0.9から1まで線形に増えて、1以上で1。子どもの比は0.74なので、出力ゲインは `4.8125×10⁻⁷` になる。上流のコメントは流量の微分による、高いF0での放射レベルを補う意図を示している。[上流の歌唱入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[体型の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L287)・[ゲイン初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L223)
- `HumanVoice::render` は肺圧、声門面積、気道を内部サンプルごとに進め、放射流量の時間微分（cm³/s²）を間引き器に入れる。48 kHz出力では96 kHzの放射を2点進めるごとに49タップのFIRを適用する。カイザー窓のβは8.5、カットオフは内部レートの0.23倍。FIRの出力にゲインを掛けて正規化振幅にし、`y[n] = x[n] − x[n−1] + exp(−2π×25/48000) y[n−1]` でDCを除く。絶対値が直前の包絡以上ならピーク更新と25 msの保持を行い、保持が尽きると時定数0.2 sで包絡を減衰させる。包絡が0.75を超えたとき現在の信号を `0.75/包絡` 倍し、その振幅が0.85を超えた場合は `tanh` で収める。最後に `f64` から `f32` に丸めてPCMを返す。[上流の出力更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の間引き器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs)
- 研究版の `run_song` はケース指定のゲインを `OutputStage::new` に渡す。体型はジェスチャーと気道に別途渡し、出力段のゲイン指定はそのまま使う。この入口で基準ゲインと0.875倍のゲインを比べる。先に差が出る段は間引きの後の乗算で、両条件の放射・間引き結果は一致し、全区間で包絡は制限しきい値0.75を下回ると予測した。上流の `output_does_not_depend_on_the_host_block_size` はブロック分割を変えてPCMをビット照合し、`the_voice_holds_for_a_child_at_low_device_rates` は子ども体型の音量を出力レート間で測る。`body_mix` は体型と連続補間を検査する。今回は子ども体型の係数を固定し、出力段の途中の値を追加で照合する。[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L260)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)・[上流のエンジン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[上流の体型試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)

## 観測と独立照合

研究版は通常の `render-pcm-tele` と同じコアを呼ぶ観測器で出力を照合する。上流は固定コミットから一時展開したコピーに観測項目を足す。既定の音源では通常の `render notes` と、音源の変動をそろえた条件では先行計測のPCMと照合する。両観測器は1出力フレームにつき、時刻順の内部放射2点、FIR出力、ゲイン後、DC除去後、包絡、保持残数の7値をリトルエンディアンの `f64` で保存する。PCMは別の `f32` ファイルに保存する。解析は先頭を1とする出力フレーム番号を使う。[上流の採取差分](../tools/patches/upstream-duet-child-output-stage.patch)・[計測CLI](../tools/measure_duet_child_output_gain.py)

独立計算はKaiser窓のベッセル関数を `scipy.special.i0` で評価し、ゼロ初期値から内部放射を `numpy.convolve` で畳み込む。2点目から2点ごとにFIR値を照合する。ゲイン後からは `scipy.signal.lfilter` でDC除去を照合し、観測したDC除去出力からは包絡・保持残数を別に計算する。包絡とDC除去の観測値から得られる制限後のPCMを、丸めを含めて照合する。体型係数の関与は、研究版の同じ放射入力を通した二条件の差で確認する。

## 実測

研究版の二条件で、96 kHzの放射182,400点と48 kHzのFIR出力91,200点はビット一致した。最初に差が出た箇所は出力フレーム18,305のゲイン乗算だった。DC除去後の包絡の最大値は、基準ゲインで0.378242、0.875倍で0.330962。両条件と固定上流でピーク制限・ソフトクリップの発動は0フレームだった。[段別の数値と判定](../runs/duet-child-output-gain-20261122-a/summary.json)

| 固定上流との差 | 研究版の基準ゲイン | 研究版の0.875倍 |
| --- | ---: | ---: |
| 内部放射の最大絶対差（cm³/s²） | 2.40×10⁻⁷ | 2.40×10⁻⁷ |
| ゲイン直後の最大絶対差 | 0.04668214 | 8.93×10⁻¹⁴ |
| DC除去後の最大絶対差 | 0.04728025 | 8.92×10⁻¹⁴ |
| PCMの最大絶対差 | 0.04728022 | 9.09×10⁻¹³ |

ゲインをそろえた後の最初の数値差は、出力フレーム18,305の2点目の内部放射にあり、`10.053169708744955` と `10.053169708747017 cm³/s²` だった。PCMで最初に丸め先が分かれたのは23,671フレーム目で、両版のDC除去出力は隣り合うFloat32値の中点を挟んだ。PCMの8,234フレームにビット差があり、探索で立てた「全て隣り合うFloat32値」という見立ては反証された。6,793フレームでは隣接値より離れていたが、その部分の最大絶対差は `2.84×10⁻¹⁴` だった。最大の絶対差 `9.09×10⁻¹³` は75,144フレーム目の隣接値。絶対差と、0に近い値で増えるFloat32表現上の距離を別々に記録する必要がある。[研究版のPCM](../runs/duet-child-output-gain-20261122-a/artifacts/matched.f32le)・[固定上流のPCM](../runs/duet-child-output-gain-20261122-a/artifacts/upstream.f32le)

独立FIRとの最大絶対差を基準ゲインで正規化すると `3.85×10⁻¹⁶` 未満、DC除去後は `1.67×10⁻¹⁶` 未満だった。包絡と保持残数は観測値から独立に更新した結果と一致した。このケースではゲインで残差の大半を説明できる。制限が作動する大振幅でのゲインの効果と、混合体型の乱流振幅差は別の入力条件で確認する。

## 再現

研究ワークスペースから実行する。両版の大容量の時系列と固定上流の一時展開先はRTL9210B-CGを使う。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_child_output_gain.py duet-child-output-gain-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。研究ディレクトリと `/private/tmp` からそれぞれ9判定・4予測と固定上流10試験が通過し、段別の系列・PCM・要約など27出力がバイト一致した。標準ライブラリでも保存ファイルを再読込し、DC更新、PCMへの丸め、隣接値から離れたフレーム数を照合した。初期舌先の回帰では10判定・3予測と固定上流11試験が通過し、以前の20出力と一致した。形状連続性のうち上流の既知の下唇形状1試験は除外設定のまま。3実行の429入力・92出力をサイズとSHA-256で照合し、採取物90,400,440バイトをRTL9210B-CGに保存した。[初回](../runs/duet-child-output-gain-20261122-a/manifest.json)・[再実行](../runs/duet-child-output-gain-20261122-repeat/manifest.json)・[初期舌先の回帰](../runs/duet-child-initial-tip-20261122-gain-regression/manifest.json)
