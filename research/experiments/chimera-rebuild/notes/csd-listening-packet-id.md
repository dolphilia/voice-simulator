# CSD試聴の回答を使った資料に結び付ける

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `crates/chimera-cli/src/compare.rs` の `compare_song` は、発音付き音符注釈と録音を読み、同じ秒座標に合成音を置く。`Analyzer::note` は各音符のF0やビブラートを計測し、`vibrato_reads_rate_and_depth_of_a_periodic_modulation` は既知の周期変調の速さと深さを照合する。試聴は人が周期的な揺れを0〜3または判定不能で記録し、自然さの選好を別に記録する。秒・Hz・セントを使う上流の計測と、試聴の評点を直接換算する式は設けない。

再実装の `prepare_csd_listening.py` は録音・固定上流・再実装を同じ秒区間で切り出し、48 kHzへそろえて1区間3 WAVを作る。表示するA・B・Cは区間ごとに入れ替え、音源対応を別ファイルに保存する。`collect_csd_listening_responses.py` は第1版では素材の実行IDと区間番号を使う。回答CSVに素材IDがないため、同じ区間番号を持つ別資料が選ばれると、違うA・B・C対応でも回答の形式を満たし得る。第2版では素材の版、音源対応と全WAVを識別する資料IDをCSVの各行に付け、取込前に全行を照合する。[生成の条件](../cases/csd-listening.json)・[回答検証の条件](../cases/csd-listening-responses.json)

## 生成と取り込み

資料IDは、固定上流コミット、ケースIDと版、CSVの列順、評点の選択肢、音源対応表と試聴WAV18本のSHA-256を、キー順をそろえたUTF-8 JSONにしてSHA-256で求める。生成時はそれを `listening-packet.json` に記録し、試聴ページで書き出すCSVと記入用CSVの全区間行に入れる。集計時には保存済みケースとWAV・対応表から資料IDを再計算してから照合する。第1版の資料は生成時に記録した列に従い、試聴した実行IDを指定して集計する。[第2版の試聴ページ](../runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)・[記入用CSV](../runs/csd-listening-packet-20261122-a/artifacts/listening/observations.csv)・[集計の実装](../tools/collect_csd_listening_responses.py)

## 検証

macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1、Chrome 157.0.8103.79。作業ツリーと `/tmp` から試聴資料の生成13判定、回答検証14判定を再現した。第1版と第2版の18 WAVと音源対応表はバイト一致し、第2版は別ディレクトリから生成しても資料IDが一致した。全WAVをChromeで再生し、揺れ・自然さ・自由記述を入れたCSVの書き出しを確認した。第1版の回帰は11判定に合格した。[資料のマニフェスト](../runs/csd-listening-packet-20261122-repeat/manifest.json)・[回答CSVの検証](../runs/csd-listening-packet-responses-20261122-repeat/summary.json)・[第1版の回帰](../runs/csd-listening-packet-v1-regression-20261122/summary.json)

別資料のID、1行だけ異なるID、資料IDの列がないCSVを拒否した。通常の取込コマンドでも、試験回答2件の集計は既知の票数と一致し、資料IDを書き換えた1件は失敗理由を保存した。固定上流のビブラート既知信号の1試験にも合格した。標準ライブラリで資料ID、18 WAV、既知の集計と旧版との一致を独立に照合し、7実行の216入力・74出力のサイズとSHA-256を検証した。実体7,328,317バイトをRTL9210B-CGに保存した。人による回答は未取得。[通常取込の試験](../runs/csd-listening-packet-collect-fixture-20261122/summary.json)・[不一致の記録](../runs/csd-listening-packet-reject-fixture-20261122/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-csd-listening-packet-id.py)

研究ワークスペースから新しい資料と試験の集計を再実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/prepare_csd_listening.py csd-listening-packet-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=5000000 \
  ../../.venv/bin/python tools/collect_csd_listening_responses.py csd-listening-packet-check-new \
  --package-run csd-listening-packet-new --verify
