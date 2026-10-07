# 中心化先行の局所F0比較

承認済み1 campaign `nas-local-f0-projection-20261003-v1`。旧固定モデルを再利用し、射影順だけ変更。新8文・2条件・4方式の64波形を固定2認識器で評価した。全候補内容保護不通過、品質未認定。

実行順: campaign.py → prepare.py → entry_audit.py → render.py → evaluate.py --engine whisper → evaluate.py --engine reazon → summarize.py → support_audit.py → export_runtime.py → measurement_audit.py → closeout.py → seal.py。依存遮断はmacOS sandbox-execで実施。既存研究環境を使い、取得・共有モデル学習・教師追加を行わない。

全費用・失敗はresults内追記台帳、生成前契約・結果・終了監査は別ファイルに保存する。封印後は追加ジョブを拒否。旧成果の変更・上書き・枠延長をしない。独立最終確認群を研究診断へ転用しない。
