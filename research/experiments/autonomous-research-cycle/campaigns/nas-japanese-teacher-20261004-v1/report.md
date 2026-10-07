# 日本語教師とWORLD解析再合成の診断結果

2026-10-05。固定比較は終了。共有文章制御への移出と知覚品質は未検証で、包括研究の品質目標は未達。

Style-Bert-VITS2 JP-Extra/JVNV F1 NeutralをKokoro jf_alphaと比較した。モデル全体・声・G2P・内部正規化・依存版の差を含み、日本語学習だけの因果効果ではない。教師の内部attention時間は予測で、音響上の正解ではない。

既知4文は診断再利用、新短4/長4文は生成前に固定。新教師生成20回と旧Kokoro4波形で教師24音声を用意し、24のWORLD再合成と合わせ48音声を両認識器で評価した。全48波形は同じ24kHz入口・共通.25headroom。WORLDはDIO+StoneMask/5ms、CheapTrick FFT2048、D4C .85を用い、追加gain1・教師sample数へのcropを固定。保存教師音声を必要とする再合成であり、最終文章合成ではない。

結果（全文字数と整数誤り、固定群の不通過数）:

legacy_diagnostic
- teacher_jvnv_vs_kokoro: whisper 1→1/54、不通過群2; reazon 1→14/54、不通過群5
- WORLD_jvnv_vs_own_teacher: whisper 1→1/54、不通過群0; reazon 14→14/54、不通過群0
- WORLD_kokoro_vs_own_teacher: whisper 1→1/54、不通過群0; reazon 1→1/54、不通過群0
- WORLD_jvnv_vs_WORLD_kokoro: whisper 1→1/54、不通過群2; reazon 1→14/54、不通過群5

prospective_once
- teacher_jvnv_vs_kokoro: whisper 10→9/160、不通過群1; reazon 2→14/160、不通過群6
- WORLD_jvnv_vs_own_teacher: whisper 9→18/160、不通過群7; reazon 14→14/160、不通過群3
- WORLD_kokoro_vs_own_teacher: whisper 10→10/160、不通過群2; reazon 2→3/160、不通過群3
- WORLD_jvnv_vs_WORLD_kokoro: whisper 10→18/160、不通過群5; reazon 3→14/160、不通過群5

限定内容/再合成支持: False。E0全48: False。ASRの平均改善を自然さ認定へ読み替えない。独立最終確認は未開封。

新依存を専用prefixへ保存し、旧環境・全旧封印を維持した。最初のBERT検査は非persistent position_idsの照合先を修正して再照合した。生成前再読込の監査同値比較は、学習専用未保存キーの集合列挙順だけで失敗したため両側の同リストをソートした。元ソース・失敗・全重み厳密照合は保持し、科学設定や入力を変更していない。

費用: {"setup": 34, "download": 1669306871, "dsp": 196, "teacher": 20, "render": 24, "audit": 5, "ai": 96}。失敗attemptを含めcost-auditへ保存。キャンペーン上限は開始後変更していない。

利用条件・モデル由来を保存。コードAGPL-3.0、JVNV/BERT CC-BY-SA-4.0の条件を後続の研究資産にも引き継ぐ。公開・外部配布は本実験では行っていない。

次は本結果に基づいて共有制御の学習経路を登録する。教師内部時間を音響上の正解として使わず、音素対応とスペクトル表現の測定検査を先に行う。非ニューラル直接対照とニューラル経由蒸留を同じ入力資料で比較し、既知診断とは別の新文章を出力前に固定する。
