"""欠損を合格へ置き換えず、文単位で固定比較を集計する。"""
import json
import numpy as np
from campaign import ROOT, RESULT, save, digest


def cer(rows):
    errors = sum(r['errors'] for r in rows)
    characters = sum(r['characters'] for r in rows)
    return {'n': len(rows), 'errors': errors, 'characters': characters,
            'cer': errors/characters if characters else None}


def main():
    protocol = json.loads((RESULT/'protocol.json').read_text())
    groups = {'all': {r['id'] for r in protocol['rows']}}
    for row in protocol['rows']:
        c = row['challenge']
        groups.setdefault(f"f0-{c['requested_f0']}-speed-{c['speed']}", set()).add(row['id'])
    render = [json.loads(p.read_text()) for p in sorted((RESULT/'render').rglob('*.json'))]
    asr = {}
    for engine in ['whisper', 'reazon']:
        rows = [json.loads(p.read_text()) for p in sorted((RESULT/'asr'/engine/'render').rglob('*.json'))]
        comparison = {}
        for condition in protocol['conditions']:
            for group, ids in groups.items():
                values = {variant: cer([r for r in rows if r['condition'] == condition and r['id'] in ids and r['variant'] == variant])
                          for variant in protocol['models']}
                complete = all(v['n'] == len(ids) for v in values.values())
                comparison[condition+'/'+group] = {'values': values, 'complete': complete,
                    'content_protection': {v: complete and values[v]['cer'] <= values['native']['cer']
                                           for v in protocol['models'] if v != 'native'}}
        asr[engine] = comparison
    responses = []
    lookup = {(r['id'], r['condition'], r['variant']): r for r in render}
    for row in protocol['rows']:
        for variant in protocol['models']:
            a = lookup.get((row['id'], 'neutral', variant))
            b = lookup.get((row['id'], 'challenge', variant))
            if not a or not b:
                continue
            f0ratio = b['measurement']['f0_hz']/a['measurement']['f0_hz']
            dratio = b['measurement']['active_seconds']/a['measurement']['active_seconds']
            ferr = abs(f0ratio/(row['challenge']['requested_f0']/220)-1)
            derr = abs(dratio*row['challenge']['speed']-1)
            responses.append({'id': row['id'], 'variant': variant, 'f0_ratio': f0ratio,
                              'active_duration_ratio': dratio, 'f0_relative_error': ferr, 'duration_relative_error': derr,
                              'f0_pass': ferr <= .05, 'duration_pass': derr <= .10,
                              'saturated': b['settings']['saturated']})
    response_summary = {v: {'n': sum(r['variant'] == v for r in responses),
        **{key: sum(r[key] for r in responses if r['variant'] == v) for key in ['f0_pass', 'duration_pass', 'saturated']},
        **{key+'_mean': float(np.mean([r[key] for r in responses if r['variant'] == v])) for key in ['f0_relative_error', 'duration_relative_error']}}
        for v in protocol['models']}
    teachers = {}
    for engine in ['whisper', 'reazon']:
        rows = [json.loads(p.read_text()) for p in sorted((RESULT/'asr'/engine/'teacher').rglob('*.json'))]
        teachers[engine] = {v+'/'+g: cer([r for r in rows if r['variant'] == v and r['id'] in ids])
                           for v in ['jf_alpha', 'jf_gongitsune'] for g, ids in [('all', groups['all']), ('paired8', {r['id'] for r in protocol['rows'][:8]})]}
    starts = [json.loads(line) for line in (RESULT/'ledger.jsonl').read_text().splitlines() if json.loads(line)['event'] == 'start']
    result = {'protocol_sha256': digest(RESULT/'protocol.json'), 'render_count': len(render),
              'E0_pass_count': sum(r['evaluation']['E0_pass'] for r in render),
              'asr': asr, 'responses': responses, 'response_summary': response_summary, 'teachers': teachers,
              'counts': {k: sum(r.get('count', 1) for r in starts if r['kind'] == k) for k in ['teacher', 'render', 'ai', 'setup']},
              'perceptual_quality_certified': False,
              'measurement_caveat': '固定ACF推定器は70–450Hz。範囲外と倍音誤りを含む可能性があり、知覚認定に使わない'}
    save(RESULT/'summary.json', result)
    print(json.dumps({k: result[k] for k in ['render_count', 'E0_pass_count', 'response_summary', 'counts']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
