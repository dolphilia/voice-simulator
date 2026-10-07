"""全人工条件・否定条件・歴史診断を固定分母で集計する。"""
from paths import *
from controller import verify
def frame_qualified(primary,rows,method):
    uv=sum(x['measurements'][method]['unvoiced_frames'] for x in rows)
    fp=sum(x['measurements'][method]['false_voiced_frames'] for x in rows)
    return dict(primary_expected=96,primary_observed=len(primary),primary_pass_count=sum(x['measurements'][method]['core_pass'] for x in primary),unvoiced_frames=uv,false_voiced_frames=fp,false_voiced_fraction=fp/uv if uv else None,qualified_known_period_primary=bool(len(primary)==96 and all(x['measurements'][method]['core_pass'] for x in primary) and uv and fp/uv<=.05),qualified_for_Japanese_non_neural_speech=False,perceptual_qualification=False,quality_certified=False)
def main():
    verify();b=Budget();b.recover()
    manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==272
    rows=[]
    for item in manifest['rows']:
        assert digest(REPO/item['record'])==item['sha256'];row=read(REPO/item['record']);assert digest(REPO/row['wav'])==row['wav_sha256'];rows.append(row)
    primary=[x for x in rows if x['primary_domain']];negative=[x for x in rows if x['spec']['kind']!='positive']
    assert len(primary)==96 and len(negative)==16
    runtime=read(HERE/'runtime-audit.json');assert runtime['passed'] and len(runtime['pairs'])==272 and len(runtime['CLI'])==4
    methods=['dio','harvest','centered_acf'];qualifications={m:frame_qualified(primary,rows,m) for m in methods}
    global_fp=sum(x['global_ACF']['negative_false_accept'] for x in negative)
    qualifications['legacy_global_ACF']=dict(primary_expected=96,primary_pass_count=sum(x['global_ACF']['core_pass'] for x in primary),negative_cases=16,false_accept_cases=global_fp,qualified_known_period_scalar=bool(all(x['global_ACF']['core_pass'] for x in primary) and global_fp/16<=.05),qualified_fixed_voiced_support=False,qualified_for_Japanese_non_neural_speech=False,perceptual_qualification=False,quality_certified=False)
    groups={}
    definitions=[('all',lambda x:True),('primary',lambda x:x['primary_domain']),('negative',lambda x:x['spec']['kind']!='positive')]
    for key,values in [('f0',[110,220,280,440]),('voiced_ms',[35,60,120,240]),('harmonic',['all','missing_fundamental']),('vowel',['a','u']),('SNR',['none',10]),('ramp_ms',[2,8]),('kind',['positive','white_noise','formant_noise'])]:
        for value in values:definitions.append((key+'/'+str(value),lambda x,k=key,v=value:x['spec'][k]==v))
    for name,select in definitions:
        chosen=[x for x in rows if select(x)];positive=[x for x in chosen if x['spec']['kind']=='positive']
        groups[name]=dict(expected=len(chosen),positive=len(positive),negative=len(chosen)-len(positive),frame={m:dict(core_pass=sum(x['measurements'][m]['core_pass'] for x in positive),core_frames=sum(x['measurements'][m]['core_frames'] for x in positive),correct_core_frames=sum(x['measurements'][m]['correct_core_frames'] for x in positive),unvoiced_frames=sum(x['measurements'][m]['unvoiced_frames'] for x in chosen),false_voiced_frames=sum(x['measurements'][m]['false_voiced_frames'] for x in chosen)) for m in methods},global_ACF=dict(positive_pass=sum(x['global_ACF']['core_pass'] for x in positive),negative_false_accept=sum(x['global_ACF']['negative_false_accept'] for x in chosen)))
    diagnostic_manifest=read(HERE/'diagnostic-manifest.json');assert len(diagnostic_manifest['rows'])==192
    diagnostic={}
    for item in diagnostic_manifest['rows']:
        assert digest(REPO/item['path'])==item['sha256'];row=read(REPO/item['path']);method=row['variant']
        aggregate=diagnostic.setdefault(method,dict(records=0,legacy_missing=0,harvest_missing=0,centered_acf_missing=0,source_truth_available=False,old_decision_changed=False))
        aggregate['records']+=1;aggregate['legacy_missing']+=len(row['reused_legacy_measurement']['missing_support'])
        for tracker in ['harvest','centered_acf']:aggregate[tracker+'_missing']+=len(row['measurements'][tracker]['missing_support'])
    assert all(x['records']==32 for x in diagnostic.values()) and len(diagnostic)==6
    with b.job(NAME,'audit','周期既知域の全条件と192診断を集計',reserve_bytes=500000) as job:
        b.save(HERE/'aggregate-summary.json',dict(known_period_conditions=272,primary_conditions=96,negative_conditions=16,qualifications=qualifications,groups=groups,diagnostic=diagnostic,all_generation_E0_pass=all(x['meta']['E0_pass'] for x in rows),normal_isolated_pairs=272,CLI=4,source_noise_false_accept_is_not_human_voicing_ground_truth=True,scope='人工の周期/雑音源だけの測定検査。HMM/日本語実音声の有声真値や知覚資格は別に必要。',protected_confirmation_opened=False,quality_goal_completed=False,perceptual_qualification=False),job)
    print(qualifications,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
