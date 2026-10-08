"""全21333旧比較frame。有限grid資格を未知音声の品質へ移さない。"""
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
