# /ð/ 対応後のTSP録音との発話区間比較

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。従来の6録音に、元の調整用登録で `/ð/` だけが未対応だった `FA01_01` と `MA01_01`、確認用の同じFK・MKから入力検査で選んだ62_02と62_04の男女各2録音を追加した。調整用4件、確認用8件を同じ条件で測定した。選定時の判定に使ったのは本文の発話計画の可否と録音ID。元の8件と未対応一覧は先行する登録と入力検査に残している。[今回の条件](../cases/tsp-active-duration-after-dh.json)・[最初の登録](../cases/tsp-active-duration-pilot.json)・[入力の再検査](../runs/tsp-active-duration-inspect-20261121-dental/summary.json)

## 比較位置と計測方法

固定上流の `chimera-cli/src/render.rs::say` は `render text` と `compare/tsp.rs::say_all` で共用される。`say` は本文を辞書で音素列にし、体型別の112または205 Hzを基準にスコアを作用させ、48 kHzのモノラルを128フレームごとに描画する。`HumanVoice::render` は出力64フレームごとに調音を更新し、内部96 kHzの放射を間引き、ゲイン、DC除去、制限を通す。上流の `load_utts` は録音の時刻注釈を読み、`measure_pair` と `match_phones` で録音と合成の同じ音素を対応させる。関連する上流試験は対応の順序と、アラインメント用ノイズを再現できることを確認する。今回の文全体の指標は `render text --float` と候補の `vocal-cli render-pcm` から得る加工前PCMに適用し、録音も同じ式で扱った。[発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L169)・[上流の音素比較と試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)・[内部更新と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L370)

計測器の既定ケースを維持した上で `--case` で入力登録を選べるようにした。候補を生成する前に、固定上流の本文から再構成した入力のSHA-256と出力予定フレーム数を事前検査に照合する。窓は20 ms、ホップは5 ms。各波形の最大窓RMSを基準とし、主しきい値−35 dBと副しきい値−45 dB以上の窓が3つ以上連続した部分を使う。計測の開始は最初の採用窓の始端、終了は最後の採用窓の終端。独立計算では二乗したPCMを幅960の矩形で直接畳み込み、最大窓電力に対し `10^(dB/10)` を掛けたしきい値から区間の切れ目を求めた。全72区間の両端が一致した。保存済み6録音の計測値と各CLIの12 WAVも照合し、すべて一致した。[計測器](../tools/measure_tsp_active_duration.py)・[独立した照合](../runs/tsp-active-duration-after-dh-20261121-independent/summary.json)

## 追加した6録音の主しきい値の結果

| 分割 | 録音ID | 録音の区間長 ms | 固定上流 ms | 再実装 ms | 再実装 − 録音 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 調整用 | FA01_01 | 2,380 | 2,410 | 2,405 | +25 |
| 調整用 | MA01_01 | 2,155 | 2,430 | 2,430 | +275 |
| 確認用 | FK62_02 | 1,980 | 2,370 | 2,370 | +390 |
| 確認用 | MK62_02 | 1,930 | 2,385 | 2,385 | +455 |
| 確認用 | FK62_04 | 2,160 | 2,490 | 2,490 | +330 |
| 確認用 | MK62_04 | 2,070 | 2,510 | 2,510 | +440 |

主しきい値では全12録音で両合成の長さの差が5 ms以内で、登録した10 msの許容差を満たした。FA01_01の5 ms差は末尾の1ホップ。出力フレーム116,640からの960フレームの窓は、固定上流では最大窓比−34.523 dB、候補では−35.004 dBだった。この窓がしきい値をまたぎ、終端が1ホップ違った。追加した6録音に対する候補の長さは25〜455 ms長い。同じ調整用本文でも、話者と合成体型が異なる2件では差が25 msと275 msだった。結果の範囲は合成可能だった本文と4話者。[本測定の要約](../runs/tsp-active-duration-after-dh-20261121-repeat/summary.json)・[FA01_01の全窓](../runs/tsp-active-duration-after-dh-20261121-repeat/artifacts/FA01_01/windows.csv)

