"""対応版ヘッダと既存Xcode clangで、C hookだけを構築する。"""
import sys,subprocess
from paths import *
def main():
 b=Budget();cmd=['xcrun','clang','-dynamiclib','-O2','-undefined','dynamic_lookup','-isysroot','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk','-I'+str(HERE/'vendor'),str(HERE/'counter.c'),'-o',str(HERE/'counter.dylib')]
 with b.job(NAME,'setup','単位LPF hookを構築',reserve_bytes=200000) as j:
  with b.external_output(HERE/'counter.dylib',100000,j):
   result=subprocess.run(cmd,capture_output=True,text=True);assert result.returncode==0,result.stderr
  b.save(HERE/'build-audit.json',{'command':cmd,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'source_sha256':digest(HERE/'counter.c'),'binary_sha256':digest(HERE/'counter.dylib')},j)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
