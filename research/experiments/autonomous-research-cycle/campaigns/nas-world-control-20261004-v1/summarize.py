"""全分母を保持し、WORLD対照と直接/学生対標準を別判定する。"""
from paths import *
import sys,numpy as np
from group_contract import groups,tests

def pairs(p,cohort,method,baseline_method,engine):
 out=[]
 for row in [r for r in p['rows'] if r['cohort']==cohort]:
  for condition in row['requests']:
   a=read(HERE/'asr'/engine/'world'/row['id']/condition/(method+'.json'))
   n=read(HERE/'asr'/engine/'baseline'/row['id']/condition/(baseline_method+'.json'))
   pair={'text_id':row['id'],'condition':condition,'length':row['length'],'challenge_group':row['challenge_group'],'status':'missing'}
   if a['status']==n['status']=='completed':
    assert a['reference_kana']==n['reference_kana'] and a['characters']==n['characters']
    for r in [a,n]:assert digest(REPO/r['wav'])==r['wav_sha256'] and r['protocol_sha256']==digest(HERE/'protocol.json')
    pair.update(status='completed',errors=a['errors'],native_errors=n['errors'],characters=a['characters'],candidate_hypothesis=a['hypothesis'],baseline_hypothesis=n['hypothesis'])
   out.append(pair)
 return {'pairs':out,'groups':groups(out),'both_lengths_and_four_groups':len(out)==16,
  'all_21_groups_non_worsening':len(out)==16 and all(r['non_worsening'] for r in groups(out).values())}

def main():
 b=Budget();p=read(HERE/'protocol.json');engines=['whisper','reazon'];content={};engineering={};qualifications={}
 with b.job(NAME,'audit','WORLD生成器対照の全群・全欠損と技術条件を集計',reserve_bytes=2_000_000) as j:
  test=tests()
  for cohort in ['legacy_diagnostic','prospective_once']:
   content[cohort]={};engineering[cohort]={}
   for method in p['variants']:
    content[cohort][method]={e:pairs(p,cohort,method,method,e) for e in engines}
    checks=[]
    for row in [r for r in p['rows'] if r['cohort']==cohort]:
     for condition in row['requests']:
      path=row['id']+'/'+condition+'/'+method+'.json'
      a=read(HERE/'render/identity'/path);n=read(HERE/'render/baseline'/path)
      assert a['source_parameter_hashes']==n['source_parameter_hashes'] and a['state_deltas_sha256']==n['state_deltas_sha256']
      assert a['output_gain']==n['output_gain']
      av=a['measurement'];nv=n['measurement'];differences={}
      for f,limit in [('f0_hz',.05),('active_seconds',.03)]:
       x=av['global_acf'].get(f);z=nv['global_acf'].get(f)
       differences[f]=x/z-1 if x is not None and z is not None and z>0 else None
      x=av['dio_median_hz'];z=nv['dio_median_hz'];differences['dio_f0']=x/z-1 if x is not None and z is not None and z>0 else None
      local=[r for r in av['local'] if r['index'] in [v['label_index'] for v in n['local_measurements']]+n['missing_support']]
      guards={'E0':a['E0_pass'] and n['E0_pass'],'candidate_support':a['support_complete'],
       'baseline_support':n['support_complete'],'fixed_internal_and_gain':True,
       'global_f0':all(differences[k] is not None and abs(differences[k])<=.05 for k in ['f0_hz','dio_f0']),
       'active_duration':differences['active_seconds'] is not None and abs(differences['active_seconds'])<=.03}
      checks.append({'id':a['id'],'checks':guards,'passed':all(guards.values()),'relative':differences,
       'baseline_missing':n['missing_support'],'candidate_missing':a['missing_support'],
       'fixed_support_lf0_dio_missing_frames':sum(r['lf0_voiced_dio_missing_frames'] for r in local),
       'fixed_support_false_voiced_frames':sum(r['lf0_unvoiced_dio_voiced_frames'] for r in local),
       'boundary_included_gross_frames':sum(r['over_one_half_tone_frames'] for r in local),
       'rms_ratio':a['rms']/n['rms'] if n['rms'] else None,
       'wave_shape_pair_mse':float(np.mean((np.asarray(a['wave_shape'])-np.asarray(n['wave_shape']))**2)) if a['wave_shape'] is not None and n['wave_shape'] is not None else None})
    engineering[cohort][method]={'pairs':checks,'all_old_guards_pass':all(r['passed'] for r in checks)}
   content[cohort]['direct_identity_vs_native']={e:pairs(p,cohort,'direct_non_neural','native',e) for e in engines}
   content[cohort]['student_identity_vs_native']={e:pairs(p,cohort,'distilled_non_neural','native',e) for e in engines}
   content[cohort]['direct_prosody_vs_native']={e:pairs(p,cohort,'direct_prosody','native',e) for e in engines}
   content[cohort]['student_prosody_vs_native']={e:pairs(p,cohort,'distilled_prosody','native',e) for e in engines}
  for method in p['variants']:
   qualifies=all(content[c][method][e]['all_21_groups_non_worsening'] for c in content for e in engines)
   protection=all(engineering[c][method]['all_old_guards_pass'] for c in engineering)
   qualifications[method]={'both_asr_both_cohorts_non_worsening':qualifies,'old_engineering_and_support':protection,
    'limited_diagnostic_supported':qualifies and protection,'quality_certified':False}
  b.save(HERE/'summary.json',{'content':content,'engineering':engineering,'qualifications':qualifications,
   'normal_isolated_runtime':read(HERE/'runtime-audit.json')['passed'],'group_negative_tests':test,
   'teacher_target_mse_available':False,'scope':'旧8と新8は教師なし。形状の相互差MSEは記述統計で、教師目標への改善と呼ばない。',
   'quality_goal_completed':False,'independent_final_quality_confirmation':False,'no_optimization_after_asr':True,
   'limitations':['二ASRは固定診断で知覚資格ではない','DIOの短イベント資格不足を維持','旧8は内容/原因分析へ使用済み','新8は観測済み全履歴と照合した前向き診断。保護された独立最終確認は未開封']},j)
 print(qualifications,flush=True)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
