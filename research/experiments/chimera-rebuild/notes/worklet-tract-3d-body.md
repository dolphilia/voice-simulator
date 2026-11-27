# 体型を切り替えた実時間IPAの三次元断面

## 読解と事前登録

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AnatomyView3D` が現在の体型と一致するテレメトリを採用する。`VoiceModel` は体型から気道モデルを組み立て、調音姿勢からフレームを作る。体型が変わると描画の中心を求め直し、視点の向きは維持する。`BodyMix` の混合入力を `female=0.4`、`child=0.3` とすると、男性・女性・子どもの重みはそれぞれ `(1−0.3)(1−0.4)=0.42`、`(1−0.3)×0.4=0.28`、`0.3`。固定上流の体型、基準形状、閉鎖時刻のRust試験を合わせて11件実行した。[表示と体型の比較](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L173)・[気道モデルとフレーム](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L23)・[体型の重み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L331)・[体型テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)・[形状テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs)・[閉鎖時刻のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/stop_spans.rs)

候補ではIPA画面から選んだ体型で `renderRealtimeIpaVoice` が今回のWorkletを作る。Rustの `ArticulatedVoice::step` は調音状態の更新、声道の適用、舌と口蓋の接触補正、接触時の断面再適用、音響ブロックの開始の順に処理する。Workletは合成済み出力数から1を引いた番号に測定線と音響セルをそろえる。絶対位置は、その処理量子の `currentFrame` に量子内の合成済みフレーム数を足して1を引く。音響セル当たりに長さ・面積・最小面積と圧力・流量の5値があり、測定線の開始位置は体型ごとの咽頭・口腔セル数に従う。長さと座標は cm、面積は cm²、圧力は dyn/cm²、流量は cm³/s。[IPA画面](../../../../web/prototypes/chimera-research/src/main.tsx#L389)・[実時間発声](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L110)・[Workletの採取](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L170)・[Rustの更新順序](../crates/vocal-core/src/voice.rs#L460)

子どもでは咽頭11・口腔13、混合では15・16セルを予測した。出力48 kHz・内部96 kHzの `ɑpɑ` を出力768フレーム（16 ms）ごとに観測する。Chromiumの960・390 CSS pxで体型の順序を変え、画面を再読み込みせず続けて実行する。全測定線をCLIと照合し、`/p/` の予定区間内で唇端の幾何隙間 `≤ 1×10⁻¹² cm` および音響セル最小面積 `≤ 0.0002 cm²`、前後の母音中で両面積 `≥ 0.1 cm²` を満たす点を確認する。固定上流との測定線の許容差は `1×10⁻⁹`、独立計算した描画頂点との許容差は `3×10⁻⁶ cm`。観測条件と閾値は事前登録の初版を使用した。[体型別の条件](../cases/worklet-tract-3d-body.json)・[従来の実時間表示](worklet-tract-3d-live.md)

## 実装と測定手順

`SpeechTract3D` は描画後にそのサンプル番号を保持し、計測器から要求があったときだけ現在のメッシュのFloat32頂点と閉鎖マーカーを返す。サンプルがなくなればその番号も消す。最初の表示、閉鎖前、閉鎖中、再開口後を採取し、次の発声前に表示と読み出しが消えることも確認する。独立計算では、外側交点から測定線の方向に有効隙間の半分 `a` だけ内側を楕円の中心に置く。`a > 0` のとき断面積 `A` からもう一方の半径 `A/(πa)` を得て64頂点を生成し、`a = 0` のときは外側交点にまとめる。[描画の読み出し](../../../../web/prototypes/chimera-research/src/speech-tract-3d.tsx#L30)・[三次元シーン](../../../../web/prototypes/chimera-research/src/tract-3d-scene.ts)・[独立計算と判定](../tools/measure_worklet_tract_3d_body.py)

CLIの `speech_voice.tract_profile_posture` は、`tract_profile_frames` に指定した出力フレームで確定済みの調音17軸を倍精度CSVに記録する。測定線や音響セルの列と切り替えて採取できる。保存した姿勢と同じ体型を上流の格子計算に渡し、それとは別に上流が同じ入力を自分で発声した場合の格子とPCMも採った。こうして、形状計算の比較と、姿勢や発声の更新を含む比較を同じフレーム番号で行った。[CLIのCSV出力](../crates/vocal-cli/src/timing_case/speech_voice.rs#L964)・[上流の格子プローブ](../tools/upstream_sagittal_probe.rs)・[上流の発声プローブ](../tools/upstream_bilabial_probe.rs)

## 実測

Chromium 156.0.8078.4で3回実行し、それぞれ38項目すべてに合格した。48 kHzの49,828フレームのPCM、65時点の全測定線、全咽頭・口腔セルの幾何量・圧力・流量が候補CLIと一致した。同じ65件を実時間で受信し、両画面幅で同じキャンバスを使って異なるセル数に切り替えた。最初に描いた断面も新体型のCLIと一致した。[初回の判定](../runs/worklet-tract-3d-body-20261120-a/summary.json)・[再実行の判定](../runs/worklet-tract-3d-body-20261120-repeat/summary.json)・[最終版の判定](../runs/worklet-tract-3d-body-20261120-final/summary.json)

| 体型 | 咽頭・口腔のセル数 | 測定線の本数 | 描画頂点の最大誤差 | 上流の同一姿勢との最大差 |
|---|---:|---:|---:|---:|
| 子ども | 11・13 | 49 | `2.39×10⁻⁷ cm` 未満 | `1.43×10⁻¹⁴` 未満 |
| 三体型の混合 | 15・16 | 49 | `4.77×10⁻⁷ cm` 未満 | `3.02×10⁻¹⁴` 未満 |

フレーム11,519では両体型の唇端の隙間・幾何面積・音響セル最小面積が0で、マーカーはつぶれた楕円の座標に一致した。フレーム14,591では子どもの幾何面積が約1.743 cm²、音響セル最小面積が約0.850 cm²。混合体型は約2.839 cm²、約1.340 cm²だった。初回と再実行で全観測を受信しても、描画に使われた時点は58〜62件で変動した。閉鎖前の描画を混合体型の960 pxで採った点は初回6,143、再実行6,911だった。[初回のブラウザ記録](../runs/worklet-tract-3d-body-20261120-a/artifacts/960-bodies-live.json)・[再実行のブラウザ記録](../runs/worklet-tract-3d-body-20261120-repeat/artifacts/960-bodies-live.json)

固定上流自身の発声を使った測定線の最大差は表の同一姿勢の場合と同じだった。CSVを採取順に比較すると、最初の採取フレーム767ですでに外側交点のX座標に差があった。子どもは測定線3で `+8.88×10⁻¹⁶ cm`、混合は測定線1で `−8.88×10⁻¹⁶ cm`。上流に候補と同じ調音姿勢を渡した場合にも、同じ測定線に同じ差があった。PCMの最初のビット差は子どもが16,106、混合が13,414フレームで、最大絶対差はそれぞれ `9.09×10⁻¹³`、`4.66×10⁻¹⁰`（PCMの正規化振幅）。格子の微小差がPCMに伝わったかを切り分けるには、96 kHz側の口端・鼻端・壁面放射を個別に比較する。[上流と候補の比較値](../runs/worklet-tract-3d-body-20261120-final/summary.json)・[子どもの同一姿勢の格子](../runs/worklet-tract-3d-body-20261120-final/artifacts/child/upstream-pose-767.csv)・[混合体型の同一姿勢の格子](../runs/worklet-tract-3d-body-20261120-final/artifacts/three-way/upstream-pose-767.csv)

変更後の男性体型の実時間三次元表示は47項目、候補の `cargo test --locked -p vocal-cli -p vocal-wasm` はWASMの25試験に合格した。[男性体型の回帰](../runs/worklet-tract-3d-live-20261120-body-regression/summary.json)・[回帰のコマンドと環境](../runs/worklet-tract-3d-live-20261120-body-regression/manifest.json)

研究用の仮想環境を有効にし、研究ディレクトリから新しい実行IDを指定する。最終版の音声、各セルのCSV、描画の採取記録とソースの写しは作業用RTL9210B-CGに直接出力し、リポジトリ内の `runs/` に判定・マニフェストと各成果物へのリンクを残した。[最終版のコマンド・環境・ハッシュ](../runs/worklet-tract-3d-body-20261120-final/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  python3 tools/measure_worklet_tract_3d_body.py worklet-tract-3d-body-local-1
```
