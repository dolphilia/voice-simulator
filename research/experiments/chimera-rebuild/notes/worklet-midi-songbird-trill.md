# Web MIDIで鳴らすCanary trill

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの `noteOn` がMIDI音番号を左鳴管の400〜9,000 Hzに合わせ、コールIDと周波数を `AudioEngine`、Worklet、WASMへ送る。MIDI 60・67は3オクターブ上の2,093.00・3,135.96 Hz。コール開始はこの周波数を基準3,000 Hzで割った倍率と、現在の制御時計を記憶する。離鍵は押下一覧を更新し、コールの呼気は自動で続く。[鍵盤の変換](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L100)・[コールを鳴らす入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[再発音の時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

`songbird::trill` は16 Hzの周期を18回、各周期に4つのキーを生成する。周期先頭で呼気目標0と音高2,475 Hzに切り替わる。5 msで呼気目標1、38.75 msまで音高は指数補間で3,525 Hzへ上昇し、46.875 msで呼気目標が0になる。16 Hzの時刻列は鍵盤による移調を受けない。音高目標だけに倍率が掛かる。再発音では目標と時計を先頭へ戻す。平滑値と鳴管・気道の状態を引き継ぎ、64出力フレームごとに音高を8 ms、呼気を立ち上がり4 ms・下降12 msで追従させる。最後のキーから50 msを超えた更新で演奏者の目標に戻る。[キー生成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L122)・[補間と所有期間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[平滑化と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

`Songbird::control` は気嚢圧を圧力（kPa）×10,000×平滑呼気でdyn/cm²に換算する。右の周波数は左×2^(音程差÷12)。コールの `voices=0.15` では左の開口ゲート1、右0.3へ向かい、`drive=0.3` は左右の振動に入る。各鳴管は変位と速度を有限ステップのRK4で進め、表から求めた振幅範囲に沿って0〜1に正規化する。開口はその二乗と平滑開口ゲートの積で、係数を掛けて枝の断面cm²に換算する。左右の開口を更新した後に気道を進め、くちばしの放射を得る。出力48 kHzでは内部192 kHzで計算し、間引き・DC除去・振幅制限を通して単精度PCMを得る。[左右の制御と換算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L82)・[鳴管の状態更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs#L112)

上流のゴールデン試験の単発Canary trillは48 kHz・61,410フレームでTypeScript基準のPCM・包絡・観測値に照合する。実時間試験はコールの制御点と描画中のメモリ割り当てを、ABI試験はWorklet経由のコール配送と観測の列を検査する。[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・2.4秒でMIDI 60を押し、約520 ms後に67を押す。理論的な呼気目標0.5の交差時刻は、各押下後2.5 msから62.5 msおき。制御更新に丸め、再発音で途切れる第1音の範囲と、第2音の18パルスを別々に比較する。両離鍵後25〜200 msには2つ以上の立ち上がりと左右の流量が残ると予測する。最初のパルスの音高の両端、再発音直前と直後の平滑値、左右の開口と断面、気嚢圧を比較し、放射からPCMまでを独立に計算する。[登録条件](../cases/worklet-midi-songbird-trill.json)・[固定時刻での確認](../cases/worklet-songbird-trill.json)

## 実装と比較

研究版と固定上流の通常画面のCanary trillへ仮想MIDIを送る。候補のWorkletが採用したフレームから113フレーム分割のCLIで再実行し、同じフレームに固定上流の画面が送った周波数を入れて固定Rustの系列を採取する。Flute phraseのMIDI計測を共通にし、Canary trillの各立ち上がりと最初の上昇の音高範囲を追加した。再発音直前の平滑値を使って、直後の呼気と音高を独立に一更新する。左右の枝の有効断面は開口×0.03 cm²、気嚢圧は独立の平滑制御、PCMは内部放射を起点に比較する。[研究版のMIDI入口](../crates/vocal-core/src/songbird_voice.rs#L121)・[MIDIの共通計測](../tools/measure_worklet_midi_songbird_call.py)・[パルスと左右鳴管の計測](../tools/measure_worklet_midi_songbird_trill.py)・[独立の出力処理](../tools/measure_songbird_sustain_pcm.py#L79)

## 検証結果

研究ディレクトリと `/tmp` から実行し、各17項目に合格した。48 kHzの115,200フレームはブラウザとCLIでビット一致し、1,800時点の17列は差0。正式実行の採用フレームは8,064、16,256、32,896、46,464で、初回押下を基準にした入力時刻の最大差は2.67 msだった。最初の上昇音の目標はMIDI 60で1,726.729→2,459.280 Hz、67で2,587.170→3,684.757 Hzとなった。[正式結果と採用フレーム](../runs/worklet-midi-songbird-trill-20261121-final/summary.json)・[初回](../runs/worklet-midi-songbird-trill-20261121-a/summary.json)

第1音は再発音まで9パルス、第2音は18パルスだった。立ち上がり間隔は2,944または3,008フレーム。第2音の8番目では理論時刻0.440秒と制御境界が一致する。採用フレーム54,016で累積時計は0.4399999999999985秒、呼気目標は0.49999999999970024だった。0.5以上に達したのは次の制御境界54,080で、他の立ち上がりは理論を切り上げたフレームと一致した。再発音で呼気目標は1→0、平滑呼気は0.97226→0.87001、平滑音高は1,977.135→2,060.466 Hz。直前の状態からの一更新で両方を再現し、第2音の押下1.160秒後に演奏者の目標へ戻った。[パルス・再発音と終了](../runs/worklet-midi-songbird-trill-20261121-final/summary.json)・[制御時計を含む時系列](../runs/worklet-midi-songbird-trill-20261121-final/artifacts/cli.retained.csv)

| 離鍵後25〜200 ms | パルス立ち上がり | 左の流量RMS | 右の流量RMS | 右／左の開口RMS比 |
| --- | ---: | ---: | ---: | ---: |
| MIDI 60 | 2回 | 12.03 cm³/s | 5.77 cm³/s | 0.30007 |
| MIDI 67 | 3回 | 6.79 cm³/s | 6.01 cm³/s | 0.30007 |

両離鍵窓で左右の鳴管が流れを通し、PCM RMSは0.10973・0.13469だった。開口に0.03 cm²を掛けた断面は全フレームで一致し、独立に計算した気嚢圧と候補との差は最大2.73×10⁻¹² dyn/cm²だった。開口RMS比は両音で約0.30、流量RMS比は約0.48・0.89だった。音高だけの寄与を測るには、同じ発音履歴で音高を交換する対照が必要になる。[左右の開口・流量と独立計算](../runs/worklet-midi-songbird-trill-20261121-final/summary.json)

系列の最初の差は、第1音の押下6内部サンプル後の総放射だった。候補−0.06761771914937614、固定Rust−0.06761771914937617 cm³/s²で、同じ出力フレームから間引きとDC除去に差が現れた。左右の開口と気嚢圧は全区間で一致し、最初の差を生んだ演算は未特定。正式実行のPCMは固定Rustともビット一致した。初回の最大差は1.14×10⁻¹³で、正式実行の放射から独立に再構成したPCMは候補とビット一致した。[段階別の最初の差](../runs/worklet-midi-songbird-trill-20261121-final/summary.json)・[初回の比較](../runs/worklet-midi-songbird-trill-20261121-a/summary.json)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。正式実行の128フレーム量子は900回、1 ms刻みで測ったp95は1 ms、最大2 ms。音声時計に欠落はなかった。全サンプルで判定後、CSV2本を103.8 MBから83.0 MBへ絞って各115,200行をRTL9210B-CGに保存した。固定時刻のTrill回帰18項目、Flute phraseのMIDI回帰14項目、`cargo test --locked --workspace`の40件に合格した。物理MIDIと許可画面は未検証。[環境・コマンド・保存記録](../runs/worklet-midi-songbird-trill-20261121-final/manifest.json)・[固定時刻の回帰](../runs/worklet-midi-songbird-trill-20261121-fixed-regression/summary.json)・[Flute phraseの回帰](../runs/worklet-midi-songbird-trill-20261121-flute-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 \
  ../../.venv/bin/python tools/measure_worklet_midi_songbird_trill.py worklet-midi-songbird-trill-local-1
```
