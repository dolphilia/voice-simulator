"""外部の所有一時領域を使い、対応版C入口だけを構築する。"""
from paths import *
import subprocess
def main():
    b=Budget();b.recover()
    tool=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    assert tool.is_file() and sdk.is_dir()
    cmd=[str(tool),'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),'-I'+str(HERE/'vendor'),str(HERE/'postfilter.c'),'-o',str(HERE/'postfilter.dylib')]
    with b.job(NAME,'setup','MCP後処理入口のC build',reserve_bytes=20000000) as job:
        with b.workspace(job,'clang中間物とcache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'postfilter.dylib',100000,job):
                result=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,source_sha256=digest(HERE/'postfilter.c'),binary_sha256=digest(HERE/'postfilter.dylib'),temporary_removed=True,new_download=0),job)
    print(b.reconcile(),flush=True)
if __name__=='__main__': main()
