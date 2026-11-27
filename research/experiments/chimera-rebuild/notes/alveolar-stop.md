# 歯茎破裂音の舌先閉鎖と再開口

比較版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。英語の語末に出る /d/ を発話レンダーへつなぎ、同じ部位の無声破裂音 /t/ を対照にする。

## 固定版の入力と状態更新

1. `render::speech` と `render::say` は、それぞれIPAと辞書から音素列を作り、`plan_utterance` に渡す。成人男性の /d t/ の優勢調音は舌先X・Yで、目標は (6.25, 9.68) cm。較正表に /d t/ の上書きはない。[CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L137)・[較正表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json)
2. 閉鎖を狙う時刻 `a` は音素の開始 `t0` に遅延を加えた点。母音の後は19 ms、/s z ʃ ʒ/ の後は30 ms、語頭などでは0。直前の破裂音が手前で閉じ、そのさらに前の音素が舌先の両座標を指定する場合は25 ms。遅延は `max(0,t1−t0−0.030)` が上限。[遅延](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L712)・[先行する調音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L781)
3. 舌先の目標は `a−0.031` から `max(a+0.010,t1−0.020)` まで。入り30 ms、出18 ms、速度延長45 ms、速度1.55、強さ40。別のジェスチャーが舌体 (3.2, 7.4) cm を `a` から `t1` まで弱い強さ1.2で前へ誘導する。前後の母音との重なりを残す。速度1超ではランプと速度延長を縮める。/t/ は破裂の有気・無気を両唇破裂音と同じ式で計画し、/d/ の通常発音では開大を足さない。[口腔の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[開大の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L510)
4. `HumanVoice` が64出力フレームごとに目標を混合し、調音器の位置と速度を進めて声道の目標を更新する。`HumanVocalTract::resample` は口腔格子の接触をセルの最小断面に反映し、`AirwayNetwork` がその最小断面を使って流路の閉鎖を判定する。舌先の閉鎖部位は口端より上流なので、唇端の最小断面と口端放射は別途観測する。`fast_speech` は1.8倍速の母音で開口が戻ることを、`speech_quality` は語末 /d/ からの復帰に相当する姿勢列で断面の連続性を、`consonant_artifacts` は /ɹpt/ で閉鎖を先行させすぎた場合の過渡を検査する。[制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[幾何](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[高速発話](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/fast_speech.rs)・[断面の連続性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/speech_quality.rs#L97)・[連結音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/consonant_artifacts.rs#L76)

## 実装前の予測と判定

`ɑdɑ` と `ɑtɑ` では口腔の最小断面がネットワークの閉鎖閾値0.0002 cm²を下回り、その中央で唇端は0.1 cm²以上開くと予測する。開放後の40 msでPCMを観測する。`ˈɑtɑtɑ` は1.8倍速でも中間母音の最大開口0.5 cm²以上を予測し、`ɑsptɑ` は25 msの遅延を式と照合する。`Dad.` では語頭と語末で閉鎖遅延が異なり、最後20 msでは音量が低下する。全ケースを内部96 kHz・出力48 kHzで計測し、舌先座標・最小断面・閉鎖したセル・声門・圧力・流量・PCMを比較する。声門の周期変動と乱流は0とし、77・128フレームのホスト分割でも同じ出力を予測する。

[有声](../cases/alveolar-d.json)・[無声](../cases/alveolar-t.json)・[高速](../cases/alveolar-t-fast.json)・[先行する調音](../cases/alveolar-t-placed.json)・[英語](../cases/alveolar-d-english.json)

## 初回計測と観測方法の改訂

`ˈɑtɑtɑ` の1.8倍速では、最初の /t/ の口腔は最小 `0.03418 cm²` まで狭まった。候補と上流の双方で閾値0.0002 cm²に達せず、全破裂音の閉鎖を要件にした初回は不通過だった。中間母音は最大2.5825 cm²に開き、次の /t/ は135フレーム閉じた。初回を保存して、改訂ケースに「最初の /t/ は0.0002〜0.06 cm²に狭まり、次は閉じる」を追加した。母音の開口条件とPCMの許容差は保った。[初回の結果と入力](../runs/alveolar-t-fast-20261119-a/manifest.json)・[初回の判定](../runs/alveolar-t-fast-20261119-a/summary.json)・[改訂ケース](../cases/alveolar-t-fast.json)

`Dad.` では、フレーム5,439で口腔の最小断面が両方とも0 cm²に達し、報告セルが候補11・上流10に分かれた。固定上流と候補の閉鎖・再開口の時刻は一致し、口腔最小断面の差は全区間で最大 `5.77×10⁻¹⁴ cm²`。最小セル番号だけの比較を改め、セルごとの実面積を追加して、各フレームで候補と上流が選ぶセルが双方の最小面積から `10⁻⁹ cm²` 以内にあり、全セルの閉鎖判定が一致するかを調べる。生のセル番号と当該断面は記録に残す。[初回の結果](../runs/alveolar-d-english-20261119-a/summary.json)・[計測コード](../tools/measure_alveolar_stop.py)

## 実装と測定値

[発話計画](../crates/vocal-core/src/phonetics/speech.rs) は両唇閉鎖の有気・無気と口蓋化の式を共有する。舌先の閉鎖には固有の保持時刻、舌体前進の目標、先行音による補正を与えた。[音声CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs) は /d t/ を含むときに舌先と口腔断面を記録する。出力CSVのフレーム `n` は `(n+1)/48000` 秒の内部状態に対応し、セル番号は口腔管の入口から0始まり。`ɑsptɑ` の観測では開いた唇を条件にして /p/ の唇閉鎖と /t/ の舌先閉鎖を区別する。口腔内の閉鎖では口端放射の状態が残るため、唇閉鎖に用いた0.995倍の残留放射式は適用しない。[上流の放射更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1102)

| 条件 | 観測 | 固定上流とのPCM最大絶対差 |
| --- | --- | ---: |
| [等速 /d/](../runs/alveolar-d-20261119-b/summary.json) | 口腔閉鎖33.40 ms、中央の唇端は6.2566 cm²。中央の声門開大0.00225 cm² | `1.82×10⁻¹²` |
| [等速 /t/](../runs/alveolar-t-20261119-b/summary.json) | 口腔閉鎖33.71 ms、中央の唇端は6.2567 cm²。中央の声門開大0.36225 cm² | `3.64×10⁻¹²` |
| [1.8倍速](../runs/alveolar-t-fast-20261119-b/summary.json) | 1番目は狭窄、中間母音は2.5825 cm²、2番目は2.81 ms閉鎖 | `1.46×10⁻¹¹` |
| [先行する /s/ の調音](../runs/alveolar-t-placed-20261119-b/summary.json) | /t/ の目標開始の補正25 msを独立式に照合。唇が開いた状態で55.50 ms閉鎖 | `1.82×10⁻¹²` |
| [英語 `Dad.`](../runs/alveolar-d-english-20261119-b/summary.json) | `dˈæd`。語頭は73.83 ms、語末は42.92 ms閉鎖。WAVは42,636フレーム、末尾20 msのPCMピーク `5.27×10⁻⁸` | `2.91×10⁻¹¹` |

`Dad.` で最小セル番号の報告が異なる128フレームでは、双方が選んだセルの最小値からの差は最大 `2.75×10⁻¹⁸ cm²`。フレーム5,439で候補はセル10が `2.75×10⁻¹⁸ cm²`、セル11が0。上流はセル10・11とも0。全条件で各セルの閉鎖判定が一致した。初回のケースと許容差、比較器は実行記録のソーススナップショットで照合できる。[英語の再計測](../runs/alveolar-d-english-20261119-b/manifest.json)・[上流のMIT通知](../LICENSE-CHIMERA)

`/tmp` から5条件を再実行し、音声・計画・時系列・結果の50ファイルが一致した。新規実行の入出力はマニフェストのSHA-256と照合した。両唇破裂音・歯茎摩擦音・基準IPA発話の3回帰では30ファイルが先行実行と一致。英語の回帰では波形を含む16ファイルが一致し、発音JSONの変更は /d t/ が未対応の一覧から外れた92箇所だった。候補のワークスペーステストとClippy、上流の `fast_speech`、`aspiration`、`speech_quality`、`consonant_artifacts` が通過した。Pythonは研究環境の3.14.4、NumPy 2.4.4、SciPy 1.17.1。[英語の再実行とハッシュ](../runs/alveolar-d-english-20261119-c/manifest.json)・[英語の回帰](../runs/english-frontend-20261119-c/summary.json)・[基準IPAの回帰](../runs/bilabial-nasal-vcv-20261119-d/summary.json)