```

## 人手回答として受け付ける条件

上流の `main::run` は `compare csd` を `compare::csd` に渡し、曲ごとに `compare_song` が楽譜の秒座標を録音と合成の両方に適用する。`Analyzer::note` は音高を5 ms刻みで測り、`vibrato` は最長の連続有声区間が0.4秒以上のときにセント列の平均と傾きを引く。最初の正規化自己相関ピークが0.5以上で、ラグを秒に換算した周期の逆数が4〜9 Hzに入れば検出する。深さは残差RMSの√2倍。上流試験では4.5・5.5・8.5 Hz、深さ50セントの信号で、それぞれ0.3 Hz・8セント未満の誤差を確認した。人の揺れの評点0〜3と自然さの選択は、同じ試聴区間への回答として別に記録する。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[音符ごとの観測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)・[ビブラートの演算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)・[既知波形の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1329)

変更前の通常CLIで、空欄だけのCSVと既知の試験CSVがいずれも `response_csv` として保存された。第3版の集計ケースでは人手の登録を `--kind human` で明示する。資料ID・区間・選択肢を検査してから、記入がある区間番号とA・B・Cの各評点、自然さ、所見を照合する。この照合だけではBOM、行順、番号の先頭ゼロ、欄の端の空白、改行形式、記入のない行の差を除く。入力全部の照合後に、元のCSV・区間別回答・集計を保存する。拒否時には入力バイト数とSHA-256を匿名IDごとにマニフェストへ残す。回答の人手区分は提出時の申告に基づく。[事前登録](../cases/csd-listening-responses.json)・[実装](../tools/collect_csd_listening_responses.py)・[変更前の空欄の保存](../runs/csd-human-intake-before-empty-20261122/manifest.json)・[変更前の試験回答の保存](../runs/csd-human-intake-before-fixture-20261122/manifest.json)

記入のない雛形、ブラウザ・手入力の試験CSVを書き換えたもの、第1版の試験CSV、先に有効な0点の入力を渡して後続が試験CSVだった組の計5実行を拒否した。いずれも集計と回答ファイルの出力は0件。検査内の対照として0点だけの入力と所見だけの入力は判定を通した。資料を変えず、既存の通常区分 `response_csv` と明示した試験区分 `synthetic` で、従来の区分別件数・音源別分布と音源対応後の行データを再現した。調整用は6予定行中4提出・2記入で研究版への自然さの票が2、確認用は6予定行中5提出・2記入で「差なし」と「判定不能」が各1だった。[空欄の拒否](../runs/csd-human-intake-reject-final-blank-20261122/manifest.json)・[書式変更の拒否](../runs/csd-human-intake-reject-final-browser-20261122/manifest.json)・[複数回答の拒否](../runs/csd-human-intake-reject-final-batch-20261122/manifest.json)・[通常の試験入力](../runs/csd-human-intake-synthetic-final-20261122/summary.json)

研究ワークスペースと `/tmp` の各16判定で要約がバイト一致し、第1版の13判定も通った。固定上流の既知波形の1試験は `cargo test --locked --offline -p chimera-cli compare::tests::vibrato_reads_rate_and_depth_of_a_periodic_modulation` で確認した。最初の拒否記録には入力ファイルのハッシュがなかったため、読み込んだバイト列をその場で記録する処理を加えて再検証した。比較前2実行と確定10実行の391入力・33出力を独立に照合した。計44,591バイトの外部出力はRTL9210B-CGに保存した。macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1、Chrome 157.0.8103.79。実際の試聴回答は未取得。[最初の拒否記録](../runs/csd-human-intake-reject-browser-20261122/manifest.json)・[確定版の要約](../runs/csd-human-intake-verify-final-repeat-20261122/summary.json)・[第1版の再実行](../runs/csd-human-intake-verify-final-legacy-20261122/manifest.json)

研究ワークスペースから資料に付属する試験を再現する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=5000000 \
  ../../.venv/bin/python tools/collect_csd_listening_responses.py csd-listening-intake-check-new --verify
```

試聴後に届いた回答には集計コマンドの `--kind human` を指定する。[試聴ページ](../runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)・[回答の取込手順](csd-listening-responses.md#再現と回答の集計)
