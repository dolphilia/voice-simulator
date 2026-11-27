# IPA発話の各時刻の三次元断面

## 読解と事前登録

固定上流の `HumanVoice` は制御周期に調音を積分し、`HumanAirway::apply` で形状を計算します。舌の接触制約で調音状態が変われば `reapply` で形状を更新してから、気道の補間を始めます。上流 Web の `AnatomyView3D` は調音テレメトリから別途フレームを作り、外壁から有効隙間の半分を内側へ移した点を断面の中心にします。反対方向の半径は面積から求め、狭い隙間の打ち切りと横幅の上限を設けています。[上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L496)・[上流の三次元表示](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L185)・[楕円の組み立て](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1090)

再実装の `ArticulatedVoice::step` でも、調音スコアと接触補正を反映した測定線から音響セルの目標を作ります。測定線の `gap_cm` と計算面積 `area_cm2` は幾何モデルの量です。音響セルの長さ、平均・最小面積は再標本化、変化率の制限と内部サンプルごとの補間を経ます。同じフレーム番号は採取時刻を対応させるために使い、各量の空間位置や数値は独立に比較します。[制御更新](../crates/vocal-core/src/voice.rs#L460)・[断面積の算出](../crates/vocal-core/src/anatomy/area.rs)・[再標本化と変化率制限](../crates/vocal-core/src/airway/tract_control.rs)

閉鎖前の採取点は唇の閉鎖ジェスチャー開始 192.380 ms より前の 192 ms です。閉鎖中の 256 ms と開放後の 352 ms は既存の音響断面ケースと同じです。48 kHz の出力フレームは 0 始まりで、採取後の経過時刻は `(frame + 1) / sampleRate` です。予測、採取フレーム、許容差を実装前に固定しました。[事前登録ケース](../cases/worklet-tract-3d-dynamic.json)・[既存の音響断面の実行](../runs/worklet-tract-profile-3d-regression-20261120/summary.json)

## 採取と描画

上流の比較用プローブは `HumanAirway::frame` から接触補正後に確定した `grid` を直接読みます。上流の連続性テストは発話範囲と母音間の断面の急変を検査し、別のゴールデンテストはRustとTypeScriptの幾何を照合します。今回の比較は、確定した格子を実発話の途中で取り出すため、上流UIの調音テレメトリの丸めを経由しません。[フレームの確定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L229)・[連続性テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L118)・[ゴールデンテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs#L15)・[上流プローブ](../tools/upstream_bilabial_probe.rs)

再実装は再標本化に使った測定線の配列を調音制御が保持します。オフラインIPA発話で採取を有効にすると、Workletは768出力フレームごとと末尾で、再標本化前の格子と補間後の音響セルを同じレンダー位置で保存します。WASMとWorkletの採取用バッファは開始時に確保します。時系列は選択時刻以前の最後の音響セル行を探し、その行に対応する測定線で既存のWebGLシーンの形状を更新します。[Worklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[時刻の選択](../../../../web/prototypes/chimera-research/src/ipa-timeline.tsx)・[表示と保存](../../../../web/prototypes/chimera-research/src/speech-tract-3d.tsx)

楕円の矢状面内の半径は有効隙間の半分です。もう一方向の半径は計算面積を `π × 矢状面内の半径` で割ります。完全閉鎖では全頂点が同じ位置になり、画面ではそこに点を重ねます。比較スクリプトは保存された実頂点について、対頂点の距離、中心、断面の平面、外側端点、外積から得る多角形面積を独立計算します。64頂点への離散化による面積の比は `64 sin(2π/64)/(2π)` です。[三次元シーン](../../../../web/prototypes/chimera-research/src/tract-3d-scene.ts)・[独立計算](../tools/measure_worklet_tract_3d.py)

## 実測

| 状態 | 観測フレーム | 経過 | 末端の隙間（cm） | 末端の計算面積（cm²） | 唇端音響セルの最小面積（cm²） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 閉鎖前 | 9,215 | 192 ms | 0.339119 | 1.202257 | 1.710792 |
| 閉鎖中 | 12,287 | 256 ms | 0 | 0 | 0 |
| 開放後 | 16,895 | 352 ms | 1.914030 | 6.787171 | 6.417602 |

ブラウザの65時点×49本×11列はCLIと数値が一致しました。固定上流との絶対差は全列通算で最大 `3.38×10⁻¹⁴` でした。加工前PCMの49,828フレームもCLIとビット一致し、固定上流との差は最大 `1.82×10⁻¹²` でした。三次元の頂点から復元した面積の最大誤差は `1.13×10⁻⁶ cm²` でした。960・390 CSS pxの両幅で二つの視点を確認し、閉鎖時の4画像にはそれぞれ49ピクセルの橙色の点が現れました。[測定値と判定](../runs/worklet-tract-3d-dynamic-20261120-b/summary.json)・[閉鎖中の表示](../runs/worklet-tract-3d-dynamic-20261120-b/artifacts/tract-3d-closed-section.png)

初回は閉鎖した楕円の頂点が一致するところまで確認しました。画面では同一点を結ぶ線が見えなかったため、次の実行で位置を示す点と画像の検査を追加しました。計算の事前条件と観測値は維持しました。環境では `bun` の直接起動ができなかったため、既存スクリプトの Bun 1.4.4 の `npx` 経路を使いました。固定姿勢の三次元回帰57項目と、従来の二次元回帰12項目を通過し、両要約は以前の実行と同一でした。[初回](../runs/worklet-tract-3d-dynamic-20261120-a/manifest.json)・[固定姿勢の回帰](../runs/worklet-tract-static-motion-regression-20261120/manifest.json)・[二次元の回帰](../runs/worklet-tract-profile-motion-regression-20261120/manifest.json)

`/tmp` と研究ディレクトリからの実行がともに23項目を通過しました。要約、PCM、観測CSV・JSON、キャプチャ画像、WASMを含む52ファイルのSHA-256が一致しました。[別ディレクトリからの実行](../runs/worklet-tract-3d-dynamic-20261120-b/manifest.json)・[研究ディレクトリからの再実行](../runs/worklet-tract-3d-dynamic-20261120-repeat/manifest.json)

末端の面積差には測定線とセルの空間的な採り方、および時間変化への追従の両方が含まれます。次の対照は開閉境界の前後だけを制御周期の先頭・末尾で採取し、測定線から再標本化した直後のセル、変化率制限後の目標、実際の補間値を順に比較します。今回の実測は男性体型・オフラインIPA・ChromiumのSwiftShaderです。実時間表示、頭部や圧力の重ね合わせ、別体型や舌の側方開きのある発話の描画、物理GPUでの表示は未照合です。
