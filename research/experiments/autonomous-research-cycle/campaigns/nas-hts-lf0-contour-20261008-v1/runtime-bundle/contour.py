"""校正済みLF0の中央値周りを固定倍率にする。語ごとのlookupはない。"""
import numpy as np
from hts_arrays import ah
SCALE={'native':1.,'half_contour':.5,'flat_contour':0.}
def apply_contour(params,pitch,method):
    if method not in SCALE:raise ValueError('未登録のLF0輪郭倍率')
    x=[np.ascontiguousarray(v,dtype=np.float64) for v in params];before=[ah(v) for v in x]
    y=[v.copy() for v in x];voiced=x[1][:,0]>0;scale=SCALE[method];center=np.log(pitch)
    if not np.any(voiced):raise ValueError('校正する有声LF0がない')
    if scale!=1.:y[1][voiced,0]=center+scale*(x[1][voiced,0]-center)
    expected=x[1][voiced,0] if scale==1. else center+scale*(x[1][voiced,0]-center)
    error=float(np.max(np.abs(y[1][voiced,0]-expected)))
    passed=bool(error<=2e-15 and np.array_equal(y[1][:,0]>0,voiced)
        and np.array_equal(y[1][~voiced],x[1][~voiced]) and ah(y[0])==before[0] and ah(y[2])==before[2]
        and np.all((np.exp(y[1][voiced,0])>=70)&(np.exp(y[1][voiced,0])<=800)))
    assert [ah(v) for v in x]==before and passed
    return y,dict(scale=scale,center_hz=pitch,target_max_abs_error=error,passed=passed,
        MCP_LPF_and_unvoiced_sentinel_exact=True,voicing_mask_exact=True,original_relative_LF0_preserved=scale==1.,
        flattened_is_mechanism_diagnostic_not_naturalness_candidate=scale==0.,
        input_LF0_log_range=float(np.ptp(x[1][voiced,0])),output_LF0_log_range=float(np.ptp(y[1][voiced,0])))
