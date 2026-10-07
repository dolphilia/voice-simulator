"""独立C周波数変換対照を予約された一出力へ構築する。"""
from paths import *
import subprocess
b=Budget()
with b.job(NAME,'setup','HTS_freqt独立数値対照の構築',reserve_bytes=200000) as j:
 cmd=['/usr/bin/xcrun','clang','-dynamiclib','-O2',str(HERE/'reference_freqt.c'),'-o',str(HERE/'reference_freqt.dylib')]
 with b.external_output(HERE/'reference_freqt.dylib',100000,j):
  r=subprocess.run(cmd,capture_output=True,text=True);assert r.returncode==0,r.stderr
 b.save(HERE/'reference-build.json',{'command':cmd,'source_sha256':digest(HERE/'reference_freqt.c'),'binary_sha256':digest(HERE/'reference_freqt.dylib'),'used_in_runtime':False},j)
print(b.reconcile(),flush=True)
