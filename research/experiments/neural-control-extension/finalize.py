"""追加比較の完全性、費用、旧封印、未達条件を監査する。"""
import json
import time
from pathlib import Path
import numpy as np
from campaign import ExtensionBudget, ROOT, PRIOR, RESULT, save, digest
from summarize import cer


def comparison(source, protocol_name):
    protocol = json.loads((RESULT/protocol_name).read_text())
    groups = {'all': {r['id'] for r in protocol['rows']}}
    if source == 'relative':
        for r in protocol['rows']:
            c = r['challenge']
            groups.setdefault(f"f0-{c['requested_f0']}-speed-{c['speed']}", set()).add(r['id'])
    out = {}
    for engine in ['whisper', 'reazon']:
        rows = [json.loads(p.read_text()) for p in (RESULT/'asr'/engine/source).rglob('*.json')]
        out[engine] = {}
        for group, ids in groups.items():
            values = {v: cer([r for r in rows if r['variant'] == v and r['id'] in ids]) for v in protocol['models']}
            complete = all(v['n'] == len(ids) for v in values.values())
            out[engine][group] = {'values': values, 'complete': complete,
                'content_protection': {v: complete and values[v]['cer'] <= values['native']['cer'] for v in protocol['models'] if v != 'native'}}
    return out


