"""各固定境界対照を欠損・固定7群込みで集計する。"""
from paths import *

def grouped(pairs):
 result={}
 for label in ['all','short','long','group0','group1','group2','group3']:
  chosen=[r for r in pairs if label=='all' or r['length']==label or (label.startswith('group') and r['challenge_group']==int(label[5:]))];valid=[r for r in chosen if r['status']=='completed'];chars=sum(r['characters'] for r in valid);e=sum(r['errors'] for r in valid);be=sum(r['baseline_errors'] for r in valid)
  result[label]=dict(expected=len(chosen),missing=len(chosen)-len(valid),errors=e,baseline_errors=be,characters=chars,non_worsening=bool(chosen) and len(valid)==len(chosen) and chars>0 and e<=be)
 return result

def compare(p,cohort,candidate,baseline,engine):
 rows=[]
 for r in [r for r in p['rows'] if r['cohort']==cohort]:
  a=HERE/'asr'/engine/candidate[0]/r['id']/candidate[1]/(candidate[2]+'.json');n=HERE/'asr'/engine/baseline[0]/r['id']/baseline[1]/(baseline[2]+'.json');q=dict(text_id=r['id'],length=r['length'],challenge_group=r['challenge_group'],status='missing')
  if a.exists() and n.exists():
   x,y=read(a),read(n)
   if x['status']==y['status']=='completed':
    assert x['reference_kana']==y['reference_kana'] and x['characters']==y['characters']
    assert all(digest(REPO/v['wav'])==v['wav_sha256'] and v['protocol_sha256']==digest(HERE/'protocol.json') for v in [x,y])
    q.update(status='completed',errors=x['errors'],baseline_errors=y['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],baseline_hypothesis=y['hypothesis'])
  rows.append(q)
 g=grouped(rows);return dict(pairs=rows,groups=g,all_groups_non_worsening=all(a['non_worsening'] for a in g.values()))
def main():
 b=Budget();p=read(HERE/'protocol.json');content={};engineering=[]
 with b.job(NAME,'audit','境界全固定群・埋め込みstep・先生間比較',reserve_bytes=1500000) as j:
  assert not all(q['non_worsening'] for q in grouped([]).values())
  for cohort in ['legacy_diagnostic','prospective_once']:
   content[cohort]={}
   for mode in ['teacher','world']:
    for teacher in p['teachers']:
     for policy in ['pad_900ms','taper12ms_pad900ms']:
      name='/'.join([mode,teacher,policy,'vs_raw']);content[cohort][name]={e:compare(p,cohort,(mode,policy,teacher),(mode,'raw',teacher),e) for e in ['whisper','reazon']}
    for policy in ['raw','pad_900ms','taper12ms_pad900ms']:
     name='/'.join([mode,policy,'jvnv_vs_kokoro']);content[cohort][name]={e:compare(p,cohort,(mode,policy,'jvnv'),(mode,policy,'kokoro'),e) for e in ['whisper','reazon']}
   for teacher in p['teachers']:
    for policy in ['raw','pad_900ms','taper12ms_pad900ms']:
     name='/'.join([teacher,policy,'WORLD_vs_own_teacher']);content[cohort][name]={e:compare(p,cohort,('world',policy,teacher),('teacher',policy,teacher),e) for e in ['whisper','reazon']}
  for q in read(HERE/'render-manifest.json')['rows']:
   r=read(REPO/q['record']);engineering.append(dict(id=q['id'],cohort=r['cohort'],condition=r['condition'],mode=r['mode'],teacher=r['variant'],E0_pass=r['E0_pass'],source_payload_safe=r['source_payload_checks_except_endpoint_pass'],boundary=r['boundary'],joint_engineering_pass=r['E0_pass'] and r['source_payload_checks_except_endpoint_pass'] and r['boundary']['internal_join_continuity']))
  qualifications={}
  for mode in ['teacher','world']:
   for teacher in p['teachers']:
    for policy in ['pad_900ms','taper12ms_pad900ms']:
     name='/'.join([mode,teacher,policy,'vs_raw']);q=[r for r in engineering if r['cohort']=='prospective_once' and r['mode']==mode and r['teacher']==teacher and r['condition']==policy];qualifications[name]=len(q)==8 and all(r['joint_engineering_pass'] for r in q) and all(v['all_groups_non_worsening'] for v in content['prospective_once'][name].values())
  b.save(HERE/'summary.json',dict(content=content,engineering=engineering,qualifications=qualifications,quality_goal_completed=False,final_non_neural_text_transfer_verified=False,perceptual_qualification=False,protected_confirmation_opened=False,old_ASR_results_not_rewritten=True,old_reuse_not_independent_evidence=True,whole_boundary_policy_not_recognizer_training_causal_test=True,limitations=['全教師/声/内部正規化の対照で単一原因ではない','24k波形paddingと公式16k後paddingは厳密同一入口でない','旧12は診断、新8は前向き境界比較、独立最終確認は未開封','WORLDは教師音声を必要とする研究再合成','工程/内容支持と自然さ/未知文共有移出を区別']),j)
 print(qualifications,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
