# 同一本文のTSP録音と両合成の音素・語境界

調整用 `FA01_02` と `MA01_02` は同じ8語を読む。両録音と上流・候補の合成4件に、上流と同じMFA 3.4.3および `english_us_arpa` v3.0.0を適用した。録音と合成は先行の発話区間長比較で使ったファイルと同じSHA-256のものを選び、確認用の録音はこのケースに入れなかった。上流の収録済み境界との許容差は1窓分の10 msと、秒表現の丸め分1 µs。入力選定時には音素別の結果を使っていない。[事前登録](../cases/tsp-phone-boundaries-calibration.json)・[先行の実録音比較](tsp-active-duration-original.md)

## 上流の処理と照合方法

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare::tsp::run` は `load_utts` で録音、本文、音素注釈を対応させる。録音側の `tools/tsp/align.py` は1発話を1話者ディレクトリに置き、公開辞書でMFAを実行し、語と音素の時刻を秒単位で小数3桁に書き出す。合成側の `say_all` は通常の `render::say` からPCMと調音計画を取得し、`align_synth` は `said_words` と `EnglishG2P::word` の弱形から発音辞書を作る。`to_arpa` は母音に強勢番号を付け、`/ə/` は `AH0`、`/ɚ/` は `ER0` に固定する。Kaldiの特徴量に対するディザと話者適応は `mfa.yaml` で無効にする。[録音の準備と集計](../../../../docs/reference/chimera-vocal-synth/upstream/tools/tsp/align.py)・[上流の合成準備](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L248)・[MFA設定](../../../../docs/reference/chimera-vocal-synth/upstream/tools/tsp/mfa.yaml)

上流の `over_noise_floor` は合成の48 kHzのPCMを重ならない960フレーム窓に分け、完全な窓だけで平均二乗を求める。電力の95パーセンタイル `P95` を線形補間し、固定シード `0x2545f491` からxorshift32の一様雑音を作る。振幅の係数は `√(3 × P95 × 10^(−47/10))`。合成と加算してfloat32を通し、`wav::write` のCLIPと `Math.round` 相当でPCM16に量子化する。ノイズの実測電力比は全4合成で−47.0025 dB。固定上流の関数をRustで実行する別の照合で、アラインメント入力のPCM16が535,296フレームすべて一致した。測定用の元WAVは保存済みのfloat32を使う。[上流のノイズ生成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L204)・[PCM16への変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/wav.rs)・[Rustによる照合](../runs/tsp-phone-boundaries-20261121-noise-rust/summary.json)

`measure_pair` は `match_phones` の編集距離表から同じ音素の組を順序を保って取得する。今回も同じ再帰と同点時の経路を使い、通常の強勢番号を除いて音素を対応させた。`AH0` と `ER0` は弱母音として区別する。先行CLIの音素計画では `/aʊ/` が二つに展開されるので、同じ入力番号の区間をまとめてMFAの `AW2` と照合した。上流の `matching_keeps_only_the_same_phones_in_order` は余分な音と異なる母音を除くこと、`a_render_is_aligned_over_a_noise_floor_like_the_recordings` はレベルと再現性を確かめる。今回は語・音素の始端と終端を独立して比較し、語区間と間隔の和を最初の語から最後の語までの長さに照合した。[上流の対応付けと試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L761)・[研究用計測器](../tools/measure_tsp_phone_boundaries.py)

## 語・音素の計測結果

同じ入力の整列を別の作業領域で2回実行し、全6波形の語と音素の時刻・ラベルが一致した。録音2件の保存版注釈との最大境界差は `9.54×10⁻⁵ ms`。MFAのJSONが持つ浮動小数点の秒を小数3桁に丸めると元注釈に一致する。上流の計画と候補の計画は同じ区間を返し、合成4件ではすべて27音素が発音辞書どおりだった。実録音と合成は26音素が対応した。対応しなかった1音素は `to` の母音で、実録音は `AH0`、合成の辞書と整列結果は `UW0` だった。[生の区間・計画・対応する区間](../runs/tsp-phone-boundaries-20261121-final/summary.json)

| 話者と音声 | 語と語間の合計 ms | 語の合計 ms | 語間 ms |
| --- | ---: | ---: | ---: |
| FA01_02 録音 | 2,100 | 2,100 | 0 |
| FA01_02 上流・候補 | 2,380 | 2,200 | 180 |
| MA01_02 録音 | 2,100 | 2,100 | 0 |
| MA01_02 上流 | 2,390 | 2,190 | 200 |
| MA01_02 候補 | 2,390 | 2,180 | 210 |

候補の録音との差はFAで280 ms、MAで290 ms。MFAが語間とした区間はそのうち180・210 msで、主に `sheet` と `to` の間と、`dark` と `blue` の間に現れた。`background` 自体も候補が録音よりFAで100 ms、MAで190 ms長かった。対応する `/ʃ/` は候補のほうが10・30 ms短く、`background` の `AW2` は80・190 ms長かった。これらの語間には破裂音の閉鎖が含まれ得る。発話を聴いた判断や、閉鎖と意図的な間の区別は未実施。先行の相対RMSで得た長さとの差は、音声の端点の定義が違う測定として保存する。[全区間](../runs/tsp-phone-boundaries-20261121-final/summary.json)・[先行するRMS区間](tsp-active-duration-original.md#元の登録8件の主しきい値の結果)

## 実行環境と保存

macOS 15.6.1 arm64でmicromamba 2.10.0、Python 3.11、MFA 3.4.3、KaldiとKalpyをconda-forgeから用意した。音響モデルZIPと公開辞書は固定上流の `tools/tsp/setup.sh` のSHA-256と一致。環境、パッケージキャッシュ、モデルはRTL9210B-CGの `scratch/chimera-mfa` にあり、作業前の空きは約870 GiBだった。現在の環境とキャッシュなどの合計は約2.0 GiB。上流のセットアップで指定されているLinux x86-64の配布物に対応するmacOS arm64のmicromambaを使った。モデルと辞書、MFAの版を計測時に検査し、環境のパッケージ一覧を各実行と一緒に保存した。[固定上流のハッシュ](../../../../docs/reference/chimera-vocal-synth/upstream/tools/tsp/setup.sh)・[condaの実行環境一覧](../runs/tsp-phone-boundaries-20261121-final/artifacts/conda-explicit.txt)・[MFA 3.4.3の公式手順](https://montreal-forced-aligner.readthedocs.io/en/v3.4.3/getting_started.html)・[micromambaのmacOS手順](https://github.com/mamba-org/mamba/blob/main/docs/source/installation/micromamba-installation.rst)

環境は `micromamba --no-rc create --prefix <作業用ディスクのenv> --platform osx-arm64 --override-channels --channel conda-forge --strict-channel-priority montreal-forced-aligner=3.4.3 python=3.11` で構築し、`MAMBA_ROOT_PREFIX` と `TMPDIR` も作業用ディスクを指定した。最終実行は `/tmp` から絶対パスで起動し、7判定が通過した。初回と最終実行の音素・語区間とノイズの記録は一致した。リンクで公開した最終成果は約2.58 MBで、作業用ディスクに残したMFAの `tmp` は約1.0 GiBだった。最初の事前見積もり512 MiBは少なかったため、再現コマンドでは同じ6入力の作業領域に2 GiBを見込む。[初回実行](../runs/tsp-phone-boundaries-20261121-a/manifest.json)・[最終実行](../runs/tsp-phone-boundaries-20261121-final/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python tools/measure_tsp_phone_boundaries.py tsp-phone-boundaries-local-1
```

固定上流の録音注釈、Python計測器、確認した合成WAV、音素表記の根拠、MFAの設定と出力はマニフェストで追える。音響アラインメントの作業領域は各実行の `tmp` に分け、語と音素のJSONおよびアラインメントに使ったPCMを `artifacts` に残した。次は当初の確認用4録音を同じ条件で測り、破擦音の閉鎖に隣接するMFAの無音区間を音響観測と比較する。[初回実行](../runs/tsp-phone-boundaries-20261121-a/manifest.json)・[最終実行](../runs/tsp-phone-boundaries-20261121-final/manifest.json)
