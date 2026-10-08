# 句/アクセント指令の共有文脈韻律機構

原論文Fig2のalpha=3/beta=20/gamma=.9を参照し、Ap=.15秒/Aa=.25/句先行.2秒と時刻規則を出力前に固定した。原有声LF0値の輪郭を使わず、生成maskとHMM状態長・A/F/I文脈から指令を作る。教師/録音/残差学習/発話lookupなし。原pulse/noise/MLSAとgain=.25を保持する。

独立LTIのimpulse/step、独立scalar重畳、将来指令の前半不変、不正入力拒否、人工ラベル時刻、全8実条件のMCP/LPF/duration/MSD/state/variance不変、native配列入口の完全一致を確認した。原native8・候補8・独立native8の24HTS生成。応答/輪郭分を含め80render/256DSPを保守的に課し返金しない。

句/アクセント応答は因果的だが、全発話有声中央値の校正はstreaming因果ではない。F2の末尾核/無アクセント同値化を保持し音韻正解を仮定しない。モデルの典型値をMeiの測定値/最適値と主張せず、機構通過を自然さ・内容・知覚pitchの資格へ拡張しない。方式間のLF0/源時計は意図して異なる。

一次資料: [Fujisaki and Hirose (1984)](https://www.jstage.jst.go.jp/article/ast1980/5/4/5_4_233/_pdf)、[Open JTalkラベル定義](https://raw.githubusercontent.com/r9y9/open_jtalk/master/src/jpcommon/jpcommon_label.c)。式と文脈定義を参照した独自実装。

全機構通過時のみ新16文のnative/Fujisakiを別登録し、固定支持・二ASR・通常/隔離CLIを同じ全分母で比較。不改善時は同応答係数/指令時刻/gainを同コホートで救済しない。

P5未開封・日本語知覚資格なし・品質未達。
