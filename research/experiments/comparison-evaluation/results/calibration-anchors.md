# 比較評価ベンチマーク

カテゴリ得点は診断用で、試聴校正前の総合点ではない。

| task | variant | split | gate | noise_frication | pitch_voicing | resonance | signal_integrity | source_voice_quality | spectral_timbre | timing_transition |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| anchor-human-clean | human-clean | development | pass | T - / H 75.1 | T 100.0 / H 98.2 | T 100.0 / H 67.3 | T 71.3 / H 54.8 | T 100.0 / H 83.0 | T 100.0 / H 70.2 | T - / H 50.0 |
| anchor-human-noise-20db | human-noise-20db | development | pass | T - / H 47.4 | T 100.0 / H 98.2 | T 12.3 / H 83.6 | T 73.4 / H 33.3 | T 99.8 / H 83.8 | T 87.0 / H 76.0 | T - / H 50.0 |
| anchor-human-noise-5db | human-noise-5db | development | pass | T - / H 0.0 | T 97.6 / H 98.2 | T 7.5 / H 69.2 | T 89.4 / H 33.3 | T 99.5 / H 68.4 | T 61.7 / H 64.8 | T - / H 50.0 |
| anchor-human-lowpass | human-lowpass | development | pass | T - / H 80.6 | T 99.9 / H 98.2 | T 59.9 / H 77.7 | T 69.6 / H 82.4 | T 99.9 / H 83.6 | T 55.2 / H 52.0 | T - / H 50.0 |
| anchor-human-pitch-formant-up | human-pitch-formant-up | development | pass | T - / H 42.9 | T 42.3 / H 90.4 | T 38.2 / H 82.4 | T 71.2 / H 73.9 | T 99.8 / H 84.6 | T 66.4 / H 64.7 | T - / H 50.0 |
| anchor-web-parallel-formant | web-parallel-formant | development | pass | T - / H 69.8 | T 25.0 / H 90.2 | T 12.8 / H 81.8 | T 92.0 / H 61.0 | T 99.3 / H 88.5 | T 67.1 / H 60.6 | T - / H 50.0 |
| anchor-harmonic-source-only | harmonic-source-only | development | pass | T - / H 46.4 | T 25.1 / H 90.2 | T 18.0 / H 46.5 | T 67.7 / H 33.3 | T 99.5 / H 82.0 | T 63.1 / H 50.6 | T - / H 50.0 |
| anchor-sine-only | sine-only | development | pass | T - / H 46.4 | T 33.4 / H 90.2 | T 2.1 / H 45.8 | T 51.7 / H 62.2 | T 97.2 / H 33.6 | T 42.6 / H 9.4 | T - / H 50.0 |

## Pareto候補

- anchor-human-clean
- anchor-human-noise-20db
- anchor-human-noise-5db
- anchor-web-parallel-formant

改善と悪化がカテゴリ間で併存する場合、その候補を一律に優位とは扱わない。

## 主な方向差

- anchor-human-clean: signal_integrity: level_delta_db +4.06 dB（生成側が高い／遅い）; spectral_timbre: spectral_centroid_hz_delta -0.00 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents -0.00 cent（生成側が低い／早い）; source_voice_quality: cpp_db_delta -0.00 dB（生成側が低い／早い）; resonance: b1_delta_hz -0.00 Hz（生成側が低い／早い）
- anchor-human-noise-20db: signal_integrity: level_delta_db +3.71 dB（生成側が高い／遅い）; spectral_timbre: spectral_centroid_hz_delta +13.86 Hz（生成側が高い／遅い）; pitch_voicing: f0_median_delta_cents +0.05 cent（生成側が高い／遅い）; source_voice_quality: cpp_db_delta -4.25 dB（生成側が低い／早い）; resonance: f3_delta_hz +970.32 Hz（生成側が高い／遅い）
- anchor-human-noise-5db: signal_integrity: level_delta_db +1.35 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta +2727.22 Hz（生成側が高い／遅い）; pitch_voicing: f0_median_delta_cents -1.47 cent（生成側が低い／早い）; source_voice_quality: hnr_db_delta -9.50 dB（生成側が低い／早い）; resonance: f3_delta_hz +1385.26 Hz（生成側が高い／遅い）
- anchor-human-lowpass: signal_integrity: level_delta_db +4.35 dB（生成側が高い／遅い）; spectral_timbre: spectral_centroid_hz_delta -66.82 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents +0.15 cent（生成側が高い／遅い）; source_voice_quality: cpp_db_delta +2.20 dB（生成側が高い／遅い）; resonance: b1_delta_hz -393.55 Hz（生成側が低い／早い）
- anchor-human-pitch-formant-up: signal_integrity: level_delta_db +4.07 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta +427.46 Hz（生成側が高い／遅い）; pitch_voicing: f0_median_delta_cents +382.16 cent（生成側が高い／遅い）; source_voice_quality: cpp_db_delta +3.51 dB（生成側が高い／遅い）; resonance: b1_delta_hz -411.41 Hz（生成側が低い／早い）
- anchor-web-parallel-formant: signal_integrity: level_delta_db +0.99 dB（生成側が高い／遅い）; spectral_timbre: spectral_centroid_hz_delta +266.81 Hz（生成側が高い／遅い）; pitch_voicing: f0_median_delta_cents -788.50 cent（生成側が低い／早い）; source_voice_quality: cpp_db_delta +16.74 dB（生成側が高い／遅い）; resonance: f3_delta_hz +493.60 Hz（生成側が高い／遅い）
- anchor-harmonic-source-only: signal_integrity: level_delta_db +4.68 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta +467.05 Hz（生成側が高い／遅い）; pitch_voicing: f0_median_delta_cents -785.69 cent（生成側が低い／早い）; source_voice_quality: cpp_db_delta +15.12 dB（生成側が高い／遅い）; resonance: f3_delta_hz +754.51 Hz（生成側が高い／遅い）
- anchor-sine-only: signal_integrity: level_delta_db +7.91 dB（生成側が高い／遅い）; spectral_timbre: spectral_rolloff_hz_delta -1508.83 Hz（生成側が低い／早い）; pitch_voicing: f0_median_delta_cents -773.12 cent（生成側が低い／早い）; source_voice_quality: h1_h2_db_delta +64.42 dB（生成側が高い／遅い）; resonance: f3_delta_hz +1717.48 Hz（生成側が高い／遅い）

