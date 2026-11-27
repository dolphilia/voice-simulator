# デュエットの再生時計

## 読解と事前登録

固定上流の `App` は `?show=` のIDから `DuetPage` を読み込みます。`DuetPage` は `show.json` を開き、混合済みの音源を `Transport.load` で復号し、声部ごとのファイルを `TeleTrack` に渡します。混合音源のサンプル位置が共通の時計で、各声部は `Transport.time()` の秒を自分のサンプルレートと採取間隔に変換します。シークで増える `epoch` は描画側の履歴を切り替える合図です。今回は共通の音源・時計・操作までを比較し、声部ごとの採取列と口のアニメーションは次の工程で接続します。[ページの選択](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/App.tsx#L26)・[素材の読込](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L58)・[声部の観測位置](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L171)

`Transport` は専用の `AudioContext` と、復号した `AudioBuffer`、一度だけ開始できる再生ノードを持ちます。停止中の `offset` は音源先頭からの秒です。再生するとグラフ時刻 `currentTime` を開始時刻に保存し、同じ引数でノードを予約します。`getOutputTimestamp()` の `contextTime` に観測からの経過秒を足し、その結果を `currentTime` 以下に制限します。利用できる時刻がない場合は `currentTime` から `outputLatency`、それがなければ `baseLatency` を引きます。再生位置は開始位置に、開始から可聴時刻までの非負の経過秒を足し、音源の長さまでに制限した値です。したがって、出力待ちの間はシーク位置より前には戻りません。[上流の開始と時計](../../../../docs/reference/chimera-vocal-synth/upstream/src/show/transport.ts#L59)・[Web Audioの出力時刻](https://www.w3.org/TR/webaudio/#dom-audiocontext-getoutputtimestamp)

一時停止はその瞬間の可聴位置を保存してノードを止めます。シークは区間内へ位置を制限し、`epoch` を増やし、再生中なら新しいノードを作ります。非同期の `resume` の失敗や古いノードの `ended` が、後続操作に影響しないよう世代とノードそのものを比較します。`ended` はグラフでレンダーが終わった印です。再生完了への遷移には可聴位置が末尾へ達することも必要です。上流の6件の `Transport` テストと、時計からサンプルを取得する `TeleTrack` の3件を実行しました。[上流の時計テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/transport.test.ts)・[上流のサンプルテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts)

入力は既存 `Pop Dee` の歌唱ケースから、開始0.50秒の上声と開始0.64秒で音高を変えた下声をCLIで別々にレンダーし、ゲインを各0.35として足した2.2秒・48 kHzのWAVとします。元ケースの先頭無音と各声部の音源サンプル番号を保ち、2.2秒まで不足分を0で補います。仮想時計では200 msの出力待ち、出力タイムスタンプ、60 msの代替遅延、開始・停止・シーク・中断を固定した期待値で照合します。実ブラウザでは保存した同じWAVを読み、ボタンと位置の入力を操作します。グラフ内で採った2,048サンプルをCLIの混合音に相互相関で合わせ、実際に聴こえる位置の推定にはブラウザの出力タイムスタンプを使います。表示との差は50 ms以内、グラフ内の波形は相関0.995以上と予測します。物理端末のスピーカーから出た音はこの経路では測れません。[事前登録](../cases/duet-transport.json)・[歌唱ケース](../cases/song-voice-long.json)

## 再開が拒否される条件の追加

初版は仮想時計の両実装各23操作とブラウザ比較の全19項目を通過しました。候補の表示と可聴時刻の推定との差は最大約1.5 msで、2つの採取区間はグラフ時刻から計算したサンプル番号に一致しました。[初版の実行](../runs/duet-transport-20261120-a/manifest.json)・[初版の判定](../runs/duet-transport-20261120-a/summary.json)

固定上流の `play` は `resume` の拒否時に操作の世代を比較します。`seek` もその世代を増やしますが、新しい `resume` は要求しません。再開を保留したまま1.12秒へシークしてから拒否すると、再開の失敗が無視され、コンテキストは停止したまま表示だけが再生中になると予測します。初版の候補も同じ世代の扱いです。改訂版のケースでは仮想時計と実ブラウザの双方で、固定上流がこの状態を再現し、改善候補が1.12秒を保持して停止状態になることを先に定めます。従来の19項目の入力・基準は引き継ぎます。[上流の開始とシーク](../../../../docs/reference/chimera-vocal-synth/upstream/src/show/transport.ts#L59)・[改訂したケース](../cases/duet-transport.json)

修正前の候補で追加した二つの判定だけが失敗しました。実ブラウザでは `AudioContext.suspend()` の後で `resume()` だけを保留・拒否し、通常の再生ボタンとシークを通しました。両方とも1.12秒（53,760フレーム）、コンテキストは `suspended` のまま、画面と再生ノードは再生中として残りました。次は、再生を開始・停止・破棄する操作にだけ再生要求の世代を適用し、シークには引き続き表示側の `epoch` を使います。[修正前の判定](../runs/duet-transport-20261120-before-resume-fix/summary.json)・[実ブラウザの時系列](../runs/duet-transport-20261120-before-resume-fix/artifacts/browser.json)

## 実装と実測

研究画面のリンクから `?show=duet-clock` を開くと、`show.json` とWAVを読み、再生・一時停止・シーク・最初からの再生を操作できます。秒の表示は `getOutputTimestamp` を使った推定値です。元のWAVのフレーム位置には秒と48,000 Hzを掛けた最寄りの整数を表示し、末尾では区間の終端を示す105,600を表示します。候補は時刻を更新してから再生状態を作るため、終端と停止の表示は同じ更新で切り替わります。画面では各声部の名称を表示し、時変のテレメトリは次工程で接続します。[再生時計](../../../../web/prototypes/chimera-research/src/duet-transport.ts)・[デュエット画面](../../../../web/prototypes/chimera-research/src/duet-page.tsx)・[デモの混合音源](../../../../web/prototypes/chimera-research/public/shows/duet-clock/mix.wav)

Rust CLIの声部は91,200フレームと97,920フレームでした。不足を0で補い、加算後のピークは約0.397、16ビットのデモWAVと独立に再生成したWAVはバイト一致しました。仮想時計では候補と固定上流に各30操作を渡しました。固定上流の `Transport` と候補を同じChromiumで起動し、候補は研究画面のリンクと操作部を、固定上流は再生クラスを直接呼ぶ比較画面を使いました。1.12秒へシークした後の再開拒否では候補が停止へ戻り、53,760フレームを保持してノードを停止・切断しました。上流は同じ位置で再生表示が残りました。最終の2実行は各25項目、既存の実時間歌唱も通過しました。コマンド、環境、入力と出力のSHA-256は各マニフェストから確認できます。[最終実行](../runs/duet-transport-20261120-final/manifest.json)・[再実行](../runs/duet-transport-20261120-repeat/manifest.json)・[実時間歌唱の回帰](../runs/duet-transport-song-regression-20261120/manifest.json)

再実行の片方では、波形と一致する末尾が67,072で、測定後に読んだグラフ時計からは68,096となりました。表示に使う可聴時刻との差はこの時点でも約1.4 msでした。波形を取得する関数と時計取得の間でグラフが進む可能性があり、2,048サンプルの採取関数の直前と直後の時計も保存するようにしました。追加計測の2回では候補・上流の8区間すべてで、その前後の時計から求めた末尾フレームと採取波形が一致し、1,024サンプル差は再現しませんでした。候補表示は可聴時刻の推定に対し最大8.7 ms遅れ、相関は全区間で0.999999999を超えました。候補の全25項目と既存歌唱の回帰25項目が通過しています。物理装置の出力遅延、再標本化した音源、声部別の採取列との同期は未測定です。[差が出た旧計測](../runs/duet-transport-20261120-repeat/summary.json)・[追加計測](../runs/duet-transport-20261120-clock-bracket/summary.json)・[追加計測の再実行](../runs/duet-transport-20261120-clock-bracket-repeat/summary.json)
