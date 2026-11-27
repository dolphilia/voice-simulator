# 歌唱フレーズを声門・声道・PCMに接続する

## 固定上流の読解

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。歌詞と音符を音素区間とF0目標に変換する部分は[歌唱計画](song-timing.md)で照合済み。

1. `render::song` は歌詞を音節にし、MIDI番号と拍数の組に順番に割り当てる。初音の周波数を基準F0、肺圧を9 cmH₂O、声帯張力を0.55に設定する。エンジンの現在F0は初期値110 Hzから基準値へ移る。レンダーは楽譜の終わりと実際のフレーズ終端の遅い方からさらに0.4秒まで加える。[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L245)
2. `plan_song` はフレーズごとに `plan_utterance` を歌唱モードで呼ぶ。冒頭子音の開始で呼気ジェスチャーが最大重みとなる。最後の母音と後続する共鳴音の合計が180 ms以上なら、呼気目標を音素末尾の15 ms後まで維持し、90 ms前から150 msのランプで声門開大を始める。二重母音は同一F0の末尾母音を遡って時間を数える。短音または阻害音末尾では呼気の最大重み区間が音素末尾で終わり、開大の立ち上がりは30 msとなる。[呼気と開大](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L565)・[語尾の上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs)
3. 歌唱のF0ジェスチャーは音符内の子音にも付く。名目上の母音長が300 msを超えた音符にはビブラートを加える。ランプは拍の80 ms前に始まり、拍の220 ms後に最大重み4に達し、拍に名目母音長を加えた時刻から60 msで減衰する。子音の最小長で実際の母音が拍から遅れる場合も、ビブラートは元の拍を参照する。[ビブラートの形](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L115)・[拍への割り付け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L238)・[高速歌唱テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)
4. 制御の更新時には、ジェスチャーの重みに基準F0の重み0.02とビブラート深さの基準重み0.05を足して加重平均する。F0の現状態は対数周波数で指数平滑化する。目標値が付く間の時定数は30 ms、離れた後は60 ms。声門は32内部サンプルごとにセントで求めた揺れを周波数倍率に変換し、位相を進める。呼気と開大は声門前後の圧力差と有声度を変え、実流量が声道・放射・PCMへ伝わる。[制御の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[ブロック処理のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

## 実装前に登録した比較

成人男性の同じ初期姿勢とゲート0を使用する。内部96 kHz、出力48 kHzの固定条件で、上流のジッタ・シマー・ドリフトは0に設定する。乱流は主な比較で上流既定の1とし、高速条件は発声・調音と語尾の違いを観測しやすいよう0にする。実際のF0は声門時系列と、出力波形を直接読むYINの両方で確認する。声門の平滑化F0は登録されたジェスチャーを使う独立離散計算と照合する。

| 入力 | 予測 |
| --- | --- |
| [二音の Pop Dee](../cases/song-voice-long.json) | 母音の拍は0.5 / 1.0秒、音高はC4 / A4付近、遷移は /d/ 開始から次の拍の50 ms後まで。開大ランプは1.36秒に始まり、呼気の最大区間は1.465秒まで |
| [深さ0の対照](../cases/song-voice-flat.json) | 時間と調音の条件は同一。声門の瞬時F0にビブラート周波数の偏差が出ない |
| [高速の二音](../cases/song-voice-fast.json) | 約44 msの終母音にビブラートや緩やかな開大は入らない。開大ランプは末尾の15 ms後 |
| [無声破裂音で終わる Pop](../cases/song-voice-stop.json) | 長母音には揺れが出る。末尾の /p/ で短い開大を選び、呼気保持は0.95秒で終わる |

全ケースでPCMの有限性、長さ、128/77フレーム分割での再現性を確認する。出力末尾20 msの絶対ピークは0.001以下、冒頭の唇の閉鎖と開放はそれぞれ登録区間内を予測する。

## 初回の判定と第2版の観測窓

第1版の4条件では、ジェスチャー、内部系列、PCM、F0の独立計算の照合が通過した。物理的な閉鎖だけが事前の観測窓を外れた。冒頭 /p/ の軌道は0.432秒の音素区間開始より早く、目標の保持開始0.410秒、その30 ms前の0.380秒から動き始める。上流・候補ともに最小断面が閾値を下回った時刻は0.422458秒だった。第2版では早い閉鎖の検査窓を、音素開始の30 ms前から開始までの0.402〜0.432秒に変更した。

高速条件の第1版は開口も観測窓を外れた。2個の /p/ の口唇ジェスチャーが0.4865〜0.499秒で重なり、1番目の予定母音区間を通じて唇は閉じたままだった。口唇の開口は0.568042秒、有声度が初めて0.5に達するのは0.590354秒だった。第2版では高速の開口を /d/ 開始から第2母音開始の30 ms後まで、発声開始を第2母音区間内とし、第1母音区間全体で閉鎖が続くことを検査する。また、観測窓と重なる連続閉鎖の実際の開始・終了を記録するよう計測器を修正した。

第1版の入力、全判定と計測器を各実行に残した。[長音](../runs/song-voice-long-20261119-a/manifest.json)・[深さ0](../runs/song-voice-flat-20261119-a/manifest.json)・[高速](../runs/song-voice-fast-20261119-a/manifest.json)・[破裂音末尾](../runs/song-voice-stop-20261119-a/manifest.json)

## 第2版の結果

| ケース | PCMフレーム | 上流とのPCM最大絶対差 | ビブラート最大偏差 | 末尾20 msのピーク |
| --- | ---: | ---: | ---: | ---: |
| [長音](../runs/song-voice-long-20261119-b/summary.json) | 91,200 | 2.33×10⁻¹⁰ | 34.57セント | 3.39×10⁻¹⁰ |
| [深さ0](../runs/song-voice-flat-20261119-b/summary.json) | 91,200 | 2.33×10⁻¹⁰ | 0セント | 3.02×10⁻¹⁰ |
| [高速](../runs/song-voice-fast-20261119-b/summary.json) | 49,200 | 2.91×10⁻¹¹ | 0セント | 1.29×10⁻⁹ |
| [破裂音末尾](../runs/song-voice-stop-20261119-b/summary.json) | 67,200 | 2.33×10⁻¹⁰ | 34.57セント | 2.06×10⁻¹⁰ |

長音のPCMから測った母音のF0は262.63 Hzと441.79 Hz。上流でも表示精度0.01 Hzで一致した。平滑化F0は2音の幾何平均を0.976021秒に超え、次の拍より23.98 ms早かった。口腔の /d/ の閉鎖は0.970438秒、開口は1.001375秒だった。冒頭 /p/ は拍から0.021 ms後に唇が開き、有声度は拍から63.56 ms後に0.5に達した。

長音の語尾では、予定末尾1.45秒の時点で呼気ゲートは1、開大面積は0.14478 cm²、有声度は0.7740だった。50 ms後に有声度は0.0201まで低下した。破裂音末尾では /p/ による開大が先行し、同音素の予定末尾0.95秒で有声度は約1.71×10⁻⁵だった。呼気を保ったまま衰える長音と子音で振動を止める例を測定した。

4条件の各7判定が通過した。独立計算との差は平滑化F0で最大1.27×10⁻¹⁰ Hz、開大面積で最大4.57×10⁻¹³ cm²。128と77フレームのホスト分割でWAVとPCMのCSVはバイト一致した。第2版を `/tmp` から再実行し、第1版と上流・候補の時系列、波形、上流の計画が同一のハッシュであることを確認した。既存の歌唱計画と英語発話の音響出力も直前の通過版と一致した。[歌唱計画](../runs/song-plan-20261119-c/manifest.json)・[英語発話](../runs/lateral-hello-20261119-d/manifest.json)・[高速の発話](../runs/bilabial-p-fast-20261119-song-regression/summary.json)

## 追試の方法

研究ワークスペースから実行する。実行IDは毎回新しいものを使う。上流に観測を加えるプローブは固定版の公開APIを呼び、上流の作業ツリーに書き込まない。[上流プローブ](../tools/upstream_bilabial_probe.rs)・[計測器](../tools/measure_song_voice.py)・[CHIMERAのMIT通知](../LICENSE-CHIMERA)

```bash
python3 tools/measure_song_voice.py song-voice-long-local-1 long
python3 tools/measure_song_voice.py song-voice-flat-local-1 flat
python3 tools/measure_song_voice.py song-voice-fast-local-1 fast
python3 tools/measure_song_voice.py song-voice-stop-local-1 stop
```

このケースは成人男性の既存の調音対象を使う。前回の歌唱計画で記録した /ɹ/ は音素区間とF0目標まで確認済みで、発声は未対応。歌唱のタイミングを調べるときは `song_plan`、対応済み音素を発声させるときは `song_voice` を使う。
