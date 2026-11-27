# 人間の録音と合成の発話区間長

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。同じ4話者の240録音に対応する本文のうち、候補が発話計画を作れた3文・6録音を測った。調整用はFAとMAの共通1文、確認用はFKとMKの共通2文。音源と判定しきい値は事前登録した値で測った。未対応音素で停止した元の8件と、全240件の入力可否を保存している。[測定条件](../cases/tsp-active-duration-supported.json)・[元の条件としきい値](../cases/tsp-active-duration-pilot.json)・[入力検査](../runs/tsp-active-duration-inspect-20261121-a/summary.json)

## 上流の経路と比較位置

`chimera-cli/src/main.rs::run` から `render.rs::text` に進む。`text` はCMUdictから `EnglishG2P` を作り、`say` は本文の句・音素・強勢・句境界から `plan_phrases` で調音スコアを作る。F0の基準は成人女性205 Hz、成人男性112 Hz。計画の始点は0.05 s、WAVの長さは計画末尾に0.30 sを足し、48,000を掛けた値を丸める。`HumanVoice::new` の内部クロックは96 kHzで、制御更新は内部128サンプルごと。内部では肺境界圧、声門面積、気道への流量と放射の順に進み、放射を間引き、DC除去とリミッターを経てPCMを出す。ホストは出力128フレームずつ処理する。`wav.rs::write` の `--float` はモノラルのf32サンプルを保存する。[発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L169)・[内部更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L370)・[WAV書き出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/wav.rs)

上流の `compare/tsp.rs::run` も `render::say` を使う。`align_synth` では録音のノイズ床に近い水準の乱数をアラインメント用信号に加え、`measure_pair` は `match_phones` で対応づけた音素を原波形で測る。`read_wav` のPCM16換算は符号付き整数を32,768で割る。上流の `a_render_is_aligned_over_a_noise_floor_like_the_recordings` は床の水準と再現性を、`matching_keeps_only_the_same_phones_in_order` は対応音素の順序を、CLIの `render_speech_writes_a_sounding_wav_of_the_planned_length` は長さと有音を調べる。今回の指標は文単位の区間長で、アラインメント用のノイズは加えず、同じ式を各WAVに直接適用した。[上流のTSP比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)・[WAV読み出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L330)・[CLI試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/tests/cli.rs)

