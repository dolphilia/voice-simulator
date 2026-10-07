"""1音声ごとの計数を保ち、単独入口と同じ関数で一つのarchiveへ生成する。"""
import argparse,json,zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import generate,verify
from storage_output import open_output
def main():
 p=argparse.ArgumentParser();p.add_argument('--requests',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 rows=json.loads(a.requests.read_text());assert 1<=len(rows)<=160 and not a.output.exists();verify();records=[]
 with open_output(a.output) as output, zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
  for i,r in enumerate(rows):
   ident=r['id'];assert '..' not in ident and not ident.startswith('/') and set(r)=={'id','text','method','speed','pitch'}
   data,meta=generate(r['text'],r['method'],r['speed'],r['pitch']);records.append(dict(id=ident,**meta));z.writestr(ident+'.wav',data);z.writestr(ident+'.json',json.dumps(meta,ensure_ascii=False,sort_keys=True))
   if (i+1)%16==0:print('batch',i+1,'/',len(rows),flush=True)
  assert len(records)==len(rows);z.writestr('manifest.json',json.dumps(dict(records=records,synthesis_calls=len(records),E0_calls=len(records),no_generation_deduplication=True),ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