## 副しきい値の境界と発話頭の /ð/

全12件の合成PCMは先頭でビット差があった。-45 dBでは追加の男性3件でも、候補で区間がファイル先頭から始まった。候補の舌先を旧対照と同じ静止位置 `(6.241413, 6.810460)` cmに置き直すと、3件の開始は固定上流と同じになり、長さは35・35・50 ms短くなった。主しきい値での区間は4件とも同じだった。合成2版の全区間の最大PCM差は舌先の対照でも変化しなかった。比較に使ったレンダーは既定の発話を維持し、この舌先対照は別の実行に保存した。[舌先対照の第2版](../runs/tsp-startup-after-dh-20261121-b/summary.json)

舌先対照の第1版は、一律に先頭50 msを無音と見込んだため不合格だった。調整用2録音と確認用 `MK62_02` の本文は `/ð/` で始まる。音素区間は0.110 sに始まるが、閉鎖の舌先目標に31 msの先行、30 msのランプがあるので、`Gesture::weight` により0.049 s（2,352フレーム）から重みを持ち得る。次の64フレーム制御境界は2,368フレーム（約49.33 ms）。第2版は観測する先頭区間の終端を2,352とし、固定上流と舌先対照の両方で3件の最初の非ゼロPCMが2,368に現れることを確認した。計測の主・副しきい値は維持し、不合格の第1版の観測も保存した。[歯音のジェスチャー](dental-dh.md)・[制御の重み](../crates/vocal-core/src/score.rs#L165)・[改訂した観測区間](../cases/tsp-startup-after-dh.json)・[第1版の不合格](../runs/tsp-startup-after-dh-20261121-a/summary.json)

## 実行と保存

研究ワークスペースから下記を実行し、同じ登録を `/tmp` から絶対パス指定で再実行した。本測定は両方6判定を通過し、時刻と実行パスを含むログ以外の101成果がバイト一致。独立検証は5判定、固定上流の `compare::tsp::tests` は6試験に通過した。元のTSP ZIPは作業用ディスクからメモリに読み出した。候補CSV計128,768,600バイトを全件判定してから、12録音各64行・4列と元のハッシュを残した。本測定1回の保存成果は約22.6 MB。候補、固定上流、計測器の版と出力ハッシュはマニフェストにある。[本測定](../runs/tsp-active-duration-after-dh-20261121-a/manifest.json)・[再実行](../runs/tsp-active-duration-after-dh-20261121-repeat/manifest.json)・[独立検証](../runs/tsp-active-duration-after-dh-20261121-independent/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_tsp_active_duration.py tsp-active-duration-after-dh-local-1 --case cases/tsp-active-duration-after-dh.json
../../.venv/bin/python tools/verify_tsp_active_duration.py cases/tsp-active-duration-after-dh.json runs/tsp-active-duration-after-dh-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_tsp_startup.py tsp-startup-after-dh-local-1 --case cases/tsp-startup-after-dh.json
```

試聴用に主しきい値の区間を切り出し、録音と候補のRMSを対ごとにそろえた12対を作った。判断の記録欄は音響計測と別に置き、提示順の鍵は試聴用ディレクトリの外に保存した。聞き手による結果は未取得。発話区間長の比較から、音素ごとのタイミングと試聴へ進むには、合成と録音に同じ音響アラインメントを適用する比較が残る。固定上流の `tools/tsp/alignment.tsv.gz` に録音側の音素時刻があり、合成側に必要な設定は `tools/tsp/mfa.yaml` にある。[試聴手順](../runs/tsp-active-duration-after-dh-20261121-repeat/artifacts/listening/README.md)・[試聴記録欄](../runs/tsp-active-duration-after-dh-20261121-repeat/artifacts/listening/observations.csv)・[音素計測の手順](../../../../docs/reference/chimera-vocal-synth/upstream/docs/speech-comparison.md)
