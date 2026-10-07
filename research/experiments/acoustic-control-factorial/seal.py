"""終了した比較の全成果・失敗・ソース・判断を封印する。"""
from collections import Counter
import time
from campaign import FactorialBudget, ROOT, RESULT, REPO, read, save, digest, check_seal


def main():
    budget = FactorialBudget()
    if (RESULT/'artifact-seal.json').exists():
        raise RuntimeError('封印済みです')
    events = budget.events()
    starts = [e for e in events if e['event'] == 'start']
    finishes = {e['id']: e for e in events if e['event'] == 'finish'}
    assert len(starts) == len(finishes) and all(e['id'] in finishes for e in starts)
    counts = Counter()
    for event in starts:
        counts[event['kind']] += event['count']
    assert counts['render'] == 240 and counts['ai'] == 240 and counts['teacher'] == counts['train'] == 0
    for item in read(RESULT/'input-preservation.json')['seals']:
        assert check_seal(REPO/item['seal']) == item
    for name, sha in read(RESULT/'protocol.json')['source_hashes'].items():
        assert digest(ROOT/name) == sha
    assert read(RESULT/'solo-runtime-audit.json')['passed']
    assert not any(x['content_diagnostic_supported'] for x in read(RESULT/'summary.json')['decisions'].values())
    contract = read(RESULT/'contract.json')
    save(RESULT/'closeout.json', {'campaign_closed': True, 'counts': dict(counts),
        'unused_render_calls': 16, 'unused_ai_calls': 0, 'pending_processes': [],
        'no_further_jobs_in_this_campaign': True, 'quality_goal_completed': False,
        'reason': '事前固定した比較と単独実行検査を完了。全方式が内容保護に不通過。',
        'failed_audit_jobs': sum(e['status'] == 'failed' for e in finishes.values()),
        'failure_resolved': True, 'no_automatic_extension': True,
        'next_proposal': 'docs/plans/local-f0-transfer-proposal-2026-10-03.md',
        'next_proposal_authorized': False, 'fresh_resumed_turn': 1, 'current_turn_classification': 'progress'})
    files = [p for p in RESULT.rglob('*') if p.is_file() and p.name != '.lock' and '__pycache__' not in p.parts]
    files += list(ROOT.glob('*.py'))
    files += [REPO/'docs/note/acoustic-control-factorial-result-2026-10-03.md',
              REPO/'docs/plans/local-f0-transfer-proposal-2026-10-03.md']
    inv = budget.inventory()
    elapsed = time.time()-contract['started_epoch']
    assert elapsed < contract['limits']['seconds'] and inv['bytes']+65536 < contract['limits']['bytes']
    save(RESULT/'artifact-seal.json', {'path_base': str(REPO),
        'files': {str(p.relative_to(REPO)): digest(p) for p in sorted(set(files))},
        'campaign': RESULT.name, 'counts': dict(counts), 'wall_seconds_at_seal': elapsed,
        'inventory_before_seal': inv, 'quality_certified': False, 'all_requirements_met': False})
    verified = check_seal(RESULT/'artifact-seal.json')
    print({'sealed_files': verified['verified_files'], 'seconds': elapsed, 'bytes': budget.inventory()['bytes']})


if __name__ == '__main__':
    main()
