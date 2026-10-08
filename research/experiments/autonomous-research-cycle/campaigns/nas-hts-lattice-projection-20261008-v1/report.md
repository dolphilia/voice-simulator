# 実MCPの全極近似と安定域の監査

保存新native32列の全20,276 frameを観測した。波形の読取/再生成0、係数調整0。原order34/alpha.55/FFT16384を固定し、32768は観測refinementだけに使った。

|native条件|全frame|通過frame|不通過frame|最大振幅RMSE dB|
|---|---:|---:|---:|---:|
|bound-fresh-00/neutral/native|326|219|107|3.28161828972432|
|bound-fresh-00/higher/native|286|179|107|3.2981905676303316|
|bound-fresh-01/neutral/native|363|231|132|3.7039523892855732|
|bound-fresh-01/higher/native|312|195|117|3.705438161680099|
|bound-fresh-02/neutral/native|331|221|110|3.3448271296295418|
|bound-fresh-02/higher/native|290|184|106|3.335940744082664|
|bound-fresh-03/neutral/native|361|250|111|3.5001291654456668|
|bound-fresh-03/higher/native|315|218|97|3.4944346061812404|
|bound-fresh-04/neutral/native|328|233|95|3.9700808676070922|
|bound-fresh-04/higher/native|286|195|91|3.9876202333604334|
|bound-fresh-05/neutral/native|325|207|118|3.7293844142794206|
|bound-fresh-05/higher/native|284|175|109|3.7714201519100405|
|bound-fresh-06/neutral/native|305|196|109|3.202484331416345|
|bound-fresh-06/higher/native|267|167|100|3.2343644025555927|
|bound-fresh-07/neutral/native|322|213|109|3.749868931099676|
|bound-fresh-07/higher/native|280|181|99|3.743432375250193|
|bound-fresh-08/neutral/native|973|563|410|4.449050361597182|
|bound-fresh-08/higher/native|847|462|385|4.420910261399726|
|bound-fresh-09/neutral/native|976|575|401|4.28970598187491|
|bound-fresh-09/higher/native|843|489|354|4.294163079563842|
|bound-fresh-10/neutral/native|1062|584|478|4.353367618991452|
|bound-fresh-10/higher/native|921|489|432|4.375909223211315|
|bound-fresh-11/neutral/native|1086|629|457|4.16797266258439|
|bound-fresh-11/higher/native|945|528|417|4.167204139248895|
|bound-fresh-12/neutral/native|986|602|384|4.615429773011685|
|bound-fresh-12/higher/native|858|510|348|4.616799408744382|
|bound-fresh-13/neutral/native|1079|646|433|4.6122593619094605|
|bound-fresh-13/higher/native|927|538|389|4.6039043968454845|
|bound-fresh-14/neutral/native|926|515|411|4.345519767391801|
|bound-fresh-14/higher/native|804|432|372|4.315605862955419|
|bound-fresh-15/neutral/native|1104|637|467|4.111752214592021|
|bound-fresh-15/higher/native|958|524|434|4.1311201429947815|

全件近似資格: False。2dB/独立解1e-10/refinement1e-8等は事前の操作的閾値で、自然さ・内容・動的安定や連続全周波数を保証しない。定義不能・不通過を分母から除外していない。既知ARの元14/16不通過も保持する。

同order/warp/loadingの係数救済を封印し、別の共有音響モデル/文脈表現または調音制御へ移る。旧17→96同8残差/同learnerの救済は継承しない。

旧欠測249/各ASR33群・全凍結は保持。知覚資格なし・P5未開封・品質未達。
