"""科学72後のレビュー12。固定語句の工学/隔離とWhisperを保持し、残るReazonへ。"""
import ast,hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261009-v12';NAME='long-horizon-review-v12'
LABELS=['normal-long-higher','isolated-short-neutral','isolated-short-higher','isolated-long-neutral','isolated-long-higher','asr-whisper']
def place(label):return ROOT/('campaigns/nas-vtl-frozen-phrase-'+label+'-20261009-v1')
def main():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values())
 assert s['long_horizon']['scientific_completed']==72 and b.review_due(s)['due'];previous=s['long_horizon']['last_review'];assert previous['scientific_completed']==66 and digest(ROOT/previous['path'])==previous['sha256']
 lim=dict(seconds=3600,bytes=64000000,write_bytes=500000000,setup=6,audit=8,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(review_number=12,scientific_completed=72,previous_review=previous,trigger='前回66から科学六終了',controller_sha256=digest(Path(__file__)),limits=lim,scientific_outputs=0)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),lim,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with b.job(NAME,'audit','六封印/全工学/隔離/Whisper33系列/残ASRを照合',reserve_bytes=16000000) as j:
  b.save(HERE/'registration.json',reg,j);checked={};seals={}
  for label in LABELS:
   path=place(label)/'artifact-seal.json';seal=read(path);assert seal['experiment_completed'] and not seal['quality_goal_completed'];seals[str(path.relative_to(REPO))]=digest(path)
   for n,h in seal['files'].items():
    assert not any(x in Path(n).parts for x in ['protected','holdout','splits'])
    if n in checked:assert checked[n]==h
    else:assert digest(REPO/n)==h,n;checked[n]=h
  b._science_ready(b.snapshot());assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in b.snapshot()['temporary_work'].values())
  engineering={m:dict(expected=16,E0_pass=0,pitch_pass=0,missing_records=0,fixed_support_intervals=0,missing_support=0) for m in ['native','baseline','learned']}
  for label in ['measure-normal-short-neutral','normal-short-higher','normal-long-neutral','normal-long-higher']:
   for method,x in read(place(label)/'aggregate-summary.json')['engineering'].items():
    for k in engineering[method]:
     if k!='expected':engineering[method][k]+=x[k]
  isolated=sum(read(place(label)/'aggregate-summary.json')['expected_records'] for label in LABELS[1:5]);assert isolated==48
  manifest=read(place('asr-whisper')/'asr-manifest.json');assert digest(REPO/manifest['path'])==manifest['sha256'];data=read(REPO/manifest['path']);records={x['id']:x for x in data['rows']};assert len(records)==48
  source=(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/summarize.py').read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='grouped');scope={};exec(ast.get_source_segment(source,node),scope);grouped=scope['grouped'];content={}
  for method,reference in [('baseline','native'),('learned','native'),('learned','baseline')]:
   pairs=[]
   for row in read(place('suite')/'protocol.json')['rows']:
    for condition in ['neutral','higher']:
     x=records[row['id']+'/'+condition+'/'+method];n=records[row['id']+'/'+condition+'/'+reference];assert x['reference_kana']==n['reference_kana'] and x['characters']==n['characters']
     pairs.append(dict(condition=condition,length=row['length'],challenge_group=row['challenge_group'],status='completed' if x['status']==n['status']=='completed' else 'missing',errors=x['errors'],native_errors=n['errors'],characters=x['characters']))
   groups=grouped(pairs);content[method+'_vs_'+reference]=dict(groups=groups,active_groups=sum(x['expected']>0 for x in groups.values()),worsening_active_groups=[k for k,x in groups.items() if x['expected'] and not x['non_worsening']],zero_denominator_groups=[k for k,x in groups.items() if not x['expected']],all33_non_worsening=all(x['non_worsening'] for x in groups.values()))
  current=b.snapshot()['counts']['render'];assert current==83849
  decision=dict(review_number=12,scientific_completed=72,previous_review=previous,current_stage='D',engineering=engineering,ordinary_isolated_exact_records=48,CLI_exact_records=3,Whisper=content,Whisper_completed=48,Whisper_missing=0,Reazon_unperformed=48,candidate_coefficients_and_gates_unchanged=True,old_CV_and_reference_failures_kept=True,stage_D_render=dict(consumed=current-52455,maximum=36000,total_including_failed=31394,global_consumed=current,margin_before70=84000-current),resources=b.review_due(),stage_clock=b.snapshot()['research_execution_plan'],actual_generalizable_speech_improvement_verified=False,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False,adopted=False,no_group_or_cohort_pool=True,next='固定波形の未実施ReazonSpeech48件を同じ凍結モデル/正規化/全33群で実施し、D全体を封印する。工学不通過・0分母・C不通過と知覚/P5不足を保持。D全体の結論後、CV二組/語句の同経路不通過を踏まえてこの六係数の最終採択・追加救済を撤退し、新しい音声改善要因の訓練へ切り替える。新renderの70%境界越えは配分レビューを先に保存する。')
  b.save(HERE/'integrity-audit.json',dict(seals=seals,checked_files=len(checked),checked_files_digest=hashlib.sha256(encode(checked)).hexdigest(),all_owned_temporary_absent=True,old_guards_valid=True,P5_text_read=False),j);b.save(HERE/'decision.json',decision,j)
  lines=['# 第12回レビュー：固定語句の工学・隔離・Whisper','','科学72件。品質未達、知覚資格なし、P5未開封。研究を継続する。','','|方式|全E0|固定支持/F0|欠測支持|','|---|---:|---:|---:|']+[f"|{m}|{x['E0_pass']}/16|{x['pitch_pass']}/16|{x['missing_support']}/{x['fixed_support_intervals']}|" for m,x in engineering.items()]+['','全48通常/隔離・CLI3一致は生成独立性の証拠で、工学/内容/知覚の代替ではない。','','|Whisper比較|悪化した対象群|0分母群|','|---|---:|---:|']+[f"|{k}|{len(x['worsening_active_groups'])}/{x['active_groups']}|{len(x['zero_denominator_groups'])}/33|" for k,x in content.items()]+['','二ASRのうちReazon48件は未実施。全33群のgroup4..7は0分母を不通過として保持し、異なる条件や旧コホートの率をpoolしない。訓練内の三母音MSE改善を内容・自然さ・一般化へ拡張しない。','',decision['next'],'']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=72,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(active_campaign=None,id='review12-D-Reazon-ready',next=decision['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/'long-horizon-review12-completed-20261009.json',dict(scientific_completed=72,current_stage='D',quality_goal_completed=False,next=decision['next'],budget=b.reconcile()));print(json.dumps(dict(review_completed=True,Whisper_worsening={k:len(x['worsening_active_groups']) for k,x in content.items()},Reazon_unperformed=48,quality_goal_completed=False),ensure_ascii=False))
if __name__=='__main__':main()
