# 音声境界処理と内容認識の比較結果

2026-10-05。旧診断12文と出力前固定の新8文、二教師と各WORLD再合成に対し、raw、前後.9秒無音、12ms線形端点taper＋同無音を比較した。教師は新16生成、WORLD新16生成、旧48音声再利用。240境界音声を二認識器で評価し、完全同波形・同text・同reading・同engine契約の旧/同run結果だけ厳密再利用した。

Reazon公式K2 transcribe.pyはPAD_SECONDS=.9を用い、audio.pyのpad_audioは16k mono正規化の後に両側constant paddingする。今回は24k波形境界処理を二認識器に共通適用した対照で、公式resample入口全体と同一ではない。[公式transcribe.py](https://github.com/reazon-research/ReazonSpeech/blob/master/pkg/k2-asr/src/transcribe.py)、[公式audio.py](https://github.com/reazon-research/ReazonSpeech/blob/master/pkg/k2-asr/src/audio.py)。webで一次ソースを確認。任意のローカル原本保存は実行環境内のDNS解決失敗（原因未確定）で失敗し、原本hashは未取得。失敗の保守予約100KBは計数し、枠を事後増加しなかった。

paddingはspeechの全sampleを保持する。taperは両端各288sampleだけ変更し中間payloadを保持する。全長を正確に+43200sampleし、speech offset .9秒を記録した。追加peak正規化はしなかった。無音外端のE0だけで内部stepを隠さず、埋め込みspeech両端amplitude<=1e-6を工程支持の追加条件にした。これは自然さの測定資格ではない。

全分母の結果（baseline→candidateの整数誤り、文字数、固定7群の不通過数）:

legacy_diagnostic
- teacher/kokoro/pad_900ms/vs_raw: whisper 11→9/214、不通過群2; reazon 3→2/214、不通過群0
- teacher/kokoro/taper12ms_pad900ms/vs_raw: whisper 11→9/214、不通過群2; reazon 3→2/214、不通過群0
- teacher/jvnv/pad_900ms/vs_raw: whisper 10→13/214、不通過群4; reazon 28→2/214、不通過群0
- teacher/jvnv/taper12ms_pad900ms/vs_raw: whisper 10→14/214、不通過群4; reazon 28→3/214、不通過群0
- teacher/raw/jvnv_vs_kokoro: whisper 11→10/214、不通過群2; reazon 3→28/214、不通過群6
- teacher/pad_900ms/jvnv_vs_kokoro: whisper 9→13/214、不通過群4; reazon 2→2/214、不通過群1
- teacher/taper12ms_pad900ms/jvnv_vs_kokoro: whisper 9→14/214、不通過群5; reazon 2→3/214、不通過群3
- world/kokoro/pad_900ms/vs_raw: whisper 11→13/214、不通過群4; reazon 4→3/214、不通過群1
- world/kokoro/taper12ms_pad900ms/vs_raw: whisper 11→13/214、不通過群4; reazon 4→3/214、不通過群1
- world/jvnv/pad_900ms/vs_raw: whisper 19→16/214、不通過群0; reazon 28→2/214、不通過群0
- world/jvnv/taper12ms_pad900ms/vs_raw: whisper 19→18/214、不通過群2; reazon 28→2/214、不通過群0
- world/raw/jvnv_vs_kokoro: whisper 11→19/214、不通過群4; reazon 4→28/214、不通過群7
- world/pad_900ms/jvnv_vs_kokoro: whisper 13→16/214、不通過群3; reazon 3→2/214、不通過群2
- world/taper12ms_pad900ms/jvnv_vs_kokoro: whisper 13→18/214、不通過群4; reazon 3→2/214、不通過群2
- kokoro/raw/WORLD_vs_own_teacher: whisper 11→11/214、不通過群2; reazon 3→4/214、不通過群3
- kokoro/pad_900ms/WORLD_vs_own_teacher: whisper 9→13/214、不通過群6; reazon 2→3/214、不通過群4
- kokoro/taper12ms_pad900ms/WORLD_vs_own_teacher: whisper 9→13/214、不通過群6; reazon 2→3/214、不通過群4
- jvnv/raw/WORLD_vs_own_teacher: whisper 10→19/214、不通過群7; reazon 28→28/214、不通過群3
- jvnv/pad_900ms/WORLD_vs_own_teacher: whisper 13→16/214、不通過群5; reazon 2→2/214、不通過群2
- jvnv/taper12ms_pad900ms/WORLD_vs_own_teacher: whisper 14→18/214、不通過群5; reazon 3→2/214、不通過群1

prospective_once
- teacher/kokoro/pad_900ms/vs_raw: whisper 9→9/159、不通過群3; reazon 0→2/159、不通過群3
- teacher/kokoro/taper12ms_pad900ms/vs_raw: whisper 9→9/159、不通過群3; reazon 0→2/159、不通過群3
- teacher/jvnv/pad_900ms/vs_raw: whisper 20→21/159、不通過群3; reazon 20→4/159、不通過群0
- teacher/jvnv/taper12ms_pad900ms/vs_raw: whisper 20→21/159、不通過群3; reazon 20→3/159、不通過群0
- teacher/raw/jvnv_vs_kokoro: whisper 9→20/159、不通過群7; reazon 0→20/159、不通過群7
- teacher/pad_900ms/jvnv_vs_kokoro: whisper 9→21/159、不通過群6; reazon 2→4/159、不通過群5
- teacher/taper12ms_pad900ms/jvnv_vs_kokoro: whisper 9→21/159、不通過群6; reazon 2→3/159、不通過群3
- world/kokoro/pad_900ms/vs_raw: whisper 10→12/159、不通過群4; reazon 0→2/159、不通過群3
- world/kokoro/taper12ms_pad900ms/vs_raw: whisper 10→12/159、不通過群4; reazon 0→2/159、不通過群3
- world/jvnv/pad_900ms/vs_raw: whisper 21→20/159、不通過群1; reazon 29→4/159、不通過群0
- world/jvnv/taper12ms_pad900ms/vs_raw: whisper 21→21/159、不通過群2; reazon 29→4/159、不通過群0
- world/raw/jvnv_vs_kokoro: whisper 10→21/159、不通過群7; reazon 0→29/159、不通過群7
- world/pad_900ms/jvnv_vs_kokoro: whisper 12→20/159、不通過群6; reazon 2→4/159、不通過群5
- world/taper12ms_pad900ms/jvnv_vs_kokoro: whisper 12→21/159、不通過群6; reazon 2→4/159、不通過群5
- kokoro/raw/WORLD_vs_own_teacher: whisper 9→10/159、不通過群3; reazon 0→0/159、不通過群0
- kokoro/pad_900ms/WORLD_vs_own_teacher: whisper 9→12/159、不通過群5; reazon 2→2/159、不通過群0
- kokoro/taper12ms_pad900ms/WORLD_vs_own_teacher: whisper 9→12/159、不通過群5; reazon 2→2/159、不通過群0
- jvnv/raw/WORLD_vs_own_teacher: whisper 20→21/159、不通過群3; reazon 20→29/159、不通過群5
- jvnv/pad_900ms/WORLD_vs_own_teacher: whisper 21→20/159、不通過群1; reazon 4→4/159、不通過群1
- jvnv/taper12ms_pad900ms/WORLD_vs_own_teacher: whisper 21→21/159、不通過群1; reazon 3→4/159、不通過群3

新8文の内容全群＋工程支持: {"teacher/kokoro/pad_900ms/vs_raw": false, "teacher/kokoro/taper12ms_pad900ms/vs_raw": false, "teacher/jvnv/pad_900ms/vs_raw": false, "teacher/jvnv/taper12ms_pad900ms/vs_raw": false, "world/kokoro/pad_900ms/vs_raw": false, "world/kokoro/taper12ms_pad900ms/vs_raw": false, "world/jvnv/pad_900ms/vs_raw": false, "world/jvnv/taper12ms_pad900ms/vs_raw": false}

工程結果:
- raw: E0 40/80、埋め込みstep込み 40/80
- pad_900ms: E0 80/80、埋め込みstep込み 40/80
- taper12ms_pad900ms: E0 80/80、埋め込みstep込み 80/80

旧結果は保持した。旧12文の改善を独立確認へ数えず、新8文の境界対照も広い日本語自然さ・最終共有制御の成功とは扱わない。教師モデル/声/内部正規化差は単一原因に分離していない。WORLD再合成は教師波形を必要とし、非ニューラル未知文生成への移出は未検証。包括品質目標は未達。

費用: {"setup": 12, "audit": 7, "teacher": 16, "download": 100000, "dsp": 848, "render": 256, "ai": 384}。ASR新384、厳密再利用96。登録上限は増加せず、失敗はcost-auditへ保存した。旧全封印・教師/評価依存を維持した。

次の経路は新8文の全群と両認識器の結果を基に選ぶ。支持された教師・境界条件があれば、その音素対応/測定検査と低次元共有制御への移出を別campaignで登録し、直接非ニューラル対照とニューラル経由蒸留を同資料で比較する。条件が支持されなければ別教師または合成制御の表現へ切り替え、確認結果を使ったpadding長の探索は行わない。
