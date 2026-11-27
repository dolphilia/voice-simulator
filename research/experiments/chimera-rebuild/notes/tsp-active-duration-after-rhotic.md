# /ɹ/ 対応後のTSP確認用2録音との比較

先行の調整用4件・確認用8件を保持し、元の登録の確認用 `FK61_01` と `MK61_01` を加えた。両録音は同じ本文で、録音IDと候補が入力を処理できることを事前に確認して選んだ。本文の合成予定は各116,132フレーム。先行12件の境界と波形が再現し、追加2件の主しきい値による発話区間長は合成同士で10 ms以内と予測した。人間の録音との差は符号付きで記録する。[今回の登録](../cases/tsp-active-duration-after-rhotic.json)・[元の登録](../cases/tsp-active-duration-pilot.json)・[入力の確認](../runs/tsp-active-duration-inspect-20261121-rhotic/summary.json)

## 呼び出し順と観測位置

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `main.rs::run` は `render text --float` を `render.rs::text` に渡す。`text` と `compare/tsp.rs::say_all` は `render::say` を共用する。`say` は本文を辞書で句・音素列へ変換し、50 msを起点に調音計画を作る。体型別の基準音高は女性205 Hz、男性112 Hz。計画末尾から300 msまでの出力を、48 kHzの128フレーム単位で描画する。`HumanVoice::render` は64出力フレームごとに調音状態を更新し、内部96 kHzで肺圧と声門を気道に適用する。伝搬から得た放射を間引き、出力ゲイン、DC除去、ピーク制限、float32化の順に通す。候補も `vocal-cli render-pcm` → `speech_voice::run` の英語経路で辞書と句計画を使い、通常の出力をCSVの間引き後サンプルと照合した。[上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[発話とWAV](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L169)・[音源の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[候補](../crates/vocal-cli/src/timing_case/speech_voice.rs#L133)

上流の `load_utts` は録音IDとMFAの音素時刻を読み、`measure_pair` は同じ音素を `match_phones` の編集距離で順序を保って対応付ける。関連する試験は音素の対応順、辞書の往復と機能語、欠測、同じ乱数を使うアラインメント用ノイズを確かめる。今回の比較では文全体の区間を扱い、同じ48 kHzの窓処理を録音と両合成に適用した。元録音はアーカイブ中のPCM16を `32768` で割った振幅。合成は加工前のfloat32を用いた。[TSPの上流処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L49)・[音素の対応と測定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L761)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1505)

960フレームの窓で振幅二乗の平均の平方根を求め、240フレームずつ進める。各信号の最大窓RMSを基準とし、−35 dBと−45 dBの各しきい値を `最大RMS × 10^(dB/20)` で求める。3窓以上連続した部分の最初の窓の始端と最後の窓の終端を使う。独立計算は二乗PCMに矩形カーネルを直接畳み込み、電力比 `10^(dB/10)` と連続区間の切れ目を使う。全14件の録音、上流、候補について84区間の両端が一致した。前後100 msを余分に加えた無音対照では、両端が100 msずつ移動し、区間長は変化しなかった。[計測器](../tools/measure_tsp_active_duration.py)・[独立検証](../runs/tsp-active-duration-after-rhotic-20261121-independent-final/summary.json)

## 追加2録音の結果

| 録音ID | しきい値 dB | 録音 ms | 固定上流 ms | 再実装 ms | 再実装 − 録音 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| FK61_01 | −35 | 2,220 | 2,115 | 2,110 | −110 |
| MK61_01 | −35 | 2,210 | 2,125 | 2,125 | −85 |
| FK61_01 | −45 | 2,365 | 2,135 | 2,135 | −230 |
| MK61_01 | −45 | 2,260 | 2,140 | 2,215 | −45 |

先行12録音の計測値と両合成のWAV24件のハッシュが先行実行と一致した。全14件で主しきい値による合成同士の差は最大5 msだった。`FK61_01` の開始は両合成で75 ms。フレーム104,160からの960フレーム窓が上流−34.902 dB、候補−36.142 dBで、しきい値をまたいで終端が1ホップずれた。`MK61_01` は主しきい値の両端が両合成で一致した。副しきい値では候補の最初の4窓が−39.86〜−42.94 dBで、開始はファイル先頭。固定上流の開始は75 msだった。[14件の要約](../runs/tsp-active-duration-after-rhotic-20261121-repeat/summary.json)・[FK61_01の窓](../runs/tsp-active-duration-after-rhotic-20261121-repeat/artifacts/FK61_01/windows.csv)・[MK61_01の窓](../runs/tsp-active-duration-after-rhotic-20261121-repeat/artifacts/MK61_01/windows.csv)

## 波形差の起点と舌先対照

2件とも候補のフレーム0の間引き出力から差があり、上流は最初の1,984フレームが無音だった。上流の `ArticulatorBank::new` が使う静止舌先を、顎の回転と舌体の偏差から独立に計算した。候補の舌先だけを `(6.45, 7.30)` cmから、その静止位置 `(6.241413, 6.810460)` cmに変えたところ、最初の1,920フレームの間引き出力とPCMは両方とも厳密に0になった。語頭 `/ə/` の目標110 msと立ち上がり70 msから、40 msに当たる1,920フレームでは準備ランプの重みが0。次の制御境界1,984フレームで、上流と舌先対照の両方が最初の非ゼロPCMを出した。`MK61_01` では候補の副しきい値の区間が `[0, 106320)` から `[3600, 106320)` に移り、上流と一致した。主しきい値の区間と全区間の最大波形差は両件とも変化しなかった。[上流の舌先初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L78)・[舌先対照](../cases/tsp-startup-after-rhotic.json)・[対照結果](../runs/tsp-startup-after-rhotic-20261121-a/summary.json)

舌先対照の最初の非ゼロ8サンプルでは、上流と候補の振幅比が女性で0.875から `4×10⁻⁸` 以内、男性で1だった。女性の最初の比は上流 `HumanVoice::new` の体型別ゲインと一致する。有声部まで含めると、通常経路の最大波形差は女性0.558、男性0.574。上流の通常CLIでは、調音比較で合わせていた音源変調と出力倍率が既定値で動く。後続の波形差に対するこれらの寄与は未分離。[体型別出力倍率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L276)・[音源の既定値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L51)・[調音比較の設定](english-rhotic.md#実装と実測)

## 再現と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行した。初回と `/tmp` からの再実行は各6判定、独立検証は5判定、舌先対照は6判定を通過。上流のTSP試験6件とCLIのWAV試験1件も通過した。独立検証の最初の保存では計測用のCSV抜粋設定を引き継いだため、独立計算の終了コードは0でもマニフェストは不合格だった。その出力とエラーを保存し、独立検証の保存では一般の元条件を使い、測定条件は検証器への入力としてハッシュを記録した。[初回の保存記録](../runs/tsp-active-duration-after-rhotic-20261121-a/manifest.json)・[独立検証の保存エラー](../runs/tsp-active-duration-after-rhotic-20261121-independent/manifest.json)・[独立検証の再実行](../runs/tsp-active-duration-after-rhotic-20261121-independent-final/manifest.json)

元録音は作業用ディスクのZIPからメモリに読み出した。候補CSV14件の全フレームを使った後、約149.3 MB分のハッシュと必要行を残した。本測定1回の保存成果は約26.4 MB。`/tmp` からの再実行はログを除く117成果と元CSV14件のハッシュが一致し、成果の実体はRTL9210B-CGにある。試聴用には主しきい値で切り出し、同じ対のRMSをそろえた14対を用意した。聞き手の判定、共通の音響アラインメントによる音素別比較、歌唱の独立評価は未実施。元の8録音では `/ʃ/` または `/dʒ/` が必要な4件が残る。[再実行の保存記録](../runs/tsp-active-duration-after-rhotic-20261121-repeat/manifest.json)・[試聴手順](../runs/tsp-active-duration-after-rhotic-20261121-repeat/artifacts/listening/README.md)・[記録欄](../runs/tsp-active-duration-after-rhotic-20261121-repeat/artifacts/listening/observations.csv)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_tsp_active_duration.py tsp-active-duration-after-rhotic-local-1 --case cases/tsp-active-duration-after-rhotic.json
../../.venv/bin/python tools/verify_tsp_active_duration.py cases/tsp-active-duration-after-rhotic.json runs/tsp-active-duration-after-rhotic-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_tsp_startup.py tsp-startup-after-rhotic-local-1 --case cases/tsp-startup-after-rhotic.json
```
