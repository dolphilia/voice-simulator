# 完全生成母音ベースライン実験

のこぎり波/LF系音源と、並列formant/cascade all-pole声道の2×2比較です。録音断片、生成AI、onset軌道は使いません。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py test
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening
```

`prepare` は4候補の信号gateを通した後、4比較＋隠し重複2件を `baseline-wizard-v2` として凍結します。既存セッションは上書きしません。未回答のv1は設定・manifest hashをprivate provenanceへ追加する前の版なので使用しません。

4候補はすべて人声判定を通らなかったため、B2と自励発振2質量音源B4の限定比較を追加しました。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session physical-source-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session physical-source-wizard-v1
```

B4は人声性の改善を示さず、B2は主に `/a/` の明瞭さで選ばれました。次はのこぎり波を固定し、並列formant、cascade all-pole、Kelly–Lochbaum waveguideの声道差を3提示で確認します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session waveguide-tract-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session waveguide-tract-wizard-v1
```

B5 waveguideも `/a/` 同一性と人声同一性を回復しなかったため、B2へ声門スペクトル傾斜、微細変動、aspirationを順に追加するB6〜B8を比較します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session voice-quality-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session voice-quality-wizard-v1
```

B7は凍結実現値として人声判定を通過しましたが、事後テストでF0変動量が設定0.64%に対し実測約5.64%だと判明しました。端点バイアスを除いたB9（0.64%）とB10（5.644%）で変動量を分離します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session voice-quality-correction-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session voice-quality-correction-wizard-v1
```

補正比較ではB9とB10がともに人声判定を通過し、B9（0.64%）の方が人声に近いと判定されました。B9方式を未使用3 seedで検証します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session b9-seed-validation-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session b9-seed-validation-wizard-v1
```

未使用3 seedがすべて合格したため、B9を定常 `/a/` ベースラインv1として確定しました。次はonsetを人声性の主要因としてではなく、開始自然さの副次要因として限定比較します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session onset-secondary-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session onset-secondary-wizard-v1
```

副次onset比較では60 ms gain attackと80 ms減衰aspirationが順に開始自然さを改善し、F0安定化の追加効果は`SAME`でした。最小候補O2のaspirationを未使用3 seedで検証します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session onset-aspiration-validation-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session onset-aspiration-validation-wizard-v1
```

aspirationは3 seedのうち2 seedで改善しましたが、seed 502は重複を含め2/2で`SAME`となり、事前合格条件を通過しませんでした。主線を決定的なgain attackへ戻し、40・60・80 msを比較します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session gain-attack-duration-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session gain-attack-duration-wizard-v1
```

40・60・80 msは開始自然さで相互に`SAME`だったため、最短規則でG40が候補です。ただしO0対G60重複でcontrol側の人声判定が揺れたため、G40候補側の最終確認を3提示で行います。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen --session g40-final-wizard-v1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-listening --session g40-final-wizard-v1
```

G40は最終確認でO0より2/2で開始が自然、G80よりも自然と判定され、全提示で `/a/` yes・人声yes・artifactなしでした。G40をonsetベースラインv1として確定しています。

- 定常部確定: `results/baseline-release-v1/`
- onset確定: `results/onset-release-v1/`
- 次期計画: `docs/plans/synthetic-vowel-generalization-plan.md`

利用可能な試聴者が1名のため、次期計画は複数人比較ではなく、24時間以上離した3回の個人内反復から開始します。回答回数を参加者数としては扱いません。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-longitudinal --run 1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen-longitudinal --run 1
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-longitudinal
```

run 2とrun 3も同じコマンドの番号を変えて実施します。`listen-longitudinal` は前回完了から24時間未満の場合に停止します。集計はいつでも更新できますが、3回完了するまで合格にはなりません。

反復試聴の待機中も開発を止めないため、F0 160/220/300 HzのB9/G40候補は事前生成と信号検査まで先行しています。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-f0-preflight
```

生成済みmanifestは `results/f0-generalization-candidates/manifest.json` です。全6候補が信号gateを通過し、220 Hzは既存v1とhash一致済みです。160/300 Hzは試聴前の `signal-qualified` 候補で、まだ採用音ではありません。

日本語5母音についても、220 HzのB9/G40を計10音、試聴前候補として生成できます。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-vowel-preflight
```

`/a/` は既存v1とのhash一致を必須とし、他4母音は既存Web `reference` プリセットを暫定値として使います。試聴前なので採用音ではありません。

一般化全体の進捗と、信号合格・知覚合格・releaseの違いは次で確認できます。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py generalization-status
```

後続のF0試聴と5母音試聴はすでに凍結準備できますが、前提ゲートが通るまで試聴コマンドが自動停止します。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-f0-listening
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen-f0-generalization
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-f0-generalization

research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-vowel-listening
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen-vowel-generalization
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-vowel-generalization
```

gain attackの固定40 msとF0周期比例の候補も事前生成できます。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-gain-scaling-preflight
```

220 Hzでは両方式が同一、160 Hzでは比例55 ms、300 Hzでは比例約29.33 msです。現段階では信号合格のみで、知覚的な採用結果ではありません。

スケーリング試聴も準備済みで、5母音試聴合格後にだけ実行できます。

```bash
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py prepare-gain-scaling-listening
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py listen-gain-scaling
research/.venv/bin/python research/experiments/synthetic-vowel-baseline/run.py analyze-gain-scaling
```

Web統合は現行のparallel formantエンジンへ値だけを移さず、研究release用の明示DSP経路を別実装する方針です。詳細は `docs/note/web-generalization-integration-audit.md` にあります。
