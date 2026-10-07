"""スペクトル共有制御を二指定・固定全21群・欠損込みで集計する。"""
from paths import *

def grouped(pairs):
 result={}
 for condition in ['both','neutral','higher']:
  for group in ['all','short','long','group0','group1','group2','group3']:
   chosen=[r for r in pairs if (condition=='both' or r['condition']==condition) and (group=='all' or r['length']==group or (group.startswith('group') and r['challenge_group']==int(group[5:])))];valid=[r for r in chosen if r['status']=='completed'];chars=sum(r['characters'] for r in valid);e=sum(r['errors'] for r in valid);base=sum(r['baseline_errors'] for r in valid)
   result[condition+'/'+group]=dict(expected=len(chosen),missing=len(chosen)-len(valid),characters=chars,errors=e,native_errors=base,non_worsening=bool(chosen) and len(valid)==len(chosen) and chars>0 and e<=base)
 return result

def comparison(p,cohort,method,baseline,engine):
 pairs=[]
 for row in [r for r in p['rows'] if r['cohort']==cohort]:
  for c in row['requests']:
   q=dict(text_id=row['id'],length=row['length'],challenge_group=row['challenge_group'],condition=c,status='missing');a=HERE/'asr'/engine/'diagnostic'/row['id']/c/(method+'.json');n=HERE/'asr'/engine/'diagnostic'/row['id']/c/(baseline+'.json')
   if a.exists() and n.exists():
    x,y=read(a),read(n)
    if x['status']==y['status']=='completed':
     assert x['reference_kana']==y['reference_kana'] and x['characters']==y['characters']
     assert all(digest(REPO/r['wav'])==r['wav_sha256'] and r['protocol_sha256']==digest(HERE/'protocol.json') for r in [x,y]);q.update(status='completed',errors=x['errors'],baseline_errors=y['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],baseline_hypothesis=y['hypothesis'])
   pairs.append(q)
 groups=grouped(pairs);return dict(pairs=pairs,groups=groups,all_groups_non_worsening=len(pairs)==16 and all(r['non_worsening'] for r in groups.values()))
def tests():
 assert not all(r['non_worsening'] for r in grouped([]).values());p=[dict(condition=c,length=l,challenge_group=g,status='completed',characters=10,errors=0,baseline_errors=0) for c in ['neutral','higher'] for l in ['short','long'] for g in range(4)];assert all(r['non_worsening'] for r in grouped(p).values());p[0]['status']='missing';assert not all(r['non_worsening'] for r in grouped(p).values());p[0]['status']='completed';p[0]['errors']=1;assert not all(r['non_worsening'] for r in grouped(p).values());return dict(empty_missing_worse_group_rejected=True,fixture_not_quality_evidence=True)
def main():
 b=Budget();p=read(HERE/'protocol.json');content={};engineering={};qualifications={};student_vs_direct={};training={}
 with b.job(NAME,'audit','スペクトル比較の固定21群と全工学分母を集計',reserve_bytes=1500000) as j:
  negative=tests()
  for cohort in ['legacy_diagnostic','prospective_once']:
   content[cohort]={};engineering[cohort]={}
   for method in p['variants']:
    content[cohort][method]={e:comparison(p,cohort,method,'native',e) for e in ['whisper','reazon']};pairs=[]
    for row in [r for r in p['rows'] if r['cohort']==cohort]:
     for c in row['requests']:
      r=read(HERE/'render/diagnostic'/row['id']/c/(method+'.json'));pairs.append(dict(id=r['id'],E0_pass=r['E0_pass'],support_complete=r['support_complete'],missing_support=r['missing_support'],state_and_unchanged_streams_pass=r['c0_c9plus_LF0_LPF_state_clock_unchanged'],L1_bound_pass=r['frame_coefficient_L1_max']<=.5+1e-12))
    engineering[cohort][method]=dict(pairs=pairs,all_required_pass=len(pairs)==16 and all(r['E0_pass'] and r['support_complete'] and r['state_and_unchanged_streams_pass'] and r['L1_bound_pass'] for r in pairs))
   student_vs_direct[cohort]={e:comparison(p,cohort,'distilled_non_neural','direct_non_neural',e) for e in ['whisper','reazon']}
  for method in p['variants']:
   training[method]={}
   for e in ['whisper','reazon']:
    values=[read(HERE/'asr'/e/'training'/q['id']/'neutral'/(method+'.json')) for q in read(SPECTRAL1/'alignment-manifest.json')['rows'] for q in [q['row']]];done=[r for r in values if r['status']=='completed'];training[method][e]=dict(expected=17,missing=17-len(done),errors=sum(r['errors'] for r in done),characters=sum(r['characters'] for r in done),training_not_independent_quality=True)
   qualifications[method]=engineering['prospective_once'][method]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content['prospective_once'][method].values()) and (method=='neural' or read(HERE/'runtime-audit.json')['passed'])
  b.save(HERE/'summary.json',dict(content=content,engineering=engineering,student_vs_direct=student_vs_direct,training_ASR=training,training_loss=read(HERE/'model-comparison.json')['training_projected_MSE'],qualifications=qualifications,negative_tests=negative,final_non_neural_runtime_verified=read(HERE/'runtime-audit.json')['passed'],waveform_improvement_not_equivalent_to_training_loss=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
 print(qualifications,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
