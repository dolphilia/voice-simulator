# 追加4枠の測定・励振・内容保護の統合

第25〜27回の結果と、6コホート31方式・992既存波形・1,984既存ASR記録の二認識器33群を統合した。全方式の旧資格は不通過のまま。コホート内のnative対照を保持し、コホート間の総率で順位を作らない。

現時点で、新たな係数比較の採否を旧DIO/ACFだけで判断する根拠は不足している。HTSの源時計は224件確認できたが、LPF後の周期寄与・知覚pitchは未確認。WORLD768件の実励振は互換不通過のためunknown。短窓・動的区間へ安定60ms資格を流用できない。

|コホート/方式|ピッチ通過/32|支持欠測区間|悪化群W/R|
|---|---:|---:|---|
|nas-absolute-f0/native|0|0|0/0|
|nas-absolute-f0/calibrated|20|18|16/8|
|nas-voicing-ap/native|0|0|0/0|
|nas-voicing-ap/calibrated|18|16|4/11|
|nas-voicing-ap/voicing|26|1|6/13|
|nas-voicing-ap/aperiodicity|18|16|6/9|
|nas-voicing-ap/combined|26|1|8/13|
|nas-vocoder-f0/native|0|0|0/0|
|nas-vocoder-f0/calibrated|12|26|4/11|
|nas-vocoder-f0/voicing|24|5|10/9|
|nas-vocoder-f0/hts_native|0|16|9/13|
|nas-vocoder-f0/hts_calibrated|11|24|11/15|
|nas-vocoder-f0/hts_voicing|25|2|13/12|
|nas-mcp-postfilter/native|0|0|0/0|
|nas-mcp-postfilter/postfilter|0|18|12/5|
|nas-mcp-postfilter/voicing|22|7|13/15|
|nas-mcp-postfilter/voicing_postfilter|16|21|16/17|
|nas-mcp-postfilter/hts_native|0|7|5/15|
|nas-mcp-postfilter/hts_postfilter|0|21|20/17|
|nas-mcp-postfilter/hts_voicing|27|7|16/20|
|nas-mcp-postfilter/hts_voicing_postfilter|20|17|22/23|
|nas-gv-ablation/native|0|0|0/0|
|nas-gv-ablation/voicing|22|8|13/13|
|nas-gv-ablation/voicing_no_mcp_gv|29|2|21/0|
|nas-gv-ablation/voicing_no_lf0_gv|30|2|2/14|
|nas-gv-ablation/voicing_no_gv|31|1|20/0|
|nas-gv-ap-interaction/native|0|0|0/0|
|nas-gv-ap-interaction/voicing_no_lf0_gv|27|5|11/14|
|nas-gv-ap-interaction/voicing_no_lf0_gv_ap_half|28|4|8/12|
|nas-gv-ap-interaction/voicing_no_gv|30|2|18/15|
|nas-gv-ap-interaction/voicing_no_gv_ap_half|30|2|20/15|

固定支持は計31601区間、欠測は249区間。欠測の源区分: {'WORLD_unknown_compatibility_nonpass': 155, 'pulse_present_acoustic_ambiguity': 94}。
源の無声/短いパルス列と、パルス存在下の音響的な曖昧さを分けた。後者には周期成分の弱さ、SNR、残響、非定常、測定器の限界が混在し、測定器の失敗と断定しない。WORLDは未確認を保持した。kana編集は音素時刻と対応付けない。
次は既存HTSのLPF後周期成分、WORLDの未観測原実装の演算再現、短窓/動的測定の対象範囲を検証する。新しい人の回答をこれらの研究の必須条件にしない。知覚資格・独立P5は未充足で、全体品質は未達。
