# 確認話者FLでF2の費用が0になる条件

## 読解と比較方法

第57版と同じ女性10名・男女19名の参照と、学習側の39位置・2値を使う。確認用の女性FLで、固定上流の録音注釈に `EH1` がある辞書順先頭6録音を採った。録音と合成の強勢付き `/ɛ/` の有限F2を別々に集約し、同じ参照を通したFKの保存結果と比較する。 [事前登録](../cases/tsp-f2-pooled-reference-held-fl.json)・[第57版の介入](tsp-f2-pooled-reference-sweep.md)

| 固定上流の関数 | 入力と観測点 |
| --- | --- |
| `compare::tsp::run`、`say_all`、`align_synth`、`measure_pair` | FLの文IDを上流のG2Pに通し、女性の合成をレンダーする。MFA整列と録音の既存注釈を使い、編集距離から同じIPAの音素を対応させる。 |
| `Sig::formants` と `values` | 48 kHzを12 kHzに間引き、音素の35、50、65%を中心にした25 msの窓から女性用12次LPCでF2を求める。採れた窓のHz中央値を音素値とし、強勢を揃えた `/ɛ/` の有限F2が3件以上あればHz中央値の `log2` を使う。 |
| `held_out`、`score`、`reference` | FLは末尾Lの確認側。固定した女性のみ・男女の学習参照を使い、中心・残差・MAD・評価幅を第57版の観測結果と照合する。 |
| `costs`、`fold`、`a_missing_measurement_has_no_cost` | 女性の参照中心と確認値の絶対差を評価幅で割り、1を引いた値の非負部分を費用として使う。幅の内側、外側、欠測を区別し、`formants` 欄に診断を出す。 |
| `over_sets` | 通常の上流報告では確認用話者ごとの合成値を性別ごとに集約する。本比較の観測単位はその集約前の確認話者別の文集合。 |

FL合成で男女の参照を使っても正の費用が出る介入があると予測した。また、男女をまとめると女性のみと同数以上の費用0の条件が生じ、録音側の最大変動が小さくなると予測した。固定上流の録音計測と、保存済みの参照にFLの中央値を通す独立計算を行う。 [固定上流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)・[計測入口](../tools/measure_tsp_f2_pooled_reference_held_fl.py)

## 実測

FLの6録音は録音側・合成側で強勢付き `/ɛ/` の有効F2が各10件だった。Hz中央値は録音が2,130.08 Hz、合成が2,043.75 Hz。録音の10件は元WAVから独立に再計算し、最大差は `2.02e-11 Hz` で採択の有無も一致した。2コホートの基準と介入156条件で学習参照は第57版と一致し、FLの診断費用は上流と独立計算で一致した。 [録音と合成の対応音素](../runs/tsp-f2-pooled-reference-held-fl-20261123-a/artifacts/collection/native.json)・[全介入の診断](../runs/tsp-f2-pooled-reference-held-fl-20261123-a/summary.json)

| 確認話者と区分 | 女性参照で費用0 | 男女参照で費用0 |
| --- | ---: | ---: |
| FK・録音 | 0 / 78 | 9 / 78 |
| FK・合成 | 64 / 78 | 78 / 78 |
| FL・録音 | 0 / 78 | 8 / 78 |
| FL・合成 | 78 / 78 | 78 / 78 |

FL合成側で正の費用が出るという予測は外れた。幅の上端に最も近い条件は、`FA01_03` の対応音素列の13番を822.19 Hzにしたときだった。FL合成の値は、女性参照の上端より0.00326オクターブ、男女参照の上端より0.04004オクターブ内側にあった。録音と合成のF2中央値には86.33 Hzの差がある。 [固定上流の79条件](../runs/tsp-f2-pooled-reference-held-fl-20261123-a/artifacts/native.json)

FL録音側の最大絶対変動は女性参照の0.54524から男女参照の0.10408に減った。ここでの比較は確認話者別の文集合を単位にしている。次はFKとFLの合成値を上流の `over_sets` に通し、確認女性全体の合成F2の診断が話者別の診断とどう対応するか照合する。

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、MFA 3.4.3。外部ディスク上にFLの選定録音を展開し、音素対応とF2を固定上流で計測した。同じディスクで第57版と同じ観測入口をビルドし、固定した78条件に通した。録音のハッシュ、音素対応、参照・診断費用、観測パッチ、ログを保存した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=3221225472 \
  ../../.venv/bin/python tools/measure_tsp_f2_pooled_reference_held_fl.py \
  tsp-f2-pooled-reference-held-fl-new
```

研究ワークスペースと `/tmp` からの再実行はともに4判定と上流6試験を通過した。録音のハッシュ一覧、音素対応、固定入力、上流出力、計測要約を含む8出力がバイト一致した。計測入口を共用する学習女性10名の回帰は9出力が一致した。 [再実行](../runs/tsp-f2-pooled-reference-held-fl-20261123-repeat/manifest.json)・[学習側の回帰](../runs/tsp-f2-training-reference-ten-speakers-20261123-fl-regression/manifest.json)