def main():
    budget = ExtensionBudget()
    with budget.job('audit', '追加campaignの完全性と旧封印を監査', 3000000):
        artifact_checks = {}
        for source, expected in [('render', 96), ('teacher', 24), ('relative', 48), ('bounded', 6)]:
            rows = [json.loads(p.read_text()) for p in (RESULT/source).rglob('*.json')]
            wavs = [r for r in rows if 'wav' in r]
            matches = [digest(ROOT/r['wav']) == r['wav_sha256'] for r in wavs]
            if len(wavs) != expected or not all(matches):
                raise ValueError('成果物の件数またはハッシュ不一致: '+source)
            artifact_checks[source] = {'n': len(wavs), 'hashes_verified': True,
                'E0_pass': sum(r.get('evaluation', {}).get('E0_pass', False) for r in wavs) if source != 'teacher' else None}
        for engine in ['whisper', 'reazon']:
            for source, expected in [('render', 96), ('teacher', 24), ('relative', 24), ('bounded', 6)]:
                rows = [json.loads(p.read_text()) for p in (RESULT/'asr'/engine/source).rglob('*.json')]
                if len(rows) != expected or any(digest(ROOT/r['wav']) != r['wav_sha256'] for r in rows):
                    raise ValueError('認識結果の欠損またはハッシュ不一致')
        seals = []
        for name in ['artifact-seal.json', 'post-pilot/artifact-seal.json']:
            seal = json.loads((PRIOR/name).read_text())
            changed = [p for p, h in seal['files'].items() if digest(Path(seal['path_base'])/p) != h]
            if changed:
                raise ValueError('旧封印の変更: '+repr(changed))
            seals.append({'path': str(PRIOR/name), 'files_verified': len(seal['files']), 'sha256': digest(PRIOR/name), 'changed': changed})
        pitch = {}
        for source, protocol_name in [('render', 'protocol.json'), ('relative', 'relative-protocol.json')]:
            protocol = json.loads((RESULT/protocol_name).read_text())
            pitch[source] = {}
            for variant in protocol['models']:
                responses = []
                for row in protocol['rows']:
                    a = json.loads((RESULT/'pitch-audit'/source/row['id']/'neutral'/(variant+'.json')).read_text())
                    b = json.loads((RESULT/'pitch-audit'/source/row['id']/'challenge'/(variant+'.json')).read_text())
                    raw_a = json.loads((RESULT/source/row['id']/'neutral'/(variant+'.json')).read_text())
                    raw_b = json.loads((RESULT/source/row['id']/'challenge'/(variant+'.json')).read_text())
                    ferror = abs(b['dio']['f0_hz']/a['dio']['f0_hz']/(row['challenge']['requested_f0']/220)-1)
                    derror = abs(raw_b['measurement']['active_seconds']/raw_a['measurement']['active_seconds']*row['challenge']['speed']-1)
                    responses.append({'id': row['id'], 'f0_relative_error': ferror, 'duration_relative_error': derror,
                                      'saturated': raw_b['settings']['saturated']})
                pitch[source][variant] = {'n': len(responses), 'f0_pass': sum(r['f0_relative_error'] <= .05 for r in responses),
                    'duration_pass': sum(r['duration_relative_error'] <= .10 for r in responses),
                    'saturation_count': sum(r['saturated'] for r in responses), 'rows': responses}
        known = [json.loads(p.read_text()) for p in (RESULT/'pitch-audit/selfcheck').glob('*.json')]
        save(RESULT/'extended-summary.json', {'relative': comparison('relative', 'relative-protocol.json'),
            'bounded': comparison('bounded', 'bounded-protocol.json'), 'pitch_diagnostic': pitch,
            'pitch_selfcheck': {'n': len(known), 'maximum_dio_relative_error': max(r['dio_relative_error'] for r in known)},
            'artifact_checks': artifact_checks, 'old_seals': seals, 'perceptual_quality_certified': False,
            'primary_summary_unchanged': digest(RESULT/'summary.json')})
        previous = json.loads((PRIOR/'post-pilot/requirements-audit-v2.json').read_text())
        save(RESULT/'requirements-audit.json', {'previous_audit': str(PRIOR/'post-pilot/requirements-audit-v2.json'),
            'previous_audit_sha256': digest(PRIOR/'post-pilot/requirements-audit-v2.json'), 'previous_requirements': previous['requirements'],
            'updates': [
                {'requirement': 'F0/速度組合せ', 'status': 'tested-not-passed', 'evidence': 'summary.json', 'scope': '16文の4条件。固定回帰で11/16飽和、内容保護は不通過'},
                {'requirement': '複数教師', 'status': 'limited', 'evidence': 'summary.json', 'scope': '同じKokoroの2声。別基盤の独立性はない'},
                {'requirement': '内容保護', 'status': 'failed-for-transferred-controls', 'evidence': 'extended-summary.json', 'scope': '主比較・相対版の両方でnativeを上回る認識誤り'},
                {'requirement': 'F0測定', 'status': 'limitation-found', 'evidence': 'pitch-audit-protocol.json', 'scope': 'ACF450の折り返しを検出。DIO800の既知14信号の誤差を記録、実日本語の正解資格にはしない'},
                {'requirement': '自然さの対象資格と独立確認', 'status': 'unavailable', 'evidence': 'public-evidence-review.json', 'scope': '追加調査でも個別評点と対象波形の適格な組を取得できていない'}],
            'all_requirements_met': False, 'quality_goal_unchanged': True,
            'reason': '認識の保護条件、局所制御・測定、知覚資格、独立した最終品質確認が未達'})
    events = budget.events()
    starts = [e for e in events if e['event'] == 'start']
    finishes = {e['id']: e for e in events if e['event'] == 'finish'}
    pending = [e['id'] for e in starts if e['id'] not in finishes]
    if pending:
        raise RuntimeError('監査後に未終了の処理があります')
    contract = budget.initialize()
    counts = {kind: sum(e.get('count', 1) for e in starts if e['kind'] == kind) for kind in ['teacher', 'render', 'ai', 'setup', 'audit']}
    inv = budget.inventory()
    elapsed = time.time()-contract['started_epoch']
    save(RESULT/'cost-audit.json', {'counts': counts, 'limits': contract['limits'], 'wall_seconds': elapsed, 'inventory': inv,
        'failures': [e for e in events if e['event'] == 'finish' and e['status'] != 'completed'], 'pending': pending,
        'within_limits': all(counts[k] <= contract['limits'][k] for k in ['teacher', 'render', 'ai']) and elapsed < contract['limits']['seconds'] and inv['bytes'] < contract['limits']['bytes'],
        'seconds_by_kind': {k: sum(finishes[e['id']]['seconds'] for e in starts if e['kind'] == k) for k in counts},
        'inventory_scan_seconds': sum(e['inventory']['seconds'] for e in starts),
        'remaining_ai': contract['limits']['ai']-counts['ai'], 'campaign_extension_automatic': False})
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
