# 局所F0制御の実現性・転移比較

承認済み `nas-local-f0-20261003-v1` を実施し終了。教師・HMM・辞書・認識器は旧資料を読み取り再利用し、HTS対応版のソース77,527 bytesだけ取得した。既存評価環境を変更していない。

問いは、発話全体の補正から16特徴の局所F0へ移すことで、直接学習・研究用ニューラル・蒸留のどの経路が非ニューラル実波形へ改善を移せるか。HMM状態別の入口と依存遮断の4組一致は成立。新8文の全比較群の内容保護は全候補で不通過、品質未達。

[実施報告](../../../docs/note/local-f0-transfer-result-2026-10-03.md)と `results/nas-local-f0-20261003-v1/summary.json` を参照。保守的レンダー181、AI128、教師0、fit3。失敗を含む台帳・原認識文字列・読み診断・個別波形・係数・由来を保持する。

`campaign.py` は契約と上限、`acquire.py`・`build.py` は固定版shimの準備、`entry_audit.py` は厳密波形一致、`prepare_data.py` は既存教師とHMMの局所資料、`train.py` は3fit、`render.py` は4方式、`evaluate.py` は2認識器、`summarize.py` は系列別判断、`export_runtime.py` は非ニューラルbundleと依存遮断、`closeout.py` は完了範囲監査を扱う。封印後の再実行は認めない。初版入口と構築・取得の失敗も削除しない。

利用するPythonは `../autonomous-speech-synthesis/.venv-eval/bin/python`。最終経路を再現する研究用CLIは `results/nas-local-f0-20261003-v1/bundle/runtime.py` と同梱README参照。固定16係数と非ニューラルHMMを使い、教師・ニューラル重み・発話別軌跡を検索しない。macOS arm64、pyopenjtalk 0.4.1・NumPy・SciPy・既存辞書に依存する。品質認定版ではない。

`centered_projection.py` は次版向けの純粋関数で今回のrendererへ接続していない。共通オフセット不変の準備検査は生成・ASR・学習0。今回の中心化前クリップの制約と教師内部区間・波形DIO／状態平均の差を、自然さ改善の証拠へ置換しない。
