# Metric catalog 1.0.0

距離は特記がなければ小さいほど target に近い。単位、用途、不変条件を固定し、用途外の指標を総合判断へ混ぜない。

| 指標 | 単位 | カテゴリ | 主用途 | 不変にしたい変化 | 避ける用途 |
| --- | --- | --- | --- | --- | --- |
| clipping / silence / DC / Nyquist ratio | ratio | signal integrity | 入力・出力gate | なし | 自然さの順位付け |
| level delta | dB | signal integrity | 出力レベル差 | なし | 正規化後の音色 |
| F0 contour RMSE | cent | pitch / voicing | 音高軌跡 | 単純ゲイン、極性 | 声道共鳴 |
| F0 correlation / voicing F1 | ratio | pitch / voicing | 抑揚・有声判定 | 単純ゲイン | 定常無声音 |
| F1/F2/F3 delta | Hz | resonance | 声道共鳴 | 単純ゲイン、極性、先頭無音 | 自然さ全体 |
| B1/B2/B3 | Hz | resonance | 共鳴の鋭さ | 単純ゲイン | 短い無声音 |
| log-mel / MFCC distance | dB / coefficient | spectral / timbre | 知覚帯域上の包絡 | 単純ゲイン、極性、整列可能な遅延 | 厳密な位相回帰 |
| multi-resolution log-STFT | dB | spectral / timbre | 複数時間周波数解像度の差 | 単純ゲイン、極性 | 単独の自然さ判定 |
| centroid / rolloff / slope | Hz / dB/kHz | spectral / timbre | 明るさ・傾斜 | 単純ゲイン | 音素同一性の単独判定 |
| H1-H2 / HNR / CPP | dB | source / voice quality | 声門音源・周期性 | 単純ゲイン | 無声音 |
| flatness / ZCR | ratio | noise / frication | ノイズ性・摩擦性 | 単純ゲイン、極性 | 母音らしさ全体 |
| onset / duration / DTW warp | ms / ratio | timing / transition | 時間構造 | 音量正規化 | 定常区間の音色 |
| waveform RMSE / correlation | amplitude / ratio | waveform / phase | 決定論的回帰 | なし（極性にも反応） | 人間音声同士の自然さ |

## 欠損契約

- 推定不能は `null`、`available=false`、`confidence=0` と理由で表す。
- 欠損を距離0や満点へ置き換えない。
- カテゴリは coverage と confidence を併記する。
- listening との校正前はカテゴリをまたぐ正式な総合点を出さない。
