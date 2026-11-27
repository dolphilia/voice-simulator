# /h ɦ/ の声門開大と乱流

比較するCHIMERAは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。IPAの母音間と英語の語頭を使い、声門の開大、周期成分の減衰、乱流による圧力を観測する。

## 固定版の処理と単位

1. IPAの `render::speech` と英語の `render::say` は音素列を `plan_utterance` に渡す。目録では /h ɦ/ は `Manner::Glottal`。口腔目標は空で、調音は前後の母音が担う。/h/ は音素区間の両端を10 ms早め、開大0.33 cm²、強さ5、入り30 ms、出35 ms。/ɦ/ は音素の区間をそのまま使い、開大0.10 cm²、強さ5、入りと出を30 msにする。両方とも話速1超ではランプを縮める。[IPAのCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[英語のCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L203)・[開大の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L498)
2. `HumanVoice::control` が64出力フレームごとにスコアを合成する。開大の基準は成人男性、有声、息漏れ0.15の条件で `0.1×0.15²=0.00225 cm²`。ジェスチャーの合成開大に `min(重み合計/2, 1)` を掛け、基準に足す。`ParametricGlottis::next` は声門前後の圧力差を平滑化し、開大で声帯の接触が減ると周期成分の係数を下げる。新しい声門面積を設定し、気道ネットワークを内部サンプルごとに進める。[制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[有声化の係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L171)・[開大の上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)
3. `HumanAirway::update_noise` は声門の枝を励起源にし、順流では咽頭内の枝、逆流では気管末端側の枝へ直列圧力源を設定する。利得は `3.2×10⁻⁶`、ハイパス300 Hz、二段のローパス3,500 Hz。源の励起枝と順方向注入先が同じなら、制御更新後も各フィルタの状態を引き継ぐ。乱流の乱数はシード12345。開大と呼気のスコアは乱流倍率で変化しない。[声門由来の乱流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[開始シード](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L429)・[フィルタ状態の継承](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L785)
4. 気道は枝流量の更新前に圧力注入を計算する。枝面積 `A` は cm²、流量 `U` は cm³/s、動粘度 `ν=1.86×10⁻⁴/1.14×10⁻³ cm²/s`。`Re=2|U|/(ν√(πA))`、`x=max(Re²−1800²,0)`、振幅は `3.2×10⁻⁶×倍率×√(96000/fs)×x/(1+x/(12000²−1800²))`。枝面積が閉鎖閾値以下なら0。帯域制限後の乱数と掛けた値を流れの向きに応じて足すか引く。枝面積と流量の配列は圧力注入後に更新するため、出力フレームと内部サンプルが一対一なら、記録した一つ前の行から振幅を予測できる。[物性値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs#L5)・[更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L917)・[圧力源の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)

## 実装前の予測と判定

内側96 kHz・出力48 kHzで、/h/ と /ɦ/ の中央50%の声門開大、有声化係数、口端最小断面、順流側への圧力を測る。/h/ の有声化係数の中央値は0.15以下、/ɦ/ は0.5以上、次の母音の中ほどはどちらも0.7以上と予測した。倍率0では開大・口腔形状を保ち、注入圧力は0、3〜12 kHzの電力は倍率1より少なくとも3 dB低くなる。内部48 kHzでも実行して、前サンプルの声門面積・流量から算出した注入振幅を別に照合する。英語 `Hi.` は辞書で `hˈaɪ` を得て、語頭の開大から有声母音へ進む。上流と周期変動を停止して比較し、PCMは振幅の最大絶対差 `10⁻⁶`、77・128フレーム分割はバイト一致を判定する。

[/h/](../cases/glottal-h.json)・[乱流倍率0](../cases/glottal-h-muted.json)・[/ɦ/](../cases/glottal-voiced.json)・[内部48 kHz](../cases/glottal-h-48k.json)・[英語](../cases/glottal-h-english.json)

## 実装と実測

発話計画で /h ɦ/ を開大の目標に結び付け、CLIで既存の声門乱流を既定で有効にした。倍率0のケースでも源の位置・フィルタ更新を維持する。CSVの各行は、その出力フレームの最後の内部サンプルを処理した直後の状態。/h ɦ/ を含む入力には `glottis_jet_area_cm2` を追加した。[発話計画](../crates/vocal-core/src/phonetics/speech.rs)・[CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[既存の源配置](../crates/vocal-core/src/airway/human/frication.rs)・[独立計算と比較器](../tools/measure_glottal_frication.py)・[上流のMIT通知](../LICENSE-CHIMERA)

| 条件 | 中央50%の開大の中央値 (cm²) | 有声化係数の中央値 | 咽頭側圧力RMS (dyn/cm²) | 上流とのPCM最大絶対差 |
| --- | ---: | ---: | ---: | ---: |
| [ˈɑhɑ](../runs/glottal-h-20261119-a/summary.json) | 0.33225 | 0.0000486 | 54.57 | `1.46×10⁻¹¹` |
| [ˈɑhɑ、乱流倍率0](../runs/glottal-h-muted-20261119-a/summary.json) | 0.33225 | 0.0000486 | 0 | `5.82×10⁻¹¹` |
| [ˈɑɦɑ](../runs/glottal-voiced-20261119-a/summary.json) | 0.10225 | 0.93233 | 31.79 | `7.28×10⁻¹²` |
| [ˈɑhɑ、内部48 kHz](../runs/glottal-h-48k-20261119-a/summary.json) | 0.33225 | 0.0000486 | 103.68 | `5.82×10⁻¹¹` |
| [英語 `Hi.`](../runs/glottal-h-english-20261119-a/summary.json) | 0.33225 | 0 | 51.91 | `1.82×10⁻¹²` |

内部96 kHzの母音間 /h/ では、中央区間の口端最小断面は6.3461 cm²以上で、別の狭窄・歯の乱流は中央で振幅0だった。通常条件と倍率0で唇端・狭窄・開大の比較系列は全区間で一致した。通常条件は、倍率0に比べ中央の3〜12 kHz電力が71.79 dB高い。/h ɦ/ とも次の母音で有声化係数の中央値は0.99999以上に戻った。英語 `Hi.` の出力は48 kHz・37,440フレームだった。[乱流倍率の対照](../runs/glottal-h-muted-20261119-a/summary.json)・[英語のWAV](../runs/glottal-h-english-20261119-a/artifacts/pcm-128.wav)

5条件とも77・128フレームのホスト分割でWAVと出力段CSVが一致した。独立式による開大の差は全条件で最大 `9.47×10⁻¹⁴ cm²`。内部48 kHzでは前サンプルで算出した振幅が18,234サンプルで正となり、上流・候補で実測と最大 `2.28×10⁻¹³ dyn/cm²` の差で一致した。[内部48 kHzの比較](../runs/glottal-h-48k-20261119-a/summary.json)

内部48 kHzの再実行では時刻の対照を追加した。同じ行の面積・流量を使うと、振幅に最大5.94 dyn/cm²の差が出た。5条件を `/tmp` から再実行し、波形・計画・観測を含む49ファイルが初回とバイト一致した。更新した48 kHzの要約には同じ行で計算した差を追加した。新規実行の入出力はマニフェストのSHA-256と照合した。[内部48 kHzの再実行](../runs/glottal-h-48k-20261119-b/summary.json)・[英語発話の実行記録](../runs/glottal-h-english-20261119-b/manifest.json)

既存の歯茎破裂音、歯茎摩擦音、基準IPAの回帰で30ファイルが一致した。英語の発音と `Mom? Pop.` の回帰では波形を含む16ファイルが一致し、発音JSONでは /h/ が未対応一覧から外れた20箇所を確認した。候補のワークスペーステストとClippy、上流の `lung_port`、`sound_marks`、`speech_quality` が通過した。[歯茎破裂音](../runs/alveolar-d-english-20261119-d/summary.json)・[歯茎摩擦音](../runs/sibilant-s-20261119-f/summary.json)・[基準IPA](../runs/bilabial-nasal-vcv-20261119-e/summary.json)・[英語](../runs/english-frontend-20261119-d/summary.json)
