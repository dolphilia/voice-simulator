"""S1、必要ならS2を一度ずつ実施して、測定適合の可否を固定する。"""
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import scipy
from .models import known, response, starts
from .objective import metrics, optimal_gain, state
from .optimization import fit


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def qualify(root):
    spec_path = root/'config/e0-spec.json'
    spec = json.loads(spec_path.read_text())
    proposal = root.parents[2]/'docs/note/independent-voice-synthesis-proposal-v3.md'
    if digest(proposal) != spec['proposal_sha256']:
        raise ValueError('提案書のhashが固定仕様と異なります')
    out = root/'results/e0/qualification'
    out.mkdir(parents=True, exist_ok=False)
    summary = dict(status='running', started=datetime.now(timezone.utc).isoformat(),
                   spec_sha256=digest(spec_path), proposal_sha256=digest(proposal),
                   environment=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,
                                    platform=platform.platform(), precision='binary64'),
                   code_sha256={str(p.relative_to(root)):digest(p) for p in sorted((root/'src').rglob('*.py'))},
                   settings={}, selected_setting=None, evaluations=0, auxiliary_evaluations=0,
                   public_data_read=False)
    save(out/'summary.json',summary)
    def evaluate(p,f):
        if summary['auxiliary_evaluations'] >= spec['budget']['auxiliary']:
            raise ValueError('別枠評価上限に達しました')
        summary['auxiliary_evaluations'] += 1
        return response(p,f)
    try:
        grid = np.arange(100.,5001.)
        ffit, fcheck = grid[1::2],grid[::2]
        for label,setting in spec['settings'].items():
            details = {}
            q = np.r_[3.2,np.full(99,-3.2/99)]
            a,m = optimal_gain(q)
            details['K0'] = dict(gain_db=a, score=m, passed=bool(metrics(q)['J']>1 and metrics(q-.25)['J']<1 and m['J']<1 and optimal_gain(np.tile([-.6,.6],50))[1]['J']<m['J']))
            targets = {}
            all_fits = {}
            for k,zero in [('K1',False),('K2',True)]:
                targets[k] = 20*np.log10(abs(evaluate(known(zero),grid)))
                truth_error = metrics(20*np.log10(abs(evaluate(known(zero),grid)))-targets[k])
                details[k] = dict(truth_error=truth_error)
                p5 = None
                for model in ('P5','P5Z'):
                    result = fit(ffit,targets[k][1::2],setting,spec['budget']['qualification_per_start'],p5)
                    summary['evaluations'] += result['evaluations']
                    if summary['evaluations'] > spec['budget']['qualification_total']:
                        raise ValueError('点検探索の総予算超過')
                    save(out/f'{label}-{k}-{model}.json',result)
                    all_fits[(k,model)] = result
                    if model == 'P5':
                        p5 = result['best']['parameters']
                    elif result['best']['J'] > all_fits[(k,'P5')]['best']['J']+1e-8:
                        raise ValueError('P5との包含成績が不整合です')
                    print(f'{label} {k} {model}: Jfit={result["best"]["J"]:.6f}, 評価={result["evaluations"]}',flush=True)
            # 各設定の4候補を保存後にのみ保留点を評価する。
            for (k,model),result in all_fits.items():
                check = metrics(20*np.log10(abs(evaluate(result['best']['parameters'],fcheck)))-targets[k][::2])
                details[k][model] = dict(fit={v:result['best'][v] for v in ('R','M','J')}, check=check,
                                           state=state(result['best']['J'],check['J']))
            h = evaluate(known(),grid)
            inclusion = float(np.max(abs(evaluate({**known(),'rho':0.,'fz':2000.},grid)/h-1)))
            points = np.array([1800.,2000.,2200.])
            delta = 20*np.log10(abs(evaluate(known(True),points)/evaluate(known(),points)))
            notch = bool(delta[1]+6 <= min(delta[0],delta[2]))
            recovery = {}
            for k,model in [('K1','P5'),('K2','P5Z')]:
                d = details[k][model]
                recovery[k] = all(d[part]['R'] <= .05 and d[part]['M'] <= .15 for part in ('fit','check'))
            passed = bool(details['K0']['passed'] and inclusion <= 1e-12 and notch and all(recovery.values()) and
                          all(details[k]['truth_error']['M'] <= 1e-8 for k in ('K1','K2')) and details['K1']['P5']['state']=='pass')
            summary['settings'][label] = dict(options=setting,details=details,inclusion_relative_error=inclusion,
                                             notch_delta_db=delta.tolist(),notch_passed=notch,recovery=recovery,passed=passed)
            save(out/'summary.json',summary)
            if passed:
                summary['selected_setting'] = label
                break
        summary['status'] = 'qualified' if summary['selected_setting'] else 'qualification_failed'
        summary['e0_conclusion'] = '測定適合へ進める' if summary['selected_setting'] else '既知応答の点検不通過。公開測定について結論なし。追加探索せずE0終了。'
        summary['finished'] = datetime.now(timezone.utc).isoformat()
        save(out/'summary.json',summary)
    except Exception as exc:
        summary.update(status='invalid',error=str(exc),finished=datetime.now(timezone.utc).isoformat())
        save(out/'summary.json',summary)
        raise
