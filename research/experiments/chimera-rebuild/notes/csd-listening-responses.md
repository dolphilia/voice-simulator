# 歌唱のブラインド試聴回答を音源別に集計

新しい回答には[第2版の試聴ページ](../runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)を使う。第2版は書き出したCSVの各区間行に資料IDを付ける。下記の検証結果は第1版の記録。[第2版の照合方法と検証](csd-listening-packet-id.md)

## 上流から回答CSVまで

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song()` は、録音の秒座標に合成音を配置し、同じ注釈の音符を `Analyzer::note()` で測る。ビブラートは連続有声区間のセント列から求め、区間長を秒、振動の速さをHz、深さをセントで扱う。`vibrato_reads_rate_and_depth_of_a_periodic_modulation()` は既知の周期変調に対してその深さと速さを照合する。今回の試聴回答は人が付ける0〜3の無単位の評点で、上流のビブラート値への換算は行わない。[上流の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[有声区間からの推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)・[既知波形の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)

既存の `prepare_csd_listening.py` の `generate()` は `balanced_orders()` から区間別の音源順を取得し、WAVをA・B・Cと名付ける。`html_trial()` は区間番号、A・B・Cごとの揺れ、自然さの選択、自由記述を表示する。HTMLのフォームは現在の状態を表示順に読み、引用符を二重化してBOM付きUTF-8のCSVにする。未入力の選択欄は空文字を出力する。音源対応表は試聴ページの外に保存される。ブラウザ検査は18 WAVの再生と排他、表示幅、CSV書き出しを検証する。[素材生成と対応表](../tools/prepare_csd_listening.py#L238)・[フォーム書き出し](../tools/csd_listening.html#L65)・[実ブラウザの検査](../../../../web/prototypes/chimera-research/tools/verify-csd-listening.mjs)

集計CLIは素材の実行IDから、生成時のケースと音源対応表のSHA-256を照合する。CSVの列名、区間番号、値を検査した後、区間ごとのA・B・Cを録音・固定上流・再実装に対応付ける。揺れの0は有効な評点とし、空欄と「判定不能」を別に数える。自然さの「差なし」も独立の回答とする。欠けている行は未回答として集計し、出力の `row_present` に行の有無を残す。自由記述は区間全体への所見として回答IDと区間番号に付ける。現行の回答CSVには素材固有のIDが無いため、集計時に実際に使った素材の実行IDを指定する。[事前登録](../cases/csd-listening-responses.json)・[集計CLI](../tools/collect_csd_listening_responses.py)

## 検証

保存済みの試聴ページをChromeで読み、既存のブラウザ検査の入力を実際に書き出した。区間01はAの揺れを2、Bを「判定不能」、Cを空欄にし、自然さはCを選んだ。もう一つの試験CSVでは、先頭ゼロの無い番号で区間05・02・04を順不同に記入した。区間02のAと区間01のCは同じ再実装音源で、調整用の自然さの欄に再実装2票と集計された。確認用には「差なし」と「判定不能」が1件ずつ入った。12予定行のうち9行がCSVにあり、何らかの記入があったのは4行。揺れの全36枠と自然さの全12枠が、事前に手計算した分布と一致した。日本語、カンマ、引用符、行内改行を含む自由記述もそのまま残った。[集計の検証結果](../runs/csd-listening-responses-20261122-repeat/summary.json)・[各行の音源対応](../runs/csd-listening-responses-20261122-repeat/artifacts/fixture-responses-by-source.json)

空の記入用CSVは有効な評点と票を加えなかった。重複番号・未登録番号・範囲外の評点・未定義の選択・列数のずれ・閉じていない引用符の6条件を拒否した。通常の集計コマンドでも、`01` と `1` を同じ区間の重複として停止し、マニフェストに理由を残した。別途、通常の集計コマンドへ作業ツリー外の試験CSV2本を渡し、素材の照合、入力CSVの保存、正規化した回答と集計結果がブラウザ試験と一致することを確認した。実際の聴取者からの回答は今回の集計に含まれない。[重複入力の失敗記録](../runs/csd-listening-responses-20261122-duplicate-fixture/manifest.json)・[通常コマンドの試験](../runs/csd-listening-responses-20261122-fixture-cli/manifest.json)

## 再現と回答の集計

macOS 15.6.1 arm64、Python 3.14.4、Chrome 157.0.8103.79で検証した。研究ワークスペースと `/private/tmp` で各11判定が成立し、それぞれChromeで18 WAVを再生した。集計要約・音源対応後の回答・元の試験CSV2本・ブラウザの検証結果はバイト一致した。成功3実行と重複入力1実行の82入力・16出力をサイズとSHA-256で照合した。採取物20,435バイトはRTL9210B-CGにあり、音声は元の試聴素材を参照した。[初回](../runs/csd-listening-responses-20261122-a/manifest.json)・[別ディレクトリの再実行](../runs/csd-listening-responses-20261122-repeat/manifest.json)

研究ワークスペースでブラウザ検査と既知回答の集計を再現する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=67108864 ../../.venv/bin/python \
  tools/collect_csd_listening_responses.py csd-listening-responses-local-check --verify
```

人による試聴は[第2版の試聴ページ](../runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)から始め、採点が終わったCSVを集計に使う。次の例はこのページで書き出した2人分の回答を匿名IDで保存する。別の素材を使った場合は、その素材の実行IDを指定する。

```bash
../../.venv/bin/python tools/collect_csd_listening_responses.py csd-listening-responses-local \
  --package-run csd-listening-packet-20261122-a --kind human \
  --response listener-01 /path/to/first-response.csv \
  --response listener-02 /path/to/second-response.csv
```

実行の `summary.json` に回答の出所区分と区分・音源別の件数を保存する。`artifacts/responses-by-source.json` には区間別に正規化した評価と自由記述、`artifacts/responses/` には検証に使った元CSVを保存する。既知の試験回答と未記入の雛形は人手区分では拒否する。回答の件数はこの6区間の記述的な集計で、試聴に使った音源や他の歌唱全体の評価を一般化する基準は別途必要になる。[人手区分の照合](csd-listening-packet-id.md#人手回答として受け付ける条件)
