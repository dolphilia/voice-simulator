# seems の初期舌先と発話冒頭の放射

固定上流の `seems` と研究版でドリフト・ジッター・シマーを0にした状態から比較する。前回は1.1525〜1.1775秒のLPC入力300標本と高域LPC極が一致した。冒頭は舌先Yと口端流量が第0内部標本、圧差が第1内部標本、PCMが第0フレームから異なった。過去の別発話 `fine` や調整用の男女2例では、初期舌先を休止位置へ移すと発話前PCMが無音に揃った。今回は `seems` で初期セルの実効面積・最小面積も照合し、音源を揃えた全PCMに残る差を測る。[事前登録](../cases/tsp-seems-initial-tip.json)・[先行のシマー比較](tsp-seems-amplitude-shimmer.md)・[fineの休止舌先](tsp-active-duration-original.md#確認用07の初期舌先と発話前の放射)

## 上流の読解

- `crates/chimera-cli/src/render.rs` の `say` が辞書と発話を計画し、`crates/chimera/src/voice/human_voice.rs` の `HumanVoice::new` が最初の声道を作る。`control/articulators.rs` の `ArticulatorBank::new` は `NEUTRAL` の姿勢・目標・速度0から始め、自由舌先では位置と目標を `rest_tip` に揃える。`anatomy/human.rs` の `rest_tip` は歯裏の点を顎の軸の周りに `−jaw / 9.84` rad回し、舌体の中立位置からのX・Y偏差に0.30と0.35を掛けて加える。位置は成人男性テンプレート上のcm。
- `HumanVoice::new` は初期姿勢を `HumanAirway::apply`（`dt = 0`）に渡す。`voice/human_airway.rs` の `commit` は姿勢から矢状面を計算して咽頭・口腔に再サンプリングし、セル長（cm）、実効面積と最小面積（cm²）を設定する。`AirwayNetwork::snap_to_targets` は現値を目標へ移し、`max(面積, 下限面積) × セル長` の体積を保存する。最初の制御更新以後は、`begin_block` が面積とセル長を目標に近づける勾配を求め、96 kHzで `step` が `−ΔV / Δt` を容積速度（cm³/s）として気道へ与える。`step` は口端・鼻端・壁の流量を合計して時間微分し、48 kHzでは間引き・DC除去・レベル調整を通る。
- 研究版の `crates/vocal-core/src/voice.rs` の `for_speech_with_body` は、`articulators.rs` の `ArticulatorBank::new` へ入力姿勢を渡す。初期座標は可動域内に収め、速度0の現在値・目標になる。`for_tract` はこの姿勢で断面を確定する。自由舌先が `rest_tip` を追う処理は後の制御更新で実行される。元のケースは舌先を `[6.45, 7.30]` cmから始めるので、この座標だけを置き換えて差を比較する。
- 上流の `tests/geometry_continuity.rs` は調音器や母音の遷移に伴う断面の連続性を、`tests/engine.rs` と `golden_voice.rs` は通常の描画とブロック分割での不変性を確認する。今回は独立な座標の回転・並進と、保存した流量からの放射・出力計算を照合する。

## 実測

固定上流の初期舌先は `[6.241412821929657, 6.810460479056529]` cmで、独立した回転・並進の計算と一致した。研究版の `speech_voice.posture.tongue_tip_cm` だけをこの値に置き換えた。通常CLIと観測付きの全116,132 PCMフレームは候補の各条件で一致し、発話計画も一致した。固定上流と研究版の基準側の全PCMハッシュは、シマーの比較の保存結果と一致した。

| 固定上流との比較 | 元の研究版 | 初期舌先を揃えた研究版 |
| --- | ---: | ---: |
| 咽頭18セルの初期実効面積の最大差（cm²） | 0.002783 | 4.44×10⁻¹⁵ |
| 口腔18セルの初期実効面積の最大差（cm²） | 1.053814 | 7.99×10⁻¹⁵ |
| 冒頭50 msの口端流量の最大差（cm³/s） | 64.11116 | 4.22×10⁻¹² |
| 冒頭50 msのPCMの最大差 | 0.0025693944 | 0 |
| 全116,132フレームのPCMの最大差 | 0.0025693944 | 4.66×10⁻¹⁰ |

舌先を揃えると咽頭・口腔のセル長が全36セルで一致し、最小面積の最大差も8.88×10⁻¹⁵ cm²だった。補正前のPCM最大差は第191フレーム（約3.98 ms）にあり、保存した流量を独立に出力へ変換すると、口端の寄与は−0.002564686、鼻端は0、壁は−0.000004709で、絶対値の約99.82%を口端が占めた。冒頭の流量成分を変換して足したときのDC除去後の最大差は3.36×10⁻¹⁶以下。独立に間引きと出力段を照合した。

固定上流と補正後で最初にPCMが非ゼロになる箇所は第1,984フレーム（約41.33 ms）で、先頭2,400フレームは全標本が一致した。補正後の最初のPCM差は第2,953フレーム、最大差は第21,210フレーム。補正後は全フレームで1×10⁻⁶以下となり、先行の母音中央窓のLPC入力300標本も一致した。計測5判定と事前登録の3仮説が成立した。[計測の要約](../runs/tsp-seems-initial-tip-20261123-repeat/summary.json)

同じ音源と初期舌先で `seems` の全PCMが許容差内に収まった。次は既存の確認用の別発話にも同じ合わせ方を適用し、発話単位の最大PCM差と母音・子音の区間を比較する。得られた波形は実録音F2注釈や試聴回答を待つ評価の再現用条件とする。

## 再実行

`research/experiments/chimera-rebuild` で別の実行IDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_seems_initial_tip.py tsp-seems-initial-tip-new
```

冒頭の流量、圧差、放射、PCMは `pre-roll.npz`、母音中央のLPC入力は `lpc-windows.npz`、最初の制御更新前の断面は各条件の `initial-geometry.json` に保存した。実行環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。ビルドと一時波形・成果はRTL9210B-CGを使用した。[初回](../runs/tsp-seems-initial-tip-20261123-a/manifest.json)・[再実行](../runs/tsp-seems-initial-tip-20261123-repeat/manifest.json)

実験ディレクトリと `/tmp` の両方で、要約、初期断面、観測窓、LPC入力、発話計画がバイト単位で一致した。上流9試験と研究版17試験は両方で通過した。突き出した下唇を引く際の断面積の不連続は、上流が1試験を既存の `ignore` 指定にしている。描画前の断面観測を追加した後に、従来の1.165秒の線形応答比較も再実行し、断面・応答・要約が保存出力とバイト一致した。[上流の試験ログ](../runs/tsp-seems-initial-tip-20261123-repeat/artifacts/upstream-geometry-tests.log)・[発話中の断面比較の再確認](../runs/tsp-seems-tract-transfer-20261123-recheck-after-initial-tip/manifest.json)
