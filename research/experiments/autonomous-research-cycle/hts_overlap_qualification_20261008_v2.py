"""時刻の秒表現をサンプル位置へ照合する技術修正。旧数式・出力は不変。"""
import argparse
import hashlib
import subprocess
from pathlib import Path
import hts_overlap_qualification_20261008 as original
from budget import digest,read

HERE=original.HERE; ROOT=original.ROOT; REPO=original.REPO
def prepare():
    b=original.Budget();b.recover();assert not b.snapshot()['jobs']
    diagnosis=read(HERE/'clock-failure-diagnosis-01.json')
    assert diagnosis['total']==128 and all(x['wave_centers_exact'] and x['source_centers_exact'] and x['old_length']==x['current_length'] for x in diagnosis['rows'])
    old=(HERE/'analysis.py').read_text()
    check="assert np.array_equal(times,legacy['times'])"
    replacement="assert len(times)==len(legacy['times'])\n            assert np.array_equal(np.rint(times*24000),np.rint(legacy['times']*24000))\n            assert np.array_equal(np.rint(times*48000),np.rint(legacy['times']*48000))"
    assert old.count(check)==1
    updated=old.replace(check,replacement)
    anchor="    for n,h in c['runtime_hashes'].items():assert digest(REPO/n)==h,n"
    addition=anchor+"\n    amendment=read(HERE/'execution-control-amendment-01.json')\n    assert digest(HERE/'analysis_v2.py')==amendment['worker_sha256']\n    assert digest(ROOT/'hts_overlap_qualification_20261008_v2.py')==amendment['controller_sha256']"
    assert updated.count(anchor)==1;updated=updated.replace(anchor,addition)
    __import__('ast').parse(updated)
    with original.job(b,'setup','秒表現差の別版修正とサンプル位置契約',1,1000000,120) as j:
        b.write(HERE/'analysis_v2.py',updated.encode(),j)
        b.save(HERE/'execution-control-amendment-01.json',dict(reason='秒列の丸め差。全128の窓中心は24kHz/48kHzとも一致。',old_worker_sha256=digest(HERE/'analysis.py'),worker_sha256=digest(HERE/'analysis_v2.py'),controller_sha256=digest(Path(__file__)),clock_diagnosis_sha256=digest(HERE/'clock-failure-diagnosis-01.json'),physical_clock_centers_exact_required=True,legacy128_all_3width_F0_and_confidence_byte_exact_still_required=True,LPF_ground_all224_exact_still_required=True,measurement_formula_peak_selection_confidence_gate_and_inputs_unchanged=True,old_failure_and_consumption_preserved=True,no_limit_increase=True),j)
    print('サンプル位置修正版を登録',flush=True)

def run():
    b=original.Budget();b.recover();assert not b.snapshot()['jobs']
    assert read(HERE/'fixture-audit.json')['passed']
    assert digest(Path(__file__))==read(HERE/'execution-control-amendment-01.json')['controller_sha256']
    for begin in range(0,224,16):
        end=begin+16
        if (HERE/'batches'/f'{begin:03d}-{end:03d}.json').exists():continue
        count=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in read(HERE/'protocol.json')['records'][begin:end])
        with original.job(b,'dsp' if count else 'audit',f'短窓2×2と全分母 {begin}:{end}',max(1,count*31),100000000,300) as d:
            with b.workspace(d,'短窓測定初期化') as (_,env):
                subprocess.run([str(original.PYTHON),'-B',str(HERE/'analysis_v2.py'),'batch','--begin',str(begin),'--end',str(end),'--job',d],env=env,check=True,timeout=300)
    print(b.reconcile(),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','run','close'));a=p.parse_args()
    prepare() if a.stage=='prepare' else original.close() if a.stage=='close' else run()
