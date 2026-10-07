"""CPU/arm64対応の固定wheelとsafe tensorの取得計画を固定する。"""
from paths import *
import urllib.request,json
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename

def main():
 b=Budget();rank={t:i for i,t in enumerate(sys_tags())};total=0;rows=[]
 versions={'torch':'2.3.1','numpy':'1.26.4','transformers':'4.44.2','tokenizers':'0.19.1','huggingface-hub':'0.24.7','pydantic':'2.9.2','pydantic_core':'2.23.4','annotated-types':'0.7.0','loguru':'0.7.2','num2words':'0.5.13','sympy':'1.12.1'}
 with b.job(NAME,'download','専用CPU wheelのmetadata 最大2MB保守予約',count=2000000,reserve_bytes=2100000) as j:
  for name,version in versions.items():
   url='https://pypi.org/pypi/'+name+'/'+version+'/json'
   with urllib.request.urlopen(url,timeout=30) as response:data=response.read(300001)
   total+=len(data);assert len(data)<=300000 and total<=2000000;v=json.loads(data)
   target=HERE/'metadata/wheels'/(name+'.json');b.write(target,data,j);candidates=[]
   for q in v['urls']:
    if not q['filename'].endswith('.whl'):continue
    tags=parse_wheel_filename(q['filename'])[3];score=min((rank[t] for t in tags if t in rank),default=999999)
    if score<999999:candidates.append((score,q['filename'],q))
   assert candidates,'対応wheelなし: '+name;q=sorted(candidates)[0][2]
   rows.append({'package':name,'version':version,'filename':q['filename'],'url':q['url'],'bytes':q['size'],'sha256':q['digests']['sha256'],'metadata_sha256':digest(target)})
  models=[]
  for label in ['teacher','bert']:
   v=read(HERE/'metadata'/label/'model-info.json');wanted='jvnv-F1-jp/jvnv-F1-jp_e160_s14000.safetensors' if label=='teacher' else 'model.safetensors';q=next(q for q in v['siblings'] if q['rfilename']==wanted)
   models.append({'label':label,'filename':wanted,'bytes':q['size'],'sha256':q['lfs']['sha256'],'url':'https://huggingface.co/'+v['id']+'/resolve/'+v['sha']+'/'+wanted,'repo_revision':v['sha']})
  plan={'wheels':rows,'models':models,'payload_download_bytes':sum(q['bytes'] for q in rows+models),'metadata_actual_bytes':total,'metadata_conservative_charge':2000000,'payload_download_not_started':True,'pickle_model_files':0,'existing_environments_modified':False,'shared_older_freeze_read_only':True,'max_download_job_bytes':1800000000,'max_post_extract_total_extra_bytes':3000000000,'NUMBA_DISABLE_JIT':'1。教師推論で使わない訓練alignmentのimport JIT書込を避ける。inferenceの演算は変更しない','WORLD_import_package_readonly':str(WORLD/'packages-v2')}
  assert plan['payload_download_bytes']<1800000000;b.save(HERE/'payload-plan.json',plan,j)
 print({'download_bytes':plan['payload_download_bytes'],'wheels':[{k:r[k] for k in ['package','version','filename','bytes']} for r in rows]},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
