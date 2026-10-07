"""全文字、固定支持、両認識器の全群を旧ゲートのまま集計する。"""
from paths import *
from group_contract import groups,tests

def pairs(p,cohort,method,baseline,engine):
 rows=[]
 for r in p['rows']:
  if r['cohort']!=cohort:continue
  for c in r['requests']:
   a=read(HERE/'asr'/engine/(r['id']+'/'+c+'/'+method+'.json'));n=read(HERE/'asr'/engine/(r['id']+'/'+c+'/'+baseline+'.json'))
   z={'text_id':r['id'],'condition':c,'length':r['length'],'challenge_group':r['challenge_group'],'status':'missing'}
   if a['status']==n['status']=='completed':
    assert a['reference_kana']==n['reference_kana'] and a['characters']==n['characters']
    for q in [a,n]:assert digest(REPO/q['wav'])==q['wav_sha256'] and q['protocol_sha256']==digest(HERE/'protocol.json')
    z.update(status='completed',errors=a['errors'],native_errors=n['errors'],characters=a['characters'],candidate_hypothesis=a['hypothesis'],baseline_hypothesis=n['hypothesis'])
   rows.append(z)
 out=groups(rows);return {'pairs':rows,'groups':out,'all_21_groups_non_worsening':len(rows)==16 and all(q['non_worsening'] for q in out.values())}
def main():
 b=Budget();p=read(HERE/'protocol.json');content={};engineering={}
 with b.job(NAME,'audit','旧群条件のまま韻律制限による内容・工学差を集計',reserve_bytes=2_000_000) as j:
  test=tests()
  for cohort in ['legacy_diagnostic','prospective_once']:
   content[cohort]={};engineering[cohort]={}
   for method in p['variants'][1:]:
    content[cohort][method]={e:pairs(p,cohort,method,'native',e) for e in ['whisper','reazon']};checks=[]
    for row in [r for r in p['rows'] if r['cohort']==cohort]:
     for c in row['requests']:
      a=read(HERE/'render'/(row['id']+'/'+c+'/'+method+'.json'));n=read(HERE/'render'/(row['id']+'/'+c+'/native.json'));av=a['measurement'];nv=n['measurement'];relative={}
      for key in ['f0_hz','active_seconds']:
       x,z=av['global_acf'].get(key),nv['global_acf'].get(key);relative[key]=x/z-1 if x is not None and z is not None and z>0 else None
      x,z=av['dio_median_hz'],nv['dio_median_hz'];relative['dio_f0']=x/z-1 if x is not None and z is not None and z>0 else None
      flags={'E0':a['E0_pass'] and n['E0_pass'],'support':a['support_complete'] and n['support_complete'],'internal':a.get('internal_unchanged',a.get('all_state_streams_unchanged_except_registered_lf0',False)),'global_f0':all(relative[k] is not None and abs(relative[k])<=.05 for k in ['f0_hz','dio_f0']),'duration':relative['active_seconds'] is not None and abs(relative['active_seconds'])<=.03}
      checks.append({'id':a['id'],'checks':flags,'passed':all(flags.values()),'relative':relative,'missing_support':a['missing_support'],'native_missing_support':n['missing_support'],'raw_peak':a['raw_peak'],'gain':a['output_gain'],'rms':a['rms']})
    engineering[cohort][method]={'pairs':checks,'all_old_guards_pass':all(q['passed'] for q in checks)}
   for a,n in [('direct_prosody','direct_non_neural'),('distilled_prosody','distilled_non_neural')]:content[cohort][a+'_vs_16']={e:pairs(p,cohort,a,n,e) for e in ['whisper','reazon']}
  qualifies={}
  for m in p['variants'][1:]:
   c=all(content[k][m][e]['all_21_groups_non_worsening'] for k in content for e in ['whisper','reazon']);eng=all(engineering[k][m]['all_old_guards_pass'] for k in engineering)
   qualifies[m]={'content_non_worsening_both_cohorts_both_ASR':c,'engineering':eng,'limited_diagnostic_supported':c and eng,'quality_certified':False}
  b.save(HERE/'summary.json',{'content':content,'engineering':engineering,'qualifications':qualifies,'training_wave':read(HERE/'training-wave-summary.json'),'model_training_proxy':read(HERE/'model-comparison.json'),'normal_isolated_runtime':read(HERE/'runtime-audit.json')['passed'],'group_negative_tests':test,'quality_goal_completed':False,'independent_final_confirmation':False,'limitations':['旧8は再使用診断','新8も小標本の前向き診断で広い日本語自然さの正解ではない','DIO短イベント資格未達を維持','訓練4文の波形教師距離は未知文転移の証明ではない'],'no_tuning_after_ASR':True},j)
 print(qualifies,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
