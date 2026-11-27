# 学習側のF2を1件ずつ差し替えたときの参照の感度

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第52版の音素対応から学習女性FA〜FEの強勢付き `/ɛ/` の有効なF2を39件取り出す。各位置だけを先行の `again` の値822.19 Hzと2,009.79 Hzに替える。39件×2条件の数値対照で、確認用FKの録音と合成のF2は既定のままにする。差し替え値は別途算出した数値であり、学習話者の再発声を伴わない。[事前条件](../cases/tsp-f2-training-reference-sensitivity.json)・[固定した音素対応](tsp-again-f2-term-effect.md#実測)

| 固定上流の処理 | 参照に使う状態と観測点 |
| --- | --- |
| `crates/chimera-cli/src/compare/tsp.rs` の `term_defs` と `values` | `F2 ɛ` を指定し、強勢付きの有限F2を話者ごとに集める。件数3以上ならHz中央値の `log2` を保存する。今回は保存済みの対応済みトークンからこの項目だけを再構成する。 |
| `reference`、`mad_sd`、`spread_floor` | 同性学習話者5名以上の評価値から中心を取る。同性の中心からの残差のMADを `1.4826` 倍し、0.07オクターブを下限にして評価の単位とする。中心と幅は別々に観測する。 |
| `costs` と `a_missing_measurement_has_no_cost` | 固定した確認側値を参照へ通し、`max(0, |x − centre| / spread − 1)` を計算する。上流の試験で欠測の扱いを確認する。F2は診断欄に属する。 |

有限値の代入では支持数が維持される。同じ位置で代入値を増やすと、話者中央値と参照中央値は同じか上がると予測した。MADは中心以外の話者の順序にも依存するため、参照中心が等しくても評価の幅を変える位置があると予測した。既定の5話者の中心は1,912.54 Hz相当、幅は0.083516オクターブ。各介入の前に他の全値を初期値へ戻す。

## 実測

| 差し替えた話者 | 対象トークン | 話者中央値が変化 | 参照中心が変化 | 参照中心を保って幅が変化 |
| --- | ---: | ---: | ---: | ---: |
| FA | 9 | 5 | 0 | 5 |
| FB | 7 | 7 | 0 | 7 |
| FC | 9 | 9 | 5 | 0 |
| FD | 7 | 7 | 4 | 0 |
| FE | 7 | 7 | 7 | 0 |
| 計 | 39 | 35 | 16 | 12 |

同じ位置の2つの代入値の比較で、28件で参照の幅とFKの録音・合成のF2診断費用が変わった。そのうち12件では参照中心が同じだった。たとえば `FA01_03` の対応音素列の13番では参照中心が1,912.54 Hz相当のまま、幅が0.082026から0.083516オクターブへ変わり、FKの録音側費用は0.16552から0.14472、合成側は0.30575から0.28245へ下がった。支持数は全78条件で維持され、代入値を上げたときに参照中心が下がった例は0件だった。[全対照と費用](../runs/tsp-f2-training-reference-sensitivity-20261123-repeat/summary.json)

全78条件で参照中心は1,839.30〜1,922.66 Hz相当、MADを1.4826倍した値は0.019303〜0.094805オクターブだった。8条件は0.07の下限を使った。FKのF2診断費用は録音側が0〜0.47453、合成側が0.04942〜1.04229だった。第52版の基準値は録音側0.14472、合成側0.28245。差し替えを終えて元の値へ戻した場合も基準と一致した。ここで測ったのは5名の学習女性で構成した部分集合の感度であり、次は学習話者を増やして同じ差し替えに対する参照の感度がどう変わるかを調べる。[固定上流の数値](../runs/tsp-f2-training-reference-sensitivity-20261123-repeat/artifacts/native.json)・[使用したF2一覧](../runs/tsp-f2-training-reference-sensitivity-20261123-repeat/artifacts/inputs.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4。上流CLIの一時コピーに観測入口を加え、前回の対応音素からF2集約に必要な値を使った。初回は `include!` 先の内側文書コメントが `E0753` となってビルド前半で停止した。通常のコメントへ直し、初回の入力と修正後がバイト一致することを確認した。[初回のビルドログ](../runs/tsp-f2-training-reference-sensitivity-20261123-a/artifacts/cargo.log)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_f2_training_reference_sensitivity.py \
  tsp-f2-training-reference-sensitivity-new
```

研究ワークスペースと `/tmp` から各3判定、上流6試験を通過した。入力・上流出力・要約・パッチの4出力がバイト一致し、差は実行ログ2点だった。上流CLIの観測入口の準備を共用した第52版の回帰では5出力が一致した。成果はRTL9210B-CGに保存した。[修正後](../runs/tsp-f2-training-reference-sensitivity-20261123-resolved/manifest.json)・[再実行](../runs/tsp-f2-training-reference-sensitivity-20261123-repeat/manifest.json)・[第52版の回帰](../runs/tsp-again-f2-term-effect-20261123-training-regression/manifest.json)
