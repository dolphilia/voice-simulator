# HMM制御からWORLDへの文章入力合成の比較結果

2026-10-04。比較は終了したが、包括研究の品質目標は未達。固定変換を伴う別非ニューラル生成器の診断であり、純粋な位相/励起差、保存波形の再合成、知覚品質認定とは扱わない。

旧SRC前向き8文を診断再利用し、履歴照合後に新短4・長4を出力前固定した。6制御方法×2指定×16文×HTS/WORLDで384音声。支持はHTS native baselineだけから固定。共通利得min(1,.95/HTSrawpeak)*.25を両生成器へ適用し、候補peak・支持・閾値を結果で救済しなかった。

MCPをalpha .55の複素all-pass式へ展開し、power=exp(2logamp)/32768²へ変換。LPFから周期/雑音powerとAPを近似し、48k/FFT4096/5msでWORLD生成後24kへ変換。先頭frame複製と末尾240sample切りでフレームendpoint時計を対応させた。補間物理やAP推定がHTSと同じとは主張しない。保存の先生音声からスペクトルを解析して未知文に流用する機構ではない。

HTS_freqt(-alpha)の独立C対照との対数振幅差は最大 1.4210854715202004e-14。固定4合成fixtureの2反復も同波形。最初のimportはpkg_resources不足で音声生成前に失敗し、凍結環境を変更せず標準importlib.metadata入口の別版を保存した。元package/native binary/失敗を保持し、自己検査の浮動小数220Hz equalityだけrtol1e-12にした。科学条件は不変。

旧96の共通.25利得波形・状態・LF0一致、384 E0通過、通常/隔離20組の40実行80生成一致、NN/教師/旧結果/保存波形/network実拒否を確認。元コードのbaseline_pre_headroomという補助field名は今回には不正確で、実検査は旧SRCの既に.25適用済みwaveとの一致。completion-auditの正確な記述を用いる。利用通知とWORLD/PyWORLD/HTS通知を最終bundleへ保持。

全群と支持の結果:

cohort legacy_diagnostic
- native: whisper 26→21/304、不通過群2; reazon 15→18/304、不通過群6; 固定支持欠損対 0→3
- direct_non_neural: whisper 21→24/304、不通過群11; reazon 16→18/304、不通過群6; 固定支持欠損対 2→4
- neural: whisper 30→25/304、不通過群5; reazon 18→18/304、不通過群4; 固定支持欠損対 3→5
- distilled_non_neural: whisper 25→23/304、不通過群4; reazon 16→21/304、不通過群9; 固定支持欠損対 2→4
- direct_prosody: whisper 21→23/304、不通過群11; reazon 16→19/304、不通過群8; 固定支持欠損対 3→4
- distilled_prosody: whisper 22→22/304、不通過群7; reazon 15→15/304、不通過群0; 固定支持欠損対 3→4

cohort prospective_once
- native: whisper 31→26/308、不通過群6; reazon 11→8/308、不通過群2; 固定支持欠損対 0→2
- direct_non_neural: whisper 31→35/308、不通過群11; reazon 6→4/308、不通過群5; 固定支持欠損対 5→4
- neural: whisper 39→37/308、不通過群0; reazon 14→21/308、不通過群12; 固定支持欠損対 2→2
- distilled_non_neural: whisper 32→32/308、不通過群8; reazon 6→2/308、不通過群4; 固定支持欠損対 4→3
- direct_prosody: whisper 29→28/308、不通過群7; reazon 7→8/308、不通過群6; 固定支持欠損対 4→4
- distilled_prosody: whisper 34→31/308、不通過群7; reazon 14→7/308、不通過群0; 固定支持欠損対 4→4

資格判定: {"native": {"both_asr_both_cohorts_non_worsening": false, "old_engineering_and_support": false, "limited_diagnostic_supported": false, "quality_certified": false}, "direct_non_neural": {"both_asr_both_cohorts_non_worsening": false, "old_engineering_and_support": false, "limited_diagnostic_supported": false, "quality_certified": false}, "neural": {"both_asr_both_cohorts_non_worsening": false, "old_engineering_and_support": false, "limited_diagnostic_supported": false, "quality_certified": false}, "distilled_non_neural": {"both_asr_both_cohorts_non_worsening": false, "old_engineering_and_support": false, "limited_diagnostic_supported": false, "quality_certified": false}, "direct_prosody": {"both_asr_both_cohorts_non_worsening": false, "old_engineering_and_support": false, "limited_diagnostic_supported": false, "quality_certified": false}, "distilled_prosody": {"both_asr_both_cohorts_non_worsening": false, "old_engineering_and_support": false, "limited_diagnostic_supported": false, "quality_certified": false}}

平均/一認識器/一群の改善を全群・固定支持通過へ読み替えず、日本語自然さ資格と短イベント測定資格の不足を保持した。新8文は前向き診断、独立最終確認は未開封。

費用: {"setup": 16, "download": 200000, "dsp": 1193, "render": 472, "ai": 832, "audit": 5}。fit/教師/逆推定0。失敗と未予約import起動の保守計数はcost-audit参照。全予約終了、旧封印保持、個別予算上限は変更していない。

次は日本語で学習された第二ニューラル教師の取得条件・固定実行と、教師の音声を非ニューラル機構へ移す経路を検証する。WORLD/APの細かい事後探索を本確認集合で行わない。既存Kokoro教師との内容診断と、教師→WORLD分析再合成は共有未知文生成への移出と別段階として記録する。
