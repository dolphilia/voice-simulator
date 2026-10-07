"""対応版ヘッダと既存clangで、状態長だけのC hookを構築する。"""
import sys,subprocess
from paths import *
def main():
 b=Budget();cmd=['xcrun','clang','-dynamiclib','-O2','-undefined','dynamic_lookup','-isysroot','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk','-I'+str(HERE/'vendor'),str(HERE/'timing.c'),'-o',str(HERE/'timing.dylib')]
 with b.job(NAME,'setup','MLPG前の状態長hookを構築',reserve_bytes=200000) as j:
  with b.external_output(HERE/'timing.dylib',100000,j):
   result=subprocess.run(cmd,capture_output=True,text=True);assert result.returncode==0,result.stderr
  b.save(HERE/'build-audit.json',dict(command=cmd,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,source_sha256=digest(HERE/'timing.c'),binary_sha256=digest(HERE/'timing.dylib'),headers={q.name:digest(q) for q in (HERE/'vendor').iterdir()},scientific_change='state_duration_only'),j)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
