# B9+G40 Web統合監査

作成日: 2026-08-26

状態: 設計完了・実装保留（listener-qualified release待ち）

## 結論

現行 `vowel-formant-prototype` のパラメータを差し替えるだけでは、研究側B9+G40と同じ生成機構にならない。既存エンジンを維持したまま、明示DSPによる研究release専用エンジンを別経路として追加する必要がある。

## 実装差

| 項目 | 研究B9+G40 | 現行Web |
|---|---|---|
| 音源 | 位相積分saw | `OscillatorNode` sawtooth |
| スペクトル傾斜 | 600 Hz一次low-pass | brightnessによるformant gain補正 |
| 微細変動 | 6 Hz以下、F0 0.64%、振幅0.67 dB、相関0.5 | なし |
| 声道 | 3段cascade all-pole | 3本parallel bandpass |
| onset | 40 ms正弦二乗gain attack | 通常startに専用attackなし |
| 母音 `/a/` | 800/1200/2500 Hz | referenceは730/1090/2440 Hz |
| 再現性 | seed・manifest・hashを凍結 | breath noiseに`Math.random()` |

この差は単なる数値差ではなく、グラフ構造と時間制御の差である。既存 `VoiceEngine` のformant値だけを書き換えて研究成果を統合したことにはしない。

## 統合方針

1. 現行 `VoiceEngine` とUI既定値を維持する。
2. `ExplicitVoiceEngine`相当の別実装を追加し、初期はopt-inとする。
3. source、tilt、微細変動、cascade極、gain attackを通常のTypeScript DSPとして実装する。
4. 録音断片や生成AI音声は使用しない。
5. release manifestからパラメータを読み、手作業で別の値を二重管理しない。
6. ブラウザsample rate差があるためPCM hash一致は要求せず、パラメータと音響指標の回帰を要求する。
7. 220 Hz `/a/` から実装し、F0・5母音・attack scalingの順にlistener-qualified範囲だけを開放する。

## 実装開始条件

骨格やテストfixtureの準備は先行可能だが、Webの利用可能プリセットとして公開するのは該当する知覚ゲート通過後とする。未合格候補を既定値へ入れない。

機械可読な契約は `research/experiments/synthetic-vowel-baseline/config/web-integration-contract.json` に置く。
