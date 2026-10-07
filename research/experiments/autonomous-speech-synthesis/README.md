# 無人非ニューラル音声合成

[実装・検証計画](../../../docs/plans/autonomous-non-neural-speech-plan-2026-10-02.md)の独立実験。旧B9/G40の認定、旧holdout、Webの既定音を変更しない。

解析LF、帯域制限、共有母音標的、連続声道制御、閉鎖・局所雑音・鼻腔近似と規則韻律で未知入力を生成する。研究側はJVS、VTL、UTMOSv2、別系統の音素診断、ASRを利用できる。録音・学習済み音響生成器を最終音源に使用しない。試聴回答は必須としない。

## 実行

リポジトリルートから、既存のDSP環境を使用する。

```bash
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py inventory --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py qualify --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py benchmark-cost --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py run --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py diagnose --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py confirm --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py export --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py status --campaign ans-pilot-v1
research/.venv/bin/python -m unittest discover -s research/experiments/autonomous-speech-synthesis/tests -v
```

`run` はP0/P1、母音比較、P3/P4、未知入力の工学検査、移出と報告まで実行する。人間参照の最終確認は必須評価器の資格が揃った場合に限り開封する。工学検査だけをP5の品質完了と扱わない。

同一campaign IDではコード・設定・環境の変更を拒否し、完了試行を再利用する。中断試行は新しいattempt番号で追記し、中断・失敗も予算に含む。プロセス同時起動はロックで拒否する。新しいコードは新しいIDで実行する。最大6campaign、48時間、40GBの上限は自動で増やさない。

## ファイルと境界

- `config/`: 予算、評価契約、モデル登録、分割方針、移出許可リスト。
- `src/autonomous_speech_synthesis/generator.py`, `gestures.py`: 生成側。標的の単位と相対音圧の扱いを明記。
- `inventory.py`, `data.py`: 保存履歴の棚卸し、話者・文単位の分割、境界摂動と除外率。
- `qualification.py`, `evaluation.py`: 数値資格、信号/機構診断、欠損を通過にしない昇格規則。
- `runner.py`, `search.py`: 追記台帳、有界探索、同予算の無作為対照、アブレーション。
- `export.py`: 許可された生成コードと共有係数だけのbundle、別プロセス同一入力比較。
- `evaluate_ai.py`, `diagnostics.py`, `phoneme_diagnostic.py`: 研究側のみの評価、辞書前段の試験。

`render(phonemes, prosody, voice, seed, sample_rate)` は波形と実行時の制御ログを返す。フレーム列は音素規則から毎回計算する。実測Paではなく相対音圧を出力し、流量微分を励起に使った後の二重微分を行わない。

## 研究側の依存

DSPはNumPy/SciPyのみ。評価側はPython 3.11の `.venv-eval` に分離した。評価器の実際の版は `config/evaluation-requirements.lock.txt`、重みハッシュはAI結果の `weights` に保存する。生成bundleにPyTorch・認識器・参照音声を含めない。

