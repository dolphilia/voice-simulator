"""成功済みC/資産を保持し、重複ラベルをhash参照にして入力契約を固定する。"""
from paths import *
import ast,hashlib

def main():
    b=Budget();b.recover()
    recovery=read(HERE/'preparation-recovery-v2.json')
    for n,h in recovery['successful_asset_hashes'].items():assert digest(HERE/n)==h,n
    with b.job(NAME,'setup','観測前の全ソース・旧128入力契約を固定',reserve_bytes=2_000_000) as j:
        p=read(PREVIOUS/'protocol.json');records=[]
        for row in p['rows']:
            for condition in p['conditions']:
                for method in ['hts_native','hts_postfilter','hts_voicing','hts_voicing_postfilter']:
                    base=PREVIOUS/'render'/row['id']/condition/method;x=read(base.with_suffix('.json'))
                    assert x['status']=='completed' and digest(REPO/x['wav'])==x['wav_sha256']
                    assert digest(base.with_suffix('.json'))==read(PREVIOUS/'artifact-seal.json')['files'][str(base.with_suffix('.json').relative_to(REPO))]
                    records.append(dict(id=row['id']+'/'+condition+'/'+method,row=dict(id=row['id'],length=row['length'],context_labels_sha256=hashlib.sha256(encode(row['full_context_labels'])).hexdigest()),condition=condition,method=method,
                        old_record=str(base.with_suffix('.json').relative_to(REPO)),old_record_sha256=digest(base.with_suffix('.json')),
                        parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),
                        native_initial=str(base.with_name('native').with_suffix('.npz').relative_to(REPO)),
                        native_initial_sha256=digest(base.with_name('native').with_suffix('.npz'))))
        assert len(records)==128
        b.save(HERE/'protocol.json',dict(records=records,conditions=p['conditions'],registration_sha256=digest(HERE/'registration.json'),
            inputs_are_existing_audit_only=True,no_prospective_quality_claim=True,protected_confirmation_opened=False),j)
        bundle=HERE/'runtime-bundle'
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},
            observer_only=True,diagnostic_from_saved_parameters=True,final_generator_qualification=False),j)
        for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
        b.save(HERE/'execution-contract-v2.json',dict(registration_sha256=digest(HERE/'registration.json'),
            protocol_sha256=digest(HERE/'protocol.json'),source_hashes={p.name:digest(p) for p in HERE.glob('*.py')},
            C_source_sha256=digest(HERE/'observer.c'),observed_primary_sha256=digest(HERE/'HTS_vocoder_observed.c'),
            runtime_manifest_sha256=digest(bundle/'manifest.json'),all_conditions_fixed_before_output=True,
            observer_only=True,old_gates_unchanged=True,quality_goal_completed=False),j)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
