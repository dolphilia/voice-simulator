# デュエットの歌詞と拍境界

## 読解と事前登録

固定上流の `DuetPage` は `show.json` の各声部から `melody` を読みます。`syllables` が明示されていればその配列を使い、省略時は辞書を準備して `lyricsToSyllables` を呼びます。`render notes` も同じ旋律ファイルを読み、休符で句を区切って合成します。歌詞表示に使うのは拍の時刻です。母音や頭子音が実際に鳴る区間はそれぞれ歌唱計画が決めます。[素材の読み込み](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L81)・[歌詞から音節](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/engine.ts#L156)・[音声をレンダーする呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L529)

`sungWords` は1拍を `60 / bpm` 秒に換算し、`t0`（省略時0.3秒）から拍長を順に足します。MIDIが0以下の休符の長さも時計に足し、音節は正のMIDIの音符にだけ割り当てます。メリスマの音符は、直前の音符が参照する親音節の番号を引き継ぎます。置き換え表記は小文字化した音節文字列で探し、親が語末でなければ `-` を表示します。`wordAt` は現在秒以下で最後に始まった音符を二分探索し、現在秒が終端以上なら表示を返しません。`mouthWords` は同じキーを同じ音節の継続として扱うため、後で同じ表記を発音し直す場合も、キーを区別します。固定上流の7テストは発話の語区間、口元の残像、テレメトリを検査しています。今回の比較では歌唱用の `sungWords` と `wordAt` を直接呼びます。[音節と区間の選択](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/src/show/words.ts)・[口元の履歴](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/mouthWords.ts)・[上流のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/words.test.ts)

既存の二声は音源と `.tele` を保ち、CLIが使った音節と譜面を取得します。対照の第1声部は0.375秒で開始し、2音のメリスマの後に0.5秒の休符を置き、別の音節として同じ表記 `Low-` を再び歌います。第2声部は0.625秒で開始する `Pop Dee` です。候補CLIでは対照の休符を挟む句をそれぞれ絶対時刻で合成して重ねます。歌詞と混合音源は同じサンプル0を共有します。停止中は指定サンプル、再生中は取得した時計の位置から表示のキーと文字列を判定します。[事前登録](../cases/duet-words.json)・[既存の声部と時計](duet-telemetry.md)

独立計算は10進のJSON値を有理数として扱います。事前のJavaScriptで `0.64 + 0.5` が `54720 / 48000` より `2.22×10⁻¹⁶` 秒大きくなることを確認しました。次の終端78,720でも同じ差があるので、この2点に限り固定上流の結果が理論上のサンプル境界より1サンプル遅れると予測します。初版では固定上流の秒比較を再現して差を保存します。この境界を調整する場合は、前後1サンプルの値と他の分岐を保って別の条件として記録します。[登録した観測点](../cases/duet-words.json)

## 初回結果と休符の判定

初版では上流と候補の両方に、54,720で `Pop` が残り、78,720で `Dee` が残る差が出ました。Chromiumの画面も同じ結果でした。休符の音声判定だけが失敗し、第1声部の61,800〜62,400でRMSが約0.01345でした。句ごとのWAVを比較すると、第1句は61,200サンプルで終わり、その区間の音は第2句から来ていました。第2句は拍が1.375秒、子音 `/l/` の予定開始が1.323秒、発声準備の開始が1.263秒でした。休符中央を測るため、判定区間を55,000〜55,600へ移します。旧区間は、表示が空でも次の句の準備が聴こえる対照として保存し、RMSが0.001以上であることを別に検査します。[初版の判定](../runs/duet-words-20261120-baseline/summary.json)・[初版のケース](../runs/duet-words-20261120-baseline/artifacts/source/research/experiments/chimera-rebuild/cases/duet-words.json)

修正した音声区間では、休符中央のRMSが約 `1.53×10⁻⁸`、次の句の準備区間が0.01345で、上流と同じ表示をする候補は26項目を通過しました。これを対照として固定します。次は音源の整数サンプル時刻から倍精度の丸め誤差以内にある表示境界だけをそのサンプルへ揃えます。譜面の時刻を足す処理や実際の音源は維持し、87件の比較では54,720・78,720の2点だけが変わると予測します。[上流の挙動を再現した実行](../runs/duet-words-20261120-upstream-timing/manifest.json)・[次の比較の登録](../cases/duet-words.json)

## 実装と実測

既存の `Pop Dee` には、CLIが使った旋律と音節を照合して2ファイルを追加しました。第1声部は採取した音節を保存し、第2声部は歌詞をブラウザで辞書とWASMへ通しました。追加したWASMの入口は既存のRustの音節化を呼び、音節を返します。画面はテレメトリと同じ再生スナップショットから各声部の歌詞を選びます。音節数が合わない声部は理由を表示し、他方の歌詞と混合WAVの再生を続けます。[譜面と歌詞の選択](../../../../web/prototypes/chimera-research/src/duet-words.ts)・[歌詞の表示](../../../../web/prototypes/chimera-research/src/duet-page.tsx)・[WASMの音節化](../crates/vocal-wasm/src/planning.rs)

候補では時刻 `t` を最も近い整数サンプルに換算し直した値との差が `Number.EPSILON × max(1, |t|)` 秒以内のときに表示境界を揃えました。実際に変化したのは第2声部の54,720で `Pop` から `Dee`、78,720で `Dee` から空表示の2点でした。両方とも有理数の計算と一致し、残り85件は固定した補正前の候補と一致しました。基準のWAV・テレメトリと対照WAVはハッシュが一致しました。別のサンプルレートや長い譜面での丸め誤差の分布は未測定です。[補正結果](../runs/duet-words-20261120-final/summary.json)・[上流と候補の全比較点](../runs/duet-words-20261120-final/artifacts/word-selection.json)

対照の第1声部は18,000と30,000で `Low-` とキー0を表示し、42,000と61,800は空、66,000で再び `Low-` とキー2を表示しました。前方シークで休符へ移り、後方シークでメリスマの音節へ戻り、一時停止で両声部の文字が保持されました。既存デモと対照の停止中のシークは合わせて35位置です。対照は既存CLIが休符を譜面から処理する経路を持たないため、句をそれぞれ絶対時刻でレンダーし、同じサンプル0から重ねています。句の切替時の発声器の状態連続性は今回の測定範囲外です。[ブラウザの採取結果](../runs/duet-words-20261120-final/artifacts/browser-words.json)・[対照音源](../runs/duet-words-20261120-final/artifacts/diagnostic/mix.wav)

`/tmp` と研究ディレクトリの最終実行は各28項目を通過しました。Chromium 156.0.8078.4を使い、Node・Bun・Rustの版、実行コマンド、出力SHA-256をマニフェストに保存しました。再生時計の回帰25項目と `cargo test --locked -p vocal-wasm` の25テストも通過しました。最後の記録更新時に空き容量が不足し、`cargo clean --profile dev -p vocal-wasm` で再生成可能な開発用ビルドキャッシュを整理しました。[最終実行](../runs/duet-words-20261120-final/manifest.json)・[再実行](../runs/duet-words-20261120-repeat/manifest.json)・[再生時計の回帰](../runs/duet-words-transport-regression-20261120/manifest.json)
