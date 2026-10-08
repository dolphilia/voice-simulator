# 既存6コホートの不採択理由整理

全方式を保持し、各比較内のnativeと照合した。コホート間の総率をpoolして優劣を推定しない。事後の記述診断で、旧ゲート・採否・知覚資格は変更していない。

|コホート/方式|件数|ピッチ通過|支持通過|支持欠測区間|Whisper誤り|Reazon誤り|悪化群W/R|
|---|---:|---:|---:|---:|---:|---:|---|
|absolute-f0/native|32|0|32|0|52/730|32/730|0/0|
|absolute-f0/calibrated|32|20|20|18|58/730|32/730|16/8|
|voicing-ap/native|32|0|32|0|52/644|14/644|0/0|
|voicing-ap/calibrated|32|18|18|16|43/644|23/644|4/11|
|voicing-ap/voicing|32|26|31|1|49/644|21/644|6/13|
|voicing-ap/aperiodicity|32|18|18|16|46/644|22/644|6/9|
|voicing-ap/combined|32|26|31|1|51/644|21/644|8/13|
|vocoder-f0/native|32|0|32|0|50/712|35/712|0/0|
|vocoder-f0/calibrated|32|12|12|26|41/712|32/712|4/11|
|vocoder-f0/voicing|32|24|27|5|47/712|28/712|10/9|
|vocoder-f0/hts_native|32|0|18|16|49/712|39/712|9/13|
|vocoder-f0/hts_calibrated|32|11|12|24|44/712|42/712|11/15|
|vocoder-f0/hts_voicing|32|25|30|2|52/712|35/712|13/12|
|mcp-postfilter/native|32|0|32|0|43/1160|22/1160|0/0|
|mcp-postfilter/postfilter|32|0|19|18|44/1160|22/1160|12/5|
|mcp-postfilter/voicing|32|22|25|7|44/1160|27/1160|13/15|
|mcp-postfilter/voicing_postfilter|32|16|19|21|49/1160|31/1160|16/17|
|mcp-postfilter/hts_native|32|0|25|7|38/1160|33/1160|5/15|
|mcp-postfilter/hts_postfilter|32|0|17|21|58/1160|37/1160|20/17|
|mcp-postfilter/hts_voicing|32|27|28|7|45/1160|35/1160|16/20|
|mcp-postfilter/hts_voicing_postfilter|32|20|21|17|55/1160|42/1160|22/23|
|gv-ablation/native|32|0|32|0|42/1062|13/1062|0/0|
|gv-ablation/voicing|32|22|25|8|45/1062|22/1062|13/13|
|gv-ablation/voicing_no_mcp_gv|32|29|30|2|60/1062|12/1062|21/0|
|gv-ablation/voicing_no_lf0_gv|32|30|30|2|33/1062|23/1062|2/14|
|gv-ablation/voicing_no_gv|32|31|31|1|57/1062|12/1062|20/0|
|gv-ap-interaction/native|32|0|32|0|62/1134|11/1134|0/0|
|gv-ap-interaction/voicing_no_lf0_gv|32|27|27|5|62/1134|20/1134|11/14|
|gv-ap-interaction/voicing_no_lf0_gv_ap_half|32|28|28|4|56/1134|19/1134|8/12|
|gv-ap-interaction/voicing_no_gv|32|30|30|2|75/1134|32/1134|18/15|
|gv-ap-interaction/voicing_no_gv_ap_half|32|30|30|2|78/1134|33/1134|20/15|

理由の件数は重複を許す。源LF0支持は保存control metadataで判別できるものだけを表示し、未知を推定で補完しない。
kana編集区分は保存済み認識結果の記述整理で、音素時刻対応や因果の証明には使わない。
第18回の人工周期資格と第22回の実励振周期診断は適用範囲を保持し、旧測定ゲート・採否・知覚資格へ広げない。
新しい生成・音響測定・ASR・教師・fit・逆推定・取得・一時ファイルは0。全体品質未達、P5未開封。
