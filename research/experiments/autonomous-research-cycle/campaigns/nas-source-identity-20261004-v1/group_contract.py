import numpy as np

def groups(rows):
    output={}
    for condition in ('neutral','challenge','both'):
        for group in ('all','short','long','group-0','group-1','group-2','group-3'):
            selected=[r for r in rows if (condition=='both' or r['condition']==condition) and
                (group=='all' or r['length']==group or group=='group-'+str(r['challenge_group']))]
            complete=[r for r in selected if r['status']=='completed'];errors=sum(r['errors'] for r in complete)
            native=sum(r['native_errors'] for r in complete);characters=sum(r['characters'] for r in complete)
            output[condition+'/'+group]={'expected':len(selected),'missing':len(selected)-len(complete),
                'independent_texts':len({r['text_id'] for r in selected}),'errors':errors,'native_errors':native,'characters':characters,
                'cer':errors/characters if characters else None,'native_cer':native/characters if characters else None,
                'non_worsening':bool(selected) and len(complete)==len(selected) and errors<=native}
    return output

def mse_groups(rows):
    output={}
    for condition in ('neutral','challenge'):
        for length in ('all','short','long'):
            selected=[r for r in rows if r['condition']==condition and (length=='all' or r['length']==length)]
            complete=[r for r in selected if r['wave_mse'] is not None and r['native_mse'] is not None]
            value=float(np.mean([r['wave_mse'] for r in complete])) if complete else None
            native=float(np.mean([r['native_mse'] for r in complete])) if complete else None
            output[condition+'/'+length]={'expected':len(selected),'missing':len(selected)-len(complete),'mean_mse':value,'native_mean_mse':native,
                'non_worsening':bool(selected) and len(complete)==len(selected) and value<=native,
                'strict_improvement':bool(selected) and len(complete)==len(selected) and value<native}
    return output

def tests():
    rows=[{'text_id':str(i),'condition':c,'length':'short' if i<4 else 'long','challenge_group':i%4,
        'status':'completed','errors':1,'native_errors':1,'characters':5} for i in range(8) for c in ('neutral','challenge')]
    assert len(groups(rows))==21 and all(g['non_worsening'] for g in groups(rows).values())
    bad=[dict(r) for r in rows];bad[0]['status']='missing';assert not all(g['non_worsening'] for g in groups(bad).values())
    bad=[dict(r) for r in rows];bad[0]['errors']=2;assert not all(g['non_worsening'] for g in groups(bad).values())
    assert not any(g['non_worsening'] for g in groups([]).values())
    m=[{**r,'wave_mse':.5,'native_mse':1.} for r in rows];assert all(g['non_worsening'] and g['strict_improvement'] for g in mse_groups(m).values())
    m[0]['wave_mse']=None;assert not all(g['non_worsening'] for g in mse_groups(m).values())
    return {'twenty_one_content_groups':True,'missing_worse_empty_rejected':True,'mse_missing_rejected':True,'render_calls':0,'ai_calls':0}
