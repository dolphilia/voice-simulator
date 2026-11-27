# 可動声道と呼気を同じレンダーで進める

2026-11-19。固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の成人男性モデルを使う。内部96 kHz、出力48 kHz、制御周期は内部128サンプル。初期姿勢は較正済み /i/、舌先を固定目標で駆動して /ɑ/ と /u/ へ移る。声道の形状と圧力による差を観測するため、乱流の利得、ジッタ、シマー、ピッチドリフトは0にそろえる。

## 呼び出しと状態の更新

1. 上流の [HumanVoice::new と set_articulation](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L220) では、調音器の位置と目標、気道の現在断面、内部と出力のレートを別々に持つ。初期姿勢は位置・目標ともに同じ値へそろえ、`HumanAirway::apply` の経過時間を0にして `snap_to_targets` で音響セルを初期化する。
2. [HumanVoice::render](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) が内部サンプルを進める。カウンタが0のサンプルの先頭で、[control](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457) が調音器、接触補正、[断面・長さ・ポートの補間](moving-human-tract.md)を準備し、呼気の目標を更新する。出力フレームの開始前に与えた入力は、そのフレームに含まれる制御境界で反映する。ホストが1回に要求するサンプル数はこの時刻に影響しない。
3. [呼気更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L508) ではゲートを一次の指数応答で更新し、圧力目標は `設定圧力 × 980.665 × ゲート` dyn/cm²。圧力はブロック内を線形に進む。毎サンプル、前回の肺ポート流量の低域成分に直列抵抗の差を掛けて境界圧へ加え、前の声門上下圧差を [ParametricGlottis::next](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs) に渡す。[呼気の式と固定姿勢の検証](lung-breath.md)
4. 声門ポートの断面積（cm²）は毎サンプル即時設定する。軟口蓋の補間を保持したまま、気道の更新で実際の流量（cm³/s）と放射流量の差分を得る。差分はFIR間引き→出力ゲイン→25 HzのDC除去→ピーク保持付きリミッターの順に進み、最後にf32へ丸める。出力フレーム `i` は内部サンプル `2i+1` で確定する。[出力段の独立検証](pcm-output.md)
5. [engine.rs のホスト分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L35) は、コマンドを絶対サンプル位置で適用し、異なるホスト分割でPCMビットを比較する。今回の上流比較では実際の `HumanVoice::render` を使い、イベント位置で出力ブロックを区切る。

## 実装前に登録した予測

全条件は内部59,392サンプル、出力29,696フレーム。出力フレーム8,960と19,328で母音目標を切り替える。圧力・流量・放射を上流と比較し、候補の全内部サンプルの放射から独立したFIR畳み込みと出力処理でPCMを再計算する。

- [通常の母音遷移](../cases/vowel-motion-voice-vowels.json) で、/i ɑ u/ の各50 ms窓のF0が約110 Hzを保ち、LPCの第1〜第3ピークはそれぞれ約353・2254・2913 Hz、722・1351・2549 Hz、391・998・2273 Hzになる見込み。鼻端流量は全区間ゼロ。
- [軟口蓋を開く条件](../cases/vowel-motion-voice-nasal.json) で、出力フレーム13,312〜18,158付近にポートが開き、鼻端流量は最大約31.62 cm³/s。/ɑ/ の窓で第1・第3ピークが約760・2752 Hzへ移る見込み。
- [呼気ゲート0](../cases/vowel-motion-voice-unvoiced.json) で、初期姿勢の保持中はPCMがゼロ。母音遷移の開始後は声門の有声化係数が0のままPCMが現れ、最初の閾値越えは出力8,965フレーム付近になる見込み。観測された境界圧と声門流量も保存する。

形状の絶対差は `1e-9` 以下（cmまたはcm²）、各音響系列は上流のピーク比 `1e-8` 未満、上流と候補のPCM絶対差は `5e-7` 未満を事前判定とした。ホスト分割128・77の候補PCMと出力段CSVはバイト一致を求める。

## 実装と観測結果

[ArticulatedVoice](../crates/vocal-core/src/voice.rs) は既存の呼気・声門の処理と制御カウンタを使い、同じ境界で調音と気道の目標を更新する。[CLI](../crates/vocal-cli/src/articulation_case/voiced.rs) はイベントを絶対制御フレームで適用し、通常の `render` と `render-pcm` で同じ内部サンプル列を進める。[上流プローブ](../tools/upstream_articulation_probe.rs) は `HumanVoice::render` を直接呼び、出力フレームごとの最後の内部状態を記録する。候補では全内部サンプルの放射を保存し、[独立計測](../tools/measure_voiced_vowel_motion.py) がFIR、DC除去、リミッターを再計算する。

| 条件 | 実測値 | 実行 |
| --- | --- | --- |
| 通常 | PCMが閾値を最初に超えたのはフレーム39、最大絶対振幅0.28208。/i ɑ u/ のPCM由来のF0は110.039、110.000、109.991 Hz | [要約](../runs/vowel-motion-voice-vowels-20261119-b/summary.json) |
| 軟口蓋を開放 | 軟口蓋開口はフレーム13,312〜18,158、鼻端の最大絶対流量は31.62 cm³/s。/ɑ/ のLPC第1・第3ピークは721.87→760.02 Hz、2548.63→2752.15 Hz | [要約](../runs/vowel-motion-voice-nasal-20261119-b/summary.json) |
| 呼気ゲート0 | 初期保持はPCMが全サンプル0。フレーム8,965でPCMが閾値を超え、最大0.05068。有声化係数は0のまま、静的開口を通る声門流量は最大1.173 cm³/s | [要約](../runs/vowel-motion-voice-unvoiced-20261119-b/summary.json) |

全67項目が通過。3条件の音響系列の最大差は各上流系列のピーク比 `3.38×10⁻¹²`。固定上流のPCMと比べ、開放条件は全フレームのビットが一致した。通常条件はフレーム14,120の1点で `9.09×10⁻¹³` の差、呼気ゲート0は169点で最大 `2.33×10⁻¹⁰` の差。観測できる最初の丸め差は、出力フレーム0に対応する内部サンプル1の初期形状にある。口腔中央の平均面積差は `1.11×10⁻¹⁶ cm²`、セル長差は `5.55×10⁻¹⁷ cm`。この差は放射やPCMに差が現れる前から観測された。両方のホスト分割比較ではPCMがバイト一致した。