## 方式別中央値

| variant | category | target | human-likeness |
| --- | --- | ---: | ---: |
| human-clean | signal_integrity | 71.3 | 54.8 |
| human-clean | spectral_timbre | 100.0 | 70.2 |
| human-clean | pitch_voicing | 100.0 | 98.2 |
| human-clean | source_voice_quality | 100.0 | 83.0 |
| human-clean | resonance | 100.0 | 67.3 |
| human-clean | noise_frication | - | 75.1 |
| human-clean | timing_transition | - | 50.0 |
| human-noise-20db | signal_integrity | 73.4 | 33.3 |
| human-noise-20db | spectral_timbre | 87.0 | 76.0 |
| human-noise-20db | pitch_voicing | 100.0 | 98.2 |
| human-noise-20db | source_voice_quality | 99.8 | 83.8 |
| human-noise-20db | resonance | 12.3 | 83.6 |
| human-noise-20db | noise_frication | - | 47.4 |
| human-noise-20db | timing_transition | - | 50.0 |
| human-noise-5db | signal_integrity | 89.4 | 33.3 |
| human-noise-5db | spectral_timbre | 61.7 | 64.8 |
| human-noise-5db | pitch_voicing | 97.6 | 98.2 |
| human-noise-5db | source_voice_quality | 99.5 | 68.4 |
| human-noise-5db | resonance | 7.5 | 69.2 |
| human-noise-5db | noise_frication | - | 0.0 |
| human-noise-5db | timing_transition | - | 50.0 |
| human-lowpass | signal_integrity | 69.6 | 82.4 |
| human-lowpass | spectral_timbre | 55.2 | 52.0 |
| human-lowpass | pitch_voicing | 99.9 | 98.2 |
| human-lowpass | source_voice_quality | 99.9 | 83.6 |
| human-lowpass | resonance | 59.9 | 77.7 |
| human-lowpass | noise_frication | - | 80.6 |
| human-lowpass | timing_transition | - | 50.0 |
| human-pitch-formant-up | signal_integrity | 71.2 | 73.9 |
| human-pitch-formant-up | spectral_timbre | 66.4 | 64.7 |
| human-pitch-formant-up | pitch_voicing | 42.3 | 90.4 |
| human-pitch-formant-up | source_voice_quality | 99.8 | 84.6 |
| human-pitch-formant-up | resonance | 38.2 | 82.4 |
| human-pitch-formant-up | noise_frication | - | 42.9 |
| human-pitch-formant-up | timing_transition | - | 50.0 |
| web-parallel-formant | signal_integrity | 92.0 | 61.0 |
| web-parallel-formant | spectral_timbre | 67.1 | 60.6 |
| web-parallel-formant | pitch_voicing | 25.0 | 90.2 |
| web-parallel-formant | source_voice_quality | 99.3 | 88.5 |
| web-parallel-formant | resonance | 12.8 | 81.8 |
| web-parallel-formant | noise_frication | - | 69.8 |
| web-parallel-formant | timing_transition | - | 50.0 |
| harmonic-source-only | signal_integrity | 67.7 | 33.3 |
| harmonic-source-only | spectral_timbre | 63.1 | 50.6 |
| harmonic-source-only | pitch_voicing | 25.1 | 90.2 |
| harmonic-source-only | source_voice_quality | 99.5 | 82.0 |
| harmonic-source-only | resonance | 18.0 | 46.5 |
| harmonic-source-only | noise_frication | - | 46.4 |
| harmonic-source-only | timing_transition | - | 50.0 |
| sine-only | signal_integrity | 51.7 | 62.2 |
| sine-only | spectral_timbre | 42.6 | 9.4 |
| sine-only | pitch_voicing | 33.4 | 90.2 |
| sine-only | source_voice_quality | 97.2 | 33.6 |
| sine-only | resonance | 2.1 | 45.8 |
| sine-only | noise_frication | - | 46.4 |
| sine-only | timing_transition | - | 50.0 |
