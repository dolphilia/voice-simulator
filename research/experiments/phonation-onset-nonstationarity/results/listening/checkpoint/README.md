# 第1試聴チェックポイント

自動工程で15提示（13比較＋重複2）を凍結済みです。各 `Txx-A.wav` と `Txx-B.wav` を比較します。

`responses.csv` の回答規則:

- `more_human`, `more_natural_onset`, `more_natural_sustain`: `A`, `B`, `TIE`
- `artifact`: 加工由来の違和感が強い側を `A`, `B`, `BOTH`, `NEITHER`
- `confidence`: 1（ほぼ分からない）〜5（明確）
- `notes`: 掠れ、息、舌足らず、楽器的、ループ感など任意の理由

音量を固定し、提示順に評価してください。疲れた場合は途中で中断できます。 `presentation-key.csv` は解析用であり、ブラインド試聴前には参照しません。
