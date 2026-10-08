# 新4知覚資料の公開範囲監査

旧8資料を反復せず、新4資料の一次公開メタデータを上限付きで保存した。実音声・モデル・個別評点ファイルの取得0、校正0。全条件の通過候補0/4。日本語知覚資格なし・P5未開封・品質未達。

|資料|確認範囲|不足/判断|
|---|---|---|
|SpeechJudge-Data|公開カードは中国語/英語の単一・交差・混合言語と人による自然さ比較を記載。日本語は記載なし。実ファイルは連絡先と利用条件の同意を要するgated資料。|中国語/英語の評点を日本語HTSの校正へ移さない。gatedファイルへアクセスせず、同意・申請・連絡を行わない。カードのCC BY-NC 4.0と実ファイル利用資格を区別。|
|AnimeScore|日本語のアニメらしさをA/B比較から順位学習する資料。READMEは3,000発話、187評定者、15,000対を記載。元音声は含まれず各コーパスの条件に依存。CER/UTMOSによる選別を含む。|アニメらしさの選好を自然さMOSと同一視しない。UTMOSは人の自然さ評点ではない。READMEのMIT表記を元音声の許諾へ移さず、掲載DOIの出版確認も主張しない。|
|Expressive-Japanese-Character-TTS-2505.17320v2|VITS/SBV2のキャラクター音声比較。日本語母語話者11人の60音声評定と5人のCMOSを本文で記載。公表値は集約評点。音声学習用の収録資料と評価用の刺激を区別。|刺激・個別評点・利用条件の公開対応を特定できない。記事のCC BY-NC-SA 4.0をキャラクター音声・モデルの許諾へ転用しない。集約MOSを現HTSの品質証明にしない。|
|Humanlike-Japanese-JNLP-33-186|日本語FastPitch/WaveGANの中立/非流暢5対を106人が人間らしさで比較。本文は刺激公開頁を案内する一方、学習コーパスは制限付き私有資料。本文の公開評点は属性別の集約数。|刺激頁の存在を認める。頁の取得失敗を不存在と解釈しない。5対の内容/フィラー等の差と現HTS源・フィルタ劣化を区別し、個別評点と音声利用条件の対応未確認を保持する。記事CC BY 4.0を音声許諾へ転用しない。|

SpeechJudge-Data: [一次資料1](https://huggingface.co/api/datasets/RMSnow/SpeechJudge-Data), [一次資料2](https://huggingface.co/datasets/RMSnow/SpeechJudge-Data), [一次資料3](https://speechjudge.github.io/)

AnimeScore: [一次資料1](https://raw.githubusercontent.com/sizigi/animescore/main/README.md), [一次資料2](https://raw.githubusercontent.com/sizigi/animescore/main/data/README.md), [一次資料3](https://github.com/sizigi/animescore)

Expressive-Japanese-Character-TTS-2505.17320v2: [一次資料1](https://arxiv.org/html/2505.17320v2)

Humanlike-Japanese-JNLP-33-186: [一次資料1](https://www.jstage.jst.go.jp/article/jnlp/33/1/33_186/_article/-char/en), [一次資料2](https://www.speech-data.jp/kaken_hiryu/synthesis/ntl_vs_dis/)

取得失敗は不存在を意味しない。記事・コード・モデル・音声の許諾を区別し、gated同意/申請/連絡をしていない。メタデータのhashは実刺激/個別評点の照合を代替しない。

同資料の同条件探索を凍結。レビュー第5回分岐の異なる共有文脈/韻律表現を出力前登録する。
