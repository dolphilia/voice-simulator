# デュエットの三次元声道に流量から軌跡を描く

## 固定上流の入口と状態

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `DuetPage.Head.frame` は、可聴時刻に応じて各声部のCHTL行を返す。`AnatomyView3D.loop` はアニメーションの実時間を最大0.05秒に制限し、シーク世代が変わったら `resetMotion` を呼ぶ。リセットが無効にするのは前回の粒子の投影座標で、声門からの距離や残り寿命は保持する。`Anatomy3D.draw` では先に `airway` が全測定線から格子を作り、再生中のテレメトリと `view.particles` が揃ったときに `drawParticles` が進む。停止時は `tele=null` のため描画と状態の積分が休止する。[入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L154)・[時間刻みと世代](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L174)・[軌跡のリセット](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L681)・[描画順](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L833)

各粒子は声門からの距離 `s`（cm）、断面内の二つの無次元座標、無次元の寿命、前回の三次元位置を持つ。同じ最近傍の節点から流量 `U`（cm³/s）と面積 `A`（cm²）を読み、`u = U / max(A, 0.05 cm²)` を求める。表示速度は `sign(u) × 2.2 × log1p(|u| / 30)` cm/s。距離と寿命を更新してから、唇端・声門側の境界、寿命、`|u| < 3 cm/s` を評価する。低速の判定はそれだけで粒子を再初期化せず、寿命が残る場合は計算済みの位置を使う。通常の範囲外や寿命切れでは声門近くへ再配置し、そのフレームの線分を出さない。[粒子を更新する関数](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1171)

`airPoint` は粒子の距離から格子の前後二点を探し、輪の中心・方向・半径を距離で線形補間する。断面内の広がりは正中方向と左右方向にそれぞれ輪の半径の0.82倍まで。最初の輪より声門に近い領域では声門位置から補間し、最後の輪に達した位置には座標を返さない。前回の位置があるときに2点間の線分を描く。輪の描画を一つおきに間引いても、粒子の補間は全測定線が必要になる。[距離から断面を補間](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1149)

## 実装前の予測と比較条件

女声の30,720サンプルの最後の音響セルは断面積0 cm²だが、CHTLには流量約2.10 cm³/sが残る。面積下限を適用すると末端の物理速度は約42.0 cm/sになる。34,560サンプルでは末端の面積が5.31 cm²、流量が478 cm³/sで、速度は約90.1 cm/s。閉鎖時にも移動距離が正になり、輪の横幅が0になった位置では左右方向の描画が中心へ寄ると予測する。男声の46,080サンプルは逆流する節点があるため、制御ケースで同じ符号の流量を与えた粒子は声門側へ動く。21,504サンプルの女声の流量は全節点でほぼゼロで、別声部の流量で動く場合との差を検出できる。[登録ケース](../cases/duet-head-airflow.json)・[圧力表示の再実行](../runs/duet-head-pressure-20261120-repeat/summary.json)

合否は、固定上流と独立計算を同一の粒子状態・時刻・CHTL入力で照合し、通常画面で最初の描画と後続フレームを記録して判定する。固定上流の `tests/tele.test.ts` は音声時刻とCHTLレイアウトの回帰に使う。`drawParticles` の積分、低速、逆流、線分の出力は、粒子と乱数列を固定して `Beams.seg` を観測する対照で扱う。[既存の採取試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts)

## 実装と検証

WASMの頭部計算から各姿勢の声門座標を返し、圧力と気流で接触補正後の輪を共有した。各声部に独立した200粒子を持たせ、描画の更新ごとにその時点のCHTL流量と面積を読む。線分は不透明度ごとの3バッファに詰める。淡い背景に合わせて候補の線色を濃い色にした。候補の操作直後は表示を先に切り替え、位置の積分は次のアニメーションフレームで始まる。これは固定上流のアニメーションフレーム内だけでの更新と異なるため、操作直後は刻み0秒とした。停止では積分と描画を休止し、同一世代の再開では前の位置を継ぐ。シークと「気流の軌跡」の再表示では、粒子を置いた次のフレームから新しい線分を描く。[WASM](../crates/vocal-wasm/src/duet_head.rs)・[粒子の積分と描画](../../../../web/prototypes/chimera-research/src/duet-head-airflow.ts)・[再生時計と操作](../../../../web/prototypes/chimera-research/src/duet-page.tsx)

16 msの制御ケースの移動は、正流で `+0.02440 cm`、面積下限を使う正流で `+0.13072 cm`、逆流で `−0.03867 cm`、低速の正流で `+0.00227 cm`。候補と固定上流で、粒子状態と線分に対する独立計算の最大差はいずれも `4.45×10⁻¹⁶` 以下だった。160 msの入力は50 msに制限され、閉鎖した輪の左右座標は0になった。寿命切れ・範囲外の再配置、停止中の保持、シーク直後の線分消去も照合した。[制御ケースと実測](../runs/duet-head-airflow-20261120-repeat/summary.json)

48 kHzの女声の30,720サンプルでは、末端面積0 cm²に対して平滑化流量が `2.1005 cm³/s` 残った。表示の面積下限で割った速度は `42.01 cm/s`。開口後の34,560サンプルでは面積 `5.3071 cm²`、流量 `478.13 cm³/s`、速度 `90.09 cm/s` となった。男声の46,080サンプルでは逆流する節点の速度が `−541.05 cm/s` に達した。表示計算に使う流量列は平滑化済みであり、閉鎖中の瞬時の気流を知るには元の音響状態を採取する。[声部別の速度](../runs/duet-head-airflow-20261120-repeat/summary.json)・[流量の記録](duet-telemetry.md)

Chromiumの960・390 CSS pxで、初回と再実行が各20項目に合格した。再実行では前後シーク4回の最初の描画に旧い線分がなく、次の描画の3,176線分を独立した移動計算と実際の描画バッファに照合した。停止中は軌跡が消え、再開時には停止前の位置からつないだ。WASMの声門座標はCLIの `geometry` と一致した。圧力表示の回帰28項目、固定上流のテレメトリ・再生時計9試験、候補の `vocal-wasm` 25試験も通過した。[気流のマニフェスト](../runs/duet-head-airflow-20261120-repeat/manifest.json)・[圧力の回帰](../runs/duet-head-pressure-20261120-airflow-regression/summary.json)

採取器の初回の試行では、固定上流の `engine.ts` のトップレベルにあるWASM呼び出しの前に初期化が必要だった。`initChimera` を先に実行して採取できるようにした。登録したケースは同じまま実行した。研究ディレクトリで `python3 tools/measure_duet_head_airflow.py duet-head-airflow-local-1` を使う。[比較スクリプト](../tools/measure_duet_head_airflow.py)

```bash
npx --offline --yes --package=bun@1.4.4 -- ../../.venv/bin/python \
  tools/measure_duet_head_airflow.py duet-head-airflow-20261120-repeat
```
