"""文章から生成したLF0の相対輪郭を保ち、駆動中央値を指定Hzへ合わせる。"""
import numpy as np
def calibrated_lf0(lf0,requested_hz):
 x=np.asarray(lf0)
 if x.ndim!=2 or x.shape[1]!=1 or not np.isfinite(x).all():raise ValueError('有限のN×1 LF0を要求')
 if not np.isfinite(requested_hz) or requested_hz<=0:raise ValueError('指定Hzは有限の正数を要求')
 voiced=x[:,0]>0
 if not voiced.any():raise ValueError('有声LF0がないため絶対中央値を校正できない')
 native_log_median=float(np.median(x[voiced,0]));shift=float(np.log(requested_hz)-native_log_median)
 y=x.copy();y[voiced,0]+=shift
 if not np.isfinite(y).all() or np.any(y[voiced,0]<=0):raise ValueError('校正後LF0が不正')
 assert np.array_equal(y[:,0]>0,voiced) and y[~voiced].tobytes()==x[~voiced].tobytes()
 assert np.allclose(y[voiced,0]-x[voiced,0],shift,rtol=0,atol=2e-15)
 assert abs(np.median(y[voiced,0])-np.log(requested_hz))<2e-15
 return y,dict(native_generated_log_median=native_log_median,log_shift=shift,requested_hz=float(requested_hz),generated_median_hz=float(np.exp(np.median(y[voiced,0]))),unvoiced_sentinel_unchanged=True,relative_LF0_shape_unchanged=True,waveform_pitch_verified=False)
