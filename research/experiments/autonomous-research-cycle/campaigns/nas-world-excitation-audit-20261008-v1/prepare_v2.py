"""浮動小数点縮約を明示停止して旧WAV完全一致条件を再検証する。"""
from paths import *
import subprocess,ast
def main():
    b=Budget();b.recover()
    with b.job(NAME,'setup','観測C再試行1：FMA縮約条件の固定',reserve_bytes=20000000) as j:
        cmd=read(HERE/'build-audit.json')['command']
        cmd[cmd.index('-O2')+1:cmd.index('-O2')+1]=['-ffp-contract=off']
        cmd[-1]=str(HERE/'observer-v2.dylib')
        with b.workspace(j,'clang再試行1の中間物とcache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'observer-v2.dylib',200000,j):
                result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit-v2.json',dict(command=cmd,returncode=result.returncode,stderr=result.stderr,binary_sha256=digest(HERE/'observer-v2.dylib'),
            technical_retry=1,scientific_gate_unchanged=True,all_temporary_removed=True),j)
        source=(HERE/'observe.py').read_text().replace("HERE/'observer.dylib'","HERE/'observer-v2.dylib'")
        b.write(HERE/'observe_v2.py',source.encode(),j)
        analysis=(HERE/'analysis.py').read_text().replace("HERE/'execution-contract.json'","HERE/'execution-contract-v2.json'").replace("HERE/'observe.py'","HERE/'observe_v2.py'")
        b.write(HERE/'analysis_v2.py',analysis.encode(),j)
        old=read(HERE/'execution-contract.json')
        for n,h in old['source_hashes'].items():assert digest(HERE/n)==h
        b.save(HERE/'execution-contract-v2.json',dict(**{k:v for k,v in old.items() if k!='source_hashes'},
            source_hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.suffix in ['.py','.cpp','.h','.dylib']},
            old_contract_sha256=digest(HERE/'execution-contract.json'),technical_retry=1,
            change='浮動小数点縮約をoffに固定。ソース/係数/科学ゲートは不変。'),j)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
