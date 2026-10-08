"""対応PyWORLDの通常O3条件と、観測hookの非inline化で技術再試行2を行う。"""
from paths import *
import subprocess,sysconfig
def main():
    b=Budget();b.recover()
    with b.job(NAME,'setup','再試行2：通常O3/観測hook非inlineの固定',reserve_bytes=20000000) as j:
        original=(HERE/'observer.cpp').read_text()
        source=original.replace('static void ObsTime','__attribute__((noinline)) static void ObsTime').replace('static void ObsResponse','__attribute__((noinline)) static void ObsResponse')
        assert source.count('__attribute__((noinline))')==2
        b.write(HERE/'observer-v3.cpp',source.encode(),j)
        cmd=read(HERE/'build-audit.json')['command'];cmd[cmd.index('-O2')]='-O3'
        cmd[cmd.index(str(HERE/'observer.cpp'))]=str(HERE/'observer-v3.cpp');cmd[-1]=str(HERE/'observer-v3.dylib')
        with b.workspace(j,'clang再試行2の中間物とcache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'observer-v3.dylib',200000,j):
                result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit-v3.json',dict(command=cmd,returncode=result.returncode,stderr=result.stderr,binary_sha256=digest(HERE/'observer-v3.dylib'),
            technical_retry=2,Python_CFLAGS=sysconfig.get_config_var('CFLAGS'),primary_setup_sha256=digest(HERE/'upstream-pyworld-setup.py'),
            reason='一次setupに独自compile指定なし。CPython通常O3へ合わせ、観測hookを元演算から非inline化。',
            scientific_gate_unchanged=True,all_temporary_removed=True),j)
        source=(HERE/'observe.py').read_text().replace("HERE/'observer.dylib'","HERE/'observer-v3.dylib'")
        b.write(HERE/'observe_v3.py',source.encode(),j)
        analysis=(HERE/'analysis.py').read_text().replace("HERE/'execution-contract.json'","HERE/'execution-contract-v3.json'").replace("HERE/'observe.py'","HERE/'observe_v3.py'")
        b.write(HERE/'analysis_v3.py',analysis.encode(),j)
        old=read(HERE/'execution-contract.json')
        for n,h in old['source_hashes'].items():assert digest(HERE/n)==h
        b.save(HERE/'execution-contract-v3.json',dict(**{k:v for k,v in old.items() if k!='source_hashes'},
            source_hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.suffix in ['.py','.cpp','.h','.dylib']},
            old_contract_sha256=digest(HERE/'execution-contract.json'),technical_retry=2,
            change='O3・読取hook非inlineのみ。係数/科学ゲート/パルス条件は不変。'),j)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
