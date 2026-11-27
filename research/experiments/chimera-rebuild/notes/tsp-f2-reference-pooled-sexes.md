# 男女の学習残差をまとめたときのTSPのF2参照幅

## 読解と事前登録

第54版のFA〜FJの録音F2、第55版の `FD19_10` の対応音素列の15番と差し替え値2,009.78764 Hz、確認用FKの録音・合成のF2を固定した。追加する男性学習話者はMA、MB、MC、MD、MF、MG、MH、MI、MJの9名。固定上流のTSP注釈で `EH1` がある録音を話者ごとに辞書順で6件選んだ。女性10名、女性10名と男性4名、女性10名と男性9名のそれぞれで無介入と同じ1件の介入を比較する。[事前登録](../cases/tsp-f2-reference-pooled-sexes.json)・[第55版の固定入力](../runs/tsp-f2-reference-centre-width-20261123-repeat/artifacts/inputs.json)

| 固定上流の関数 | 入力と処理順 |
| --- | --- |
| `compare::tsp::run`、`load_utts`、`say_all`、`align_synth` | 録音IDと注釈を読み、文IDと性別の組でレンダーし、固定MFA設定で合成音素の秒区間を得る。 |
| `measure_pair`、`match_phones`、`Sig::formants` | 音素列を編集距離で整列して同じIPAを対応させる。48 kHz録音を12 kHzに間引き、音素内35、50、65%を中心とする25 ms窓を男性用14次LPCで処理する。採択できた窓のF2のHz中央値を保存する。録音側の対応音素の強勢は合成側に揃える。 |
| `score`、`held_out`、`values` | 末尾K・Lの確認用話者を学習集合から分ける。強勢付き `/ɛ/` の有限F2が3件以上ある話者を使い、Hz中央値を `log2` にする。 |
| `reference` と `mad_sd` | 指定の性別で有効話者が5名以上あれば参照中心を作る。各話者の `log2(Hz)` 値から同性の中心を引く。有限な残差を男女から1列に集め、その中央値からの絶対偏差の中央値を1.4826倍し、0.07オクターブを下限にして費用の幅を定める。性別内MADも診断に残す。 |
| `costs`、`fold`、`a_missing_measurement_has_no_cost` | FKの確認値と女性中心の絶対差を共通幅で割り、1を引いた値の非負部分を費用とする。欠測はNaNのまま評価から外れる。 `formants` は診断群に入る。 |

男性4名では男性中心が欠測となり、追加された男性の測定は幅に寄与しないと予測した。男性9名では女性の中心と女性内MADを維持したまま評価幅が変わる条件があり、FK録音側の費用変動が小さくなると予測した。上流の参照集約の直前と直後を保存し、録音のF2と集約後の差を独立に照合する。[固定上流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)・[観測コード](../tools/upstream_tsp_f2_training_reference_probe.rs)・[独立集計](../tools/measure_tsp_f2_reference_pooled_sexes.py)

## 実測

男性54録音から有効なF2を69件取得した。話者別の支持数はMA 9、MB 7、MC 9、MD 7、MF 7、MG 8、MH 6、MI 6、MJ 10。男性用14次LPCで録音WAVから独立に測り直した最大差は `2.19e-10 Hz` で、採択の有無も一致した。[対応音素](../runs/tsp-f2-reference-pooled-sexes-20261123-a/artifacts/collection/native.json)・[録音のハッシュ](../runs/tsp-f2-reference-pooled-sexes-20261123-a/artifacts/collection/recordings.json)

| 参照に使う学習話者 | プール残差数 | 評価幅（無介入 → 介入、オクターブ） | FK録音費用（無介入 → 介入） | FK合成費用（無介入 → 介入） |
| --- | ---: | --- | --- | --- |
| 女性10名 | 10 | 0.10027 → 0.07000 | 0.24257 → 0.87292 | 0 → 0.02291 |
| 女性10名と男性4名 | 10 | 0.10027 → 0.07000 | 0.24257 → 0.87292 | 0 → 0.02291 |
| 女性10名と男性9名 | 19 | 0.11706 → 0.10677 | 0.06433 → 0.22788 | 0 → 0 |

男性4名にはそれぞれ有効F2があった。男性中心を作る話者数の下限が5名なので、男性の残差は4名とも非有限となった。男性9名では男性中心が10.63994 `log2(Hz)`、男性内の補正MADが0.16419オクターブで、両方とも女性FDの介入中に一定だった。女性中心はどのコホートでも10.93027から10.93678 `log2(Hz)`、女性内の補正MADは0.10027から0.06384オクターブへ同じように動いた。上流の共通幅は、中心からの符号付き残差を19件まとめた補正MADから求めた。[6条件の残差と診断](../runs/tsp-f2-reference-pooled-sexes-20261123-a/summary.json)

男性9名を加えると、介入後も評価幅は0.07の下限を上回った。FK録音側の費用増分は0.63034から0.16354に約74%減り、合成側は両方の状態で費用0となった。事前予測3件を満たした。今回は各話者6録音から構成した19話者に対する1位置の比較。次は第54版と同じ39位置・2値を使い、この変化がどこまで再現するかを確認できる。[上流計算](../runs/tsp-f2-reference-pooled-sexes-20261123-a/artifacts/native.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、MFA 3.4.3。上流の一時コピーを使い、録音の展開、MFA整列、試験ビルドをRTL9210B-CGで実行した。録音のハッシュ、対応音素、固定入力、参照集約と診断費用、観測用パッチと実行ログを保存した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=3221225472 \
  ../../.venv/bin/python tools/measure_tsp_f2_reference_pooled_sexes.py \
  tsp-f2-reference-pooled-sexes-new
```

研究ワークスペースと `/tmp` からの再実行は、各4判定と上流6試験を通過した。上流出力と独立集計は6条件の数値308点と欠測状態で一致した。再実行ではハッシュ一覧、音素対応、設定、上流出力、要約を含む8出力がバイト一致した。共有した録音の計測入口と参照コードは女性10名の回帰も通過し、上流出力と要約が元の記録とバイト一致した。[再実行](../runs/tsp-f2-reference-pooled-sexes-20261123-repeat/manifest.json)・[女性10名の回帰](../runs/tsp-f2-training-reference-ten-speakers-20261123-pooled-regression/manifest.json)
