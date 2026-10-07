"""固定wheelはインストーラーを起動せず予約付きで専用prefixへ展開する。"""
from paths import *
import zipfile

def main():
 b=Budget();plan=read(HERE/'payload-plan.json');files={};totals={}
 assert read(HERE/'payload-audit.json')['all_expected_sha256_verified']
 for item in plan['wheels']:
  path=HERE/'wheels'/item['filename'];assert digest(path)==item['sha256']
  with zipfile.ZipFile(path) as z:
   members=[q for q in z.infolist() if not q.is_dir()];size=sum(q.file_size for q in members);assert size<500000000
   with b.job(NAME,'setup','固定wheel専用prefix展開 '+item['package'],reserve_bytes=size+100000) as j:
    for q in members:
     rel=Path(q.filename);assert not rel.is_absolute() and '..' not in rel.parts and (q.external_attr>>16)&0o170000 !=0o120000
     if any(part.endswith('.data') for part in rel.parts):
      pos=next(i for i,part in enumerate(rel.parts) if part.endswith('.data'))
      if rel.parts[pos+1] not in ['purelib','platlib']:continue
      rel=Path(*rel.parts[pos+2:])
     data=z.read(q);target=HERE/'packages'/rel;b.write(target,data,j);files[str(target.relative_to(HERE))]=digest(target)
    totals[item['package']]=size
  print('extracted',item['package'],size,flush=True)
 b.save(HERE/'environment-manifest.json',{'files':files,'wheel_uncompressed_bytes':totals,'total_uncompressed_bytes':sum(totals.values()),'payload_plan_sha256':digest(HERE/'payload-plan.json'),'pip_install_used':False,'old_environments_modified':False});print(b.reconcile(),flush=True)
if __name__=='__main__':main()
