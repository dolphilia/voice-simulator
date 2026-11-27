# デュエットの乱流源を三次元位置に対応させる

子ども体型と混合体型でも、生成した枝配置と、実ブラウザでの前後シーク直後の位置を照合した。[体型別の比較](duet-head-turbulence-body.md)

## 固定上流と記録の差

固定上流の `HumanVoice` は乱流源を走査し、最大の `level` とその `src` をテレメトリへ書く。`level` は枝の断面積と流量から求めたレイノルズ数を閾値と比較し、二乗差にゲインと飽和を適用した振幅。`src` は気道ネットワーク内の枝番号。CHTL v1のヘッダーはセル数を保存し、各管の枝の開始番号は格納しない。候補の `Recorder::snapshot` も自身のグラフの枝番号を保持する。[上流の採取](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L626)・[上流の乱流振幅](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1162)・[候補の採取](../crates/vocal-cli/src/timing_case/speech_voice/telemetry.rs#L125)

`VoiceModel.branchS` は内部枝なら、その枝の両側の音響セルの境界をセンチメートルで返す。声門ポートは0.2 cm、対応する管がない枝は−1。`drawTurbulence` は `noiseLevel > 1`、有効な枝、`min(1, log10(level) / 3.2) > 0.05` が揃ったときだけ線分を描く。乱数の状態は7から始め、素数2147483647を法とする乗算で進む。各フレームは乱流源の0.2〜1.4 cm先を `airPoint` で投影し、唇端までの有効な位置に短い線分を作る。無効位置を試した場合、座標用の乱数は進み、長さ・不透明度用の乱数は消費しない。[枝の位置](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L135)・[線分の生成順](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1205)

候補の公開デモから、男声30,720サンプルの振幅92.03（枝72）、女声34,560サンプルの振幅36.93（枝67）を読んだ。同じ体型・48 kHzで作った固定上流の声門ポートは70と65。これらの行の72・67を固定上流の `branchS` に渡す対照では−1だった。男声46,080と女声49,920の枝40は上流の口腔範囲に入った。候補の有効な位置は候補のCLIが作るグラフから取得し、枝番号だけでの流用との差を検証する。女声の21,504と43,008は枝−1で、乱流線分が出ないと予測する。[登録した入力と判定](../cases/duet-head-turbulence.json)

## 実装と検証

二声を生成した `vocal-cli inspect` から、咽頭・口腔の内部枝の開始番号、セル数、声門ポート、出力サンプルレートを採った。男声は咽頭12・18セル、口腔29・18セル、声門72。女声は咽頭12・15セル、口腔26・16セル、声門67。生成手順は同じ入力で採った枝情報を声部ごとに `show.json` に書く。再採取前後で二声のテレメトリのSHA-256と生成WAVが一致した。画面は枝情報をCHTLのセル数・出力レートと照合し、枝範囲の重なりも検査する。旧形式の公演は従来の再生と表示を利用できる。枝情報が付いた声部に乱流源を表示する。[生成方法](../tools/measure_duet_telemetry.py)・[公演定義](../../../../web/prototypes/chimera-research/public/shows/duet-clock/show.json)

候補の30,720サンプルの男声と34,560サンプルの女声は、どちらも0.2 cmの声門位置になった。枝40は男声46,080サンプルで14.4545 cm、女声49,920サンプルで13.2972 cm。両者は同じ枝番号でも、口腔のセル数と長さに応じて別の位置を返す。固定上流とは、同じ記録に別の枝配置を適用する対照で声門の判定に差が出た。[枝配置と記録行](../runs/duet-head-turbulence-20261120-repeat/summary.json)

同じ格子と乱数列の対照では、固定上流の `Beams.seg` に渡った線分が独立計算と座標差 `8.89×10⁻¹⁶ cm` 以下で一致し、不透明度の差は0だった。強度1.4では0本、1.5では40本となり、口端に近い制御入力では有効な26本が残った。無効な枝では乱数の状態も進まなかった。候補は気流表示と同じ投影を使い、線分を位置と頂点の不透明度のバッファへ書く。淡い背景用の線色を使い、線幅はThree.jsの標準の線としている。[候補の実装](../../../../web/prototypes/chimera-research/src/duet-head-turbulence.ts)・[制御用の採取と比較](../tools/measure_duet_head_turbulence.py)

Chromiumの960・390 CSS pxで20項目が2回とも合格した。前後シークで移動先の枝と強度を使い、停止・無音・非表示では線分を描かなかった。ブラウザが描画に使う位置と不透明度のバッファを独立計算に照合した。枝情報のない公演の再生と、誤ったサンプルレートの枝情報を拒否する条件も通過した。[再実行のマニフェスト](../runs/duet-head-turbulence-20261120-repeat/manifest.json)

圧力表示28項目と気流表示20項目も通過した。圧力の画素比較では乱流表示を切り、圧力だけを比較した。二声のテレメトリ採取と再生34項目はRTL9210B-CGに約178 MiBを直接出力して確認した。[圧力の回帰](../runs/duet-head-pressure-20261120-turbulence-regression/summary.json)・[気流の回帰](../runs/duet-head-airflow-20261120-turbulence-regression/summary.json)・[テレメトリの回帰](../runs/duet-telemetry-20261120-noise-layout-regression/manifest.json)

研究ディレクトリから、研究用PythonとBun 1.4.4で再実行できる。

```bash
npx --offline --yes --package=bun@1.4.4 -- ../../.venv/bin/python \
  tools/measure_duet_head_turbulence.py duet-head-turbulence-local-1
```
