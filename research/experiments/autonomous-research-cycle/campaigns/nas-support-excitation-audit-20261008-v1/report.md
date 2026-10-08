# 固定有声支持と実励振の欠測診断

既存992件の固定支持区間をすべて保持し、旧DIOのclock・有声件数・支持欠測を再照合した。WORLD768件は互換不通過のため実励振unknownを保持。HTS224件は旧128traceと、旧WAV完全一致の追加96traceを使用した。

|コホート/方式|支持区間|欠測|欠測源区分|
|---|---:|---:|---|
|nas-absolute-f0/native|820|0|{}|
|nas-absolute-f0/calibrated|820|18|{'WORLD_unknown_compatibility_nonpass': 18}|
|nas-voicing-ap/native|719|0|{}|
|nas-voicing-ap/calibrated|719|16|{'WORLD_unknown_compatibility_nonpass': 16}|
|nas-voicing-ap/voicing|719|1|{'WORLD_unknown_compatibility_nonpass': 1}|
|nas-voicing-ap/aperiodicity|719|16|{'WORLD_unknown_compatibility_nonpass': 16}|
|nas-voicing-ap/combined|719|1|{'WORLD_unknown_compatibility_nonpass': 1}|
|nas-vocoder-f0/native|797|0|{}|
|nas-vocoder-f0/calibrated|797|26|{'WORLD_unknown_compatibility_nonpass': 26}|
|nas-vocoder-f0/voicing|797|5|{'WORLD_unknown_compatibility_nonpass': 5}|
|nas-vocoder-f0/hts_native|797|16|{'pulse_present_acoustic_ambiguity': 16}|
|nas-vocoder-f0/hts_calibrated|797|24|{'pulse_present_acoustic_ambiguity': 24}|
|nas-vocoder-f0/hts_voicing|797|2|{'pulse_present_acoustic_ambiguity': 2}|
|nas-mcp-postfilter/native|1253|0|{}|
|nas-mcp-postfilter/postfilter|1253|18|{'WORLD_unknown_compatibility_nonpass': 18}|
|nas-mcp-postfilter/voicing|1253|7|{'WORLD_unknown_compatibility_nonpass': 7}|
|nas-mcp-postfilter/voicing_postfilter|1253|21|{'WORLD_unknown_compatibility_nonpass': 21}|
|nas-mcp-postfilter/hts_native|1253|7|{'pulse_present_acoustic_ambiguity': 7}|
|nas-mcp-postfilter/hts_postfilter|1253|21|{'pulse_present_acoustic_ambiguity': 21}|
|nas-mcp-postfilter/hts_voicing|1253|7|{'pulse_present_acoustic_ambiguity': 7}|
|nas-mcp-postfilter/hts_voicing_postfilter|1253|17|{'pulse_present_acoustic_ambiguity': 17}|
|nas-gv-ablation/native|1135|0|{}|
|nas-gv-ablation/voicing|1135|8|{'WORLD_unknown_compatibility_nonpass': 8}|
|nas-gv-ablation/voicing_no_mcp_gv|1135|2|{'WORLD_unknown_compatibility_nonpass': 2}|
|nas-gv-ablation/voicing_no_lf0_gv|1135|2|{'WORLD_unknown_compatibility_nonpass': 2}|
|nas-gv-ablation/voicing_no_gv|1135|1|{'WORLD_unknown_compatibility_nonpass': 1}|
|nas-gv-ap-interaction/native|1177|0|{}|
|nas-gv-ap-interaction/voicing_no_lf0_gv|1177|5|{'WORLD_unknown_compatibility_nonpass': 5}|
|nas-gv-ap-interaction/voicing_no_lf0_gv_ap_half|1177|4|{'WORLD_unknown_compatibility_nonpass': 4}|
|nas-gv-ap-interaction/voicing_no_gv|1177|2|{'WORLD_unknown_compatibility_nonpass': 2}|
|nas-gv-ap-interaction/voicing_no_gv_ap_half|1177|2|{'WORLD_unknown_compatibility_nonpass': 2}|

源が全無声、区間内パルス0、4パルス未満、パルス存在下の音響曖昧、WORLD未確認を分けた。4パルス条件は第25回の窓内平均発生率に必要な3完全間隔であり、旧支持や知覚ゲートを変えていない。
パルスがあってもLPF後の周期エネルギー・SNR・残響・非定常性の影響が残るため、DIOの欠測を測定器の失敗だけに断定しない。無励振区間の残響も保持する。源LF0の全有声は実励振truthではない。
短窓/動的測定と源区分は事後診断に限定。旧ASR/採否/P5を更新しない。次は全結果と二ASR悪化群を統合し、追加制御比較の可否と必要条件を判断する。
