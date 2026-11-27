# TSPの人手F2注釈を受け付ける条件

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare::tsp::measure_pair` は同じ音素に対応した録音・合成を `Sig::formants` に渡す。母音の35・50・65%の位置で12 kHzの300標本を評価し、LPCの極からF1・F2をHzで得る。測定できたF2を中央値にまとめ、測定が得られない場合は欠測を残す。上流の `a_missing_measurement_has_no_cost` はそれを良い測定値として集計しないことを検証する。人手注釈は同じ録音の窓に周波数や判断理由を付ける独立した比較で、コアのLPC採択は資料の判定を終えてから照合する。[窓と採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[欠測の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)・[注釈資料と観測点](tsp-f2-annotation.md)

再実装の `measure_tsp_f2_annotation.py` は資料ID・窓ID・判定・F2のHz・理由をCSVから読む。人の回答を指定する入口が、同じ資料の未記入雛形やブラウザ検証で作った試験CSVを受け付ける状態だった。TSPの試聴集計で使う、資料に紐付く既知の試験CSVとの照合と同じ方針でこの入口を検査する。録音6窓と既知の合成対照1窓で、測定・判断困難・音声や区間が不適の回答数を別々に扱う。[事前登録](../cases/tsp-f2-annotation.json)・[関連する試聴の取込](../tools/measure_tsp_listening.py)

## 取り込みの検証

改修前の関数を一時領域で実行すると、資料に同梱したブラウザの試験CSV、別の試験CSV、空の雛形の3件が人手注釈の検証を通った。改修後は `--kind human` で資料の試験CSVをハッシュ照合して読み、各窓の状態・周波数・理由で比較する。入力行の順序、未記入行の有無、BOM・改行形式は一致判定に影響しない。記入済みの判定が一つもないCSVと、既知の試験回答に一致するCSVを保存前に拒否する。実録音6窓については、F2を数値化した件数と、判断困難・音声不適の件数を含む `recording_judgments` を返す。合成対照だけを評価した場合、同じ項目はすべて0になる。[改修前の再現](/Volumes/RTL9210B-CG/voice-simulator/scratch/tsp-f2-intake-before.txt)・[取込と集計](../tools/measure_tsp_f2_annotation.py)

macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1。既存の2件は試験データとして集計すると、窓別の中央値・判定者間差・状態別の件数が第1版と一致した。録音窓の試験回答の内訳は測定2、判断困難1、音声不適1。理由付きの部分回答と合成対照だけの回答を受理することも試験入力で確認した。人手指定では元の試験CSV2件、BOM・改行・行順を変更して空欄行を省いたCSV、空の雛形を拒否した。ワークスペースと `/tmp` から集計と、表記を書き換えたCSVの拒否を再現した。固定上流の欠測試験1件が通過した。独立検算で7実行の80入力・8出力のサイズとSHA-256を照合し、成果の実体3,950バイトをRTL9210B-CGに保存した。[試験としての集計](../runs/tsp-f2-intake-synthetic-repeat-20261122/summary.json)・[書き換えた試験回答の拒否](../runs/tsp-f2-intake-reject-rewritten-repeat-20261122/manifest.json)・[空の雛形の拒否](../runs/tsp-f2-intake-reject-empty-20261122/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-tsp-f2-human-intake.py)

[録音6窓と対照1窓の評価ページ](../runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)から保存した実際の回答は、このページを生成した実行IDを `--packet` に指定して取り込む。今回保存・集計した回答の出所は試験入力で、人による録音の評価は未取得。[人の回答を取り込むコマンド](tsp-f2-annotation.md#使い方)

## 実録音の注釈を第7段階の監査で照合する

固定上流の `compare tsp` は48 kHzの録音と合成を読み、`measure_pair` で音素を対応させる。`Sig::formants` は間引いた12 kHzのPCMを使い、母音内の35・50・65%に当たる各300標本からF1・F2を求める。F1は1,300 Hz未満で帯域幅500 Hz未満、F2は採択したF1より200 Hz超かつ3,500 Hz未満の最初の候補。窓の端や必要な候補がないときはその窓を飛ばす。欠測に得点を付けない挙動を上流の試験で確認する。注釈は録音側の同じ観測窓への独立した回答なので、比較前に録音IDと標本範囲を一致させる。[録音と合成の対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と候補の採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[欠測の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

第8版監査の `--f2-annotation-run` は、通常CLIの人手区分で集計した実行を、既存資料と照合する。資料IDは窓の情報から再計算し、7窓のWAV・図と、匿名IDに対応する元CSVのSHA-256を確認する。CSVは窓の状態・周波数・理由を読み、既知の試験回答と未記入を除外する。取り込みの段階で、所見の内部の改行をLFからCRLFに変えただけの試験回答も照合できるようにした。以前の集計コードでこの表記変更が通ることを再現し、更新後の通常CLIでは拒否した。元の試験回答を試験区分で取り込むと、窓別の集計はバイト一致した。[事前登録](../cases/plan-evidence-stage7.json)・[監査の実装](../tools/audit_stage7_f2_annotations.py)・[表記変更の拒否](../runs/stage7-f2-20261123-reject-multiline/manifest.json)・[元の試験集計との照合](../runs/stage7-f2-20261123-collect-synthetic/summary.json)

実録音の6窓ごとに状態の件数、F2の中央値、判定者間の範囲を再計算する。上流既定のプリエンファシスと無適用で採ったF2を元の計測実行から読み、各 `LPCの採択値 − 注釈の中央値` をHzで報告する。単独の値は単独測定と表示する。判定者間の範囲が既定の100 Hzを超える窓や数値の測定がない窓は、偏差を空欄にする。合成対照は別に計数する。観測の状態は、録音の6窓のどこまで判定が記入されたかで示す。数値の比較に使える窓数も併記する。[元のLPC計測](../runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/summary.json)・[監査での数え方と再開手順](plan-evidence-stage7.md#第8版でf2注釈を照合する)
