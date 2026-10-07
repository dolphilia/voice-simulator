"""固定33新群/21旧群を全分母・両ASRで比較する。"""
from paths import *
def grouped(pairs,ng):
 result={}
 for condition in ['both','neutral','higher']:
  for group in ['all','short','long']+['group'+str(g) for g in range(ng)]:
   chosen=[r for r in pairs if (condition=='both' or r['condition']==condition) and (group=='all' or r['length']==group or (group.startswith('group') and r['challenge_group']==int(group[5:])))];valid=[r for r in chosen if r['status']=='completed'];chars=sum(r['characters'] for r in valid);e=sum(r['errors'] for r in valid);base=sum(r['baseline_errors'] for r in valid)
   result[condition+'/'+group]=dict(expected=len(chosen),missing=len(chosen)-len(valid),characters=chars,errors=e,native_errors=base,non_worsening=bool(chosen) and len(valid)==len(chosen) and chars>0 and e<=base)
 return result
def comparison(p,cohort,method,baseline,engine):
 rows=[r for r in p['rows'] if r['cohort']==cohort];ng=8 if cohort=='prospective_once' else 4;pairs=[]
 for row in rows:
  for c in row['requests']:
   q=dict(text_id=row['id'],length=row['length'],challenge_group=row['challenge_group'],condition=c,status='missing');a=HERE/'asr'/engine/'diagnostic'/row['id']/c/(method+'.json');n=HERE/'asr'/engine/'diagnostic'/row['id']/c/(baseline+'.json')
   if a.exists() and n.exists():
    x,y=read(a),read(n)
    if x['status']==y['status']=='completed':
     assert x['reference_kana']==y['reference_kana'] and x['characters']==y['characters']
     assert all(digest(REPO/r['wav'])==r['wav_sha256'] and r['protocol_sha256']==digest(HERE/'protocol.json') for r in [x,y]);q.update(status='completed',errors=x['errors'],baseline_errors=y['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],baseline_hypothesis=y['hypothesis'])
   pairs.append(q)
 groups=grouped(pairs,ng);return dict(pairs=pairs,groups=groups,all_groups_non_worsening=len(pairs)==ng*4 and all(r['non_worsening'] for r in groups.values()))
def tests():
 assert not all(r['non_worsening'] for r in grouped([],8).values())
 p=[dict(condition=c,length=l,challenge_group=g,status='completed',characters=10,errors=0,baseline_errors=0) for c in ['neutral','higher'] for l in ['short','long'] for g in range(8)]
 assert all(r['non_worsening'] for r in grouped(p,8).values());p[0]['status']='missing';assert not all(r['non_worsening'] for r in grouped(p,8).values());p[0]['status']='completed';p[0]['errors']=1;assert not all(r['non_worsening'] for r in grouped(p,8).values())
 return dict(empty_missing_worse_group_rejected=True,fixture_not_quality_evidence=True)
def main():
 b=Budget();p=read(HERE/'protocol.json');content={};engineering={};qualifications={};expanded_vs_frozen={};student_vs_direct={};training={}
 with b.job(NAME,'audit','全336診断/672訓練・固定群集計',reserve_bytes=8000000) as j:
  negative=tests()
  for cohort in ['legacy_diagnostic','prospective_once']:
   content[cohort]={};engineering[cohort]={};expected=32 if cohort=='prospective_once' else 16
   for method in p['variants']:
    content[cohort][method]={e:comparison(p,cohort,method,'native',e) for e in ['whisper','reazon']};pairs=[]
    for row in [r for r in p['rows'] if r['cohort']==cohort]:
     for c in row['requests']:
      r=read(HERE/'render/diagnostic'/row['id']/c/(method+'.json'));pairs.append(dict(id=r['id'],E0_pass=r['E0_pass'],support_complete=r['support_complete'],missing_support=r['missing_support'],state_parameters_preserved_pass=r['duration_only_state_change'] and r['means_variance_MSD_layout_voice_settings_unchanged'] and r['total_frame_count_fixed'] and r['sil_pau_unchanged'],duration_ratio_bounds_pass=all(.8-1e-12<=q['output_frames']/q['native_frames']<=1.25+1e-12 and q['output_frames']>=5 for q in r['time_phone_controls'])))
    engineering[cohort][method]=dict(pairs=pairs,all_required_pass=len(pairs)==expected and all(r['E0_pass'] and r['support_complete'] and r['state_parameters_preserved_pass'] and r['duration_ratio_bounds_pass'] for r in pairs))
   student_vs_direct[cohort]={e:comparison(p,cohort,'student','direct',e) for e in ['whisper','reazon']}
  for method in p['training_variants']:
   training[method]={}
   for e in ['whisper','reazon']:
    values=[read(HERE/'asr'/e/'training'/r['id']/'neutral'/(method+'.json')) for r in p['training_rows']];done=[r for r in values if r['status']=='completed'];training[method][e]=dict(expected=80,original_denominator=96,missing=80-len(done),errors=sum(r['errors'] for r in done),characters=sum(r['characters'] for r in done),training_not_independent_quality=True)
   if method=='oracle':continue
   qualifications[method]=engineering['prospective_once'][method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content['prospective_once'][method].values()) and (method.startswith('neural') or read(HERE/'runtime-audit.json')['passed'])
  b.save(HERE/'summary.json',dict(content=content,engineering=engineering,expanded_vs_frozen=expanded_vs_frozen,student_vs_direct=student_vs_direct,training_ASR=training,training_loss=read(HERE/'model-comparison.json')['training_projected_MSE'],qualifications=qualifications,negative_tests=negative,final_non_neural_runtime_verified=read(HERE/'runtime-audit.json')['passed'],waveform_improvement_not_equivalent_to_training_loss=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
 print(qualifications,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
