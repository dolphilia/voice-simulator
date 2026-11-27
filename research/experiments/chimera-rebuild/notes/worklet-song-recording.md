# 実時間歌唱の映像収録

## 読解と事前登録

上流の `playTune` は入力を音節と音符へ整理し、呼び出しがまだ有効か確認してから `onStart` を呼び、発声スコアを送ります。開始側のフックが失敗すればスコアは送られません。演奏・表示側の時計を使う `tickSinging` は、スコア終了時刻の0.4秒後に `onEnd` を呼びます。明示的な停止は `onStop` を呼び、作成中のクリップを破棄します。上流のテストは開始待ち中の停止、開始処理の失敗、終端と中止の通知を検査しています。[歌唱の順序](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L342)・[SingPanelの録画フック](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L162)・[開始・停止のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L195)

`AudioEngine::recordStream` はスピーカー側のマスター出力を `MediaStreamAudioDestinationNode` に分岐します。`Clip` は画面のキャンバスを720×1280へ収めて30 fpsで採取し、その映像とエンジン所有の音声トラックを `MediaRecorder` に渡します。録画の MIME 型は実行環境に応じて選び、約500 ms間隔のチャンクは最後の `dataavailable` と `stop` を待って結合します。上流の `Clip` が解放するのはキャンバス側のトラックです。[音声の分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L82)・[映像採取と所有権](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L35)・[MediaStream Recording](https://w3c.github.io/mediacapture-record/#dom-mediarecorder-stop)・[Canvas captureStream](https://www.w3.org/TR/mediacapture-fromelement/#html-canvas-element-media-capture-extensions)・[Web Audioの録音先](https://www.w3.org/TR/webaudio-1.1/#MediaStreamAudioDestinationNode)

同じ48 kHzの英語歌唱の入力から、2拍の時刻を `最初の拍 + 累積拍数 × 60 / BPM` で計算します。映像の色が切り替わるタイミングと、エンコード前のPCMを基準にデコードした音声を整列して得た拍時刻を比較します。映像の1フレームは約33.3 msなので、描画待ちとエンコード時刻の差も含めて85 msを事前の基準とします。自然終了と中止はそれぞれ保存の有無とトラック状態を観測します。[事前登録](../cases/worklet-song-recording.json)・[実時間歌唱の基準マニフェスト](../runs/worklet-live-song-20261120-b/manifest.json)

## 音声終端の切り分け

録画停止までの待ち時間を110 msから230 msに変えると、映像のフレームは増えましたが、両実装ともデコードしたAACのSHA-256は完全に一致しました。候補ではPCM座標の約1.835秒、上流では約1.840秒までで、登録した1.87秒までの無音区間を採れませんでした。今回の候補と上流を呼ぶ比較用画面は、歌唱が完了するまでの音声ノードを録画先に接続しています。次は録画先に値0の音源を録画完了まで接続し、音声の計算経路を維持します。原因が音声入力の終了なら、声の区間と開始の差を維持したまま、最後にデコードできるPCM座標だけが延びると予測します。比較基準は第1版のまま使います。[110 msの結果](../runs/worklet-song-recording-20261120-b/summary.json)・[230 msの結果](../runs/worklet-song-recording-20261120-c/summary.json)

230 msで録画を終える条件を保ち、オフセット0の `ConstantSourceNode` を録画先にだけ接続すると、候補・固定上流とも終端の音声がPCM上の約2.07秒まで延びました。1.78〜1.87秒のデコード音声は両方ともRMS 0でした。候補の音声先頭の整列量は105.33 msから57.33 msへ変わり、拍に対する映像の誤差は約32 ms以内に収まりました。音声の欠落は加工前PCMには現れず、録画先への音声供給を続ける条件で変わりました。録画先からエンコーダーに至る内部のどの時点で末尾が欠けたかは未分離です。[値0の入力を加えた結果](../runs/worklet-song-recording-20261120-d/summary.json)

## 実装と検証

Webの「歌唱を録画」は既存の歌唱スコアをAudioWorkletで再生し、同じ出力ノードからスピーカーと録画先に分岐します。録画を選んだ場合だけWorkletが予定した開始フレーム `C₀` をページに通知します。キャンバスはAudioContextのフレーム番号から `C₀` を引いた出力フレームを使い、計画の拍に達すると色とMIDI番号を切り替えます。音声完成後は最後の量子を録画に含める時間を設け、`stop` 通知で動画を確定します。候補では各録画が音声・映像両方のトラックを所有します。録画前の中止、録画中の中止、完走後の再開を画面の操作から検査しました。[歌唱と録画の接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[キャンバスとトラックの実装](../../../../web/prototypes/chimera-research/src/song-recording.ts)・[実ブラウザの操作と観測](../../../../web/prototypes/chimera-research/tools/capture-song-recording.mjs)

固定上流の比較は同じChromiumで無改変の `Clip` を呼び、同じ歌唱ケースの固定上流PCMと同じ拍で変化する比較用キャンバスを渡しました。上流の歌唱画面のアニメーションやスピーカー側の加工は別経路です。上流の開始・停止フックは固定上流のBunテストで確認しました。録画完走・中止後に上流の映像トラックが終わり、共有音声トラックが次の録画にも使えることを観測しました。[比較用入力](../runs/worklet-live-song-20261120-b/manifest.json)・[ブラウザの実行とトラック](../runs/worklet-song-recording-20261120-repeat/artifacts/recording-browser.json)・[上流のフックのテスト](../runs/worklet-song-recording-20261120-repeat/artifacts/upstream-singing-hooks.log)

FFmpegで動画を音声と映像に分けます。音声は二つの登録区間で振幅を正規化した相互相関が最大になる位置に整列します。映像は画面中央付近の色をフレームごとに分類し、色の変わる画像のPTSから、整列済み音声上の拍時刻を引きます。候補の2拍の誤差は3回の合格実行で最大38.24 ms未満、加工前PCMはCLIと91,200フレームすべてビット一致しました。固定上流と加工前PCMが最初に異なったのは出力フレーム4,114で、最大差は `2.33×10⁻¹⁰` でした。保存動画は720×1280のMP4（H.264/AAC）で、復号音声の相関は候補の両区間で0.99998を超えました。準備中の中止を含む23項目は研究ディレクトリと `/tmp` で確認し、従来の実時間歌唱の回帰25項目も通過しました。[最終検証](../runs/worklet-song-recording-20261120-final/summary.json)・[別ディレクトリからの再実行](../runs/worklet-song-recording-20261120-repeat/manifest.json)・[保存した動画](../runs/worklet-song-recording-20261120-final/artifacts/worklet-song.mp4)・[実時間歌唱の回帰](../runs/worklet-live-song-recording-regression-20261120/manifest.json)・[独立した検証スクリプト](../tools/measure_worklet_song_recording.py)

最初のビルドはWASMホストの歌唱型に拍とMIDI番号の列がなかったため失敗しました。Rustが出す既存の入れ子構造を型に反映しました。初回の上流の所有権判定ではトラック順序を仮定し、共有音声のIDを映像のIDと取り違えました。種別とIDで比較し、中止後は `stop` イベントまで待つよう修正しました。WebMの検証と、実時間の三次元表示の取り込みが残ります。[ビルドの失敗](../runs/worklet-song-recording-20261120-a/manifest.json)・[初回の録画判定](../runs/worklet-song-recording-20261120-b/summary.json)
