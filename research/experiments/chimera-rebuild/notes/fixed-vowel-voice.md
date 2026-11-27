# 固定母音を肺圧・声門・PCMへ接続する

## 固定上流の呼び出しと状態

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::new` は、成人男性の気道と声門を作り、初期断面を `snap_to_targets` で即時反映する。`render` では出力64フレームごとに `control` を呼ぶ。呼気ゲートは立ち上がり時定数25 msで目標へ近づき、基本肺圧はその制御区間内で線形に更新される。肺ポートの低周波補償は前の内部サンプルの流量を平滑化して、基本肺圧へ抵抗差に応じた圧力を足す。肺圧の入力は cmH₂O、気道の圧力は dyn/cm²、流量は cm³/s。[上流の初期化とレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L223)・[呼気の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L505)・[肺ポートの既存検証](lung-breath.md)

各内部サンプルで肺圧を更新し、前サンプルの声門上下の圧力差から声門面積を求め、声門ポートへ設定して気道を1ステップ進める。圧力差と発声ゲートは声門内部で平滑化される。面積と流量はそれぞれ cm² と cm³/s。放射流量の時間差分をFIRで間引き、ゲイン・DC除去・リミッターを通してモノラルf32 PCMにする。96 kHzから48 kHzへの間引きは49タップで、出力フレーム0は内部サンプル1の後に確定する。[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[上流の出力更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[間引きと既存出力](pcm-output.md)・[ホスト分割の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

較正表の固定姿勢を上流の現在値と目標値へ同時に設定し、舌先の自動追従と接触投影を抑える。ジッタ・シマー・ピッチドリフト・乱流を0にした決定的な条件を使う。姿勢と音源条件を固定し、肺呼気の立ち上がりは上流の `HumanVoice::render` で実行する。声門側は標準の成人男性のブレス感0.15、緊張0.5を使い、F0は初期値と同じ110 Hzにする。これにより初期のピッチグライドの影響を避ける。[声門のパラメータ変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)・[較正された固定姿勢の取得](vowel-transfer.md)

## 実装前に登録した比較

各ケースは内部65536サンプル、出力32768フレーム。定常窓は出力の19200以上24000未満（0.40〜0.50秒）。F0は48 kHzの窓に対するYIN（探索70〜200 Hz、閾値0.15）と声門位相の巻き戻り周期を比較する。LPCは同じPCM窓をポリフェーズFIRで16 kHzへ落とし、0.97のプリエンファシスとハミング窓、次数18を使う。上流は自己相関からLevinson–Durbin法を使い、Durand–Kerner法で極を求める。独立計算は同じ自己相関条件でToeplitz連立方程式と多項式の固有値を使う。0のPCMは有声判定と帯域推定を欠測として保存する。[上流のYIN](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)・[上流のLPC](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[解析の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L92)

| ケース | 事前の予測 |
| --- | --- |
| [固定 /i/](../cases/vowel-voice-i.json) | 定常窓のF0は約110 Hz。最初のLPCの極は353・2254・2913 Hz付近 |
| [固定 /ɑ/](../cases/vowel-voice-alpha.json) | 同じF0で、最初のLPCの極は722・1350・2546 Hz付近。3母音で最もRMSが大きい |
| [固定 /u/](../cases/vowel-voice-u.json) | 同じF0で、最初のLPCの極は394・998・2270 Hz付近 |
| [ゲート0の /i/](../cases/vowel-voice-i-silent.json) | 肺境界圧、声門流量、放射、PCMは0。位相は進む。F0とLPCは欠測 |

## 実装と測定結果

再実装は固定姿勢から初期化した `HumanAirway` に既存の `Breath` と `Glottis` を接続し、各内部サンプルで呼気・声門・気道の順に更新する。通常の `render-pcm` 経路で時間領域の放射を既存の出力段に渡す。`render` の観測CSVはPCMフレーム終端の内部サンプル番号を持つ。上流プローブも出力1フレームごとに同じ時刻を採取した。[再実装の声の更新](../crates/vocal-core/src/voice.rs)・[CLIの経路](../crates/vocal-cli/src/geometry_case/voice.rs)・[上流のプローブ](../tools/upstream_vowel_voice_probe.rs)

| 固定条件 | PCMのYIN F0 (Hz) | 最初のLPC F1・F2・F3 (Hz) | 定常窓のPCM RMS |
| --- | ---: | --- | ---: |
| [/i/](../runs/vowel-voice-i-20261119-e/summary.json) | 110.00164 | 352.74、2253.51、2912.71 | 0.07792 |
| [/ɑ/](../runs/vowel-voice-alpha-20261119-e/summary.json) | 110.00044 | 722.13、1350.00、2546.22 | 0.11299 |
| [/u/](../runs/vowel-voice-u-20261119-e/summary.json) | 110.00073 | 393.58、997.56、2270.42 | 0.06821 |
| [ゲート0の /i/](../runs/vowel-voice-i-silent-20261119-e/summary.json) | 欠測 | 欠測 | 0 |

定常窓の声門位相から求めた周期は全4条件で約110 Hz。有声3条件のPCMは、最初に `10⁻⁸` を超えるフレームが39（0.8125 ms）だった。この立ち上がりには、発声ゲートが十分に開く前に声門の隙間を通る流れも含まれる。ゲート0では肺圧、流量、放射、PCMが0のため、音響信号からF0とLPCは推定できなかった。[有声 /i/](../runs/vowel-voice-i-20261119-e/summary.json)・[ゲート0の対照](../runs/vowel-voice-i-silent-20261119-e/summary.json)

両方の波形でLPCが一致しても、同じ姿勢の線形伝達関数で測った共鳴との差は残る。最初の3ピークに対するLPCの差は `/i/` で +16.18、+28.14、+11.59 Hz、`/ɑ/` で −8.67、+13.45、+5.00 Hz、`/u/` で +15.66、+0.38、+32.90 Hzだった。生成音では声門と下気道を接続して発声させた条件と、PCMからの有限窓・全極モデルによる推定の両方が加わる。[線形応答の測定](vowel-transfer.md)・[LPCとの対応](../runs/vowel-voice-u-20261119-e/summary.json)

各16項目、計64項目が通過した。4条件で候補と上流の32768個のf32 PCMサンプルがバイト一致した。音響系列の最大差は列ピーク比 `2.80×10⁻¹³` 未満。YINのF0は有声3条件で上流と一致し、比較範囲内のLPC周波数と帯域幅の最大差は `1.09×10⁻¹⁰ Hz` 未満だった。ホストの128・77フレームの分割でWAVと出力CSVが一致し、研究ディレクトリと `/tmp` からの再実行で56ファイルが一致した。固定管PCM・固定気道・線形解析の既存8ケースでは直前の通過版と90ファイルが一致した。[実行条件・コマンド・ハッシュ](../runs/vowel-voice-i-20261119-e/manifest.json)・[既存PCMの回帰](../runs/pcm-voiced-20261119-o/manifest.json)・[既存線形解析の回帰](../runs/vowel-transfer-u-20261119-c/manifest.json)

## ナイキスト境界の極と判定の改訂

`/u/` の第1版は、PCMがバイト単位で一致し、F0と最初の3フォルマントも照合できたところで、LPCの件数の判定だけが不合格になった。上流のDurand–Kerner法は負の実軸上の根を `−0.8903178227858827 + j·3.596×10⁻³³` と返した。正の半平面を選ぶ条件にこの根が入り、16 kHz解析のナイキスト境界の約8000 Hz、帯域幅591.68 Hzとして報告された。独立の多項式求解では負の実根だった。第2版は両方の系列に同じ `f < fs/2 − 10⁻⁶ Hz` を適用し、境界の根の個数も確認する。上流の生CSV、根の座標、第1版のケース定義と不合格判定を保存した。[第1版の不合格](../runs/vowel-voice-u-20261119-b/summary.json)・[第2版の判定](../runs/vowel-voice-u-20261119-e/summary.json)

```bash
python3 tools/measure_vowel_voice.py vowel-voice-i-local-1 vowel-voice-i
python3 tools/measure_vowel_voice.py vowel-voice-u-local-1 vowel-voice-u
```
