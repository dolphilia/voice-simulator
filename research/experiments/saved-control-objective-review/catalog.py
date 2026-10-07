"""対象は終了済み成果の明示的な参照だけ。未使用確認は対象外。"""
from campaign import *
CATALOG=[
 ('pilot',PILOT/'results/nas-pilot-20261002-v1','ニューラル教師から非ニューラル制御へ移せるか', ['protocol.json','teacher-provenance.json','teacher-load-verification.json','main-comparison-summary.json','extended-comparison-summary-v2.json','quality-decision.json','bundle-audit.json','hts-runtime-audit-v2.json','completion-audit.json','cost-audit.json','control-schema.json']),
 ('extension',EXT/'results/nas-extension-20261002-v1','共有制御の相対変化・長い発話への適用', ['protocol.json','summary.json','extended-summary.json','requirements-audit.json','cost-audit.json']),
 ('acoustic_revision',REV,'固定音響目標への共有低次元制御', ['protocol.json','summary.json','model-comparison.json','runtime-audit.json']),
 ('content_evaluation',ROOT.parent/'acoustic-revision-content-evaluation/results/nas-content-20261002-v1','保存改訂波形の内容保持を二ASRで監査', ['protocol.json','summary.json','interpretation.json','final-cost-audit.json']),
 ('factorial',FRES,'固定F0・利得・教師成分の要因比較', ['protocol.json','summary.json','measurement-audit.json','solo-runtime-audit.json','cost-audit.json']),
 ('local_transfer',LRES,'局所LF0制御を直接・ニューラル・学生で比較', ['protocol.json','summary.json','model-comparison.json','training-contract.json','runtime-audit.json','cost-audit.json']),
 ('local_projection',PRES,'射影の時間表現を変えた共有制御', ['protocol.json','summary.json','model-comparison.json','novelty-audit.json','runtime-audit.json','cost-audit.json']),
 ('wave_reachability',WRES,'実波形F0目標へ到達できるか', ['protocol.json','summary.json','measurement-sensitivity.json','recovery-contract.json','cost-audit.json']),
 ('wave_target',TRES,'波形目標から共有制御へ接続できるか', ['protocol.json','cause-audit.json','target-manifest.json','training-gate-negative-test.json','closeout.json','cost-audit.json']),
 ('saved_shared',SRES,'保存波形目標を学習し未知文で比較', ['protocol.json','partial-summary.json','model-comparison.json','training-contract.json','completion-audit-v2.json','closeout.json','cost-audit-v2.json']),
 ('saved_content',ERES,'保存共有制御の単独実行・二ASR内容評価', ['protocol.json','summary.json','runtime-audit.json','support-cause-audit.json','completion-audit.json','cost-audit.json']),
 ('source_filter',CRES,'LF0固定で音源・フィルタを分ける対照', ['protocol.json','summary.json','timing-audit.json','baseline-gate.json','completion-audit.json','cost-audit.json']),
 ('short_dio',QRES,'55msを境界込みで測れるか', ['protocol.json','summary.json','completion-audit.json','cost-audit.json']),
 ('short_alternatives',ARES,'二つの局所周期性方式の限定資格', ['protocol.json','summary.json','completion-audit.json','cost-audit.json']),
 ('short_window',HRES,'基底窓変換だけで計測一致が変わるか', ['protocol.json','summary.json','boundary-audit.json','completion-audit.json','cost-audit.json'])]
DOCUMENTS=['neural-assisted-non-neural-speech-pilot-result-2026-10-02.md','neural-assisted-extension-result-2026-10-02.md',
 'acoustic-control-revision-result-2026-10-02.md','acoustic-revision-content-evaluation-result-2026-10-02.md',
 'acoustic-control-factorial-result-2026-10-03.md','local-f0-transfer-result-2026-10-03.md','local-f0-projection-revision-result-2026-10-03.md',
 'waveform-local-f0-reachability-result-2026-10-03.md','waveform-target-shared-control-result-2026-10-03.md',
 'saved-waveform-shared-control-result-2026-10-03.md','saved-shared-control-evaluation-result-2026-10-03.md',
 'source-filter-counterfactual-result-2026-10-03.md','short-voiced-event-meter-result-2026-10-03.md',
 'saved-short-event-alternative-meters-result-2026-10-03.md','window-consistent-harmonic-meter-result-2026-10-03.md']