候補は `vocal-cli render-pcm` の `speech_voice` から `speech_voice::run` に進み、`plan_voice_with_body` の結果を声道に接続する。事前検査と同じ入力ハッシュで、計画の開始・終了、出力予定数、ジェスチャーを `inspect` から保存した。候補の観測CSVは `pcm::write_frames` が出力フレームごとに記録し、その末尾内部サンプル番号は `2 × frame + 1`。波形の全フレームとCSVの `pcm_f32` をビット照合した。[候補の発話入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L133)・[CSVとPCMの出力](../crates/vocal-cli/src/network_case/pcm.rs#L42)

## 定義と結果

48 kHzのモノラルを960フレームの窓、240フレームのホップで走査する。各窓で \(R=\sqrt{\sum_i x_i^2 / 960}\) を計算し、ファイルごとの最大窓RMSに対して `−35 dB` 以上の窓が3個以上続く範囲を探す。最初に残った窓の開始から最後の窓の終端までを半開区間とする。持続時間は端点の差を48 kHzで秒に換算した値。`−45 dB` でも同じ計算を行い、境界の感度を記録した。既知の矩形パルスに100 msのゼロを両端へ足すと、両しきい値で境界は4,800フレーム移動し、長さの差は0フレームだった。[計測器](../tools/measure_tsp_active_duration.py)・[実測](../runs/tsp-active-duration-20261121-repeat/summary.json)

| 分割 | 録音ID | 録音の発話区間長 ms | 両合成の発話区間長 ms | 候補 − 録音 ms |
| --- | --- | ---: | ---: | ---: |
| 調整用 | FA02_07 | 1,960 | 2,115 | +155 |
| 調整用 | MA02_07 | 1,920 | 2,140 | +220 |
| 確認用 | FK64_08 | 2,025 | 1,945 | −80 |
| 確認用 | FK64_09 | 2,375 | 1,965 | −410 |
| 確認用 | MK64_08 | 1,640 | 1,965 | +325 |
| 確認用 | MK64_09 | 1,985 | 2,095 | +110 |

主しきい値では両合成の区間長の差は全件0 msで、登録した10 ms以内だった。`−45 dB` では開始・終了の選択が変わり、録音の区間長は15〜190 ms伸びた。両合成の区間長の差は最大55 msだった。別の計算では、SciPyの直接畳み込みでPCMの二乗和を求め、`10^(dB/10)` の比を用い、区間の切れ目から端点を得た。録音は再びZIPからPCM16を読み直し、録音と両合成の18波形を二つのしきい値で測った結果、36区間の境界が一致した。

試聴用の音声は主しきい値の区間を抽出し、A・BのRMSを対ごとにそろえた。RMSは最大−26 dBFS、ピークは最大−1 dBFS。保存済みWAVから6対すべての両者のRMS差が `10⁻⁷` 以内であることを確かめた。提示順の鍵と聞き手の記録欄は分けた。人による試聴判定は未実施。[試聴手順](../runs/tsp-active-duration-20261121-repeat/artifacts/listening/README.md)・[観察の記録欄](../runs/tsp-active-duration-20261121-repeat/artifacts/listening/observations.csv)

## 波形差の起点を確認する舌先対照

合成2版は全長でも一致した。PCMの最初の差は全件フレーム0で、候補の間引き後の値にすでに出ていた。上流の `ArticulatorBank::new` は歯裏の点を顎軸まわりに回して舌先位置を初期化し、`HumanVoice::new` はこの姿勢を気道に即時反映する。候補 `ArticulatorBank::new` はケースの舌先座標を採用し、初回の `step` で自由舌先の目標を求め、速度と位置の順に更新する。断面の更新に伴い、気道の体積源は \((V_{old}-V_{new})/\Delta t\) cm³/sを与える。肺圧を上げる前でもこの体積変化が放射へ伝わる。[上流の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L78)・[候補の初期化と時刻更新](../crates/vocal-core/src/articulators.rs#L208)・[体積源](../crates/vocal-core/src/airway/network/geometry.rs#L133)

調整用の男女2例で舌先だけを `(6.45, 7.30)` cmから、独立な回転計算で得た静止位置 `(6.241413, 6.810460)` cmに置き換えた。発話前2,400フレームの候補PCMピークは `2.16×10⁻³` と `2.57×10⁻³` からともに厳密に0となり、間引き後の値も全区間で0だった。主しきい値での区間は両例で同一。MA02_07では `−45 dB` の開始点が0から2,400へ移動し、固定上流と同じ2,165 msになった。この対照は保存した候補に対する入力だけの変更。[舌先の対照条件](../cases/tsp-startup-resting-tip.json)・[起点の比較結果](../runs/tsp-startup-resting-tip-20261121-a/summary.json)

対照後のPCMの最初の差は女性が2,439フレーム、男性が11,067フレームだった。女性では最初の4点で上流／候補の振幅比が0.875で、`HumanVoice::new` にある体型別出力倍率と一致する。男性の最初の差は `4.66×10⁻¹⁰`。全区間のPCM最大差は対照前と同じで、後続の発声で差が広がる経路が残る。次の音響切り分けでは、女性の出力倍率と声門変調を独立に合わせ、有声音開始の前後を比較できる。[上流の出力倍率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L276)

## 実行と保存

研究ワークスペースから以下を実行した。同じ計測を `/tmp` からPythonと計測器の絶対パスを指定し、`tsp-active-duration-20261121-repeat` として再実行した。両回6判定を通過し、実行時刻とパスを含むログ以外の53成果はバイト一致。上流 `compare::tsp::tests` 6件とCLIのWAV試験1件が通過した。Python、NumPy、SciPy、Rustの版は再実行マニフェストに記録した。[初回のマニフェスト](../runs/tsp-active-duration-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/tsp-active-duration-20261121-repeat/manifest.json)・[舌先対照のマニフェスト](../runs/tsp-startup-resting-tip-20261121-a/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 ../../.venv/bin/python tools/measure_tsp_active_duration.py tsp-active-duration-20261121-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=67108864 ../../.venv/bin/python tools/measure_tsp_startup.py tsp-startup-resting-tip-20261121-a
```

録音は外部ディスクのZIPから6件だけをメモリに読み、原音のコピーを作らなかった。生成したWAVとCSVはRTL9210B-CGへ直接書き出した。候補の全CSV約59.8 MBを判定した後、各64行・4列と元のSHA-256を保存した。初回、再実行、舌先対照の全128成果を既存の実験パスから再度ハッシュ照合した。録音入力の版と各録音のSHA-256は要約、加工済み試聴ファイルの利用条件は試聴フォルダに記録した。[保存の条件](../cases/tsp-active-duration-supported.json)・[出力の一覧](../runs/tsp-active-duration-20261121-repeat/manifest.json)
