# CSD音符の帯域電力、H1−H2とメルケプストラム距離

調整用 `en001a` の登録した5音符で計測器を確認してから、同じ条件を両曲の全192音符に適用した。前の実行で確定した録音と両合成のWAV、音符ごとの5 ms刻みのF0をハッシュで照合した。録音は44.1 kHz、合成は48 kHzのまま、同じ注釈の時刻で比較した。[ケースと許容差](../cases/csd-note-spectrum.json)・[F0の調整用比較](csd-acoustic-f0-en001a.md)・[F0の確認用比較](csd-acoustic-f0-en005a.md)

## 固定上流の経路と計算

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のCLI `compare csd` は `compare_song` で録音と描画を受け取り、各波形を `Analyzer::note` に渡す。 `Analyzer::new` は解析長を `0.04 × fs` 以上の最小の2のべき乗にする。今回の両レートでは2,048サンプルで、窓長は録音46.44 ms・合成42.67 ms、ビン幅は約21.53 Hz・23.44 Hz。 `power` は `trunc(t × fs) − N/2` から窓を読み、信号外の窓を除く。Hannは `0.5 − 0.5 cos(2πi/(N−1))` で両端が0。固定上流の `Fft` はビット反転後に2点から段階的に変換し、窓を掛けた実信号の片側の `Re² + Im²` を非正規化で返す。[CLIの分岐](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L114)・[録音から曲の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[分析器と電力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L449)・[FFTとHann窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/fft.rs#L39)

音符の開始側30%・終端側20%を除く。メリスマは各10%を除く。スペクトルは残った区間の先頭から10 msを繰り返し加算した中心で取り、全窓の電力をビンごとに加算する。0–500、500–1,000、1,000–2,000、2,000–4,000、4,000–8,000 Hzの半開区間の合計を、0–8,000 Hzの合計で割って相対dBとする。分子と分母に `10⁻³⁰` を加えるので、有効窓が無音のときは各帯域が0 dBになる。完全に収まる窓がなければ帯域とケプストラムは欠測になる。[音符の窓と帯域集計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)

メルフィルターは `2595 log₁₀(1 + f/700)` で60–8,000 Hzをメルに写し、メル上の42等間隔点をHzへ戻す。隣り合う3点ずつで作った40本の三角重みを、合算済みのFFT電力に掛ける。 `Lₖ = ln(フィルター出力 + 10⁻²⁰)` として、 `c_q = Σ Lₖ cos(πq(k+0.5)/40)/40` を `q = 1…13` で求める。MCDは `(10/ln 10) √(2 Σ(Δc_q)²)` のdB尺度で、各音符の相対的なスペクトル形状の距離をまとめる。音量の定数倍が `Lₖ` に加える共通項は、床から十分離れた信号の `c1…c13` には残らない。[メルの設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L443)・[対数電力と余弦変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L601)・[MCD](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L779)

H1−H2の中心は5 ms刻みのF0格子の偶数番目。上流のスペクトル合算は10 msを加算する別経路なので、両者の中心からサンプル番号を別々に算出する。有声フレームのF0と2倍のF0それぞれで、±3%または±2ビンの広い方を使い、端を床・天井関数で外に広げる。最大電力のビンと前後の3点をdBにして、曲率が負の場合に放物線頂点を求める。二つのピークレベルを引いて、有限な値の音符内中央値を取る。上流には振幅比の `h1h2_reads_the_harmonic_ratio_whatever_the_vibrato`、窓外の `a_note_with_no_spectrum_has_no_cepstrum`、基準FFTと窓の `golden_analysis`、スコア列の往復テストがある。[倍音ピークと使うF0](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L531)・[倍音と窓外の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1396)・[基準FFT](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L166)・[スコア列の往復](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/score.rs#L797)

## 検証と全曲結果

先行の音符5件について、3波形の最初の窓、計15窓のFFT電力を複素指数の直接和で求めたDFTと照合した。最大差はピーク電力で割って `3.49×10⁻¹⁵` 未満。全曲では時系列とFFT電力のParsevalの相対差が最大 `1.09×10⁻¹⁵`、独立した帯域和とSciPyのDCTでの特徴差が最大 `7.11×10⁻¹⁵` だった。振幅比2:1の対照は両レートでH1−H2が+6.02059 dB、帯域比は0.80と0.20を再現した。広帯域で振幅だけ2倍にしたときのMCDは `3.09×10⁻¹⁵ dB` 以下。無音と波形外も別々に確認した。[計測コード](../tools/measure_csd_note_spectrum.py)・[少数音符の対照](../runs/csd-note-spectrum-20261121-pilot-verified/summary.json)・[全曲の判定と全特徴](../runs/csd-note-spectrum-20261121-all/summary.json)

| 曲 | 音符数 | 録音／固定上流の平均MCD | 録音／再実装の平均MCD | 固定上流／再実装の平均MCD |
| --- | ---: | ---: | ---: | ---: |
| `en001a` 調整用 | 86 | 7.72 dB | 7.58 dB | 3.32 dB |
| `en005a` 確認用 | 106 | 9.20 dB | 9.96 dB | 3.85 dB |

3波形のスペクトル窓を合計13,323件取得した。H1−H2は12,611フレームで取得し、周期不検出520、電力ゲート177フレームを記録した。音符単位の欠測は0。各音符のH1−H2・帯域・帯域差・MCDは固定上流の通常報告の丸め幅0.005 dB内で、調整用の丸め前の値との最大絶対差は `2.14×10⁻¹⁴ dB` 未満だった。確認用の平均MCDは区分の上流スコアとも一致した。確認用の曲でH1−H2の音符中央値は録音−3.27 dB、固定上流+8.56 dB、候補+8.51 dB。録音と合成は収録条件の違いも含む。[固定上流の通常報告](../runs/csd-song-planning-20261121-final/artifacts/csd/report.json)・[スコア](../runs/csd-song-planning-20261121-final/artifacts/csd/score.json)・[確認用のフレーム別H1−H2と欠測](../runs/csd-note-spectrum-20261121-all/artifacts/en005a-h1h2-frames.csv)

両合成を同じ出力時計でたどると、最初の安定区間の先頭窓でPCMに差があった。 `en001a` は48 kHzのサンプル120,656、 `en005a` は182,852からで、Hann端の係数が0のため窓適用後の最初の差は次のサンプルだった。差はFFT電力にも残る。確認用の第39音 `/ðə/` では、両合成の5帯域の相対値は最大0.126 dB差で、MCDは8.78 dBと全106音符中で最大だった。13係数の最大差は `c1` に出た。広い周波数帯域の要約で近い値が、細かいメル帯域ではどの周波数から離れるかが次の局所的な対照になる。[各窓と第39音の係数](../runs/csd-note-spectrum-20261121-all/summary.json)

## 同じFFTのまま参照F0だけを交換した対照

調整用の第30音、21.940秒で、上流と候補の狭い探索から得たF0を、通常F0と同じFFTに与えた。通常の上流では418.31 HzからH2を追うため、強い第3倍音付近のビン36を選んだ。対照では278.02 Hzを使い、H1とH2はビン12・24になった。H1−H2は固定上流が−47.72 dBから−2.09 dB、候補が−43.74 dBから−2.10 dBへ変化。録音は両探索のF0とH1−H2が一致した。共通のFFTを使うため帯域やMCDの入力には変更がない。効果量はこのフレームのもので、4音符の中央値や曲の要約にどう影響するかは未測定。[通常と狭い探索のF0](csd-acoustic-f0-en001a.md#4音符の倍音を調べた対照)・[同じFFTの対照値とピークビン](../runs/csd-note-spectrum-20261121-all/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1、Rust 1.94.1。最初の少数音符の実行は、F0対照JSONの窓の配列を格納するキーの読み出し漏れで失敗した。 `centers_with_f0_hz` を参照して修正し、判定基準を維持した。修正後は少数音符の5判定、全曲の13判定、固定上流の比較19試験と基準分析1試験を通過した。 `/tmp` から再実行した全曲の要約とCSVはバイト一致した。全曲の成果は約2.30 MBで、CSVなどの実体はRTL9210B-CGに書いた。WAVとF0表は先行実行を参照する。[最初の少数音符の失敗](../runs/csd-note-spectrum-20261121-pilot/manifest.json)・[全曲の実行](../runs/csd-note-spectrum-20261121-all/manifest.json)・[再実行](../runs/csd-note-spectrum-20261121-repeat/manifest.json)

`research/experiments/chimera-rebuild` から、新しい実行IDを使う。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_note_spectrum.py csd-note-spectrum-local-pilot --pilot
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_note_spectrum.py csd-note-spectrum-local-all --after-pilot csd-note-spectrum-local-pilot
```
