"""先生比較/各解析再合成を全群・欠損込みで個別集計する。"""
from paths import *

def grouped(pairs,cohort):
 labels=['all','short','long','group0','group1']+(['group2','group3'] if cohort=='prospective_once' else [])
 result={}
 for label in labels:
  chosen=[r for r in pairs if label=='all' or r['length']==label or (label.startswith('group') and r['challenge_group']==int(label[5:]))]
  valid=[r for r in chosen if r['status']=='completed'];errors=sum(r['errors'] for r in valid);baseline=sum(r['baseline_errors'] for r in valid);chars=sum(r['characters'] for r in valid)
  result[label]={'expected':len(chosen),'missing':len(chosen)-len(valid),'errors':errors,'baseline_errors':baseline,'characters':chars,'non_worsening':bool(chosen) and len(chosen)==len(valid) and chars>0 and errors<=baseline}
 return result

def tests():
 assert not all(r['non_worsening'] for r in grouped([], 'prospective_once').values())
 p=[{'length':l,'challenge_group':g,'status':'completed','characters':10,'errors':0,'baseline_errors':0} for l in ['short','long'] for g in range(4)]
 assert all(r['non_worsening'] for r in grouped(p,'prospective_once').values())
 p[0]['status']='missing';assert not all(r['non_worsening'] for r in grouped(p,'prospective_once').values());p[0]['status']='completed';p[0]['errors']=1;assert not all(r['non_worsening'] for r in grouped(p,'prospective_once').values())
 return {'empty_rejected':True,'missing_rejected':True,'worse_group_rejected':True,'fixture_is_not_quality_evidence':True}

def compare(p,cohort,candidate,baseline,engine):
 pairs=[]
 for row in [r for r in p['rows'] if r['cohort']==cohort]:
  item=dict(text_id=row['id'],length=row['length'],challenge_group=row['challenge_group'],status='missing')
  a=HERE/'asr'/engine/candidate[0]/row['id']/'neutral'/(candidate[1]+'.json');n=HERE/'asr'/engine/baseline[0]/row['id']/'neutral'/(baseline[1]+'.json')
  if a.exists() and n.exists():
   x,y=read(a),read(n)
   if x['status']==y['status']=='completed':
    assert x['reference_kana']==y['reference_kana'] and x['characters']==y['characters']
    assert all(digest(REPO[r['wav']])==r['wav_sha256'] and r['protocol_sha256']==digest(HERE/'protocol.json') for r in [x,y])
    item.update(status='completed',errors=x['errors'],baseline_errors=y['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],baseline_hypothesis=y['hypothesis'])
  pairs.append(item)
 return {'pairs':pairs,'groups':grouped(pairs,cohort),'all_groups_non_worsening':len(pairs)==(8 if cohort=='prospective_once' else 4) and all(r['non_worsening'] for r in grouped(pairs,cohort).values())}

def main():
 b=Budget();p=read(HERE/'protocol.json');cfg={'teacher_jvnv_vs_kokoro':(('teacher','jvnv'),('teacher','kokoro')),'WORLD_jvnv_vs_own_teacher':(('world','jvnv'),('teacher','jvnv')),'WORLD_kokoro_vs_own_teacher':(('world','kokoro'),('teacher','kokoro')),'WORLD_jvnv_vs_WORLD_kokoro':(('world','jvnv'),('world','kokoro'))};content={}
 with b.job(NAME,'audit','先生全分母・固定7/5群・各解析再合成を集計',reserve_bytes=500000) as j:
  negative=tests()
  for cohort in ['legacy_diagnostic','prospective_once']:content[cohort]={name:{e:compare(p,cohort,a,n,e) for e in ['whisper','reazon']} for name,(a,n) in cfg.items()}
  manifest=read(HERE/'render-manifest.json');engineering=[{'id':q['id'],'E0_pass':read(REPO/q['record'])['E0_pass'],'measurement':read(REPO/q['record'])['measurement']} for q in manifest['rows']]
  diagnostic=all(content['prospective_once'][name][e]['all_groups_non_worsening'] for name in ['teacher_jvnv_vs_kokoro','WORLD_jvnv_vs_own_teacher'] for e in ['whisper','reazon']) and all(r['E0_pass'] for r in engineering)
  b.save(HERE/'summary.json',{'content':content,'engineering':engineering,'negative_tests':negative,'JVNV_limited_content_and_resynthesis_supported':diagnostic,'teacher_is_research_only':True,'WORLD_requires_teacher_waveform':True,'shared_text_control_fit_performed':False,'final_non_neural_text_transfer_verified':False,'perceptual_qualification':False,'protected_confirmation_opened':False,'quality_goal_completed':False,'limitations':['全教師/声/内部正規化/依存版の対照で単一原因ではない','旧4Kokoroは観測済み診断再利用','新8は前向き内容診断、独立最終確認は未開封','内部attention時刻は予測で音響上の正解でない','WORLD分析再合成の成功は最終文章入力への移出ではない','短有声イベントの知覚資格なし']},j)
 print({'limited_teacher_resynthesis':diagnostic,'quality_goal_completed':False},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
