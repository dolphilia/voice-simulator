"""版固定wrapper・組込WORLD sourceと利用通知を保守予約で取得する。"""
import json,urllib.request
from paths import *
def main():
 b=Budget();base='https://api.github.com/repos/JeremyCCHsu/Python-Wrapper-for-World-Vocoder/contents/lib/World?ref=v0.3.5';total=0;items=[]
 with b.job(NAME,'download','WORLD一次source・通知 最大200000bytes保守予約',count=200000,reserve_bytes=250000) as j:
  def get(url,limit=60000):
   nonlocal total
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch'}),timeout=30) as response:data=response.read(min(limit,200000-total)+1)
   total+=len(data);assert len(data)<=limit and total<=200000;return data
  info=json.loads(get(base,10000));assert info['type']=='submodule';commit=info['sha'];repo=info['submodule_git_url'].removesuffix('.git').replace('https://github.com/','')
  b.save(HERE/'upstream/submodule.json',info,j)
  urls={'pyworld.pyx':'https://raw.githubusercontent.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder/v0.3.5/pyworld/pyworld.pyx','synthesis.cpp':'https://raw.githubusercontent.com/'+repo+'/'+commit+'/src/synthesis.cpp','LICENSE-WORLD.txt':'https://raw.githubusercontent.com/'+repo+'/'+commit+'/LICENSE.txt'}
  for name,url in urls.items():
   data=get(url);b.write(HERE/'upstream'/name,data,j);items.append({'name':name,'url':url,'bytes':len(data),'sha256':digest(HERE/'upstream'/name)})
  b.save(HERE/'world-provenance.json',{'wrapper_tag':'v0.3.5','WORLD_gitlink_commit':commit,'WORLD_repo':repo,'rows':items,'actual_download_bytes':total,'charged_conservatively':200000,'synthesis_power_and_AP_scope':'sp power, AP magnitude ratio','quality_certified':False},j)
 print(items,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
