# 実装メモ: `し/す + 母音` の音素イベント化

## 概要

`web/prototypes/vowel-formant-prototype/` の `し` / `す` を、単発の sibilant ノイズから、後続母音へ接続する簡易音素イベントとして扱えるようにした。

今回の実装は、完全な日本語音素モデルではなく、UTAU の `oto.ini` で使われる `preutterance` / `overlap` の考え方を Web Audio 上の最小イベントへ落とし込む試作である。

## 追加した API

- `triggerConsonant(kind)`
  - 従来どおり、`し` / `す` の bandpass ノイズだけを鳴らす確認用 API
- `triggerSyllable(consonant, vowel)`
  - 現在の母音励振を一度下げる
  - sibilant ノイズを再生する
  - 子音末尾の `overlapSeconds` 位置から後続母音のフォルマントへ遷移する
  - 母音励振を短時間で戻す

## 音素パラメータ

`web/prototypes/vowel-formant-prototype/src/audio/phonemes.ts` に、最小限の sibilant プロファイルを置いた。

| 子音 | 中心周波数 Hz | Q | 長さ s | attack s | overlap s | peak gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `shi` | 6100 | 1.4 | 0.145 | 0.015 | 0.045 | 0.08 |
| `su` | 6000 | 1.0 | 0.155 | 0.015 | 0.050 | 0.07 |

中心周波数は、UTAU ノイズ分析で `し` / `す` が 6 kHz 前後の sibilant として分離しやすかったことを根拠にしている。

## UI

Web UI には、単体ノイズ確認用の `し noise` / `す noise` と、音素イベント確認用の以下のボタンを追加した。

- `し-a`
- `し-i`
- `し-e`
- `す-a`
- `す-u`
- `す-o`

音素イベントボタンは、後続母音を `VoiceEngine` の現在母音として更新する。これにより、フォルマント readout とスペクトルマーカーも後続母音へ更新される。

## 現時点の制約

- Web 側で生成音を WAV として保存する機能はまだないため、`compare_waveforms.py --mode transition` による定量比較は未実施である。
- `preutterance` / `overlap` は UTAU 全体の代表値を簡略化した固定値であり、音源・音素ごとの `oto.ini` を直接参照していない。
- 子音から母音へのフォルマント遷移は、現行の 166 ms 補間をそのまま使っている。実際の `し/す + 母音` では、母音ごとに立ち上がり時間を変える余地がある。

## 次の評価

次に定量評価へ進む場合は、Web または研究側に同じイベントをオフライン生成する経路を用意する。そのうえで、UTAU の `し` / `す` 系サンプルと以下を比較する。

- `dtw_log_spectral_distance_db`
- `rms_rise_delta_ms`
- `spectral_centroid_delta_hz`
- `air_band_ratio_delta`
- `noise_band_ratio_delta`

この評価により、ノイズの長さ、overlap、母音ゲイン立ち上がり、bandpass Q の調整方針を決められる。
