"""外部の所有一時領域でGV監査C入口を構築する。"""
from paths import *
import subprocess
def main():
    b=Budget();b.recover()
    tool=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    cmd=[str(tool),'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),'-I'+str(HERE/'vendor'),str(HERE/'gv.c'),'-o',str(HERE/'gv.dylib')]
    with b.job(NAME,'setup','GV内部監査のC入口',reserve_bytes=20_000_000) as job:
        with b.workspace(job,'clang中間物・cache',16_000_000,32_000_000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'gv.dylib',100_000,job):
                x=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,returncode=x.returncode,stderr=x.stderr,source_sha256=digest(HERE/'gv.c'),binary_sha256=digest(HERE/'gv.dylib'),temporary_removed=True),job)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
