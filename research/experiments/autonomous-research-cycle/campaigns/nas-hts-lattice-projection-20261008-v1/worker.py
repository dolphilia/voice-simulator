"""有限gridの近似損失と数値安定域を全frameで記録する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;reg=json.loads((here/'registration.json').read_text());corpus=json.loads((here/'corpus-contract.json').read_text())
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,reg['mechanism_bundle'])
import numpy as np
from scipy import linalg
from lattice import levinson,project,ORDER,FFT_LENGTH
assert ORDER==34 and FFT_LENGTH==16384
q={n:np.exp(-2j*np.pi*np.arange(n//2+1)/n) for n in (16384,32768)}
w={n:(v-.55)/(1.-.55*v) for n,v in q.items()}
def batch_response(mc,n):
    result=np.broadcast_to(mc[:,-1,None],(len(mc),len(w[n]))).astype(np.complex128).copy()
    for i in range(33,-1,-1):result=result*w[n][None,:]+mc[:,i,None]
    return np.exp(result)
def normalized_error(a,z):return float(np.max(np.abs(a-z))/max(1.,np.max(np.abs(a))))
records=[];waves=[];frames_expected=0
for ci,item in enumerate(corpus['rows']):
    with np.load(item['npz'],allow_pickle=False) as z:mc=z['mcp'].copy()
    assert mc.ndim==2 and mc.shape[1]==35 and np.isfinite(mc).all();frames_expected+=len(mc)
    current=[];batch_check=None
    for start in range(0,len(mc),32):
        part=mc[start:start+32];h=batch_response(part,16384);hr=batch_response(part,32768)
        power=np.abs(h)**2;refpower=np.abs(hr)**2
        r=np.fft.irfft(power,n=16384,axis=1)[:,:35];rr=np.fft.irfft(refpower,n=32768,axis=1)[:,:35]
        for offset,c in enumerate(part):
            frame=start+offset;row=dict(id=item['id'],frame=frame,passed=False,failures=[],normalized_dense_coefficient_error=None,log_magnitude_RMSE_dB=None,refinement_relative_coefficient_error=None,refinement_relative_gain_error=None,reflection_max_abs=None,root_radius_diagnostic=None)
            try:
                a,k,g=levinson(r[offset]);ar,kr,gr=levinson(rr[offset]);row['reflection_max_abs']=float(np.max(np.abs(k)))
                dense=np.r_[1.,np.linalg.solve(linalg.toeplitz(r[offset,:-1]/r[offset,0]),-r[offset,1:]/r[offset,0])]
                de=normalized_error(a,dense);ce=normalized_error(a,ar);ge=float(abs(g-gr)/max(abs(g),1e-12))
                approx=g/np.polynomial.polynomial.polyval(q[16384],a)
                rmse=float(np.sqrt(np.mean((20*np.log10(np.abs(approx)/np.abs(h[offset])))**2)))
                radius=float(np.max(np.abs(np.roots(a))))
                row.update(normalized_dense_coefficient_error=de,log_magnitude_RMSE_dB=rmse,refinement_relative_coefficient_error=ce,refinement_relative_gain_error=ge,root_radius_diagnostic=radius)
                if de>1e-10:row['failures'].append('独立密Toeplitz係数誤差')
                if rmse>2.:row['failures'].append('有限grid振幅RMSE')
                if ce>1e-8 or ge>1e-8:row['failures'].append('grid観測refinement')
                if not np.isfinite([de,rmse,ce,ge,radius]).all():row['failures'].append('非有限診断')
                if frame==0:
                    aa,kk,gg,r0=project(c);be=max(normalized_error(a,aa),float(np.max(np.abs(k-kk))),float(abs(g-gg)/max(abs(g),1e-12)),float(np.max(np.abs(r[offset]-r0))/max(float(r0[0]),1e-12)))
                    batch_check=be
                    if be>1e-12:row['failures'].append('batchと原projectの数値差')
                row['passed']=not row['failures']
            except (ValueError,np.linalg.LinAlgError,FloatingPointError) as exc:
                row['failures'].append('射影/独立解/安定域の定義不能');row['error']=repr(exc)
            for key,value in list(row.items()):
                if isinstance(value,float) and not np.isfinite(value):row[key]=None
            current.append(row);records.append(row)
    assert len(current)==len(mc)
    def maximum(key):
        vals=[v[key] for v in current if v[key] is not None];return max(vals) if vals else None
    causes={}
    for v in current:
        for reason in v['failures']:causes[reason]=causes.get(reason,0)+1
    waves.append(dict(id=item['id'],frames_expected=len(mc),frames_recorded=len(current),passed_frames=sum(v['passed'] for v in current),excluded_frames=0,failed_frames=sum(not v['passed'] for v in current),causes=causes,
        maximum_log_magnitude_RMSE_dB=maximum('log_magnitude_RMSE_dB'),maximum_normalized_dense_coefficient_error=maximum('normalized_dense_coefficient_error'),
        maximum_refinement_relative_coefficient_error=maximum('refinement_relative_coefficient_error'),maximum_refinement_relative_gain_error=maximum('refinement_relative_gain_error'),
        maximum_reflection_abs=maximum('reflection_max_abs'),maximum_root_radius_diagnostic=maximum('root_radius_diagnostic'),batch_original_project_maximum_error=batch_check,all_required_pass=all(v['passed'] for v in current)))
    Path(os.environ['TMPDIR'],'progress.json').write_text(json.dumps(dict(completed_native_cases=ci+1,total_native_cases=32,frames_recorded=len(records),failed_frames=sum(not v['passed'] for v in records))))
assert len(waves)==32 and len(records)==frames_expected==20276
print(json.dumps(dict(rows=waves,frames=records,total_frames=frames_expected,excluded_frames=0,all_frames_attempted=True,all_required_pass=all(v['passed'] for v in records),render=0,dsp=160,
    diagnostics_only=True,no_waveform_read_or_generated=True,order=34,base_FFT=16384,observation_refinement_FFT=32768,coefficient_adjustment_after_output=False,quality_certified=False),allow_nan=False))
