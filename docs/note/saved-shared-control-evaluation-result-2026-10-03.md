# 保存済み共有モデルの未完評価：結果

2026-10-03。[承認された追加案](../plans/saved-shared-control-evaluation-followup-2026-10-03.md)を新ID `nas-saved-shared-eval-20261003-v1` で実施した。**未実施だった32隔離生成と320認識記録を完了した。依存除去と旧波形への一致は通過したが、直接・研究NN・学生のすべてが採択不通過。計画全体の品質目標は未達である。**

## 固定資産と保存の修正

旧16封印・8,120ファイルを開始・終了に照合した。17文の訓練目標、3学習済みモデル、160波形、辞書・前段・支持域・ASR設定を読み取り再利用した。fit・逆推定・追加教師・診断波形再生成・取得は0。旧個別JSON、WAV、圧縮集約、モデル、結果、計画書は変更していない。

JSONをUTF-8に符号化してから、実バイト数と台帳の余裕を予約し排他的に保存する経路へ接続した。bundle、集約、認識、隔離stdout、外部WAVを対象にし、書込後の容量と予約外変更を照合した。235MB集約の事前拒否、超過JSONが作られないこと、外部書込・外部出力の予約超過の検出、21内容群の欠損・悪化・空集合拒否を検査した。新manifestは**127,498 bytes**で、snapshotを含まず旧160個別記録のpath/hashを持つ。前campaignの容量超過を取り消す修正ではない。

## 非ニューラル単独実行

固定16係数の直接・学生bundleから、新8文×通常／変更×2方式の32件を生成し、**すべて旧通常実行のWAV SHA-256と完全一致**した。教師、訓練記録、ニューラル重み・推論エンジン、ネットワークの遮断検査が通過。発話別係数やWAV検索を配布していない。E0・内部不変も通過した。

最初のCLIは外側の実行環境で `sandbox_apply: Operation not permitted`（終了71）となり、検査本体は起動しなかった。生成・AI開始前に生成なしのOS隔離起動検査を行い、隔離を適用できる実行環境へ同じprofile・probeを渡した。起動拒否記録を残し、実検査の通過後にだけ32件を実行した。生成・AI失敗の再試行は0、OS遮断を省略していない。

## 内容保持

両認識器とも160件が完了。再利用候補304件をhash検証したが、今回の文・WAVの完全一致で使えた結果は0件で、**新AI320回**だった。全制御とモデルは認識前に固定し、認識後にfitへ戻っていない。かな誤りの分母は旧12文162字／条件、新8文141字／条件。

|集合・条件|認識器|既定|直接|研究NN|学生|
|---|---|---:|---:|---:|---:|
|旧12・通常|Whisper|12|11|11|12|
|旧12・変更|Whisper|8|8|10|10|
|旧12・通常|Reazon|9|5|6|8|
|旧12・変更|Reazon|10|10|3|10|
|新8・通常|Whisper|18|14|9|8|
|新8・変更|Whisper|8|11|8|12|
|新8・通常|Reazon|4|5|5|5|
|新8・変更|Reazon|5|8|6|10|

全体・短・長・4変更群×通常／変更／両方の**21群を、旧12文と新8文で別々に判定**した。通過群数は次の通りであり、21/21を必須にした。

|方式|旧12 Whisper / Reazon|新8 Whisper / Reazon|
|---|---|---|
|直接|21 / 21|18 / 11|
|研究NN|15 / 19|19 / 11|
|学生|15 / 19|15 / 9|

直接の旧12文では個別条件の悪化も0。新8文ではWhisperのwave-new-06変更が1→4誤り、Reazonのwave-new-00通常が0→1、wave-new-04変更が1→4だった。学生には追加の悪化もある。通常と変更を平均して悪化を隠さない。

辞書診断は96種類の保存仮説を調べた。曖昧候補がある記録はWhisper91、Reazon88。上位16字句経路の診断であり、読み候補で主CERを補正していない。両ASRの不一致を多数決で解決していない。

## F0・蒸留と欠損の診断

旧封印の音響判定を維持した。直接・学生は旧12文の通常／変更それぞれの全体・短・長F0-MSE非悪化と全体の厳密改善を通過。全体MSEは通常で既定10.232302→直接8.237943／学生8.305410、変更で既定11.968529→直接9.218255／学生9.259400だった。研究NNは旧通常2条件の支持域欠損により不通過。

直接・学生は新8文で各3条件の支持域欠損。直接には全体F0保護不通過1条件、学生は0。研究NNは欠損5・全体制御不通過15条件。どれも支持域を削除・補間・変更していない。

全3方式の支持域が揃う22/24旧条件、11/16新条件に限る形状対照では、直接と学生のMSE平均は旧0.002427・新0.001722、NNと学生は旧2.027468・新1.110880。欠損7条件を除いた記述統計であり、完全な蒸留合格を意味しない。研究NNの訓練MSE0.064886に対し直接0.445620、学生0.447843で、同じ16係数の学生へ移す段階で改善の多くが失われた。

保存DIOとMLPG LF0列のみを読む追加診断で、欠損11条件すべてにおいて内部LF0の範囲内有声フレーム数とMSD・継続長の保持を確認した。/u/の6条件は既定DIO有声率がちょうど50%で、候補では1〜2フレーム減少。残5条件には1.0→0.2、0.941→0等の大きな脱落もあった。これは計測不安定と実励起変化をまだ区別できない証拠であり、計測器だけが悪いとは結論しない。F0再推定、新合成、追加ASRは行っていない。

## 費用・失敗・終了

上限1時間・100MB・render32・AI320・fit/教師/取得0に対し、終了監査は**469.975秒・13,622,074 bytes、render32・AI320・setup5・audit6**。全予約ジョブ終了、未終了プロセス0。生成・AIの失敗0、台帳の補助失敗2はOS隔離の未起動と辞書utilityのimport接続不備だった。

辞書utilityが未使用の`verify_seal`互換名をimportするため、初版集計が停止した。初版と失敗記録を残し、別集計版で互換名を接続し、同じ保存済み認識・同じ群・閾値を集計した。モデル・認識器・判定条件を変更していない。大きな状態snapshotはこの集計のメモリにも保持しない。

今回の100MB・1時間上限は順守。資料・封印を含む最終値はartifact-sealに保存する。現在のcampaignを閉じ、未使用枠を後続へ足さない。

## 次の方向

追加fitを繰り返す前に、[同じパラメータ列で音源とフィルタを切り分ける案](../plans/source-filter-counterfactual-proposal-2026-10-03.md)を用意した。欠損11条件と対応既定7条件の18列で、既定再合成・スペクトル平坦化・単純励起を比較する。既存Vocoder公開シンボルの存在は生成なしで検査したが、新wrapper・対照生成は未実施。新1時間・100MB・render54・AI0の別枠案であり、自動的に開始していない。

未知文共有制御の採択、日本語非ニューラル知覚資格、局所タイミング・閉鎖・開放・摩擦・声質、独立最終品質確認が残る。依存除去の成功を自然さの合格や計画全体の完了と記録しない。

## 成果物

- [実装](../../research/experiments/saved-shared-control-evaluation/README.md)・[集計](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/summary.json)
- [単独実行](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/runtime-audit.json)・[小さいmanifest](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/render-manifest.json)
- [支持域診断](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/support-cause-audit.json)・[保存と群の負例](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/negative-tests.json)
- [終了監査](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/completion-audit.json)・[費用](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/cost-audit.json)・[封印](../../research/experiments/saved-shared-control-evaluation/results/nas-saved-shared-eval-20261003-v1/artifact-seal.json)
