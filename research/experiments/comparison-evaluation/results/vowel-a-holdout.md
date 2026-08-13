# 比較評価ベンチマーク

カテゴリ得点は診断用で、試聴校正前の総合点ではない。

| task | variant | split | gate | noise_frication | pitch_voicing | resonance | signal_integrity | source_voice_quality | spectral_timbre | timing_transition |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| a-holdout-original-01 | original | holdout | pass | T - / H 77.9 | T 38.1 / H 98.5 | T 19.1 / H 85.2 | T 16.2 / H 87.4 | T 98.9 / H 69.4 | T 59.4 / H 61.7 | T - / H 50.0 |
| a-holdout-original-05 | original | holdout | pass | T - / H 77.0 | T 30.0 / H 98.0 | T 18.3 / H 62.5 | T 30.2 / H 92.4 | T 99.1 / H 88.1 | T 63.0 / H 68.6 | T - / H 50.0 |
| a-holdout-original-10 | original | holdout | pass | T - / H 77.4 | T 37.3 / H 98.3 | T 44.5 / H 92.1 | T 32.7 / H 88.4 | T 99.1 / H 86.8 | T 59.2 / H 64.5 | T - / H 50.0 |
| a-holdout-improved-03 | spectral-match | holdout | pass | T - / H 77.5 | T 33.2 / H 98.3 | T 29.8 / H 94.8 | T 34.2 / H 89.9 | T 99.1 / H 86.7 | T 60.8 / H 64.2 | T - / H 50.0 |
| a-holdout-improved-07 | spectral-match | holdout | pass | T - / H 87.5 | T 34.1 / H 98.3 | T 41.9 / H 77.6 | T 19.0 / H 94.1 | T 99.2 / H 88.1 | T 63.3 / H 63.2 | T - / H 50.0 |
| a-holdout-improved-10 | spectral-match | holdout | pass | T - / H 87.5 | T 30.8 / H 98.3 | T 18.2 / H 75.7 | T 35.6 / H 95.5 | T 99.1 / H 88.3 | T 59.9 / H 60.9 | T - / H 50.0 |

## Pareto候補

- a-holdout-original-01
- a-holdout-original-05
- a-holdout-original-10
- a-holdout-improved-03
- a-holdout-improved-07
- a-holdout-improved-10

改善と悪化がカテゴリ間で併存する場合、その候補を一律に優位とは扱わない。

## 主な方向差

- a-holdout-original-01: signal_integrity: level_delta_db +21.83 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -622.26 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents -262.82 cent（生成側が低い／早い）; source_voice_quality: cpp_db_delta +19.26 dB（生成側が高い／遅い）; resonance: f3_delta_hz -1540.94 Hz（生成側が低い／早い）
- a-holdout-original-05: signal_integrity: level_delta_db +14.36 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -1333.77 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents +229.66 cent（生成側が高い／遅い）; source_voice_quality: cpp_db_delta +10.00 dB（生成側が高い／遅い）; resonance: f2_delta_hz +520.33 Hz（生成側が高い／遅い）
- a-holdout-original-10: signal_integrity: level_delta_db +13.41 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -789.01 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents -384.86 cent（生成側が低い／早い）; source_voice_quality: cpp_db_delta +10.98 dB（生成側が高い／遅い）; resonance: b2_delta_hz -831.36 Hz（生成側が低い／早い）
- a-holdout-improved-03: signal_integrity: level_delta_db +12.86 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -1369.57 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents +218.21 cent（生成側が高い／遅い）; source_voice_quality: hnr_db_delta +10.58 dB（生成側が高い／遅い）; resonance: f3_delta_hz -1433.49 Hz（生成側が低い／早い）
- a-holdout-improved-07: signal_integrity: level_delta_db +19.95 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -278.54 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents -252.79 cent（生成側が低い／早い）; source_voice_quality: cpp_db_delta +14.37 dB（生成側が高い／遅い）; resonance: b1_delta_hz -509.59 Hz（生成側が低い／早い）
- a-holdout-improved-10: signal_integrity: level_delta_db +12.40 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -1633.75 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents +214.99 cent（生成側が高い／遅い）; source_voice_quality: hnr_db_delta +11.30 dB（生成側が高い／遅い）; resonance: f3_delta_hz -1672.78 Hz（生成側が低い／早い）

## 方式別中央値

| variant | category | target | human-likeness |
| --- | --- | ---: | ---: |
| original | signal_integrity | 30.2 | 88.4 |
| original | spectral_timbre | 59.4 | 64.5 |
| original | pitch_voicing | 37.3 | 98.3 |
| original | source_voice_quality | 99.1 | 86.8 |
| original | resonance | 19.1 | 85.2 |
| original | noise_frication | - | 77.4 |
| original | timing_transition | - | 50.0 |
| spectral-match | signal_integrity | 34.2 | 94.1 |
| spectral-match | spectral_timbre | 60.8 | 63.2 |
| spectral-match | pitch_voicing | 33.2 | 98.3 |
| spectral-match | source_voice_quality | 99.1 | 88.1 |
| spectral-match | resonance | 29.8 | 77.6 |
| spectral-match | noise_frication | - | 87.5 |
| spectral-match | timing_transition | - | 50.0 |
