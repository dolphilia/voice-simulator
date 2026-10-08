"""既検査MCPの全分母で有限IR不足と数値gridを切り分ける。音声は再生成しない。"""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-hts-fir-cutoff-qualification-20261008-v1';NAME='hts-fir-cutoff-qualification-v1'
PREVIOUS=ROOT/'campaigns/nas-hts-minphase-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

WORKER=r'''"""全21333旧比較frame。有限grid資格を未知音声の品質へ移さない。"""
import sys,json
from pathlib import Path
previous=Path(sys.argv[1]);sys.path.insert(0,str(previous/'runtime-bundle'))
import numpy as np
from minphase import kernel
protocol=json.loads((previous/'protocol.json').read_text());N=16384
q=np.exp(-2j*np.pi*np.arange(N//2+1)/N);a=(q-.55)/(1.-.55*q)
lengths=[1024,2048,4096];rows=[]
for row in protocol['rows']:
 for condition in protocol['conditions']:
    with np.load(previous/'render'/row['id']/condition/'native.npz',allow_pickle=False) as z:mc=z['mcp'].copy()
    maxima={L:dict(response=0.,tail=0.,worst_frame=None,failed_frames=[]) for L in lengths}
    prefix=0.;refinement=0.
    for index,c in enumerate(mc):
        target=np.exp(np.polynomial.polynomial.polyval(a,c))
        reference=np.fft.irfft(target,n=N);reference8=np.fft.irfft(target[::2],n=8192)
        scale=max(float(np.max(np.abs(reference[:1024]))),1e-12)
        current_prefix=float(np.max(np.abs(kernel(c)-reference[:1024]))/scale)
        current_refinement=float(np.max(np.abs(reference8[:4096]-reference[:4096]))/max(float(np.max(np.abs(reference[:4096]))),1e-12))
        assert np.isfinite(current_prefix) and np.isfinite(current_refinement)
        prefix=max(prefix,current_prefix);refinement=max(refinement,current_refinement)
        energy=float(np.sum(reference**2))
        for L,v in maxima.items():
            error=float(np.max(np.abs(np.fft.rfft(reference[:L],n=N)-target)/np.maximum(np.abs(target),1e-12)))
            tail=float(np.sum(reference[L:]**2)/energy)
            assert np.isfinite(error) and np.isfinite(tail)
            if error>=v['response']:v['response']=error;v['worst_frame']=index
            v['tail']=max(v['tail'],tail)
            if error>1e-3 or tail>1e-6:v['failed_frames'].append(index)
    rows.append(dict(id=row['id']+'/'+condition,frames_checked=len(mc),excluded_frames=0,lengths=maxima,
        C1024_vs_analytic_prefix_relative_error=prefix,grid_refinement_8192_to_16384_relative_error=refinement,
        numerical_checks_passed=prefix<=1e-10 and refinement<=1e-10))
assert len(rows)==32 and sum(v['frames_checked'] for v in rows)==21333
eligibility={str(L):all(not v['lengths'][L]['failed_frames'] and v['numerical_checks_passed'] for v in rows) for L in lengths}
selected=next((L for L in lengths if eligibility[str(L)]),None)
print(json.dumps(dict(rows=rows,length_eligibility=eligibility,selected_minimum_length=selected,all_frames_checked=21333,excluded_frames=0,
    saved_selected_cohort_used=True,independent_unknown_input_quality_evidence=False,render=0,dsp=128,
    scope='この既比較MCPの全frame・有限16384grid。連続全域/未知MCP/瞬時F0/知覚の資格ではない。',
    quality_goal_completed=False,protected_confirmation_opened=False)))
'''

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=8,audit=12,render=0,dsp=384,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='実MCPでのFIR1024不通過は、C IR係数誤差・8192grid alias・有限IR打切りのどれと対応するか。全21333 frameを除外せず検査する。',
        source=dict(previous_seal_sha256=digest(PREVIOUS/'artifact-seal.json'),previous_all_frame_audit_sha256=digest(PREVIOUS/'all-frame-fir-audit.json'),urls=['https://sp-nitech.github.io/sptk/latest/main/freqt.html','https://sp-nitech.github.io/sptk/latest/main/c2mpir.html']),
        lengths=[1024,2048,4096],FFT=16384,alpha=.55,MCP=35,
        thresholds=dict(complex_relative_error=1e-3,reference_tail_energy=1e-6,C_prefix_relative_error=1e-10,grid_refinement_relative_error=1e-10),
        selection_rule='全32波形・全frame・両数値検査を通る最短登録長を選ぶ。候補なしなら有限FIRの同係数救済を凍結する。選択済みコホートによる機構診断であり独立品質証拠にはしない。',
        next_if_pass='固定した長さとFFT生成IRを別機構fixtureで照合し、その後の新日本語入力比較を別契約で生成前登録。旧1024結果や旧判定を変更しない。',
        costs=dict(render=0,dsp=128,ai=0,download=0,maximum_seconds=3000,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),
        limits=limits,controller_sha256=digest(Path(__file__)),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),
        existing_input_reused_and_not_independent_confirmation=True,old_missing_and_ASR_failures_kept=True,quality_goal_completed=False,protected_confirmation_opened=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','全frame打切り/grid比較と選択条件の生成前固定',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.save(HERE/'execution-contract.json',dict(controller_sha256=digest(Path(__file__)),worker_sha256=digest(HERE/'worker.py'),previous_seal_sha256=digest(PREVIOUS/'artifact-seal.json'),previous_protocol_sha256=digest(PREVIOUS/'protocol.json'),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0068.json',dict(active_campaign=NAME,next='登録commit/push→全既比較MCPの打切り/grid検証→限定機構範囲の封印',quality_goal_completed=False,new_scientific_outputs=0,budget=b.reconcile()))
    print('有限IRの全frame切分けを生成前登録',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    contract=read(HERE/'execution-contract.json');assert digest(Path(__file__))==contract['controller_sha256'] and digest(HERE/'worker.py')==contract['worker_sha256']
    assert digest(PREVIOUS/'artifact-seal.json')==contract['previous_seal_sha256'] and digest(PREVIOUS/'protocol.json')==contract['previous_protocol_sha256']
    # 入力保存列と参照実装を科学処理前に物理hash照合。保護集合の本文は読まない。
    seal=read(PREVIOUS/'artifact-seal.json')
    with b.job(NAME,'audit','全MCP保存列・参照kernel・対照のhash照合',reserve_bytes=2000000) as j:
        files={n:h for n,h in seal['files'].items() if n.endswith('/native.npz') or '/runtime-bundle/' in n}
        assert sum(n.endswith('/native.npz') for n in files)==32
        for n,h in files.items():assert digest(REPO/n)==h,n
        b.save(HERE/'input-hash-audit.json',dict(files=files,all_exact=True,protected_confirmation_text_read=False),j)
    token=b.reserve(NAME,'dsp','全21333frameの長さ三条件と数値基準照合',128,20000000,expected_seconds=900)
    try:
        with b.workspace(token,'全MCP cutoff検証の科学ライブラリ初期化') as (_,env):
            out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py'),str(PREVIOUS)],env=env,check=True,capture_output=True,text=True,timeout=840)
        result=json.loads(out.stdout);b.save(HERE/'all-frame-cutoff-audit.json',result,token)
    except subprocess.CalledProcessError as exc:
        b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),token);b.finish(token,repr(exc));raise
    except BaseException as exc:b.finish(token,repr(exc));raise
    else:b.finish(token)
    with b.job(NAME,'audit','固定選択則と限定適用範囲・旧封印・一時回収を終了照合',reserve_bytes=2000000) as j:
        assert result['all_frames_checked']==21333 and result['excluded_frames']==0 and result['render']==0
        rows=result['rows'];selected=result['selected_minimum_length']
        summary=dict(all_frames_checked=21333,waves=32,length_eligibility=result['length_eligibility'],selected_minimum_length=selected,
            maximum_C_prefix_relative_error=max(v['C1024_vs_analytic_prefix_relative_error'] for v in rows),
            maximum_grid_refinement_relative_error=max(v['grid_refinement_8192_to_16384_relative_error'] for v in rows),
            per_length={str(L):dict(maximum_response_error=max(v['lengths'][str(L)]['response'] for v in rows),maximum_tail=max(v['lengths'][str(L)]['tail'] for v in rows),failed_frames=sum(len(v['lengths'][str(L)]['failed_frames']) for v in rows)) for L in [1024,2048,4096]},
            prior_selected_cohort_only=True,independent_quality_evidence=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
            next='有効な固定長のFFT/因果畳み込みを別fixtureで検証し、新日本語比較を登録する。' if selected else 'この有限FIR探索を凍結し、別の共有生成要因へ移る。')
        b.save(HERE/'aggregate-summary.json',summary,j)
        lines=['# 全実MCPによる有限IRの切分け','', '前の64波形比較から保存済みの全32native・21,333MCP frameを再利用し、除外0でC1024係数/解析prefix、8192→16384grid、IR長1024/2048/4096を照合した。新しい音声・ASR・P5処理は0。','',
            '|IR長|最大複素応答相対誤差|最大参考tail energy|不通過frame|全条件通過|','|---|---:|---:|---:|---|']
        for L,v in summary['per_length'].items():lines.append(f'|{L}|{v["maximum_response_error"]:.8g}|{v["maximum_tail"]:.8g}|{v["failed_frames"]}|{summary["length_eligibility"][L]}|')
        lines+=['',f'登録規則による最短長: {selected}。C prefix相対誤差最大{summary["maximum_C_prefix_relative_error"]:.8g}、grid refinement最大{summary["maximum_grid_refinement_relative_error"]:.8g}。',
            '', 'この結果は選択に用いた既コホートの有限gridに限る。未知MCP・連続全周波数・瞬時F0・知覚の資格ではない。旧FIR1024の内容悪化/欠測/不通過と旧249欠測を変更しない。',[summary['next']][0],
            '', '一次資料: [SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)、[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。P5未開封・品質未達。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        assert digest(PREVIOUS/'artifact-seal.json')==contract['previous_seal_sha256']
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_temporary_absent=True,temporary_owned=len(temporary),failures_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='FIR-cutoff-qualification-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0069.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print(summary,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','qualification']);a=p.parse_args()
    register() if a.stage=='register' else run()