[VTL公式バックエンド](https://github.com/TUD-STKS/VocalTractLabBackend-dev)を `.cache/VocalTractLabBackend-dev` へ取得し、CMake Releaseで構築する。実行時のcommit、dylib・JD3話者ファイルのhashを `generator-qualification.json` に記録する。VTLはGPL-3.0-or-later。JD3のドイツ語標的を日本語の適格性と読み替えない。

```bash
cmake -S research/experiments/autonomous-speech-synthesis/.cache/VocalTractLabBackend-dev -B research/experiments/autonomous-speech-synthesis/.cache/vtl-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build research/experiments/autonomous-speech-synthesis/.cache/vtl-build --config Release --target VocalTractLabApi -j 4
```

[UTMOSv2 v1.3.0](https://github.com/sarulab-speech/UTMOSv2/tree/v1.3.0)はCPUをモデル構築と予測の両方へ明示する。既定のモデルキャッシュ変数は上流の綴り `UTMOSV2_CHACHE` を使用する。初回取得後は `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` で評価する。

```bash
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/diagnostics.py prepare-ai --campaign ans-pilot-v1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/autonomous-speech-synthesis/evaluate_ai.py --manifest research/experiments/autonomous-speech-synthesis/results/ans-pilot-v1/ai-manifest.json --output research/experiments/autonomous-speech-synthesis/results/ans-pilot-v1/ai-evaluation.json
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/diagnostics.py summarize-ai --campaign ans-pilot-v1
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/phoneme_diagnostic.py --campaign ans-pilot-v1
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/autonomous-speech-synthesis/diagnostics.py asr --campaign ans-pilot-v1
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/autonomous-speech-synthesis/diagnostics.py frontend --campaign ans-pilot-v1 --text '紫の船がゆっくり進む。'
```

AI診断ファイルも上書きしない。コマンド再実行時は既存結果を先に確認する。ASRには正解文をヒントとして渡さない。規則前段はOpen JTalkのg2pのみを使用し、HTS音源およびニューラルアクセント推定を呼ばない。

## 証拠の解釈

数値試験の通過、音響残差の低下、知覚品質は別の結果である。公開評点との対象領域の校正がないUTMOSv2は `diagnostic-only`。JVSの自動音素境界と簡易音響分類器を、人手による音素認識精度と呼ばない。任意日本語テキストの品質や人間同等の自然さを主張しない。

確認済みの結果は `results/<campaign>/decision.json` と `report.md` を参照する。品質ゲートが満たされない場合、研究cycleの終了と品質目標達成を区別する。

## 2026-10-02の実行結果

[横断実行報告](../../../docs/note/autonomous-non-neural-speech-execution-report-2026-10-02.md)に3 campaign・2,500台帳レンダーの結果と未達条件をまとめた。判定は `inconclusive`。`ans-pilot-v1/report.md` は主campaign終了時点の不変記録なので、後続のASR・AI評価・辞書前段・OS隔離検証は横断報告と各sidecar JSONを参照する。

追加診断の入口は `vtl_speech.py`、`vtl_control_search.py`、`compare_measurements.py`、`mechanism_diagnostic.py`、`os_validate.py`。探索コアを変更せず、独立の結果へ保存する。OS隔離の採用結果は `os-isolation-v2.json`。初回失敗も保持した。`audit_results.py --campaign <id>` は台帳・分割・版・レンダー予算を点検し成果物hashを封印する。課題数40件の逸脱はこのレンダー数監査だけでは検出できず、横断報告に明記した。

生成だけを実行する例（出力パスは未使用のものを指定）:

```bash
research/.venv/bin/python -I research/experiments/autonomous-speech-synthesis/results/ans-pilot-v1/bundle/synthesize.py --text 'むらさきのふねがゆっくりすすむ' --f0 180 --speed 1.2 --seed 1009 --audit --output /tmp/autonomous-speech-example.wav
```

入力schemaの許容範囲は品質保証範囲ではない。かな・明示音素用の研究bundleであり、短文の明瞭性・自然さの完成版ではない。

## 追加検証v2

[続報](../../../docs/note/autonomous-non-neural-speech-followup-2026-10-02.md)にUTMOSの固定seed評価、辞書アクセント/モーラ/舌尖接触の96レンダー、VTL単独bundleとOS隔離の検証を記録した。累計4 campaign・2,596レンダー、23テスト通過。品質は引き続き未達。

```bash
research/.venv/bin/python -m unittest discover -s research/experiments/autonomous-speech-synthesis/tests -v
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/vtl_japanese.py
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python research/experiments/autonomous-speech-synthesis/diagnostics.py asr --campaign ans-vtl-japanese-v2
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/prosody_diagnostic.py
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/tap_geometry_diagnostic.py
research/.venv/bin/python -I research/experiments/autonomous-speech-synthesis/results/vtl-bundle-v2/synthesize.py --text 'あたらしいちずをひろげる' --accent 0 --variant accent --seed 1009 --output /tmp/vtl-research-example.wav
```

既存campaignは同じコード・設定で再開し、既存診断結果の再書込みは拒否する。`evaluate_ai_seeded.py` は31件の固定入力を評価し、既存結果があれば停止する。`japanese_frontend.py --output <新規パス>` は12文の辞書解析を保存する。高密度な発話制御列をbundleへ保存する機能はない。

`campaign_v2.py` は凍結済みv1コアを継承し、新campaignの課題数制限と初期化失敗時の解放を追加する。`vtl_japanese.py` の4比較条件は品質改善として未採用。`export_vtl.py` / `validate_vtl_bundle.py` は共有モデル・コードの移出と波形一致用。移出済みのbundleには参照録音・AI評価器が不要である。

## 最初のサイクルの終了

[終了報告](../../../docs/note/autonomous-non-neural-speech-cycle-result-2026-10-02.md)と `results/cycle-decision.json` を参照。6 campaign、2,730台帳レンダー、25テスト。品質は未達で、最終確認群は未開封。7つ目のcampaignは開始していない。

`calibrate_tap_geometry.py` は9条件の内部断面応答を調べる。`vtl_calibrated.py` は通過した42ms/7msの閉鎖を第6campaignで比較する。`free_fit.py` は第5campaignの自己回復が不通過だったため自然参照適合を開始しない。`free_fit_bounds_v2.py` はその後に発見した探索区間の交差を防ぐ次版用の写像であり、最適化器全体の資格を得たわけではない。

```bash
research/.venv/bin/python -m unittest discover -s research/experiments/autonomous-speech-synthesis/tests -v
research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py status --campaign ans-vtl-calibrated-v3
```

診断スクリプトの再保存は既存出力を上書きせず停止する。この時点では次サイクル案は未承認・未開始だった。その後の承認と実施結果は次節に記載する。旧campaignの改名や削除によって上限を回避しない。


## 承認済み追加サイクル（2026-10-02、品質未達で終了）

ユーザー承認により `ans-extension-20261002-v1` を開始した。追加の上限は3 campaign・24時間・10GB、各campaign8時間。旧6件の台帳を保持し、独立した承認・登録・容量基準を `results/cycles/ans-extension-20261002-v1/` に保存する。

- `cycle_campaign_v1.py`: 追加枠の管理。旧campaignの付け替えは禁止。
- `spectral_fit_v1.py`: 正規化スペクトル5変数の感度と自己回復。近傍のみ通過し終了。
- `spectral_multistart_v1.py`: 27格子を併用した新しい自己回復を通過。1,780レンダーで14条件の自然参照適合を完了。
- `vtl_tap_timing_v1.py`: 前後8msの接触時刻比較48レンダー。両変更とも保護条件に不合格。
- `extension_asr_v1.py`: AI評価の予約・失敗計数。
- `summarize_spectral_v1.py`: 全セル完了後の話者単位集計。
- `plot_spectral_v1.py`: 選別話者の平均と観測範囲の図。残差減少13条件、増加1条件。
- `close_extension_v1.py`: 完了台帳・封印・予算・旧成果物を検証して終了集計。

[追加サイクル結果](../../../docs/note/autonomous-non-neural-speech-extension-progress-2026-10-02.md)を参照。計1,922レンダー・135 AI評価を完了し、3 campaignの監査を通過した。全31テストが通過。品質目標は未達であり、最終確認群は未開封。追加3枠は使用済みのため、第4campaignを開始しない。現在の `confirm` は工学確認用であり、品質認定の正の経路は未実装。評価器資格に加えてこの実装も残る。

現行の自由適合は第1共鳴器利得を固定して残る利得を0.05〜1とする狭い相対利得領域に限られる。旧利得全域を保持する `free_fit_gain_domain_v3.py` は別版の係数テストまでで、音声自己回復は未検証・未採用である。


### 追加した日本語評点資料と隔離条件

`results/urgent-ja-v1/` は公式URGENT 2026 ACR配布の固定revisionと、16話者・96音声に対する108回のUTMOS推論を保持する。`protocol.json` の事前選択規則に従い、原FLAC・個票・MOS・予測・AI予算台帳の対応を監査済み。推論は `ans-spectral-multistart-v1` のAI枠へ計上した。話者平均の順位相関は0.175（95%区間 −0.122〜0.441）で、品質合否の資格は付与しない。

実装は `fetch_urgent_ja_v1.py`、`prepare_urgent_ja_v1.py`、`evaluate_urgent_ja_v1.py`、`summarize_urgent_ja_v1.py`。Parquet読込には評価用環境へ追加した `requirements-urgent-ja-v1.txt` を使用する。取得済み資料と結果は上書きしない。

新資料も読めないOS拒否設定は `results/extension-isolation-v1/profile.sb`。同フォルダの `verification.json` に追加音声・Parquet・従来参照・AI重み・ネットワークの拒否結果を保存した。旧profileは当時の証拠として保持する。新profileの検査はアクセス拒否のみで、音声再生成はしていない。
