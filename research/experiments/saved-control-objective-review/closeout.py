"""レビューの四成果・旧21封印・全費用を監査して閉じる。"""
from collections import Counter
from review_io import *

def main():
    p=verify_protocol();b=LocalBudget()
    with b.job('audit','四成果と旧21封印の終了監査',500_000):
        names=['evidence-matrix.json','goal-gap.json','objective-contract-draft.json','next-trial-registration.json'];values=[read(RESULT/n) for n in names]
        validate_outputs(*values)
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        save(RESULT/'completion-audit.json',{'review_completed':True,'artifacts':{n:digest(RESULT/n) for n in names},
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'references_verified':len(p['input_hashes']),'protected_unused_confirmation_opened':False,
            'new_render_ai_fit_inverse_teacher_download_dsp_asr':0,'quality_certified':False,'all_requirements_met':False,'pending_processes':[]})
    events=b.events();starts=[e for e in events if e['event']=='start'];ends=[e for e in events if e['event']=='finish']
    assert {e['id'] for e in starts}=={e['id'] for e in ends};counts=Counter()
    for e in starts:counts[e['kind']]+=e['count']
    assert counts['render']==counts['ai']==counts['teacher']==counts['train']==0
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory();assert seconds<1200 and inv['bytes']+65536<10_000_000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'reserved_job_failures':sum(e['status']=='failed' for e in ends),
        'all_reserved_jobs_finished':True,'seconds_before_report':seconds,'inventory_before_report':inv,
        'new_render_ai_fit_inverse_teacher_download_dsp_asr':0,'resource_limit_compliance':True,'no_automatic_extension':True})
    save(RESULT/'closeout.json',{'campaign_closed':True,'review_completed':True,'quality_goal_completed':False,'next_trial_executed':False,'pending_processes':[]})
    print({'closed':True,'counts':dict(counts),'seconds':seconds,'bytes':inv['bytes']},flush=True)
if __name__=='__main__':main()
