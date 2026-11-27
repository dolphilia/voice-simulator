# FK61_01の唇前端のx座標差を追う

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。女性体型の同じ発話で、描画前と最初の体積流量差を含む制御境界の直後を観測する。測定線45・46の番号は0始まり。 [事前登録](../cases/tsp-fk61-lip-front-origin.json)・[先行する口端断面の観測](tsp-fk61-lip-area-origin.md)

## 読解と比較条件

固定上流の通常発話では、`HumanVoice::new` が中立の調音を `HumanAirway::apply` へ渡して気道を初期化し、描画中には `control` から同じ幾何を更新する。 `HumanVocalTract::compute` は唇の横方向の広がりから前端のテンプレート座標を決め、体型の変換 `p` を通し、唇の突出量を足して唇の前端を作る。さらに上下で異なる水平・垂直のずれを加え、輪郭のベジェ曲線と前方の光線を作る。下唇が歯の側に引き込まれる場合は、前方の光線の床と接触上限も更新する。 [上流の発話初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L274)・[唇前端と輪郭](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L805)・[体型の変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L695)

研究版の `ArticulatedVoice` から `TractController` を介して `SagittalModel::compute_into` に進み、`lips` が輪郭を作る。体型の変換は `BodyParameters::point` にあり、前方のテンプレートx座標 `x > 0.5` に対する体型スケールを掛ける前の式は以下の2通り。唇前端への入力はこの範囲に入るので、今回の試験版では `lips` の唇前端1箇所だけを固定上流の式で評価する。通常の発話ケースを標準版と試験版のCLIに渡す。 [研究版の体型変換](../crates/vocal-core/src/anatomy/body.rs#L64)・[研究版の唇輪郭](../crates/vocal-core/src/anatomy.rs#L497)・[試験版の差分と観測](../tools/tsp_fk61_lip_front_observation.py)

| 実装 | スケール前のx座標 |
| --- | --- |
| 固定上流 | 0.5 + (x − 0.5) × 0.86 |
| 研究版 | x − (x − 0.5) × 0.14 |

前方の6本の測定線は、歯の位置から作る始点と、唇端に依存する終点の間に置く。x座標はcm。唇の接触上限は、唇端から測定線までの後方への距離を `depth` とすると、歯への引き込みがない姿勢では `aperture + depth²/(1.2·scale)` cm。光線と接触上限の小さい値が補正後の隙間になる場合を観測する。隙間、唇の幅、歯の位置を使い、唇の楕円面積と歯列側の面積を混合する。上流の連続性試験は、唇を歯の側へ動かしたときの面積の跳びを照合する。研究版の補間試験は目標長と開口の更新を照合する。 [上流の前方測定線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1051)・[上流の接触上限](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1165)・[研究版の接触上限](../crates/vocal-core/src/anatomy/contact.rs#L60)・[連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L236)・[補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 実測

描画前の開口・突出・広がり・唇歯音の操作値は両者とも `[0.7, 0.2, 0.5, 0.0]`、体型スケールは0.9、唇前端のテンプレートxは8.21 cmだった。唇前端の経路での最初の差は、体型変換のスケール前に現れた。2つの式を独立に評価すると固定上流は7.1306 cm、標準研究版は7.130600000000001 cmとなり、隣り合う倍精度値に丸められた。試験版の自然な発話入口でもこの差の取り除きを確認した。 [再計算と採取値](../runs/tsp-fk61-lip-front-origin-20261123-repeat/summary.json)

| 描画前の値 | 固定上流 | 標準研究版 | 試験版 |
| --- | ---: | ---: | ---: |
| 体型変換後の基準x［cm］ | 6.417540000000001 | 6.417540000000002 | 6.417540000000001 |
| 下唇端のx［cm］ | 6.363540000000001 | 6.363540000000002 | 6.363540000000001 |
| 測定線45の中央x［cm］ | 5.891544000000001 | 5.8915440000000014 | 5.891544000000001 |
| 測定線46の中央x［cm］ | 6.036876000000001 | 6.036876000000001 | 6.036876000000001 |
| 測定線46の補正後の隙間［cm］ | 0.7288049712 | 0.7288049712000005 | 0.7288049712 |
| 口端セルの平均面積［cm²］ | 1.3749486460641938 | 1.3749486460641942 | 1.3749486460641938 |

測定線45では、下唇端の位置が前方の測定範囲を介して中央xに伝わった。測定線46では中央xが同じ値に丸められ、下唇端までの水平距離が変わった。接触上限は光線の隙間より小さく、その上限の差が補正後の隙間と面積に伝わった。試験版の描画前の両測定線の面積と口端セルは固定上流と一致した。制御更新後のフレーム1985では、体型変換の2式が同じ値を返し、3条件の口端セルの平均面積と最小面積が一致した。 [測定線と接触上限の独立計算](../runs/tsp-fk61-lip-front-origin-20261123-repeat/summary.json)

| 比較 | 最初のPCM差のフレーム | 異なるフレーム数 | 最大絶対差 |
| --- | ---: | ---: | ---: |
| 固定上流と標準版 | 1989 | 2257 | 1.86265×10⁻⁹ |
| 固定上流と試験版 | 1987 | 2309 | 1.86265×10⁻⁹ |
| 標準版と試験版 | 1987 | 738 | 1.45519×10⁻¹¹ |

PCMの最初の差が後ろへ動くという予測は外れた。通常CLIと観測器は各条件の全116,132フレームで一致した。フレーム1985で長さの目標は固定上流0.4667793926043813 cm、研究版の両条件0.46677939260438106 cmだった。同時刻の口腔の開始位置は一致し、軸上の累積位置は測定線31で初めて分かれた。次にこの位置の前後の測定線中央から累積距離の計算を追う。残った長さ差が気道と波形に及ぼす影響は未検証。 [フレーム1985の観測](../runs/tsp-fk61-lip-front-origin-20261123-repeat/artifacts/trial.jsonl)

## 再実行

標準版と試験版のRustビルドはRTL9210B-CG上の一時チェックアウトに置く。実行ごとの観測、PCMハッシュ、試験版のPCMと比較結果を保存する。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の再実行で各3判定、上流の唇歯音連続性試験、試験版の補間試験が通過した。各条件の座標観測3ファイル、試験版PCM、PCMハッシュ、要約の6出力がバイト一致した。 [最初の実行](../runs/tsp-fk61-lip-front-origin-20261123/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-fk61-lip-front-origin-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_lip_front_origin.py fk61-lip-front-origin-new
```
