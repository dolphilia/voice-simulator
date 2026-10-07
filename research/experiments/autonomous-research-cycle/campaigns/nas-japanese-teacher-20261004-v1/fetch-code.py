"""固定sourceのPython入口と小さいモデル設定を取得し大取得を見積もる。"""
from paths import *
import urllib.request,json,hashlib

def main():
 b=Budget();reg=read(HERE/'registration.json');commit=read(HERE/'source-tag.json')['commit'];total=0;records=[]
 with b.job(NAME,'download','固定日本語教師sourceと設定 最大2MB保守予約',count=2000000,reserve_bytes=2500000) as j:
  def get(url,limit=200000):
   nonlocal total
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch'}),timeout=30) as response:data=response.read(min(limit,2000000-total)+1)
   total+=len(data);assert len(data)<=limit and total<=2000000;return data
  tree=json.loads(get('https://api.github.com/repos/'+reg['code_repo']+'/git/trees/'+commit+'?recursive=1',300000));assert not tree['truncated']
  b.save(HERE/'source-tree.json',tree,j)
  chosen=[x for x in tree['tree'] if x['type']=='blob' and x['path'].startswith('style_bert_vits2/') and x['path'].endswith(('.py','.json'))]
  assert sum(q['size'] for q in chosen)<1000000
  for q in chosen:
   url='https://raw.githubusercontent.com/'+reg['code_repo']+'/'+commit+'/'+q['path'];data=get(url)
   gitsha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert gitsha==q['sha'] and len(data)==q['size']
   target=HERE/'source'/q['path'];b.write(target,data,j);records.append({'path':str(target.relative_to(HERE)),'sha256':digest(target),'git_blob_sha1':gitsha,'url':url})
   if len(records)%16==0:print('source',len(records),'/'+str(len(chosen)),flush=True)
  for label in ['teacher','bert']:
   info=read(HERE/'metadata'/label/'model-info.json');repo=reg['model_repo' if label=='teacher' else 'bert_repo'];wanted=reg['model_files'] if label=='teacher' else ['config.json','tokenizer_config.json','special_tokens_map.json','vocab.txt','tokenizer.json','spm.model']
   for q in info['siblings']:
    if q['rfilename'] in wanted and q['size']<200000:
     url='https://huggingface.co/'+repo+'/resolve/'+info['sha']+'/'+q['rfilename'];data=get(url);assert len(data)==q['size'];target=HERE/'models'/label/q['rfilename'];b.write(target,data,j)
     if 'lfs' in q:assert digest(target)==q['lfs']['sha256']
     else:assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==q['blobId']
     records.append({'path':str(target.relative_to(HERE)),'sha256':digest(target),'url':url})
  b.save(HERE/'source-and-config.json',{'source_commit':commit,'files':records,'actual_download_bytes':total,'conservative_charge':2000000,'source_package_python_bytes':sum(q['size'] for q in chosen),'no_weights_or_audio_generated':True},j)
 print({'source_count':len(chosen),'actual_bytes':total,'teacher_config':read(HERE/'models/teacher/jvnv-F1-jp/config.json'),'bert_tokenizer':read(HERE/'models/bert/tokenizer_config.json')},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
