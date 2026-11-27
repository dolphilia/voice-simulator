# 実時間発声の三次元断面

## 読解と事前登録

固定上流の `ChimeraProcessor::process` は音声を生成した後、テレメトリ有効時に6量子ごとに音響状態を送ります。48 kHz・128サンプル量子では768サンプル、16 msです。`HumanVoice::telemetry` は調音を `f32` に丸め、音響配列と窓内の圧力RMSを作ります。`AudioEngine` は受信時刻と最新版を保持し、`AnatomyView3D` は次の描画時に最新の調音配列から矢状面と測定線を再計算します。幾何の連続性とRust・TypeScript間の一致は上流の別々のテストで検査されています。[Workletの採取](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L185)・[Rustの観測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L596)・[受信](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L180)・[描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L185)・[連続性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L118)・[幾何の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs#L15)

再実装のオフライン採取は、接触補正を反映して確定した `f64` の測定線と、補間後の音響セルを同時に採ります。48 kHzの男性体型 `ɑpɑ` では、出力フレーム9,215・12,287・16,895が192・256・352 msに対応します。先頭が0の出力フレームを `f`、予定開始のAudioContextフレームを `C₀` とすると、量子が連続する場合の採取位置は `C₀ + f`、出力開始からサンプル末尾までは `(f + 1) / 48000` 秒です。ページの処理時間や機器の出力遅延を別途扱えるよう、録画に渡す前に二つのフレーム番号を観測します。[オフラインの基準](worklet-tract-3d-dynamic.md)・[音声処理の量子](https://www.w3.org/TR/webaudio/#rendering-an-audio-graph)

同じ768フレーム間隔と末尾で65点を採取し、保存値と加工前PCMが既存ケースと一致すると予測します。描画側に転送したバッファを返送し、同時に最大4本を保持します。ページを180 ms止める対照では、受信が遅れている間に表示向けの送信が一部省略され、発声・全65点の保存・停止後の再生に影響しないと予測します。通常表示は閉鎖前・閉鎖中・開放後を実際の画面で観測します。[事前登録](../cases/worklet-tract-3d-live.json)・[オフラインの基準マニフェスト](../runs/worklet-tract-3d-dynamic-20261120-repeat/manifest.json)・[転送の仕様](https://html.spec.whatwg.org/multipage/structured-data.html#structuredserializewithtransfer)

## 描画の初回遅延

初回実測の960 pxでは、最初の描画に112.5 msかかり、末端の隙間が0になって閉鎖マーカーのバッファが初めて使われた観測点では受信から描画まで207.5 msかかりました。この間に送信を12点省略し、開放直後の表示を観測できませんでした。加工前PCMと保存した65点は一致し、Workletのp95は1 msでした。次は、表示を選んだ時点で線・点のシェーダーと頂点バッファの準備を済ませ、最初の実測点でカメラを合わせ直します。受信後の初回遅延が下がり、同じ事前基準で3区間とも表示できると予測します。[初回実測](../runs/worklet-tract-3d-live-20261120-b/summary.json)・[到着順と描画](../runs/worklet-tract-3d-live-20261120-b/artifacts/browser-live-tract.json)

## 実装と実測

`FixedProcessor` は既存の保存用配列を埋めてから、空いている転送用バッファがあれば同じ値を詰めてページへ送ります。男性体型の登録条件では、36セルの長さ・平均面積・最小面積・圧力・流量と、行数・49測定線の11列を含む720個の `f64` が1件です。ページは描画に必要な列を読み出してバッファを返します。4本が出払った場合は送信を省略し、その点も保存用の配列には残します。画面は1描画周期に受信した最新版を使い、WebGLの頂点バッファを再利用します。線と点は表示準備中に計測用とは別の形で初回描画を済ませ、実測値を受け取った時点でカメラを合わせます。[Workletの採取と転送](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[受信と返送](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[三次元描画](../../../../web/prototypes/chimera-research/src/tract-3d-scene.ts)

準備を追加した実行では、960 pxと390 pxで65点すべてを受信し、各62点を発声中に描画しました。閉鎖前・閉鎖中・開放後の3区間が両方の画面に現れ、960 pxの受信から描画までの最大値は17.5 msでした。180 msの停止対照では、停止中の送信は4件、全体で省略は8件でした。復帰後の送信も確認しました。全条件で保存した65点と49,828フレームのPCMがオフライン条件と一致しました。受信した値は保存した値と一致し、PCMはCLIともビット一致しました。[修正後の実行](../runs/worklet-tract-3d-live-20261120-c/summary.json)

`/tmp` からの再実行でも47項目を通過しました。960 pxで58点、390 pxで62点を描画し、両幅で65点を受信しました。停止対照は4件までの送信、8件の省略、復帰後の50件の受信を確認しました。ウォームアップ区間を除いた処理時間のp95とp99は最終実行の3条件で2 msでした。画面幅ごとの実測値、操作中止後のコンテキスト解放、独立計算による描画頂点の検証を保存しました。[別ディレクトリからの再実行](../runs/worklet-tract-3d-live-20261120-repeat/manifest.json)・[検証の数値](../runs/worklet-tract-3d-live-20261120-repeat/summary.json)

固定上流の測定線との差は11列の絶対値をまとめると最大 `3.38×10⁻¹⁴` でした。オフライン三次元23項目、通常の実時間IPA19項目、歌唱録画23項目、実時間ビートボックス13項目の回帰が通過しました。[オフライン三次元](../runs/worklet-tract-3d-live-regression-20261120/manifest.json)・[実時間IPA](../runs/worklet-live-ipa-tract-regression-20261120/manifest.json)・[歌唱録画](../runs/worklet-song-recording-tract-regression-20261120/manifest.json)・[実時間ビートボックス](../runs/worklet-live-beatbox-tract-regression-20261120/manifest.json)

出力9,983の測定線末端はすでに0 cm²で、唇端音響セルには0.344060 cm²が残っていました。採取点11,519では両方が0 cm²でした。最初に0を記録した採取点は32 ms離れます。これは16 ms間隔で観測した差です。再標本化、変化率制限、セル補間の寄与を分けるには、閉鎖の前後だけ64出力フレームずつ採り、音響セルの目標と実値を並べて比較します。[基準の全採取値](../runs/worklet-tract-3d-dynamic-20261120-repeat/artifacts/browser.json)

合成時刻、ページ到着時刻、描画時刻を分けて記録しました。物理出力の遅延や、三次元断面を録画した場合の動画PTSはこの試験の対象外です。初回のビルドはThree.jsの属性型で `set` を直接呼んだため失敗しました。生成した頂点配列への書き込みに直し、初回描画の遅延が出た実行も別に保存しました。[ビルド結果](../runs/worklet-tract-3d-live-20261120-a/manifest.json)・[初回実測の判定](../runs/worklet-tract-3d-live-20261120-b/manifest.json)
