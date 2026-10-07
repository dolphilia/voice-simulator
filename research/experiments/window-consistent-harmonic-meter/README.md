# 窓処理を揃えた調波測定

承認済み `docs/plans/window-consistent-harmonic-meter-proposal-2026-10-03.md` の24非学習測定を実施する。保存24WAVを各一回使い、音声生成・AI・制御fit・波形逆推定・教師・取得は0。旧DIO・自己相関・調波方式は保存値だけを比較し、再実行しない。日本語の新規解析はしない。

旧 `saved-short-event-alternative-meters/local_meters.py` をhash照合して参照し、`LocalHarmonic.measure` を同じ関数のまま継承する。新しい初期化は、sin/cosの各基底列へ T(b)=Hann×(b−mean(b)) を適用してからQR辞書を構成する。この一変更以外の仕様を旧protocolと一致検査する。辞書はメモリ内だけに置く。既知F0や駆動マスクは測定関数へ渡さない。

既存Python 3.11環境で `-B`、通信禁止 `offline.sb`、`OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1` を使用する。`campaign.py`、`prepare.py`、`run.py`、`summarize.py`、`closeout.py`、`seal.py` の順。一回実施後は再実行しない。開始前のテストは小行列・負例・窓の整数配置のみで、音声を生成せず保存信号も測らない。

旧短イベント評価を同一hashで参照する。境界込みの既知有声域、欠損率10%、半音誤差中央値0.5、1半音超率5%、偽有声率10%、端の差10ms、有限・完全格子・正F0範囲・測定健全性を維持する。開発12件を保存してから確認12件を実施し、開発不通過を救済しない。確認群は観測済みであり、新しい独立確認とは主張しない。旧日本語主ゲートを変更しない。

30分・50MB・24非学習測定・再試行0の上限を、失敗を含む予約と実呼出数で監査する。排他保存、符号化後容量予約、外部変更検出、旧20封印照合、終了封印・追加処理拒否を継続する。出力は `results/nas-window-harmonic-20261003-v1/`。未知文や自然さの完了認定には使わない。
