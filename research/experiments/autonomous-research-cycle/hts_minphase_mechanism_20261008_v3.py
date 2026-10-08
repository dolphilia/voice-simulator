"""既存HTS二依存の追補を照合して実行し、子の失敗stderrも永続化する。"""
import subprocess
import hts_minphase_mechanism_20261008_v2 as driver
from budget import read,digest

def main():
    e=driver.original;contract=read(e.HERE/'dependency-extension-v3.json')
    assert digest(__file__)==contract['driver_sha256']
    for n,h in contract['files'].items():assert digest(e.HERE/n)==h,n
    e.Budget=driver.Budget
    try:
        e.run()
    except subprocess.CalledProcessError as exc:
        b=driver.Budget()
        with b.job(e.NAME,'audit','子fixture失敗のstdout/stderrを保持',reserve_bytes=1000000) as j:
            b.save(e.HERE/'fixture-child-failure-v3.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr,original_constants_and_gates_unchanged=True),j)
        raise

if __name__=='__main__':main()
