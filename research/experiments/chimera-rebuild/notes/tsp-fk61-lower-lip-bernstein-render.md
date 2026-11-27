# FK61_01の下唇内面の評価順を変えた全発話比較

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行計測では、描画前の測定線43が当たる線分を、同じ4制御点から上流のBernstein基底と研究版のde Casteljau法で再計算し、端点と節点42の断面積の差を再現した。今回は、唇前端の体型変換を上流に揃えた比較元の一時ビルドから、下唇内面を作る7標本の評価順だけを変えた。 [比較元の描画と計測](tsp-fk61-ray43-intersection.md)・[事前登録](../cases/tsp-fk61-lower-lip-bernstein-render.json)

## 実装と照合

上流の `HumanVoice::control` が声道を更新すると `HumanTract::compute` が下唇内面の4制御点を組み立てる。7標本の時刻 `t = i / 6` で、Bernstein重み `(1−t)³, 3(1−t)²t, 3(1−t)t², t³` を計算し、座標［cm］に掛けた4項を左から加える。研究版では `ArticulatedVoice`、`HumanTractControl`、`SagittalModel::compute_into` を通り、`lips` が制御点を作る。試験では下唇内面の呼び出しだけを上流と同じ評価順へ切り替えた。内面の標本は音響用の下側輪郭と下唇の表示に使われる。 [上流の声道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[上流の下唇内面](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L885)・[上流の曲線評価](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L159)・[研究版の下唇内面](../crates/vocal-core/src/anatomy.rs#L529)・[試験差分](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/artifacts/lower-lip-evaluation.patch)

通常CLIの `render-pcm` と観測ビルドから48 kHzで全116,132フレームを描画する。描画前と1984・1985・2048出力フレームでは内面7点、測定線43、口腔の節点42の面積を採る。内部3952〜3979では全節点の体積源、体積差の配分、二段平滑を独立再計算する。先頭3072フレームは、口端・鼻端・壁からの放射流量の和、内部標本間の時間差分、間引き、出力ゲイン、DC除去、float32変換まで既存の検証器で再現する。既存の放射観測とは共通の2048フレームを比較する。下唇を測る光線の頂点接触や複数交差を扱うRustの試験と、気道の幾何補間試験も実行する。 [研究版の交差試験](../crates/vocal-core/src/anatomy/grid.rs#L347)・[幾何補間試験](../crates/vocal-core/tests/geometry_ramp.rs)・[体積源の再計算](../tools/measure_tsp_fk61_node42_volume_source.py)・[出力段の再計算](../tools/measure_tsp_fk61_pcm_first_difference.py)・[計測入口](../tools/measure_tsp_fk61_lower_lip_bernstein_render.py)

初回の両実行では、単体試験を同時にコンパイルする際に読み込まれる既存の `contour-buffer-reuse.json` と `bilabial-p.json` が一時チェックアウトに欠けていた。両ファイルを加えた実行ではRustの試験に通過し、次に、評価関数の追加位置が既存観測器の挿入位置と重なった。評価関数を別の位置へ移して観測器の適用を確認し、実験を再実行した。4実行のマニフェストとログを保持した。 [試験入力不足](../runs/tsp-fk61-lower-lip-bernstein-render-20261123/manifest.json)・[別ディレクトリでの試験入力不足](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-repeat/manifest.json)・[観測器の挿入位置の失敗](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-verified/manifest.json)・[別ディレクトリでの挿入位置の失敗](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-verified-repeat/manifest.json)

その次は通常CLIと観測ビルドが出力した後、ケース定義にセルの番号指定 `oral_cells_from_end` が欠けていたため集計中に `KeyError` で停止した。口端から2番目のセルを明示し、保存した波形と観測値を再解析した。両方の波形で最初のPCM差が2937へ移ったため、第2版で詳細観測の範囲を2048から3072フレームへ延長した。第1版のケース定義と描画データも保持した。 [保存した第1版](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-observed-repeat/artifacts/source/research/experiments/chimera-rebuild/cases/tsp-fk61-lower-lip-bernstein-render.json)・[再解析した第1版の描画データ](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/tsp-fk61-lower-lip-bernstein-render-20261123-observed-repeat/artifacts/render.npz)

## 実測

描画前の下唇内面の7点、測定線43の座標・隙間・面積、節点42の平均断面積が固定上流に一致した。内部3969で節点42の体積速度は −0.006386687349646536 cm³/s、二段平滑後は −2.9354556635287005×10⁻⁷ cm³/sとなり、いずれも上流に一致した。冒頭の共通区間で上流との口端放射流量の初差は3969から3971へ動いた。壁面放射流量の初差は3969、総放射流量の時間差分の初差は3968にあった。 [形状・体積源・放射の照合](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/summary.json)

| 固定上流との全PCM比較 | 唇前端を揃えた比較元 | 下唇内面の評価順を追加で揃えた試験版 |
| --- | ---: | ---: |
| 最初に差が出る出力フレーム | 1987 | 2937 |
| 差があるフレーム数 | 2309 | 2355 |
| 最大絶対差 | 1.862645149230957×10⁻⁹ | 1.862645149230957×10⁻⁹ |

最初のPCM差は950フレーム、48 kHzで約19.79 ms後ろへ移った。比較元と今回の試験版を直接比べたときの最大絶対差は7.28×10⁻¹²だった。全発話のビット一致には、2937で生じる差を含めて別の要因の照合が残る。 [全PCMの比較](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/summary.json)

2937フレームでは、試験版の変換直前値2.4556801322409847×10⁻⁶が、両版が出した隣接float32値の中点2.4556801463404554×10⁻⁶を1.409947072967101×10⁻¹⁴下回った。3072フレームまでの出力段の独立計算でその丸めを再現した。固定上流でこの標本に対応する倍精度の出力段は今回の観測範囲に含まれていない。次は固定上流の出力段を2937以降まで採り、放射入力と間引き後の最初の差を照合する。 [変換直前値と浮動小数点の中点](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/summary.json)

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296
../../.venv/bin/python tools/measure_tsp_fk61_lower_lip_bernstein_render.py tsp-fk61-lower-lip-bernstein-render-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から実行した。両実行で4判定、幾何補間の1試験、格子の5試験に通過した。通常CLIと観測ビルドは全116,132 PCMフレームがビット一致し、両実行のパッチ・観測・PCM・要約の11出力がバイト一致した。 [研究ワークスペースでの実行](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-full/manifest.json)・[別ディレクトリからの再実行](../runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/manifest.json)
