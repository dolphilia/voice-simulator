"""変更対象の局所性・否定入力・AP恒等性を人工配列で検査する。"""
import os,sys,tempfile,json
from pathlib import Path
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(Path(__file__).resolve().parent/'runtime-bundle'))
import numpy as np
from controls_v2 import fill_lf0,transform,ap_noise_power
labels=['x-a+y','x-I+y','x-k+y','x-m+y','x-sil+y']
duration=np.ones(25,dtype=int)
x=np.full((25,1),-1e10)
x[[0,2,4,5,7,9,10,12,14,15,19],0]=np.log([200,220,240,200,220,240,200,220,240,200,240])
y,meta=fill_lf0(x,labels,duration)
assert meta['filled_frame_indices']==[1,3]
assert y[x[:,0]>0].tobytes()==x[x[:,0]>0].tobytes()
assert y[5:].tobytes()==x[5:].tobytes()
assert abs(y[1,0]-(x[0,0]+x[2,0])/2)<1e-15
native=[np.zeros((25,35)),x.copy(),np.tile([0,1,0],(25,1))]
params,control,error,passed=transform('combined',native,labels,duration,220.)
json.dumps(control,allow_nan=False)
assert passed and error<=2e-15 and np.array_equal(params[0],native[0]) and np.array_equal(params[2],native[2])
assert (x[1,0]<0) and params[1][1,0]>0 and params[1][6,0]<0
for bad in [duration[:-1],np.zeros(25),duration*.5]:
    try: fill_lf0(x,labels,bad)
    except ValueError: pass
    else: raise AssertionError('不正durationを受理')
f0=np.array([0,220,280.]);power=np.ones((3,4));ap=np.array([[1.,1.,1.,1.],[.001,.1,.5,.99],[.2,.4,.6,.8]])
old=[a.tobytes() for a in [f0,power,ap]]
assert ap_noise_power(f0,power,ap,1.) is ap
half=ap_noise_power(f0,power,ap,.5)
assert half[0].tobytes()==ap[0].tobytes()
assert np.allclose(half[1:,1:]**2,ap[1:,1:]**2*.5,rtol=1e-15)
assert half[1,0]==.001 and old==[a.tobytes() for a in [f0,power,ap]]
print(json.dumps(dict(original_voiced_preserved=True,eligible_only_fill=True,unvoiced_consonants_uppercase_pause_preserved=True,under_three_frames_not_filled=True,log_interpolation_verified=True,AP_identity_byte_exact=True,AP_power_half_with_floor=True,F0_SP_unchanged=True,bad_duration_rejected=True,actual_render_calls=0,quality_evidence=False)))
