# CSDの録音注釈から歌唱計画を照合する

CSD v1.1の英語aキーから `en001a` を調整用、`en005a` を確認用に登録した。固定上流の `score::held_out` は曲IDの数字を取り出し、5の倍数を確認用にする。同じ曲のa・bは同じ分割に入る。曲は結果を見る前に選び、両方とも成人女性、60 BPM、同じ注釈を使う。録音はChoi、Kim、Park、Yong、Namによる歌唱データのCC BY-NC-SA 4.0版を研究評価に使う。[登録条件](../cases/csd-song-planning.json)・[CSD v1.1の配布記録](https://doi.org/10.5281/zenodo.4916302)・[著者によるデータ説明](https://github.com/equal-singer/CSD)・[固定上流の分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/score.rs#L81)

## 上流の入口と状態

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare::csd` は対象曲を選び、`compare_song` を呼ぶ。 `load_notes` はCSVから開始秒、終了秒、MIDI番号、下線区切りの音素表記を読む。 `csd_ipa` でIPAに変換し、最初の母音を音節の核、その前を頭子音、その後を末尾として保持する。続く音符までの隙間が80 msを超えると句が終わる。前の音と核が同じで頭子音も末尾もなく、同じ句で前の音との隙間が20 ms未満ならメリスマになる。未対応の記号はエラーとして残す。[CSVとIPAの処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L78)・[通常の比較入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1017)

`render_notes` は各句の先頭をCSVの絶対時刻に置く。句内の音符は次の音符の開始まで、句末の音符は自身の終了までを使い、60 BPMで秒と拍を一対一にする。 `plan_song` はMIDIを `440 × 2^((m−69)/12)` Hzへ変換し、前の母音から次の母音までに末子音と次の頭子音を割り当てる。子音の基準長は発話時の0.8倍。母音に確保したい50 msを残せないときは子音を比例圧縮し、各子音に12 msの下限を設ける。母音の下限20 msによって後続の長さが押し出される場合を考慮し、上流は母音開始が注釈から30 ms以内なら採用と判定する。二重母音は通常2区間で、次の音がメリスマなら後半の滑りを延ばした先の音まで保留する。譜面によるF0目標と、通常比較が録音と合成からYINで推定するピッチを別の欄に保存する。[上流の歌唱スケジューリング](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L259)・[子音の圧縮と歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L90)・[注釈との判定と報告](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)

研究用の変換器は登録したCSVを直接読み、1句ずつ既存の `song_plan` ケースを作る。通常の `vocal-cli inspect` と `render` の出力を照合し、固定上流の `compare csd` で音節、句境界、メリスマと採否を比較する。通常レポートが小数2桁に丸める母音開始は、上流の公開 `plan_song` を呼ぶプローブで元の精度でも取得する。別計算では、累積した拍に頼らずCSVにある絶対時刻を1音ずつ照合し、ピッチはPythonの `exp2` で求める。固定上流の `sing_fast` は子音で音符が遅れない条件、 `rising` は介音、 `compare::score::tests` は曲の分割、 `compare::tests` は音響計測を検証する。[計測器](../tools/measure_csd_song_planning.py)・[固定版計画のプローブ](../tools/upstream_song_probe.rs)・[候補の通常入口](../crates/vocal-cli/src/song_case.rs)

## 実測

| 曲 | 分割 | 音符 | 句 | メリスマ | 母音開始が30 msを超えた音符 | 録音フレーム（44.1 kHz） | 上流合成フレーム（48 kHz） |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| en001a | 調整用 | 86 | 50 | 0 | 0 | 2,857,680 | 3,110,400 |
| en005a | 確認用 | 106 | 36 | 0 | 0 | 3,256,616 | 3,544,616 |

合計192音符の注釈・IPA・句境界が固定上流の通常レポートと一致し、丸め前の母音開始と分節時刻、ピッチジェスチャーにも差はなかった。候補の拍時刻はCSVの絶対時刻と一致し、目標F0は別計算との差が最大 `5.68×10⁻¹⁴ Hz`。母音開始と注釈の差は両曲で数値丸めの範囲内に収まった。上流の小数2桁のレポートでは実際に最大5 msの丸めを観測したため、判定には丸め前の時刻を使う。選んだ2曲ではメリスマと30 ms超の音符の実例は0件だった。[音符ごとの観測](../runs/csd-song-planning-20261121-a/summary.json)・[上流の通常レポート](../runs/csd-song-planning-20261121-a/artifacts/csd/report.json)

上流の通常比較では、譜面に対するピッチ誤差の絶対値の中央値が `en001a` で録音11.62セント・上流合成5.95セント、`en005a` で録音20.25セント・上流合成6.25セントだった。YINで取った音高と譜面の比較であり、候補の値としては今回は計画上の目標F0を保存した。録音の双方が44.1 kHz・16ビット・2チャンネルで、上流の比較はチャンネル平均を使う。候補の音響評価でも時間座標とチャンネルの扱いを揃える。[固定上流のピッチと波形の比較](../runs/csd-song-planning-20261121-a/artifacts/csd/report.md)

## 取得と再実行

データの実体はRTL9210B-CGの `scratch/chimera-reference/csd-v1.1`。Zenodo記録4916302が公開するZIPのサイズ1,851,131,390バイトとMD5 `74d121dd8706fded26a15526a379f7a2` は、固定上流の取得スクリプトにある登録と一致した。ZIP末尾と必要な区間をHTTP Rangeで読み、中央ディレクトリのCRC32を確認して4ファイルを取り出した。保存したCSVとWAVは合計24,463,538バイト。配布メタデータと各入力のSHA-256を取得記録と各測定に残した。[配布APIの記録](../runs/csd-song-planning-20261121-final/artifacts/zenodo-4916302.json)・[4入力の照合値](../runs/csd-song-planning-20261121-final/artifacts/selected-inputs.json)・[固定上流の取得スクリプト](../../../../docs/reference/chimera-vocal-synth/upstream/tools/fetch-csd.sh)

最初の全ZIPの取得は480秒で約1.53 GBまで進んでタイムアウトした。部分取得の初回ではPythonの接続待ちが続き、curlに替えた試行では応答ヘッダーの書式指定に誤りがあった。受信範囲をcurlの `%header{content-range}` で確認する形に修正した。4入力を取得して照合した後、全ZIPの再試行を停止し、作業中に生成した未完ファイルを取り除いた。その状態でもRangeだけで同じ4ファイルを再取得し、バイト一致を確認した。全ZIPのMD5は配布元のメタデータとして記録した。

最初の測定では、録音WAVの付加チャンクにSciPyの警告が出た。録音のサンプル数・レート・チャンネル数・ビット幅の取得には標準の `wave` を使い、上流の音響比較は同じ録音を使った。実行環境はmacOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1。固定上流の歌唱試験7件と比較試験19件、および既存の歌唱計画の回帰6判定を通過した。初回と `/tmp` からの再実行で各17判定を通過し、候補の計画と上流のWAV・レポートなど8ファイルはバイト一致した。正式成果は約29.5 MB。3実行46成果のSHA-256を照合した。[初回計測](../runs/csd-song-planning-20261121-a/manifest.json)・[再実行とハッシュ](../runs/csd-song-planning-20261121-final/manifest.json)・[既存の歌唱計画の回帰](../runs/csd-song-planning-20261121-score-regression/summary.json)

`research/experiments/chimera-rebuild` で実行する。計測の場合は未使用の実行IDを指定する。

```bash
../../.venv/bin/python tools/fetch_csd_inputs.py
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_csd_song_planning.py csd-song-planning-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_song_plan.py csd-song-planning-regression-local-1
```
