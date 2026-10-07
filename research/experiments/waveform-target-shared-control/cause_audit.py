"""保存済み候補だけで資料不足と次案の仮説を点検する。生成・fit・AIは呼ばない。"""
from collections import Counter
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest
from inverse import qualify


def main():
    with LocalBudget().job('audit','21文の目標不通過・支持域失敗・既存対照候補を静的に解析',2000000):
        manifest=read(RESULT/'target-manifest.json');assert not manifest['fit_supported']
        rejected=Counter();methods=Counter();stops=Counter();rows=[];counterfactual=[]
        attempts=[read(p) for p in (RESULT/'inverse-render').rglob('*.json') if p.stem not in ('support-contract','state-inverse')]
        failures=[{'text_id':r['text_id'],'attempt':r['attempt'],'missing_support':r.get('missing_support'),
            'error':r.get('error'),'coefficients':r['coefficients']} for r in attempts if r['status']!='completed']
        for row in manifest['rows']:
            path=RESULT/'searches'/(row['id']+'.json');s=read(path);n,t,w=[s[v] for v in ('native','statefit','wavefit')]
            for k,v in row['qualification'].get('checks',{}).items():
                if not v:rejected[k]+=1
            for i in s['iterations']:
                methods.update(i['derivative_methods'])
                if 'stop_reason' in i:stops[i['stop_reason']]+=1
            qstate=qualify(n,t,t);qwave=qualify(n,t,w)
            candidates=[(name,r,q) for name,r,q in [('statefit',t,qstate),('wavefit',w,qwave)] if q['qualified'] and r['objective']<n['objective']]
            chosen=min(candidates,key=lambda item:item[1]['objective']) if candidates else None
            detail={'id':row['id'],'text':row['text'],'length':row['length'],'current_qualified':row['qualification']['qualified'],
                'state_candidate_qualified':qstate['qualified'],'state_maximum_coefficient':max(abs(c) for c in t['coefficients']),
                'wave_maximum_coefficient':max(abs(c) for c in w['coefficients']),
                'state_objective':t['objective'],'wave_objective':w['objective'],'native_objective':n['objective'],
                'state_wave_mse':t['wave_mse'],'wavefit_wave_mse':w['wave_mse'],
                'state_outside_native_three_step_reach':max(abs(c) for c in t['coefficients'])>1.5,
                'state_protection':qstate.get('relative_to_native'),'selected_for_future_proposal_only':chosen[0] if chosen else None}
            rows.append(detail)
            if chosen:
                name,r,q=chosen
                counterfactual.append({'id':row['id'],'text':row['text'],'length':row['length'],'variant':name,
                    'source':str(path.relative_to(REPO)),'source_sha256':digest(path),'attempt':r['attempt'],
                    'wav':str((ROOT/r['wav']).relative_to(REPO)),'wav_sha256':r['wav_sha256'],
                    'coefficients':r['coefficients'],'wave_mse':r['wave_mse'],'objective':r['objective'],'qualification':q})
        result={'current_qualified':manifest['qualified_utterances'],'minimum_required':12,'fit_supported':False,
            'rejected_checks':dict(rejected),'derivative_methods':dict(methods),'stop_reasons':dict(stops),
            'render_attempts':len(attempts),'render_failures':failures,'rows':rows,
            'accepted_updates':sum(read(RESULT/'searches'/(r['id']+'.json'))['iterations'][i]['accepted'] for r in manifest['rows'] for i in range(len(read(RESULT/'searches'/(r['id']+'.json'))['iterations']))),
            'extra_shrink_renders':sum(read(RESULT/'searches'/(r['id']+'.json'))['extra_shrink_renders'] for r in manifest['rows']),
            'future_candidate_inventory':counterfactual,'future_inventory_count':len(counterfactual),
            'future_inventory_lengths':dict(Counter(r['length'] for r in counterfactual)),
            'current_targets_modified':False,'future_selection_executed_as_training':False,
            'new_generation_calls':0,'new_shared_fits':0,'new_ai_calls':0,
            'interpretation':'3反復・1軸0.5ではゼロから各係数1.5まで。状態候補に届かない場合があるが、数理的最適性は示さない。保存済み実波形の状態候補も含める方法を次案で別契約にする。',
            'quality_certified':False,'all_requirements_met':False}
        save(RESULT/'cause-audit.json',result)
        print({'qualified':manifest['qualified_utterances'],'rejected':dict(rejected),'future_inventory':len(counterfactual),'fits_started':False},flush=True)

if __name__=='__main__':main()
