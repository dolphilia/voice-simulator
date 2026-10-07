"""大きい取得の前に版/hash/容量/モデルカードを上限付き取得する。"""
from paths import *
import json,urllib.request

def main():
 b=Budget();reg=read(HERE/'registration.json');total=0;files=[]
 with b.job(NAME,'download','公式モデルmetadataとコードtag 最大200KB保守予約',count=200000,reserve_bytes=250000) as j:
  def get(url,limit=60000):
   nonlocal total
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch'}),timeout=30) as response:data=response.read(min(limit,200000-total)+1)
   total+=len(data);assert len(data)<=limit and total<=200000;return data
  tag=json.loads(get('https://api.github.com/repos/'+reg['code_repo']+'/git/ref/tags/'+reg['code_tag'],10000));commit=tag['object']['sha']
  if tag['object']['type']=='tag':commit=json.loads(get(tag['object']['url'],10000))['object']['sha']
  b.save(HERE/'source-tag.json',{'tag':reg['code_tag'],'commit':commit,'github_reference':tag},j)
  for label,repo in [('teacher',reg['model_repo']),('bert',reg['bert_repo'])]:
   value=json.loads(get('https://huggingface.co/api/models/'+repo+'?blobs=true',60000));revision=value['sha'];b.save(HERE/'metadata'/label/'model-info.json',value,j)
   card=get('https://huggingface.co/'+repo+'/resolve/'+revision+'/README.md',30000);b.write(HERE/'metadata'/label/'README.md',card,j)
   files.append({'label':label,'repo':repo,'revision':revision,'siblings':[q for q in value['siblings'] if q['rfilename'] in (reg['model_files'] if label=='teacher' else ['pytorch_model.bin','model.safetensors','config.json','tokenizer_config.json','tokenizer.json','spm.model','special_tokens_map.json'])]})
  for name in ['LICENSE','LGPL_LICENSE','docs/TERMS_OF_USE.md','requirements-infer.txt']:
   data=get('https://raw.githubusercontent.com/'+reg['code_repo']+'/'+commit+'/'+name,50000);b.write(HERE/'metadata/source'/name,data,j)
  b.save(HERE/'discovery.json',{'source_commit':commit,'models':files,'actual_download_bytes':total,'conservative_download_charge':200000,'payload_download_not_started':True,'teacher_generation_not_started':True},j)
 print({'code_commit':commit,'models':files,'actual_metadata_bytes':total},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
