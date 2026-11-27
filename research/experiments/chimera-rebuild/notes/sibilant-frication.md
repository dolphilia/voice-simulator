# 歯茎摩擦音の狭窄と乱流

比較するCHIMERAは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第5段階の `ˈɑsɑ / ˈɑzɑ` を、計画、調音と声門、乱流の登録、音響の順で調べる。

## 上流の入口と更新

1. `render speech` がIPAを `plan_utterance` へ渡す。/s z/ は顎0.3 cmと舌先の前後6.3 cm、較正した高さそれぞれ9.111・9.097 cmを強さ40で制御する。保持の開始は音素より8 ms早い。入り30 ms、出18 ms、速度1.3、速度保持の延長45 ms。別の強さ1.2のジェスチャーで舌体を3.2・7.4 cmへ引く。声門の追加開大は /s/ が0.30 cm²、/z/ が0.09 cm²。声門の開大と声道の狭窄で圧力差が決まり、有声化は声門モデルの状態として観測する。[子音目録と較正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L189)・[較正表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json)・[上流の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L450)
2. `HumanVoice::control` が調音器を進め、`HumanAirway::commit` で断面を再標本化して速度制限を掛ける。接触補正で姿勢を修正した場合は同じ制限の基準から再び計算する。各回の `update_noise` は、声門、咽頭・口腔で最小の正の面積を持つセルの周回、歯の周りの順に源を登録する。咽頭・口腔の境界セルに対応する枝は除外。源の位置・注入先は枝の番号で、歯の距離には解剖学上の管長を使う。[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[乱流源の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)
3. 狭窄の利得は最小断面0.35〜0.9 cm²で滑らかに減る。歯の源の重みは、歯が狭窄から1.0〜1.5 cm離れると増え、2.6〜4.0 cmで減る。最小断面0.2〜0.5 cm²でも重みが減る。歯の帯域上端は `top = (|U|/A) D / δ²`、`D = 2√(A/π)`、`δ = max(D, 0.17 d)`。断面と流量には制御更新直前の枝の状態を使い、`A` はcm²、`U` はcm³/s、`D, δ, d` はcm、`top` はHz。利得には `√(5000/max(top, 1200))` を掛ける。[帯域と利得](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L370)
4. 内部サンプルではレイノルズ数とシード付き白色雑音で圧力注入を求める。登録が同じ励起枝・順方向注入枝の組なら内部のフィルタ状態を保つ。既存の乱流実装を利用し、音響の時系列比較に加えて `top` と歯の利得をPythonで計算する。[上流のフィルタ継続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L785)・[既存の圧力注入の検証](turbulence.md)・[上流の有声摩擦音テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs)

## 実装前の判定条件

96 kHz内部、48 kHz出力、上流の既定シード12345を使う。声門のドリフト・ジッタ・シマーは両方で0。全部のフレームを比較し、摩擦音区間の中央半分で歯の源が有効な割合、最小の正の断面、帯域、声門有声化を測定する。候補と上流でジェスチャーは絶対差 `10⁻¹²`、幾何と帯域の独立式は `10⁻⁹`、乱流・音響状態はピーク比 `10⁻⁶`、PCMは絶対差 `10⁻⁶` 以内を基準とする。ホスト分割77・128フレームでは同じ出力を予測する。[無声](../cases/sibilant-s.json)・[有声](../cases/sibilant-z.json)・[乱流倍率0](../cases/sibilant-s-muted.json)

- /s z/ とも中央区間で歯の源のレベルが正となり、狭窄は0.01〜0.3 cm²の範囲に入る。歯の源がある区間では狭窄が歯の1〜4 cm手前にある。帯域は流量によって変わる。
- /z/ の1 kHz付近以下の平均電力は直前の強勢母音より13 dB以上低くなる。/s/ と /z/ の声門開大・有声化を別々の観測値として記録する。上流テストと同じ二段の一極フィルタを使って窓内の平均電力を比較する。
- 乱流倍率0の /s/ も狭窄のある同じ発話を進め、登録した各源のレベルが0になる。摩擦音中央の3〜15 kHzのPCM電力は乱流を有効にすると増えると予測する。

## 実装と計測

[発話計画](../crates/vocal-core/src/phonetics/speech.rs) は、母音と破裂音の経路に摩擦音の舌先・顎・舌体・開大の目標を追加した。[乱流源の登録](../crates/vocal-core/src/airway/human/frication.rs) は、調音の更新直後と接触補正による再計算時に実行する。乱流源の既存のフィルタ処理では、0 Hzの低域通過を速度0から得られる値として受理する。このとき係数が0になり、既存のルールに従って内部状態を扱う。CSVには声門識別値−2と源が未登録の値−1を使い、注入先の圧力は同じ枝に加わる成分の合計を記録した。[観測コード](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[上流のMIT通知](../LICENSE-CHIMERA)

上流との比較は実行中の励起枝・注入先・利得・レベル・圧力注入を読み取った。上流の低域通過係数は非公開のため、歯の帯域上端だけは上流の枝状態と距離から復元した。候補については、同じ入力値からPythonで再計算した上端との差が最大 `3.64×10⁻¹² Hz`。/s z/ を含む発話で乱流設定を省略しても、倍率1を明示した /s/ とWAVおよび出力段CSVがバイト一致した。[上流プローブ](../tools/upstream_bilabial_probe.rs)・[比較器](../tools/measure_sibilant.py)

| 摩擦区間の中央半分 | 最小断面の中央値 | 歯の低域通過カットオフの範囲 | 歯への圧力注入のRMS | 声門有声化の中央値 |
| --- | ---: | ---: | ---: | ---: |
| [無声 /s/](../runs/sibilant-s-20261119-c/summary.json) | 0.0974 cm² | 7.27〜10.12 kHz | 30.76 dyn/cm² | 約0.00000244 |
| [有声 /z/](../runs/sibilant-z-20261119-c/summary.json) | 0.1332 cm² | 2.53〜7.54 kHz | 20.68 dyn/cm² | 0.960 |
| [乱流倍率0の /s/](../runs/sibilant-s-muted-20261119-c/summary.json) | 0.0974 cm² | 7.27〜10.13 kHz | 0 dyn/cm² | 約0.00000244 |

/z/ では声門の有声化が残る一方、1 kHz付近以下のPCM電力は先行する強勢母音より13.96 dB低かった。/s/ と乱流倍率0の /s/ の観測断面・狭窄位置は全出力フレームで同じ。3〜15 kHzの電力は乱流ありで約61.14 dB高かった。3条件で固定上流版とのPCM差は最大 `2.91×10⁻¹¹`、乱流を有効にした2条件では最大 `3.64×10⁻¹²` だった。[比較結果と対照のハッシュ](../runs/sibilant-s-muted-20261119-c/manifest.json)

最初の計測は上流プローブの `std::io` の取り込み漏れで比較前に停止した。プローブを直し、同じケースで比較を再実行した。Clippyの初回では /s/ 後の有気判定に使う条件式の簡略化が指摘され、式を整理した後のワークスペーステスト・Clippyと上流の有声摩擦音・肺圧テストが通過した。[初回を保存した実行](../runs/sibilant-s-20261119-a/manifest.json)・[修正後の実行](../runs/sibilant-s-20261119-c/manifest.json)

別ディレクトリ `/tmp` からの再実行で、候補・上流の観測CSV、PCM、設定、計画の27ファイルが同一だった。77・128フレームのホスト分割でも各WAVと出力段CSVが一致した。既存の `ɑpɑ` と固定狭窄の乱流を再実行し、前者の9ファイルと後者の3ファイルが直前の通過版に一致した。[無声の再実行](../runs/sibilant-s-20261119-c/manifest.json)・[有声の再実行](../runs/sibilant-z-20261119-c/manifest.json)・[破裂音の回帰](../runs/bilabial-p-20261119-d/manifest.json)・[固定狭窄の回帰](../runs/turbulence-forward-20261119-l/manifest.json)
