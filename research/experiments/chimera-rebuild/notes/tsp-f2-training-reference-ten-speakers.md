# 学習女性5名と10名のF2診断の感度を比べる

## 読解と事前登録

上流版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。元の学習女性FA〜FEの強勢付き `/ɛ/` 39件、確認用FKの録音・合成のF2、差し替え値822.18949 Hzと2,009.78764 Hzは第53版の実行から固定した。追加するFF〜FJは、上流の収録注釈で `EH1` を含む録音IDを話者ごとに辞書順で並べ、先頭6件を選んだ。F2や整列結果を見て録音IDを選び直す手順は設けていない。[事前登録](../cases/tsp-f2-training-reference-ten-speakers.json)・[固定入力](../runs/tsp-f2-training-reference-sensitivity-20261123-repeat/artifacts/inputs.json)

| 上流の関数 | 入力・更新の順序・観測点 |
| --- | --- |
| `compare::tsp::run`、`load_utts`、`say_all`、`align_synth` | 録音IDから話者と文を取得する。文IDと性別の組で発話をレンダーし、G2Pの発音辞書と固定MFA設定で秒単位の合成音素境界を得る。 |
| `measure_pair`、`match_phones`、`measure`、`Sig::formants` | 48 kHz録音と合成を読み、編集距離の整列から同じIPAの組を選ぶ。各音素の35、50、65%を中心とする25 ms窓で、12 kHzに間引いた波形から女性用の12次LPCの極を求める。F1は1,300 Hz未満かつ帯域幅500 Hz未満の最初の候補。F2はF1より200 Hzを超えて上で3,500 Hz未満の最初の候補。採れた窓のF2をHzで中央値にし、対応した録音側に合成側の強勢ラベルを移す。 |
| `held_out`、`term_defs`、`values` | 末尾K・Lの話者を確認用に分ける。強勢付き `/ɛ/` の有限F2が3件に達した話者は、Hzで中央値を取り `log2` に変換する。 |
| `reference`、`mad_sd`、`spread_floor`、`costs` | 同性の話者値が5名以上あれば中央値を中心にする。同じ性別の中心からの残差を集め、残差中央値からの絶対偏差の中央値を1.4826倍する。今回は女性だけの残差を使い、0.07オクターブの下限を適用する。FKの費用は `max(0, |値 − 中心| / 幅 − 1)`。 |
| `matching_keeps_only_the_same_phones_in_order`、`a_missing_measurement_has_no_cost` | 音素の一致順と、欠測を費用0として扱わない条件を確認する。 |

同じ39位置に同じ2値を1件ずつ代入する。各コホートの無介入時からの最大絶対差を比較し、参照中心とFKの録音・合成の費用は10名で小さくなると事前に予測した。MADの下限や費用のゼロ境界が変われば、中心と費用が別の方向に動き得る。機構の合否は第53版の再現、支持数、固定上流とPythonの1e-10以内の一致、元の値を戻したときの基準の復元で判定する。[固定上流の比較コード](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)・[観測入口](../tools/upstream_tsp_again_f2_term_probe.rs)・[独立計算](../tools/measure_tsp_f2_training_reference_ten_speakers.py)

## 実測

追加30録音から有効F2を37件取得した。FF、FG、FH、FI、FJの支持数は順に7、8、6、6、10件。追加分も含めた10名全員が最小支持数を満たした。録音WAVから音素ごとのF2をNumPy/SciPyで再計算した最大差は `7.89e-11 Hz` で、採択の有無も一致した。

| 観測値 | 学習女性5名 | 学習女性10名 |
| --- | ---: | ---: |
| 無介入の参照中心（Hz相当） | 1,912.54 | 1,951.36 |
| 無介入の参照幅（オクターブ） | 0.08352 | 0.10027 |
| 参照中心の最大絶対差（オクターブ） | 0.05633 | 0.03197 |
| 参照幅の最大絶対差（オクターブ） | 0.01352 | 0.03027 |
| FK録音側の診断費用の最大絶対差 | 0.32981 | 0.63034 |
| FK合成側の診断費用の最大絶対差 | 0.75983 | 0.11591 |
| 2値間で参照中心が変わった位置 | 16 | 17 |
| 2値間で中心を保ち幅が変わった位置 | 12 | 12 |
| 幅に0.07の下限が効いた条件 | 8 / 78 | 9 / 78 |

最大絶対差は、それぞれのコホートの無介入時を起点にした。参照中心の最大変動は約43%減った。FKの費用が両側で安定するという予測は外れ、録音側は最大変動が約1.91倍、合成側は約85%減だった。追加した話者のF2分布と話者数が同時に変わる比較で、他の録音の選び方や男女の残差をプールする参照への一般化は次の比較課題とする。[全介入と予測の判定](../runs/tsp-f2-training-reference-ten-speakers-20261123-a/summary.json)

録音側費用の最大変動は、5名と10名の両方で `FD19_10` の対応音素列の15番を2,009.79 Hzへ差し替えたときに出た。同じ最大値を示した位置は各4件。10名では中心の変化が0.00651オクターブに対し、参照幅は0.10027から下限の0.07000に縮み、録音側費用が0.24257から0.87292へ上がった。同じ条件でFKの合成側費用は0.02291だった。第55版で上流の保存値を照合し、この箇所に記していた0を訂正した。FKの合成側の無介入値は、5名では0.28245、10名では0だった。次の対照はこの1位置で中心のみ、幅のみを差し替え、同じ録音・合成値を使って費用の変化とゼロ境界を比較できる。[追加録音の音素対応](../runs/tsp-f2-training-reference-ten-speakers-20261123-a/artifacts/collection/native.json)・[固定上流と同じ78条件](../runs/tsp-f2-training-reference-ten-speakers-20261123-a/artifacts/native.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。第52版と同じMFA環境とモデルを用いた。追加30録音の元アーカイブと個別WAVのSHA-256、音素対応、使ったF2、上流CLIの観測用パッチとログを保存した。展開とビルドの一時ファイルはRTL9210B-CG上の実行時ディレクトリで処理し、成功後に破棄した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=3221225472 \
  ../../.venv/bin/python tools/measure_tsp_f2_training_reference_ten_speakers.py \
  tsp-f2-training-reference-ten-speakers-new
```

研究ワークスペースと `/tmp` からの再実行は、各4判定と上流6試験を通過した。WAVのハッシュ一覧、音素対応、設定、上流出力、要約を含む9出力がバイト一致した。既存入口の5名対照と `again` の回帰でも、上流出力と要約が元の記録とバイト一致した。[再実行](../runs/tsp-f2-training-reference-ten-speakers-20261123-repeat/manifest.json)・[5名対照の回帰](../runs/tsp-f2-training-reference-sensitivity-20261123-ten-regression/manifest.json)・[againの回帰](../runs/tsp-again-f2-term-effect-20261123-ten-regression/manifest.json)
