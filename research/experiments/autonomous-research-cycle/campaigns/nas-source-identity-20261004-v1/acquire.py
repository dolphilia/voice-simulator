"""固定pyopenjtalk版に対応する上流コードを上限付きで読む。"""
import sys,urllib.request
from paths import *
import pyopenjtalk,pyopenjtalk.htsengine

def main():
 b=Budget();p=read(REPO/'research/experiments/local-f0-transfer/results/nas-local-f0-20261003-v1/source-provenance.json');assert pyopenjtalk.__version__==p['package_version']=='0.4.1';assert digest(Path(pyopenjtalk.htsengine.__file__))==p['binary_sha256']
 rows=[]
 with b.job(NAME,'download','固定HTSの励起とGSSコード取得、最大100000bytes予約',count=100000,reserve_bytes=100000) as j:
  for n in ['HTS_vocoder.c','HTS_gstream.c']:
   path=HERE/'upstream'/n;url='https://raw.githubusercontent.com/r9y9/hts_engine_API/'+p['submodule_commit']+'/src/lib/'+n
   if not path.exists():
    with urllib.request.urlopen(url,timeout=30) as response:data=response.read(50001)
    assert len(data)<=50000,'1ファイル取得上限';assert b'Redistribution and use' in data,'BSD通知を保持';b.write(path,data,j)
   rows.append({'path':str(path.relative_to(REPO)),'url':url,'bytes':path.stat().st_size,'sha256':digest(path)})
  source=(HERE/'upstream/HTS_vocoder.c').read_text();assert 'HTS_Vocoder_get_excitation' in source and 'HTS_Vocoder_excite_voiced_frame' in source and 'HTS_white_noise(v)' in source
  b.save(HERE/'source-provenance.json',{'rows':rows,'submodule_commit':p['submodule_commit'],'binary_sha256':p['binary_sha256'],'actual_download_bytes':sum(r['bytes'] for r in rows),'conservative_download_charge_bytes':100000,'license':'三条項BSD通知を原ファイル内に保存','same_three_stream_same_ring_length_design':True,'actual_RNG_state_instrumented':False,'quality_certified':False},j)
 print(rows,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
