"""内容の読み取りは凍結した参照のみに限定する。"""
from campaign import *

def verify_protocol():
    p=read(RESULT/'protocol.json')
    for n,h in p['source_hashes'].items():assert digest(ROOT/n)==h,n
    for n,h in p['input_hashes'].items():assert digest(REPO/n)==h,n
    return p

def source(path):
    name=str(Path(path).relative_to(REPO));p=read(RESULT/'protocol.json')
    if name not in p['input_hashes']:raise ValueError('凍結参照以外の内容は読みません')
    assert digest(path)==p['input_hashes'][name]
    return read(path)

def validate_outputs(evidence,gap,objective,trial):
    assert len(evidence['rows'])==15 and len({r['id'] for r in evidence['rows']})==15
    assert all(r['sources'] and r['unknowns'] and r['qualification_scope'] for r in evidence['rows'])
    assert not gap['quality_goal_completed'] and not objective['adopted_as_primary_gate']
    assert trial['registered_trials']==1 and not trial['executed'] and not trial['old_primary_gates_changed']
    assert trial['controls'] and trial['inputs'] and trial['limits'] and trial['stop_rules'] and trial['novelty_audit']
    assert not trial['independent_confirmation_claimed']


def negative_tests():
    try:source(REPO/'docs/plans/unused-protected-confirmation.json')
    except ValueError:pass
    else:raise AssertionError('未登録参照を拒否しません')
    return {'unregistered_protected_reference_rejected_before_read':True,'new_audio_measurement_calls':0}
