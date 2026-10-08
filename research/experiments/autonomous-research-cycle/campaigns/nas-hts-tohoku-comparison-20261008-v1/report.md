# 原Meiと公開Tohoku共有HMM全モデルの比較

新16文×2条件×2モデル64波形。全HMMを交換するため、MCP/LF0/LPF/duration/MSD/GVはモデル固有。辞書・labels・速度/指定中央値・MLPG/HTS・resample/fade/gain.25を共通化した。nativeの音素index支持を固定し、candidate固有の時間軸へ適用。通常/隔離64組・CLI4・実拒否を確認した。

|モデル|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|
|---|---:|---:|---:|---:|---:|
|native|32/32|32/32|0/688|0/33|0/33|
|tohoku|32/32|15/32|7/688|15/33|6/33|

二モデルの保存全44674frameで各モデル固有の状態長合計・列/hash・有限性・指定LF0中央値と固定音素支持を照合した。二モデル間の源時計/列一致や同標本の対比は主張しない。

HTS voice tohoku-f01、Copyright 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University。[公式配布](https://github.com/icn-lab/htsvoice-tohoku-f01)・[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。モデルは不改変、生成時の一様LF0制御と共通resample/fade/gainを変更として表示。Meiの元CC BY 3.0表示もbundleに保持する。提供者の推奨を主張しない。

旧31方式・支持31,601・欠測249・二ASR33群と凍結経路を保持。日本語知覚資格なし・P5未開封・品質未達。最終採択なし。

全件研究保護: {'native': True, 'tohoku': False}
全モデルの工学/二ASR結果を全分母で保持。全件保護と改善が確認できれば独立新入力へ別登録し、未通過を同コホートのstyle/補間/係数/gainで救済しない。資格不足の知覚を採択根拠にしない。
