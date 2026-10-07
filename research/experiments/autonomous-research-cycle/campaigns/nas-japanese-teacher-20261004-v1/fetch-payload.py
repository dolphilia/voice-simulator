"""大取得は1MiBごとに事前予約し、外部一出力とhashを管理する。"""
from paths import *
import urllib.request,hashlib,time
CHUNK=1048576

def main():
 b=Budget();plan=read(HERE/'payload-plan.json');rows=[]
 for item in plan['wheels']+plan['models']:
  target=HERE/'wheels'/item['filename'] if 'package' in item else HERE/'models'/item['label']/item['filename'];expected=item['bytes']
  if target.exists():assert target.stat().st_size==expected and digest(target)==item['sha256'];rows.append({'path':str(target.relative_to(HERE)),'bytes':expected,'sha256':digest(target),'reused_verified':True});continue
  start=time.monotonic();first=min(CHUNK,expected);n=0
  with b.job(NAME,'download','固定payload first chunk '+target.name,count=first,reserve_bytes=expected+20000) as j:
   with b.external_output(target,expected,j):
    request=urllib.request.Request(item['url']+'?download=true' if 'package' not in item else item['url'],headers={'User-Agent':'VoiceSimulatorResearch'})
    with urllib.request.urlopen(request,timeout=90) as response,target.open('xb') as output:
     assert int(response.headers.get('Content-Length',expected))==expected
     while n<expected:
      count=min(CHUNK,expected-n)
      if n==0:data=response.read(count);assert len(data)==count;output.write(data);n+=len(data)
      else:
       with b.job(NAME,'download','payload chunk '+target.name+'/'+str(n),count=count):
        data=response.read(count);assert len(data)==count;output.write(data);n+=len(data)
      if n%(64*CHUNK)==0:print(target.name,n,'/'+str(expected),flush=True)
    assert n==expected and digest(target)==item['sha256'],'転送len/hash不一致。破損資産を使用しない'
   r={'path':str(target.relative_to(HERE)),'bytes':n,'sha256':digest(target),'url':item['url'],'seconds':time.monotonic()-start,'all_transfer_chunks_pre_reserved':True};b.save(target.with_suffix(target.suffix+'.download.json'),r,j);rows.append(r)
  print('verified',target.name,expected,flush=True)
 b.save(HERE/'payload-audit.json',{'files':rows,'all_expected_sha256_verified':True,'metadata_plan_sha256':digest(HERE/'payload-plan.json'),'pickle_models_downloaded':0,'old_env_modified':False});print(b.reconcile(),flush=True)
if __name__=='__main__':main()
