# 当初のTSP登録8件と拡張18録音の発話区間長

先行14録音の話者分割と分割内の順序を維持し、元の調整用 `FA01_02`・`MA01_02` と確認用 `FK61_02`・`MK61_02` を追加した。各追加ペアは男女で同じ本文。入力検査では前者が各133,824フレーム、後者が各144,727フレームだった。先行14件の測定と合成WAVが再現し、追加4件の主しきい値の合成間差は10 ms以内と予測した。調整用6件・確認用12件の録音で同じ条件を使った。[条件](../cases/tsp-active-duration-original.json)・[元の登録](../cases/tsp-active-duration-pilot.json)・[本文の入力検査](../runs/tsp-active-duration-inspect-20261121-dzh/summary.json)

## 上流の描画と今回の計測

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `chimera-cli/src/main.rs::run` は `render text --float` を `render::text` に渡す。`text` と `compare/tsp.rs::say_all` の両方が `render::say` を使う。辞書から得た音素と句境界を `plan_phrases` に渡すと、50 msからの計画とジェスチャーが得られる。体型別の基準F0は成人女性205 Hz・男性112 Hz。計画終端に300 msを足して48 kHzのフレーム数に丸める。声門と肺圧、気道の各枝・節点は96 kHzで進み、放射から間引き、出力ゲイン、DC除去、ピーク制限の順に適用してfloat32を出す。再実装の `render-pcm` のWAVと時系列のPCM列は全点を照合した。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[発話と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[音響状態の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

上流の `load_utts` は録音ID、本文、MFAの音素区間を読み、`measure_pair` は `match_phones` の編集距離で同じ音素を対応付ける。関連する上流試験は、音素順序、辞書の対応、欠測と合成のアラインメント用ノイズを検査する。今回の指標では録音と二つの合成の文全体を測る。録音は外部ディスクのZIPからモノラルPCM16を読み、振幅を32768で割る。各波形から960フレームの窓を240フレーム刻みで取り、窓RMSをその波形の最大窓RMSで割る。−35 dBと−45 dBの各しきい値で3窓以上連続して採用された部分について、最初の窓の開始と最後の窓の終了を用いる。独立検証は二乗PCMに幅960の矩形を直接畳み込み、しきい値を電力比 `10^(dB/10)` で計算した。前後100 msを足す無音対照では区間長が不変で、18録音の108区間の両端が独立計算と一致した。[上流の録音読み込み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L49)・[音素の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L761)・[計測器](../tools/measure_tsp_active_duration.py)・[独立検証](../runs/tsp-active-duration-original-20261121-independent-final/summary.json)

## 元の登録8件の主しきい値の結果

| 分割 | 録音ID | 録音 ms | 固定上流 ms | 再実装 ms | 再実装 − 録音 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 調整用 | FA01_01 | 2,380 | 2,410 | 2,405 | +25 |
| 調整用 | FA01_02 | 2,165 | 2,505 | 2,505 | +340 |
| 調整用 | MA01_01 | 2,155 | 2,430 | 2,430 | +275 |
| 調整用 | MA01_02 | 2,060 | 2,525 | 2,525 | +465 |
| 確認用 | FK61_01 | 2,220 | 2,115 | 2,110 | −110 |
| 確認用 | FK61_02 | 2,540 | 2,720 | 2,720 | +180 |
| 確認用 | MK61_01 | 2,210 | 2,125 | 2,125 | −85 |
| 確認用 | MK61_02 | 2,225 | 2,745 | 2,745 | +520 |

全18録音で上流と再実装の区間長差は最大5 ms。追加4件の区間両端は合成間で一致し、再実装は録音より180〜520 ms長かった。全18件で録音との差は−410〜+520 ms。先行14録音について測定値と両合成WAV28件のSHA-256が一致した。独立検証に `--require-original-registration` を指定すると、元の登録の分割と全件の有無を確認し、独立計算から得た8件の長さをまとめて出力する。初回の独立検証では108区間の照合まで保存し、元の8件の集計を指定した再実行も保存した。指定なしで先行14録音を検証した出力は以前の検証とバイト一致した。[全18件の結果](../runs/tsp-active-duration-original-20261121-repeat/summary.json)・[初回の独立検証](../runs/tsp-active-duration-original-20261121-independent/summary.json)・[元の登録を含む独立検証](../runs/tsp-active-duration-original-20261121-independent-final/summary.json)

## 発話前の放射と終端のしきい値

追加4件の再実装はフレーム0の間引き出力から差があった。`/g/` 始まりの調整用と `/h/` 始まりの確認用の両方で、最初に変化を始められる呼気ランプは50 ms。最初の64フレーム制御境界のうち50 msを超えるのは2,432フレームで、固定上流は2,439フレームでPCMが非ゼロになった。舌先だけを `(6.45, 7.30)` cmから、顎の回転と舌体偏差で求めた静止位置 `(6.241413, 6.810460)` cmへ移すと、2,400フレーム未満の放射の間引き出力とPCMが4件とも0となり、最初の非ゼロは上流と同じ2,439だった。主しきい値の結果に変化はなく、副しきい値の開始は `MA01_02` が0から40 ms、`MK61_02` が0から60 msに移り、上流と一致した。`MA01_02` には終端の5 ms差が残った。[調音と呼気の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[舌先対照の条件](../cases/tsp-startup-original.json)・[対照結果](../runs/tsp-startup-original-20261121-a/summary.json)

`MA01_02` のフレーム123,120からの窓は、絶対RMSが上流0.001032536、元の再実装0.001032545で、振幅比は0.000070 dB。波形ごとの最大窓RMSは上流0.184020、再実装0.175580で、0.408 dB違った。各波形を個別の最大値で割ると当該の窓は上流−45.019 dB、再実装−44.611 dBとなり、しきい値をまたいだ。上流の最大RMSを使い、`上流の最大RMS × 10^(−45/20)` を各波形の共通しきい値にした対照では、元の再実装と舌先対照の両方で終端が124,080から123,840へ移り、上流と一致した。本測定の各波形に対する相対しきい値は維持した。通常経路で残る有声部の波形差と、最大RMSを作る区間の違いの原因は未分離。[窓RMS](../runs/tsp-active-duration-original-20261121-repeat/artifacts/MA01_02/windows.csv)・[各波形の最大RMSと区間](../runs/tsp-active-duration-original-20261121-repeat/summary.json)

## 再現と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行した。初回と `/tmp` からの再実行は各6判定、元の登録を含む独立検証は7判定、舌先対照は8判定を通過。固定上流のTSP試験6件とCLIのWAV試験1件も通過した。ログを除く149成果と元CSV18件のハッシュが再実行で一致した。候補CSV約198.6 MBをRTL9210B-CGで全件検査し、元のハッシュと必要な行を残した。1回分の保存成果は約35.0 MB。元録音は外部ディスクのZIPからメモリへ読み出した。音量をそろえた18試聴対と記録欄を保存した。人による試聴は未実施。[初回の保存記録](../runs/tsp-active-duration-original-20261121-a/manifest.json)・[再実行の保存記録](../runs/tsp-active-duration-original-20261121-repeat/manifest.json)・[独立検証の実行記録](../runs/tsp-active-duration-original-20261121-independent-final/manifest.json)・[試聴手順](../runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)・[試聴記録欄](../runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/observations.csv)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_tsp_active_duration.py tsp-active-duration-original-local-1 --case cases/tsp-active-duration-original.json
../../.venv/bin/python tools/verify_tsp_active_duration.py cases/tsp-active-duration-original.json runs/tsp-active-duration-original-local-1 --require-original-registration
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_tsp_startup.py tsp-startup-original-local-1 --case cases/tsp-startup-original.json
```

次の音素別評価ではまず、固定上流が使うMFA 3.4.3と `english_us_arpa` v3.0.0の版を固定し、調整用録音と同じ本文の両合成で音素境界を照合する。上流の `align_synth` は発音辞書と録音ごとの作業領域を用い、合成を一定のノイズ床に重ねてアラインメントを取る。上流のセットアップはLinux x86-64のツールを取得する構成なので、macOS arm64で同じ版を使える実行環境を確認する。確認用の録音は、手順と判定を固定した後に測る。[上流のアラインメント処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L248)・[アラインメント設定](../../../../docs/reference/chimera-vocal-synth/upstream/tools/tsp/mfa.yaml)・[上流のセットアップ](../../../../docs/reference/chimera-vocal-synth/upstream/tools/tsp/setup.sh)

## 比較試聴のページと回答の取り込み

固定上流のCLI `compare tsp` は `tsp::run()` で録音本文を合成し、`--dump` を指定するとPCMと計画した音素区間を保存する。`align_synth()` は合成を再アラインし、`measure_pair()` は48 kHzの録音と合成から、同じ音素が同順で現れる部分を対応させて音響量を測る。`matching_keeps_only_the_same_phones_in_order` と `a_missing_measurement_has_no_cost` は、比較対象の対応と、欠測が測定値へ置き換わらないことを検証する。上流資料は、音響指標の順位が聴感の順位と一致しない事例も示す。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[計測と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[比較試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)・[試聴と音響指標](../../../../docs/reference/chimera-vocal-synth/upstream/docs/speech-comparison.md)

今回の試聴対は、研究版と実録音の調整用6対・確認用12対。元の `listening_pair()` は各波形から −35 dBの主しきい値で得た半開区間を切り出し、対のRMSをそろえて48 kHzモノラルFloat32 WAVに保存する。新しいページはその36 WAVをバイト単位で保持し、各標本数が元の終了フレームと開始フレームの差に一致することを確認する。画面ではA/Bのどちらが速く聞こえたか、文中の間が長く聞こえたかを記録する。比較の対象に文頭・文末の無音や固定上流の音声は含めていない。[元の試聴対の生成](../tools/measure_tsp_active_duration.py#L126)・[事前登録](../cases/tsp-listening-responses.json)

[試聴ページ](../runs/tsp-listening-responses-20261122-final/artifacts/listening/index.html)を開き、各組を聴く。未回答の組を残したままCSVを保存できる。試聴に使うのは `artifacts/listening/` 内のページ、音声、利用条件。音源対応は別の `artifacts/reference.json` にある。CSVに書き出す資料IDは、音源対応とWAVのハッシュ、資料の版、利用条件のハッシュから決まる。集計ではA/Bを元の音源に戻し、未提出の行、提出済み空欄、「同程度」、「判定不能」を区別する。「調整用」と「確認用」は元の録音選定に従う。[取込処理](../tools/measure_tsp_listening.py)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728
../../.venv/bin/python tools/measure_tsp_listening.py prepare tsp-listening-responses-new
../../.venv/bin/python tools/measure_tsp_listening.py collect tsp-listening-human-new \
  --packet tsp-listening-responses-20261122-final --kind human \
  --response 'rater-a=/path/to/tsp-listening-observations.csv'
```

2か所からの資料生成で各7判定と上流TSP 6試験を通過し、全47出力がバイト一致した。Chrome 157.0.8103.79で36音源の長さ、先頭対の逐次再生、390 px幅、引用符と改行を含むCSVの書き出しを検証した。既知の2件の試験回答は通常の取込でも手計算と一致した。調整用12回答枠で提出7・記入3、確認用24回答枠で提出14・記入3。ブラウザの試験回答をBOMと改行の異なるCSVへ書き換えても、人の回答として扱う指定は拒否された。空欄の雛形も拒否された。取込時の人手区分は提出者の申告に基づく。人の試聴結果は未取得。[資料生成](../runs/tsp-listening-responses-20261122-final/manifest.json)・[別作業場所の再実行](../runs/tsp-listening-responses-20261122-repeat/manifest.json)・[通常CLIの試験回答](../runs/tsp-listening-responses-20261122-fixture/summary.json)・[試験回答の拒否](../runs/tsp-listening-responses-20261122-reject-fixture/manifest.json)・[空欄の拒否](../runs/tsp-listening-responses-20261122-reject-blank/manifest.json)

macOS 15.6.1 arm64、Python 3.14.4、Node.js 24.19.0、Rust 1.94.1、固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`。環境、上流の試験コマンド、出力を実行記録に保存した。初回、確定、再実行、通常取込、拒否2実行の315入力と145出力は、サイズとSHA-256を照合した。採取物45,947,026バイトはRTL9210B-CGに保存した。[初回の実行記録](../runs/tsp-listening-responses-20261122-a/manifest.json)

### 人手回答と試験回答の記入内容を照合する

固定上流の `compare tsp` は `measure_pair` が48 kHzの録音・合成の音素を対応させ、`measure` が音素数を区間長 `t1 − t0` の合計秒数で割って調音速度を求める。固定上流の `matching_keeps_only_the_same_phones_in_order` は、音素が同じで出現順も揃う箇所を選ぶことを確認する。試聴では同じ録音・合成の組を用い、テンポと文中の間に対するA/B・同程度・判定不能と所見を回答者が記入する。集計は資料IDを照合し、A/Bをその区間の録音・合成へ戻してから数える。[上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L116)・[録音との比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[調音速度](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L651)・[音素の対応試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1544)

資料を生成した時点の集計コードは、音源へ対応付けた回答全行を既知の試験CSVと比較していた。ブラウザ回答から空欄行を省く、手入力回答に空欄行を足す、前者の所見の空白と改行・行順・BOMも変えるという3対照は、旧処理でいずれも人手区分を通った。これは保存済みコードでの試験で、結果は試験区分として記録した。更新後は資料IDと区間を検査してから、記入済みのテンポ・間・所見だけを比較する。所見の前後の空白と改行の表記を照合時に揃える。複数の回答はすべての検査後にまとめて書き出す。入力の匿名ID、サイズ、SHA-256、コマンドは実行記録に残す。[事前登録](../cases/tsp-listening-intake-equivalence.json)・[旧処理の結果](../runs/tsp-listening-intake-equivalence-20261122-before/summary.json)・[現在の取込処理](../tools/measure_tsp_listening.py)

既存資料を使った通常CLIで、書式変更3件、空欄、複数回答の途中の拒否を確認した。5件とも集計の出力は0件だった。選択を変えたものと所見を変えたものは試験上の同一判定から外れた。書式を変更した2回答を試験区分で集計すると、提出行は調整用7→3、確認用14→4に変わり、記入行は各3と票は一致した。元の2回答の集計と音源への対応は以前の結果とバイト一致した。実際の人による回答は未取得。[集計の再実行](../runs/tsp-listening-intake-equivalence-20261122-final-synthetic/summary.json)・[複数回答の拒否](../runs/tsp-listening-intake-equivalence-20261122-final-reject-batch/manifest.json)・[比較の要約](../runs/tsp-listening-intake-equivalence-20261122-final-repeat/summary.json)

macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1。ワークスペースと `/tmp` から各5判定が通り、要約はバイト一致した。固定上流のTSP 6試験も通過した。旧処理と確定版の10実行で402入力・30出力と取込CSVの指紋を独立に照合し、13,046バイトの採取物をRTL9210B-CGに保存した。[確定版のマニフェスト](../runs/tsp-listening-intake-equivalence-20261122-final-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=8000000 \
  ../../.venv/bin/python tools/measure_tsp_listening_intake.py tsp-listening-intake-local
```

## 試聴のテンポと区間長の照合

固定上流の `compare tsp` は `say_all()` と `align_synth()` から合成音の音素境界を作り、`measure_pair()` が録音と合成を比較する。`measure()` で使う調音速度は、音素数を各音素の区間長 `t1 − t0` の合計秒数で割った音素数毎秒である。試聴は同じ本文の対に対する速さの印象を尋ねる。今回の照合では、発話区間長と、低エネルギー時間を差し引いた区間長から、速さの方向をそれぞれ求めた。[上流の比較入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L824)・[調音速度の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L651)

元の `measure_waves()` は48 kHzのPCMについて、960フレームの窓を240フレーム刻みで進め、波形ごとの最大窓RMSを基準にする。今回も、各しきい値以上の窓が3つ続く最初の位置から、最後の該当窓の右端までを発話区間とした。内部で閾値未満の窓が3つ以上続いた箇所は、窓中心から次のホップまでを一単位として合計する。隣り合う窓の重複を二重に数えず、5 ms単位で低エネルギー時間を求める。差の絶対値が2ホップ以内のときは方向を保留する。低エネルギー区間には子音の閉鎖や弱い音も含まれ得る。文中の間をどう聴いたかは試聴回答に残す。[元の区間計測](../tools/measure_tsp_active_duration.py#L38)・[事前登録](../cases/tsp-listening-timing.json)・[照合処理](../tools/measure_tsp_listening_timing.py)

36試聴WAVの標本数は主しきい値の区間長と一致した。録音・固定上流・再実装の18組×2しきい値で再計算した108区間の両端は保存値と一致した。別の計算では、RMSを二乗し閾値を電力比 `10^(dB/10)` で適用する。得られた真偽列に `[1, 1, 1]` を畳み込み、和が3の各位置と後続2位置を集めると、全108条件で低エネルギー区間の両端と合計フレーム数が一致した。[全対の計測](../runs/tsp-listening-timing-20261122-repeat/artifacts/pair-measurements.json)

| 試聴対と区分 | 録音の総区間／低エネルギー／差し引き後（ms） | 再実装の総区間／低エネルギー／差し引き後（ms） |
| --- | ---: | ---: |
| 03 `FA01_01`（調整用） | 2,380／160／2,220 | 2,405／360／2,045 |
| 07 `FK64_08`（確認用） | 2,025／370／1,655 | 1,945／155／1,790 |

−35 dBではこの2対で、総区間と低エネルギー時間を差し引いた区間の長短の向きが逆になった。どちらの集計も全体では録音14対・再実装4対が短く、件数だけでは2対の逆転が表れない。しきい値を−45 dBにすると、5対で三つの方向判定のいずれかが変わり、確認用07の差し引き後は録音・再実装とも1,890 msになった。[両しきい値の結果](../runs/tsp-listening-timing-20261122-repeat/summary.json)

試聴回答の各CSVをもう一度読み、資料IDと元のA/B対応を照合した。2件の試験回答で、総区間長に対する7件の分類が手計算と一致した。回答行の欠落、欄の未回答、同程度、判定不能、測定方向の保留を別の値で保存している。人による回答は受領後、取り込み実行IDを `--responses` で渡す。各回答に元の調整用・確認用の区分を付ける。人の回答による一致・不一致はまだ観測していない。[試験回答の照合結果](../runs/tsp-listening-timing-20261122-repeat/artifacts/response-comparisons.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728
../../.venv/bin/python tools/measure_tsp_listening_timing.py tsp-listening-timing-new \
  --responses tsp-listening-responses-20261122-fixture
../../.venv/bin/python tools/measure_tsp_listening_timing.py tsp-listening-timing-acoustic-new
```

研究ワークスペースと `/private/tmp` から試験回答を付けた実行を行い、各4判定と固定上流TSPの6試験を通過した。3件の結果を含む4出力がバイト一致し、Cargoのログには共有キャッシュと成果ディレクトリのロック待ちの差があった。回答指定なしの実行でも3判定を通過し、試聴対の音響計測JSONがバイト一致した。macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。3実行の220入力・14出力をサイズとSHA-256で照合し、計測結果とログ265,746バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-listening-timing-20261122-a/manifest.json)・[再実行](../runs/tsp-listening-timing-20261122-repeat/manifest.json)・[音響量のみ](../runs/tsp-listening-timing-20261122-acoustic/manifest.json)

## 確認用07の低エネルギー区間と語・音素

確認用07は `FK64_08` の “Fine soap saves tender skin.”。固定上流の保存注釈で `soap` と `saves` の間は690〜890 msなので、その区間が先に観測した215 msの低エネルギー時間差の過半を占めると予測した。録音1本と同じ本文を合成した固定上流・再実装の2本は、試聴対の元になった全長WAVから選んだ。[事前登録](../cases/tsp-phone-boundaries-listening-07.json)・[保存済みの区間計測](../runs/tsp-listening-timing-20261122-acoustic/artifacts/pair-measurements.json)

固定上流の `tsp::run` は `say_all` から合成のPCMと発話計画を受け取り、`align_synth` が発音辞書形とMFAで時刻を割り当てる。`over_noise_floor` は48 kHzの完全な20 ms窓で平均二乗を求め、その95パーセンタイル電力に対して−47 dBの一様雑音を固定シードで合成に加える。境界はこの整列用音声から取得し、試聴対の低エネルギー区間は加算前の波形の窓RMSから取得した。既存の比較器の入口から録音と合成を同じMFA 3.4.3と辞書・モデルで2回ずつ整列した。固定上流のTSP試験は音素の対応、辞書の往復、ノイズ床の再現性などを検査する。[上流のノイズ床と整列](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L204)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1512)・[整列の実行記録](../runs/tsp-phone-boundaries-listening-07-20261122-a/manifest.json)

初回の入力検査は、元の8録音を持つ `tsp-active-duration-pilot` の対象範囲から確認用07を見つけられず、整列の開始前に停止した。同じ録音アーカイブを参照し、先行実行が保存した18録音の登録をケースID・固定上流版・SHA-256で照合して確認用07を選べるようにした。[対象範囲の確認処理](../tools/measure_tsp_phone_boundaries.py#L360)

MFAの秒を48 kHzのフレーム番号に丸め、低エネルギー区間を語と音素の境界で分割した。標本ごとに語列・語・音素・低エネルギーの各範囲を記録する別計算でも、両しきい値・全3波形で各分類の標本数が一致した。録音の保存注釈と比較した境界差の最大値は `8.59×10⁻⁵ ms`。全波形で語5件と音素19件が得られた。両合成の語境界は一致し、合成間の音素境界差は最大約10 msで、最初は `tender` の `EH1` の終端に出た。両合成の発話計画は一致した。[保存注釈と合成間の照合](../runs/tsp-phone-boundaries-listening-07-20261122-a/summary.json)・[低エネルギー時間の配分](../runs/tsp-listening-gaps-20261122-repeat/artifacts/attribution.json)

| しきい値 | 波形 | 語内の音素（ms） | 語間（ms） | 語列の外（ms） | 合計（ms） |
| --- | --- | ---: | ---: | ---: | ---: |
| −35 dB | 録音 | 170 | 200 | 0 | 370 |
| −35 dB | 固定上流 | 150 | 0 | 0 | 150 |
| −35 dB | 再実装 | 155 | 0 | 0 | 155 |
| −45 dB | 録音 | 110 | 200 | 15 | 325 |
| −45 dB | 固定上流 | 80 | 0 | 0 | 80 |
| −45 dB | 再実装 | 80 | 0 | 0 | 80 |

主しきい値の録音−再実装差215 msのうち200 msは、予測どおり `soap` と `saves` の語間だった。両合成は同じ境界で語が接し、低エネルギー時間を `soap` の末尾の `P` に固定上流65 ms、再実装70 ms割り当てた。録音で同じ `P` に重なったのは20 ms。副しきい値でも録音の語間への割当は200 msで、波形の端点が広がると語列外の15 msも含まれた。語間ラベルには閉鎖や次の子音に向かう区間が含まれ得る。試聴では、ここが文中の間として聞こえるかを確認する。[分類の集計](../runs/tsp-listening-gaps-20261122-repeat/summary.json)

確認用07と従来の調整用の整列で各7判定、固定上流のTSP試験6件が通過した。別ディレクトリで語・音素への配分を再計算して各3判定を通過し、配分と要約がバイト一致した。独立検証では録音のミリ秒単位の保存境界が全件一致し、固定上流のRustプローブと2本の合成整列用PCM16が計215,054フレームでビット一致した。調整用の要約も保存済み結果と全項目で一致した。macOS 15.6.1 arm64、Python 3.14.4、MFA 3.4.3、`english_us_arpa v3.0.0`、Rust 1.94.1。5実行の82入力と70出力をサイズとSHA-256で照合した。採取物3,962,445バイトと、整列用の一時領域各約1.0 GiBをRTL9210B-CGに保存した。[調整用の回帰](../runs/tsp-phone-boundaries-calibration-20261122-listening-07-regression/manifest.json)・[別ディレクトリの配分](../runs/tsp-listening-gaps-20261122-repeat/manifest.json)・[独立検証](../runs/tsp-phone-boundaries-listening-07-20261122-verified/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648
../../.venv/bin/python tools/measure_tsp_phone_boundaries.py tsp-phone-boundaries-listening-07-new \
  --case cases/tsp-phone-boundaries-listening-07.json
../../.venv/bin/python tools/measure_tsp_listening_gaps.py tsp-listening-gaps-new tsp-phone-boundaries-listening-07-new
../../.venv/bin/python tools/verify_tsp_phone_boundaries.py tsp-phone-boundaries-listening-07-verified-new \
  tsp-phone-boundaries-listening-07-new tsp-phone-boundaries-calibration-20261122-listening-07-regression \
  --case cases/tsp-phone-boundaries-listening-07.json
```

## 確認用07の再開口と歯の乱流

確認用07の「soap」末尾の /p/ と「saves」語頭の /s/ について、唇の閉鎖、再開口、放射流量の時間差分、歯の乱流を48 kHzの出力フレーム上で照合した。事前の予測は、低エネルギーと判定した /p/ の時間の半分以上が唇の閉鎖に重なり、再開口後に /s/ の乱流が1 ms以上続くこと。固定上流と再実装の入力は先行計測の全長音声を作ったものと同じ。観測窓は650〜960 ms、閉鎖の主しきい値は0.0002 cm²とした。[事前登録](../cases/tsp-soap-saves-transition.json)

固定上流の `render::say` は英語G2Pから `plan_phrases` へ進み、女性の基準音高205 Hz、50 msから開始する計画、末尾300 msの条件で描画する。`stop_closure_delay` と `oral_gestures_into` を追い、/p/ は直前の母音からの着地遅延5 msを加え、目標接触時刻より22 ms前に唇を駆動する。唇の解放を19 ms先行させ、最低保持時間10 msと比較する。/s/ の主ジェスチャーは計画始端より8 ms前から作る。この式は両版の実際のジェスチャー区間に一致した。/p/ と /s/ の計画境界は792.015 ms。[発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[閉鎖遅延](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L712)・[調音ジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L822)

`HumanVoice::control` は声道形状を更新し、`HumanAirway::update_noise` は開いた最狭部の断面と歯までの距離から乱流源を登録する。内部96 kHzで `AirwayNetwork::compute_noise` が各枝の体積流量と面積からレイノルズ数を求め、しきい値を越えたときにフィルターを通した雑音を枝の圧力へ加える。口・鼻・壁の放射流量の時間差分（cm³/s²）は間引きと出力処理を経てPCMになる。観測点は内部2サンプルを進めた直後とし、乱流源が登録されたフレーム、乱流振幅が正になったフレーム、枝に注入された圧力（dyn/cm²）を記録した。[声道の乱流源登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[気道の乱流計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[観測用プローブ](../tools/upstream_tsp_closure_probe.rs)

| 観測 | 固定上流と再実装の共通時刻 |
| --- | ---: |
| 唇の面積が0.0002 cm²以下になった最初のフレーム | 33,970（707.708 ms） |
| 歯の乱流源の登録 | 37,952（790.667 ms） |
| 唇の再開口 | 38,208（796.000 ms） |
| 再開口後8 msの放射の絶対値ピーク | 38,345（798.854 ms） |
| 歯の乱流振幅が正となったフレーム | 38,400（800.000 ms） |
| 再開口後8 msのPCMの絶対値ピーク | 38,579（803.729 ms） |
| MFAによる /p/ と /s/ の境界 | 39,360（820.000 ms） |

固定上流65 ms・再実装70 msの /p/ の低エネルギー区間は、すべて唇が閉じていた。面積しきい値を0.005 cm²へ広げても、両実装の閉鎖・再開口は同じフレームだった。歯の乱流源は再開口の約5.33 ms前に登録され、振幅が正になるのは再開口の4 ms後で、MFAが割り当てた /s/ 始端の20 ms前だった。再開口後8 msのPCMピークは固定上流0.04355、再実装0.04977。放射ピークはそれぞれ約112,268、112,267 cm³/s²だった。区間の交差をフレームごとの計数、ピーク位置を配列の走査で照合した。[時刻とピークの実測](../runs/tsp-soap-saves-transition-20261122-repeat/summary.json)

実装間のPCMにはフレーム0からビット差があり、発話全体の最大絶対差は `fine` の二重母音内のフレーム17,257（359.521 ms）で0.70616だった。観測窓の先頭650 msでは口端流量と放射にすでに差があり、唇の最小断面の窓内最大差は約 `5.68×10⁻¹⁴ cm²`。/p/・/s/ の時刻の一致から音声全体の差を説明するには、先行する母音の声門・伝搬系列が必要になる。録音の200 msの語間については、聴取者が文中の間と判断した回答を待つ。[候補の状態](../runs/tsp-soap-saves-transition-20261122-repeat/artifacts/candidate-state.retained.csv)・[固定上流の状態](../runs/tsp-soap-saves-transition-20261122-repeat/artifacts/upstream-state.retained.csv)

研究ワークスペースと `/private/tmp` から通常CLIで出力した固定上流・再実装の各107,527 PCMフレームは、それぞれの保存版と一致した。観測用上流プローブと候補のPCMトレースも各通常PCMとビット一致した。2実行で各6判定と固定上流13試験を通過し、要約・PCM・抜粋など9出力がバイト一致した。ビルド、テストのログとプローブ実行ファイルには差があった。既存の `coat to` は8判定を通過し、要約・両PCM・状態系列・図の6出力が先行結果と一致した。macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1。3実行の387入力・40出力を照合し、採取物37,944,715バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-soap-saves-transition-20261122-a/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-soap-saves-transition-20261122-repeat/manifest.json)・[既存ケースの回帰](../runs/tsp-coat-to-closure-20261122-soap-saves-regression/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824
../../.venv/bin/python tools/measure_tsp_soap_saves.py tsp-soap-saves-transition-new
../../.venv/bin/python tools/measure_tsp_coat_to.py tsp-coat-to-closure-regression-new
```

## 確認用07の fine で声門の揺らぎをそろえる

確認用07の「fine」では、通常経路の固定上流と再実装でPCMの最大差が0.70616だった。同じ本文・女性体型で、固定上流のドリフト、周期のジッター、振幅のシマーをまとめて0にする対照を登録した。再実装のこの発話設定は3成分とも0。比較範囲は出力フレーム15,360〜20,015（320〜417 ms）で、開始から440 msまでは48 kHzの出力各点に対応する96 kHzの内部2サンプルを観測する。出力ゲインと初期調音姿勢は各実装の通常設定を使った。[事前登録](../cases/tsp-fine-source-variation.json)・[先行する子音観測](#確認用07の再開口と歯の乱流)

固定上流の `render::say` は英語G2Pと `plan_phrases` から `HumanVoice::render` へ進む。基準F0は女性205 Hz、初期F0は110 Hzで、制御ブロック毎に基準値へ向かう。 `ParametricGlottis::next` は圧差を平滑化し、音高ドリフトを32内部サンプルごとに更新する。位相は各内部サンプルで `F0 / (内部レート × 周期倍率)` だけ進む。位相が一周するとジッターとシマーを適用する。面積（cm²）で声門枝を更新してから、流量（cm³/s）と放射流量の時間差分（cm³/s²）を計算する。間引いた後、体型に応じたゲイン、DC除去、包絡によるピーク制限を経てPCMになる。固定上流の `engine` と `body_mix` はブロック処理、体型と気道の動作を検査する。[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L148)・[描画と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[観測差分](../tools/patches/upstream-tsp-fine-source-states.patch)

最初の試行では、研究版の調音計画を保存JSONからデシリアライズして観測器へ渡した。通常CLIとのビット差はフレーム56,228から発生し、全発話で1,407フレーム、最大 `2.91×10⁻¹¹` だった。通常CLIと同じ辞書と英語計画関数を観測器内で呼ぶと、各107,527フレームで両通常版の保存PCMにビット一致した。修正版は位相の循環距離 `min(|Δφ|, 1−|Δφ|)` も保存する。計測対象と閾値は初回の条件を使った。[初回の不合格](../runs/tsp-fine-source-variation-20261122-a/summary.json)・[研究版の観測器](../tools/candidate_tsp_fine_probe.rs)・[修正版](../runs/tsp-fine-source-variation-20261122-b/summary.json)

上流内の比較では、最初の内部サンプルからF0が約0.00493 Hz、位相が約 `5.14×10⁻⁸` 周期異なった。ゼロ条件の最初のF0 111.51530 Hzは、110 Hzから205 Hzへ時定数60 msで進む128内部サンプル分の式と一致した。声門面積と流量に初めて差が出たのは内部サンプル22,710（236.5625 ms）で、放射の時間差分には次のサンプル、Float32のPCMには出力フレーム11,378（237.042 ms）で現れた。番号は内部・出力とも0始まり。上流内で呼気ゲートと舌先Yは同じで、既定の上流と再実装の発話先頭には舌先と放射の差がすでにあった。[系列ごとの初出点](../runs/tsp-fine-source-variation-20261122-b/summary.json)

| 条件 | 再実装との最大循環位相差（周期） | 二重母音内のPCM最大絶対差 | 同じ区間のPCM RMS差 |
| --- | ---: | ---: | ---: |
| 上流の既定 | 0.14323 | 0.70616 | 0.25350 |
| 上流の揺らぎ3成分を0 | 0 | 0.05726 | 0.02250 |

揺らぎを0にすると、観測した42,240内部サンプルすべてのF0と声門位相が再実装と一致した。二重母音のPCM最大差は約92%減った。残った最大差のフレーム17,225では、間引き値どうしの差は約 `2.75×10⁻⁶ cm³/s²` で、DC除去後は固定上流−0.400853、再実装−0.458118だった。観測した区間では両方のリミッターが作動していない。女性体型に適用される上流の出力係数0.875を再実装のDC除去後の値に掛けると、二重母音の区間での残差は最大 `1.14×10⁻¹⁰` だった。先頭の舌先の差や、揺らぎを3成分個別に変更した場合の寄与は別に検証する。[体型によるゲイン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L280)・[観測列と独立計算](../runs/tsp-fine-source-variation-20261122-b/summary.json)

研究ワークスペースと `/private/tmp` から、各3判定、固定上流10試験、研究版11試験を通過した。全条件で、放射流量の差分の再計算、Kaiser窓の独立畳み込み、DC除去、リミッターと実装の出力を照合した。結果・声門・出力段・PCMなど15出力がバイト一致した。既存の `soap → saves` 回帰は6判定を通過し、要約と両PCM・抜粋など6出力を先行結果に照合した。macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1。初回不合格を含む4実行の539入力・76出力のサイズとSHA-256を照合し、採取物66,829,140バイトをRTL9210B-CGに保存した。[別ディレクトリの再実行](../runs/tsp-fine-source-variation-20261122-repeat/manifest.json)・[子音比較の回帰](../runs/tsp-soap-saves-transition-20261122-fine-regression/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824
../../.venv/bin/python tools/measure_tsp_fine_variation.py tsp-fine-source-variation-new
../../.venv/bin/python tools/measure_tsp_soap_saves.py tsp-soap-saves-transition-regression-new
```

## 確認用07の出力ゲインをそろえた通常描画

揺らぎ3成分を0にした固定上流の保存済みPCMを基準にし、再実装の `speech_voice.voice.output_gain` を `5.5×10⁻⁷` から `4.8125×10⁻⁷` にした。設定ファイルはこの1値だけを変えた。二重母音の出力15,360〜20,015フレーム（320〜417 ms）のPCM最大差が `1×10⁻⁶` 以下になり、内部状態の系列と間引き値は一致すると予測した。[事前登録](../cases/tsp-fine-output-gain.json)・[参照した音源変動の計測](../runs/tsp-fine-source-variation-20261122-repeat/summary.json)

固定上流の `render::say` が作る `HumanVoice` は、体型の尺度が0.9の成人女性に既定ゲインの0.875を掛ける。`HumanVoice::render` では内部96 kHzの放射を48 kHzに間引いてからゲインを掛け、25 HzのDC除去とピーク包絡・リミッターを通してFloat32のPCMを得る。研究版の `speech_voice` と `OutputStage::push` も同じ順序で、ゲインは声道や声門の更新に渡さない。候補の両条件の通常CLIを実行し、別の観測器で内部状態とPCMを照合した。上流の `body_mix`・`engine` と研究版のライブラリ試験を実行し、出力段は独立したKaiser窓の畳み込み、DC除去、包絡計算へ照合した。[上流の体型係数と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L280)・[研究版の出力段](../crates/vocal-core/src/output.rs#L105)・[計測CLI](../tools/measure_tsp_fine_gain.py)

両条件の `vocal-cli render-pcm` と観測器の各107,527フレームがビット一致した。内部215,054サンプルの舌先・呼気・声門・放射の系列と、間引き値は両条件でビット一致した。出力段の最初の差は出力フレーム0でのゲイン乗算後に入った。両条件とも全発話でリミッターの発動は0回。保持残数も全点で一致した。[段別の結果](../runs/tsp-fine-output-gain-20261122-repeat/summary.json)

| 揺らぎ0の上流との差 | 元のゲイン | 女性体型に合わせたゲイン |
| --- | ---: | ---: |
| 二重母音区間のPCM最大絶対差 | 0.05726472 | `1.4901161×10⁻⁸` |
| 同区間のPCM RMS差 | 0.02249908 | `4.41316×10⁻¹⁰` |
| 発話全体のPCM最大絶対差 | 0.05726472 | 0.00188851 |

二重母音の最大残差はフレーム15,861の隣接Float32値の差だった。ゲイン調整後の発話全体の最大差は、上流のPCMが0だったフレーム219（4.5625 ms）に現れた。全発話で差が `1×10⁻⁶` を超える最後のフレームは8,400（175 ms）。先行の内部観測では冒頭の舌先と放射に差があり、次の比較では初期舌先の座標だけを合わせて起点を調べられる。[通常ゲインの音声](../runs/tsp-fine-output-gain-20261122-repeat/artifacts/base.wav)・[女性体型に合わせた音声](../runs/tsp-fine-output-gain-20261122-repeat/artifacts/matched.wav)・[上流の音源対照](../runs/tsp-fine-source-variation-20261122-repeat/artifacts/upstream_zero.f32le)

研究ワークスペースと `/private/tmp` から各5判定、固定上流10試験、研究版11試験を通過した。要約、両PCM、観測系列を含む10出力がバイト一致した。ビルドやテストのログには差があった。内部系列は一致を確認してハッシュを両条件分記録し、公開する実体は1本とした。macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1。2実行の272入力と28出力のサイズとSHA-256を照合し、採取物72,963,714バイトをRTL9210B-CGへ保存した。[初回](../runs/tsp-fine-output-gain-20261122-a/manifest.json)・[別ディレクトリからの再実行](../runs/tsp-fine-output-gain-20261122-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_tsp_fine_gain.py tsp-fine-output-gain-new
```

## 確認用07の初期舌先と発話前の放射

確認用07の `FK64_08` で、揺らぎ0の固定上流とゲイン `4.8125×10⁻⁷` の候補を使った。候補の設定では `speech_voice.posture.tongue_tip_cm` の2座標だけを変更した。事前に、発話前50 msのPCM残差が `1×10⁻¹²` 以下、最初の非ゼロが上流と同じ出力フレーム2,439、変更前の最大差があったフレーム219では口端の寄与が壁より大きいと予測した。出力は48 kHzの107,527フレームで、位置は0始まり。内部状態は96 kHzで採取した。[事前登録](../cases/tsp-fine-initial-tip.json)

上流の `render::say` は発音列を計画し、`HumanVoice::new` が `ArticulatorBank::new` で顎・舌体の中立値と舌先の休止位置を初期化する。上流の `rest_tip` は、点 (6.45, 7.35) cm を顎の回転中心 (−2.5, 10.5) cm の周りに `−jaw / 9.84` rad回転し、舌体の中立位置からの変位のXに0.30、Yに0.35を掛けて加える。最初の制御更新より前に上流の構造体から読み出した舌先 (6.241412821929657, 6.810460479056529) cm は、顎と舌体の座標を入力にした独立式と一致した。変更前の候補は (6.45, 7.30) cm。[通常の発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[調音の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L79)・[休止位置の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L454)・[計測プローブ](../tools/upstream_tsp_rest_tip_probe.rs)

`HumanVoice::control` が顎と舌を含む輪郭を更新し、気道は目標断面へ補間する。 `AirwayNetwork::step` では、節点体積の変化を `−dV/dt` の流量源（cm³/s）として開いた隣接節点にも分配し、平滑化して通気に反映する。口端・鼻端・声道壁の放射流量を合計し、前サンプルとの差に96,000 Hzを掛けて放射信号（cm³/s²）を求める。計測では成分ごとに差分を取り、独立したKaiser窓FIRで間引き、ゲインと25 HzのDC除去を適用して合成前の寄与を出した。発話前にはピーク制限が作動せず、三成分の和は出力段の値と最大 `1.51×10⁻¹⁶` の差で一致した。[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[体積変化の処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L834)・[放射の差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1147)・[独立計算](../tools/measure_tsp_fine_tip.py)

| 観測値 | 変更前の候補 | 休止位置を合わせた候補 |
| --- | ---: | ---: |
| 発話前50 msのPCM最大絶対値 | 0.00188851 | 0 |
| 最初の非ゼロPCMフレーム | 0 | 2,439 |
| `fine` の二重母音での上流とのPCM最大絶対差 | `1.49×10⁻⁸` | 0 |
| 発話全体での上流とのPCM最大絶対差 | 0.00188851 | `2.33×10⁻¹⁰` |

固定上流の発話前50 msも全フレームで0だった。変更前のフレーム219（4.5625 ms）のPCMを成分別に追うと、口端が−0.001884979、鼻端が0、壁が `−3.53×10⁻⁶` で、口端がこのフレームの総振幅の約99.8%を占めた。候補の両条件で呼気ゲート、F0、声門位相は一致した。最初の状態差は内部サンプル0の舌先Yと口端流量にあり、壁面放射流量と声門前後の圧力差にサンプル1、声門流量にサンプル6で差が現れた。休止位置変更後の最初のFloat32のビット差はフレーム23,013で、差は隣接するFloat32値の1刻みだった。[段別の集計](../runs/tsp-fine-initial-tip-20261122-repeat/summary.json)・[休止位置での通常描画](../runs/tsp-fine-initial-tip-20261122-repeat/artifacts/resting-tip.wav)

初回は通常描画と状態採取の後、独立計算で列定義 `COLUMNS` のインポートが欠けて停止した。失敗記録と採取済みの11出力を保存した。インポートを追加した修正版を研究ワークスペースと `/private/tmp` で実行し、各6判定、事前予測3件、固定上流の `body_mix` 4試験・`engine` 6試験、研究版11試験を通過した。通常CLIと観測器の全PCMを照合し、2回の要約、PCM、計画、内部系列など7出力がバイト一致した。ゲイン対照の回帰も5判定を通過し、先行の要約とPCMなど10出力が一致した。macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。418入力と失敗分を含む49出力をサイズとSHA-256で照合し、採取物124,574,370バイトをRTL9210B-CGへ保存した。[初回失敗](../runs/tsp-fine-initial-tip-20261122-a/failure.json)・[修正版](../runs/tsp-fine-initial-tip-20261122-b/manifest.json)・[別ディレクトリからの再実行](../runs/tsp-fine-initial-tip-20261122-repeat/manifest.json)・[ゲイン対照の回帰](../runs/tsp-fine-output-gain-20261122-tip-regression/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/measure_tsp_fine_tip.py tsp-fine-initial-tip-new
../../.venv/bin/python tools/measure_tsp_fine_gain.py tsp-fine-output-gain-tip-regression-new
```

## 確認用07で上流既定の音源変動を適用

確認用07の女性体型、本文、調音計画、舌先の休止位置、出力ゲイン `4.8125×10⁻⁷` を保持し、候補のケースに `speech_voice.source_variation` を追加した。ドリフト5セント、周期ジッター0.00455、振幅シマー0.042。事前に、上流の通常描画との循環位相差が `1×10⁻¹⁰` 周期以下、全PCM最大絶対差が `1×10⁻⁶` 以下になると予測した。候補内では、呼気が立ち上がる前の内部サンプル0からF0と位相が変わると予測した。内部状態は冒頭440 ms、PCMは全107,527フレームを観測した。[事前登録](../cases/tsp-fine-source-defaults.json)・[休止位置を合わせた元のケース](../runs/tsp-fine-initial-tip-20261122-repeat/artifacts/resting-tip-case.json)

上流の `render::say` は女性の基準F0を205 Hzに設定し、`SourcePatch::f0` で音高を更新する。 `HumanVoice::apply_source` は `DEFAULT_SOURCE` のドリフト5セントと粗さ0.1を使い、ジッターを `0.0021 + 0.0245 × 粗さ`、シマーを `0.02 + 0.22 × 粗さ` として声門へ渡す。研究版の発話CLIには3値を個別指定する入口を加えた。省略したときは音源の設定が0のままになる。設定は共通の描画処理が、発話計画を進める前に既存の `ArticulatedVoice` の設定関数へ渡す。[上流の発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[既定の音源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L51)・[粗さからの換算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)・[研究版の入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L165)

`ParametricGlottis::next` は声門の圧力差（dyn/cm²）を平滑化し、32内部サンプルごとに3本のIIR（0.3、0.9、2.7 Hz）からドリフトを作る。IIRの極は `exp(−2πf / 3000)`。各帯域を1、1/2、1/3で重み付けして合計を1.4で割り、ドリフトのセント値から `F0 × 2^(cents / 1200)` を算出する。位相増分は `F0 / (96000 × 周期倍率)`。折り返しのサンプルは旧周期の倍率で進み、新周期の面積振幅にはそのサンプルから新しい倍率が入る。周期長と振幅は種777の乱数列から順に4個ずつ取り、各4個の和を中心化して使用する。ドリフトには別の種4242を使う。声門面積（cm²）を枝へ反映してから流量と放射の時間差分を計算する。上流の `body_mix`、`engine`、`lung_port` では体型、描画の継続、声帯開大と圧力の結合を確かめている。[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱数とドリフト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L188)・[声帯開大の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)

| 既定の固定上流とのPCM差 | 候補で揺らぎ0 | 上流と同じ揺らぎを指定 |
| --- | ---: | ---: |
| 発話全体の最大絶対差 | 0.66125020 | `1.16×10⁻¹⁰` |
| 二重母音での最大絶対差 | 0.66125020 | 0 |
| 二重母音でのRMS差 | 0.23588924 | 0 |
| 最初にビット差が出た出力フレーム | 11,378 | 53,463 |

上流と候補で、42,240内部サンプルのF0、位相、声門面積はすべて一致した。独立計算は揺らぎ0の保存F0に乱数とIIRで得た変調を掛け、両版と最大 `5.68×10⁻¹⁴ Hz` の差で一致した。両版とも位相の折り返しは90回、最初は内部サンプル830。周期倍率を反映した位相増分の最大誤差は `1.10×10⁻¹⁶` 周期、研究版の振幅倍率は独立計算と一致した。放射の時間差分、間引き、DC除去と最終PCMも独立計算で照合した。[詳細な集計](../runs/tsp-fine-source-defaults-20261122-final/summary.json)・[周期の境界と倍率](../runs/tsp-fine-source-defaults-20261122-final/artifacts/cycle-boundaries.csv)

候補内では、揺らぎの指定でF0と位相が内部サンプル0から変わった。呼気ゲートは両条件で一致した。差は内部サンプル22,710で声門面積と流量、22,711で放射へ達した。固定上流との比較では、観測した系列の最初の微小差は内部サンプル4,879の声門流量の約 `6.31×10⁻³⁰ cm³/s` で、4,880の壁面放射と放射の時間差分にも差が現れた。全長の最大PCM差は出力フレーム96,435の `1.16×10⁻¹⁰`。内部状態の照合は440 msまでなので、この出力フレームに対応する声道内の系列は未採取。[固定上流と候補の段別差](../runs/tsp-fine-source-defaults-20261122-final/summary.json)・[通常CLIの音声](../runs/tsp-fine-source-defaults-20261122-final/artifacts/source-defaults.wav)

研究ワークスペースと `/private/tmp` で、通常の `vocal-cli inspect` と `render-pcm` を使った。4実行とも各8判定（事前予測3件を含む）と固定上流13試験・研究版11試験を通過した。初回の後、周期の折り返しが0回なら最初の位置を欠測として保存する処理を加えた。全4実行で要約、通常PCM、観測系列、周期表など10出力がバイト一致した。揺らぎ設定を省いた初期舌先ケースの回帰は6判定を通過し、先行の要約・PCM・内部系列など7出力が一致した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。5実行の717入力・68出力をサイズとSHA-256で照合し、採取物61,208,846バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-fine-source-defaults-20261122-a/manifest.json)・[最終再実行](../runs/tsp-fine-source-defaults-20261122-final/manifest.json)・[初期舌先の回帰](../runs/tsp-fine-initial-tip-20261122-source-defaults-regression/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456
../../.venv/bin/python tools/measure_tsp_fine_source_defaults.py tsp-fine-source-defaults-new
CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_tsp_fine_tip.py tsp-fine-source-defaults-tip-regression-new
```
