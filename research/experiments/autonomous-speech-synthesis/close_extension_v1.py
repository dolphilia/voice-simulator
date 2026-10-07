#!/usr/bin/env python3
"""承認済み追加3枠を、完了台帳と封印の検証後に集計する。音声は生成しない。"""
from collections import Counter
from contextlib import ExitStack
from datetime import datetime
import fcntl
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from autonomous_speech_synthesis.io import read, rows, write_once, file_hash, now
from cycle_campaign_v1 import CYCLE_ID, LIMITS, inventory

EXPECTED = {'ans-spectral-fit-v1', 'ans-vtl-tap-timing-v1', 'ans-spectral-multistart-v1'}
CYCLE = ROOT / 'results/cycles' / CYCLE_ID


def verify_seal(base, filename):
    seal = read(base / filename)
    errors = [name for name, sha in seal['files'].items()
              if not (base / name).is_file() or file_hash(base / name) != sha]
    if errors:
        raise RuntimeError('封印済み成果物が変更されています: ' + repr(errors[:10]))
    return {'file_count': len(seal['files']), 'seal_sha256': file_hash(base / filename)}


def main():
    if (CYCLE / 'decision.json').exists():
        print('追加サイクルは集計済みです。結果を上書きしません。')
        return
    members = {p.stem for p in (CYCLE / 'members').glob('*.json')}
    if members != EXPECTED:
        raise RuntimeError('承認済み追加3枠の構成が一致しません')
    campaigns = []
    with ExitStack() as stack:
        for name in sorted(members):
            path = ROOT / 'results' / name
            lock = stack.enter_context((path / '.run.lock').open('a+'))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            audit = read(path / 'extension-audit.json')
            if not audit['passed'] or audit['E0_failed']:
                raise RuntimeError(name + ': 監査またはE0が不通過')
            seal = verify_seal(path, 'extension-artifact-seal.json')
            ledger = rows(path / 'ledger.jsonl')
            started = [r for r in ledger if r['event'] == 'started']
            finished = [r for r in ledger if r['event'] == 'finished']
            if len(started) != len(finished) or len(finished) != audit['finished']:
                raise RuntimeError(name + ': 台帳と監査の不一致')
            trials = [read(path / r['result']) for r in finished]
            ai = rows(path / 'ai-ledger.jsonl')
            reserved = sum(r['count'] for r in ai if r['event'] == 'reserved')
            evaluated = sum(r['count'] for r in ai if r['event'] == 'finished')
            if reserved != evaluated:
                raise RuntimeError(name + ': AI予約と完了数の不一致')
            start = read(path / 'started.json')['unix']
            last = max(datetime.fromisoformat(r['utc']).timestamp() for r in finished)
            last_activity = max([last] + [datetime.fromisoformat(r['utc']).timestamp() for r in ai])
            wall = last - start
            audio = sum(r['samples'] / r['sample_rate'] for r in trials)
            trial_time = sum(r['elapsed_seconds'] for r in trials)
            if last_activity - start > LIMITS['max_campaign_seconds']:
                raise RuntimeError(name + ': campaign時間上限超過')
            campaigns.append({
                'campaign': name, 'renders': len(started), 'finished': len(finished),
                'stage_counts': dict(Counter(r['stage'] for r in trials)),
                'AI_reserved': reserved, 'AI_finished': evaluated,
                'E0_failed': len(audit['E0_failed']), 'state': read(path / 'decision.json')['state'],
                'wall_seconds_to_last_render': wall,
                'seconds_to_last_recorded_activity': last_activity - start,
                'sum_trial_seconds': trial_time, 'audio_seconds': audio,
                'trial_RTF': trial_time / audio, 'wall_RTF': wall / audio,
                'wall_seconds_per_render': wall / len(trials), 'seal': seal,
            })
        previous = verify_seal(ROOT / 'results', 'cycle-artifact-seal.json')
        urgent_path = ROOT / 'results/urgent-ja-v1'
        urgent_seal = verify_seal(urgent_path, 'artifact-seal.json')
        urgent = read(urgent_path / 'qualification.json')
        if not read(urgent_path / 'audit.json')['passed']:
            raise RuntimeError('公開評点評価の監査が不通過')
        isolation = read(ROOT / 'results/extension-isolation-v1/verification.json')
        if not isolation['passed']:
            raise RuntimeError('拡張隔離profileの点検が不通過')
        comparison = read(ROOT / 'results/ans-spectral-multistart-v1/speaker-comparison.json')
        valid = [r for r in comparison['rows'] if 'selection_mean_delta' in r]
        boundaries = [{'task': r['task'], 'best_point': r['best_point'],
                       'gain_upper_within_001': any(x >= .99 for x in r['best_point'][3:])}
                      for r in valid]
        approval = read(CYCLE / 'approval.json')
        elapsed = time.time() - approval['unix']
        current = inventory(ROOT)
        added = sum(max(0, size - approval['baseline_inventory'].get(p, 0)) for p, size in current.items())
        if elapsed > LIMITS['max_cycle_seconds'] or added > LIMITS['max_additional_bytes']:
            raise RuntimeError('追加サイクルの時間または保存量の上限超過')
        result = {
            'utc': now(), 'cycle_id': CYCLE_ID, 'state': 'ended-inconclusive',
            'quality_goal_achieved': False, 'promotion_allowed': False,
            'campaigns': campaigns, 'total_renders': sum(r['renders'] for r in campaigns),
            'total_AI_evaluations': sum(r['AI_finished'] for r in campaigns),
            'remaining_authorized_campaign_slots': 0, 'approved_limits': LIMITS,
            'elapsed_seconds_at_close': elapsed, 'additional_bytes_at_close': added,
            'prior_seal': previous, 'urgent_seal': urgent_seal,
            'spectral_diagnostic': {
                'tested_cells': len(valid), 'excluded_cells': comparison['cells_excluded'],
                'selection_improved_cells': comparison['selection_improved_cells'],
                'analysis_registration': comparison['analysis_registration'],
                'gain_upper_boundary_cells': sum(r['gain_upper_within_001'] for r in boundaries),
                'boundary_rows': boundaries,
                'scope': '相対利得の狭い5変数領域での条件別静的残差。共有規則へ移出しない。',
            },
            'E2_diagnostic': urgent['summary'],
            'required_conditions': {
                'unknown_input': '既存の限定入力で生成を確認。任意の日本語全体の品質は未検証。',
                'reference_AI_free': '旧DSP/VTLの隔離生成・波形一致を保持。追加資料の拒否profileはアクセス検査のみ。',
                'required_E1_E2_gates': '未達。内容誤りと物理合成に対応する独立した知覚資格が残る。',
                'P5_quality_adjudication': '未実装。現行confirm/reportは工学確認とinconclusiveの保存まで。品質認定の正の経路を完成済みとみなさない。',
                'reproducible_report': '設定・台帳・結果・コード版・予算・報告を保存。',
            },
            'confirmation_reference_acoustics_consumed': False,
            'confirmation_evidence_scope': '最終参照を用いない読込経路と成果物を確認。全OSアクセスの完全な監査証明ではない。',
            'remaining_work_requires': [
                '追加の実験枠。承認済み3 campaignを使い切ったため、第4枠は自動開始しない。',
                '新利得写像の音声自己回復・E0と、同条件での比較。係数テストだけでは未資格。',
                '対象領域での内容・知覚ゲートの独立資格と、その後の未使用条件によるP5確認。',
                '新しい版で、校正根拠と凍結ゲートを受け取るP5品質判定・認定経路を実装し、境界と再開を検証する。',
            ],
            'source_sha256': file_hash(Path(__file__)),
        }
        # この集計自体は既存結果の読取のみ。凍結済みcampaignへ追記しない。
        write_once(CYCLE / 'decision.json', result)
        tools = list(ROOT.glob('*.py')) + list((ROOT / 'tests').glob('*.py'))
        write_once(CYCLE / 'tools-manifest.json', {
            'files': {str(p.relative_to(ROOT)): file_hash(p) for p in sorted(tools)},
            'scope': '終了時点の研究用スクリプト。各campaignの凍結manifestとは別。',
        })
        print({k: result[k] for k in ('state', 'total_renders', 'total_AI_evaluations',
                                     'elapsed_seconds_at_close', 'additional_bytes_at_close',
                                     'quality_goal_achieved')})


if __name__ == '__main__':
    main()
