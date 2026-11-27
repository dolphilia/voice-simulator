# 固定母音画面でPCMと放射を同じ時刻に表示する

固定上流の `ChimeraProcessor.process` は一量子のPCMを `engine_render` から受け取り、通常の音声出力とは別に6量子ごとに `humanTelemetry` を読む。テレメトリの先頭には発声の時計や声門の状態があり、後段には声門面積と流量の系列がある。 `Stroboscope` は同じ配列添字の面積と流量をCanvasに描き、両者に共通の位置を表示する。この表示の位相は画面のストロボで進む。PCMと放射を分析する今回の画面では、資料の同時刻表示を出力フレームの実測値に適用する。 [上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[上流の声門表示](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Stroboscope.tsx#L62)・[上流のブロック分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版は `renderFixedVoice` から `OfflineAudioContext` を使う。 `FixedProcessor` は同じ呼び出しのPCMと放射観測を出力フレーム番号で揃え、観測配列を完成時に転送する。固定母音画面の基準は肺圧7.2 cmH₂O・110 Hzで、96 kHzの内部標本を48 kHzへ間引く。画面のフレーム `k` はPCMを保存する位置で、放射の5値は内部標本 `2k+1` にあたる。壁・口端・鼻端・合算は cm³/s、微分は cm³/s²、PCMは正規化振幅。時刻は `1000k/48000` msで表示する。 [ブラウザの固定発声入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L87)・[放射の受け渡し](fixed-vowel-i-wasm-radiation.md)・[事前登録](../cases/fixed-vowel-i-radiation-screen.json)

観測スイッチは既存の固定 /i/ を使い、`fixed_voice_probe.radiation_components` を有効にする。同じケースを保存でき、CLIで開くと各出力フレームに対応する放射を取り出せる。画面の20 ms表示は、選択フレームを含む960フレームの区間を表示する。末尾は実データの長さで切る。全区間表示では画素列ごとに割り当てられた連続フレームを走査し、最小値から最大値まで描く。縦軸には表示区間の絶対最大値を使い、4つの流量は同じ縦軸で比較する。グラフとスライダーは共通のフレーム番号を更新し、数値欄は元の配列を参照する。 [観測スイッチ](../../../../web/prototypes/chimera-research/src/main.tsx)・[時系列表示](../../../../web/prototypes/chimera-research/src/radiation-scope.tsx)

## 実測

ChromiumとFirefoxの両方で、観測を未選択、有効、再度無効として順に描画した。全32,768フレームのWAVは各条件と通常CLIでビット一致した。観測JSONを読み戻した放射の5値は全点で通常CLIと一致し、従来の観測値も揃った。画面から保存したケースをCLIで再描画した結果も同じだった。CLIの内部流量から合算・微分・PCMを独立計算して照合した。 [観測と保存の判定](../runs/fixed-vowel-i-radiation-screen-20261124-registered/summary.json)

フレーム0、1、960、19,200、32,767で、両表示範囲のカーソル値と時刻が元のPCM・放射流量の値と一致した。グラフをクリックした位置は両ブラウザとも19,440フレーム（405 ms）を選択した。全区間表示で採取した5画素列のPCM上下端は独立計算と最大約1.13画素差だった。幅390 pxの表示でグラフと操作のはみ出しはなかった。 [Chromiumの表示](../runs/fixed-vowel-i-radiation-screen-20261124-registered/artifacts/chromium/desktop.png)・[Firefoxの狭幅表示](../runs/fixed-vowel-i-radiation-screen-20261124-registered/artifacts/firefox/mobile.png)

今回の7.2 cmH₂Oの条件では、固定上流のPCMとも全フレームでビット一致した。共通観測で最初に差が出たのは放射微分のフレーム7、口端流量ではフレーム24だった。最大相対誤差はそれぞれ2.69×10⁻¹³、4.30×10⁻¹⁵。鼻端は固定上流・研究版とも全フレームで0だった。固定上流の保存観測には壁と合算の個別列がないため、この2列は研究版CLIと内部標本からの独立計算で照合した。 [上流との比較](../runs/fixed-vowel-i-radiation-screen-20261124-registered/summary.json)

## 実行記録

macOS 15.6.1 arm64、Rust 1.94.1、Node.js 24.19.0、Bun 1.4.4、Python 3.14.4、NumPy 2.4.4、Chromium 156.0.8078.4、Firefox 157.0を使用した。研究ワークスペースから次を実行した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_radiation_screen.py fixed-vowel-i-radiation-screen-20261124-registered \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox
```

`/tmp` からPythonとスクリプトを絶対パスで指定し、実行IDを変えて再実行した。両実行は各19判定に通過し、要約と24成果がバイト一致した。現行のWeb実装でも、44.1 kHz英語発話の共有Wasm取得を保留したときの停止・再開30判定にChromiumとFirefoxで通過した。 [初回マニフェスト](../runs/fixed-vowel-i-radiation-screen-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-radiation-screen-20261124-repeat/manifest.json)・[英語発話の回帰](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261124-radiation-screen/summary.json)

画面画像4組のうち、Chromiumのデスクトップ画像ではグラフ枠の角8画素にRGB各色で最大1階調の差があった。カーソルの検査結果と保存したデータは一致し、画像は両方保存した。 [初回の画像](../runs/fixed-vowel-i-radiation-screen-20261124-registered/artifacts/chromium/desktop.png)・[再実行の画像](../runs/fixed-vowel-i-radiation-screen-20261124-repeat/artifacts/chromium/desktop.png)

第34版の全体監査は199実行・3,286成果・413判定に通過した。研究版のRustテスト53件、固定上流17件、現行Webのビルドも通過した。画面計測2件、回帰、全体監査の1,922入力と82出力をSHA-256で照合した。RTL9210B-CG上の78出力は同じ内容を共有し、33ファイル分の45,279,008バイトを使用する。 [全体監査の要約](../runs/plan-completion-v34-fixed-vowel-i-radiation-screen-20261124/summary.json)・[監査マニフェスト](../runs/plan-completion-v34-fixed-vowel-i-radiation-screen-20261124/manifest.json)
