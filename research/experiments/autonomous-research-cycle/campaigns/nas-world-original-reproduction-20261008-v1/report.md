# 未観測原WORLDと旧PyWORLDの再現対照

固定4例のhookなし原実装の旧波形一致: 3/4。installed C直呼びと旧bindingの一致: 4/4。
全768対照の実施件数: 0。完全一致条件を緩和せず、4例不通過なら全件へ進まない。

原synthesis.cppをbyte不変で同じO2/SDK条件へ再buildした。公開関数名とwrapper ABI/build contextは差の要因に含む。元wheelのcompile flagsは断定しない。rawと最終float32の差、差の位置、切捨て前後を保持した。

今回は観測hookなしの再構成対照で、内部の実励振traceはない。旧WORLD768件の実励振unknownと固定支持欠測155を保持する。旧observerの3attempt不通過やASR/採否は上書きしない。

原実装が一致すればobserverの観測箇所/演算効果を別因子で検証。不一致なら旧768を未知のまま閉じ、独立に検証できる別版と有効なHTS測定/生成へ進む。
