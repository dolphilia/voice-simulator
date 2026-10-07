"""参照の存在とhashを内容レビュー前に固定する。"""
from catalog import *

def main():
    b=LocalBudget();refs={};missing=[];rows=[]
    with b.job('setup','保存成果と全新ソースを凍結',1_000_000):
        for ident,base,question,names in CATALOG:
            paths=[]
            for n in names:
                p=base/n
                if p.is_file():refs[str(p.relative_to(REPO))]=digest(p);paths.append(str(p.relative_to(REPO)))
                else:missing.append(str(p.relative_to(REPO)))
            rows.append({'id':ident,'base':str(base.relative_to(REPO)),'question':question,'sources':paths})
        for name in DOCUMENTS:
            p=REPO/'docs/note'/name;assert p.is_file();refs[str(p.relative_to(REPO))]=digest(p)
        for name in ['neural-assisted-non-neural-speech-plan-2026-10-02.md','saved-control-objective-review-proposal-2026-10-03.md']:
            p=REPO/'docs/plans'/name;refs[str(p.relative_to(REPO))]=digest(p)
        save(RESULT/'protocol.json',{'rows':rows,'input_hashes':refs,'missing_expected_sources':missing,
            'source_hashes':{p.name:digest(p) for p in sorted(ROOT.iterdir()) if p.is_file()},
            'protected_unused_confirmation_opened':False,'new_render_ai_fit_inverse_teacher_download_dsp_asr':0,
            'old_primary_gates_unchanged':True,'maximum_next_trials':1,'no_automatic_extension':True})
        save(RESULT/'entry-audit.json',{'passed':True,'campaign_rows':len(rows),'references':len(refs),'missing_sources_preserved':missing})
    print({'rows':len(rows),'references':len(refs),'missing':missing},flush=True)
if __name__=='__main__':main()
