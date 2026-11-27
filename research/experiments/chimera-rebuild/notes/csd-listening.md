# CSDの録音と合成を聴き比べる

[試聴ページ](../runs/csd-listening-20261121-verified/artifacts/listening/index.html)で、調整用3区間と確認用3区間のA・B・Cを再生できる。音高の周期的な揺れ、自然さの選択、音色や入り・終わりの所見を記録し、CSVとして書き出す。採点後は集計CLIで音源対応表と照合できる。人による評価はまだ実施していない。[回答の集計方法](csd-listening-responses.md#再現と回答の集計)

## 入力と選定

元のCSD比較は固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song` で録音の秒座標へ合成を載せている。採譜の読み込み、フレーム格子、連続有声、ビブラートと非周期性は、音響比較で通常レポート及び丸め前のスコアと照合済み。今回の計測器はその録音と両合成をハッシュで確かめ、既存の発話試聴用 `listening_pair` の共通RMSとピーク上限の考え方を使う。歌唱では共通の注釈時刻を使うため、トラックごとの音量しきい値で区間を切り詰める処理を省いた。[固定上流の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[先行の歌唱評価](csd-long-note-vibrato.md)・[発話の試聴準備](../tools/measure_tsp_active_duration.py#L126)

調整用 `en012a` と確認用 `en035a` で、3波形すべてでビブラートを検出した最初の長音と、録音では相関の山が見つからず両合成では検出した最初の長音を取った。調整用の無声歯摩擦音と確認用のF0誤推定を1区間ずつ加えた。これは測定値を聞き分けられるかを調べるために選んだ例で、曲全体の分布は全音符の比較で扱う。 `/θ/` の例とF0誤推定の例でも、既存の通常描画のPCMを使った。[試聴のケース](../cases/csd-listening.json)・[第3倍音の対照](csd-long-note-vibrato.md#第3倍音がビブラート推定に入る対照)

## 切り出しと音量

音符の注釈の前350 ms・後450 msを含め、端を両レートが共有できる10 ms格子へ外側に丸めた。44.1 kHzの録音は左右チャンネルを平均し、切り出した後に `resample_poly` の160/147変換で48 kHzへ載せた。合成は48 kHzのまま切り出す。試聴の設問ではその音符のクリップ内の相対秒を示す。レート変換の独立試験では44.1 kHzと48 kHzの同時刻に置いたパルスが、ともに出力フレーム7,200になった。音声同士の時間差が聞こえる状態を保つため、各トラックの個別の時刻補正は適用していない。[変換器](../tools/prepare_csd_listening.py)・[時間格子の対照](../runs/csd-listening-20261121-verified/summary.json)

区間の両端に10 msの半コサインのフェードを適用し、音符の安定区間からRMSを求める。各波形のRMSを `R`、共通目標を `T` として定数ゲイン `T/R` を掛ける。 `T` は−26 dBFSに相当する振幅と、3波形のどのピークも−1 dBFSを超えない振幅の小さい方。PCM16に丸め、WAVを読み直してレート・フレーム数・先頭と末尾・ピーク・量子化誤差・RMSを検査した。元の安定区間のRMS差は最大21.53 dB、試聴用の出力は最大0.000033 dBになった。最短1.61秒、最長2.96秒。録音条件による音色や残響も含めて聴く設計で、聴感上の音量の一致は人の所見で確認する。[各区間のレベル](../runs/csd-listening-20261121-verified/summary.json)

## 試聴画面と検証

調整用・確認用それぞれで各音源がA・B・Cの各位置に1回ずつ現れ、計6通りの順序を使った。ページとWAVの名前は音源名を伏せ、対応を外側のJSONに保存した。採点欄は周期的な揺れの0〜3または判定不能、もっとも自然に聞こえた音源の選択、自由記述。CSVは未回答と判定不能を区別する。先行の発話評価は既存の18対の手順で別に記録する。[試聴ページ](../runs/csd-listening-20261121-verified/artifacts/listening/index.html)・[空の記入用CSV](../runs/csd-listening-20261121-verified/artifacts/listening/observations.csv)・[発話の試聴手順](../runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)

出力18 WAVのPCM検査と、Chromeを使う再生・書き出しを合わせて12判定に通過した。Chromeはすべての音声を実際に再生し、ファイルのフレーム数から出した秒数と照合した。再生の排他、幅1,280・390ピクセルで横はみ出しがないこと、日本語、引用符、改行を含む試験入力のCSVも確認した。リポジトリ側の実験パスから同じブラウザ検査を通し、 `/tmp` からの再実行で音声・HTML・音源対応表・要約・検証結果がバイト一致した。試験入力はブラウザの一時領域にだけ書き出し、記入用の回答欄は空のまま保存した。macOS 15.6.1 arm64のPython 3.14.4・NumPy 2.4.4・SciPy 1.17.1と、既存のPlaywrightを使用した。正式成果は約3.66 MBで、WAVの実体は作業用RTL9210B-CGにある。[ブラウザの検証](../runs/csd-listening-20261121-verified/artifacts/browser-verification.json)・[実行とハッシュ](../runs/csd-listening-20261121-verified/manifest.json)・[再実行](../runs/csd-listening-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=67108864 ../../.venv/bin/python tools/prepare_csd_listening.py csd-listening-local-1
```

録音の出典は Choi、Kim、Park、Yong、Nam による Children’s Song Dataset v1.1。切り出した録音にチャンネル、サンプルレート、振幅、端の調整を加えた。 [CSD配布版](https://doi.org/10.5281/zenodo.4916302)・[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
