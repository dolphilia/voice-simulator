"""先生/分析再合成の同じ音響診断。短イベントの知覚資格は付けない。"""
from paths import *
import sys,io,numpy as np
sys.path[:0]=[str(WORLD/'packages-v2'),str(BUNDLE)]
import pyworld as pw
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0

def packed(**x):
 f=io.BytesIO();np.savez_compressed(f,**x);return f.getvalue()
def measure_record(b,row,path):
 target=path.with_suffix('.measured.json')
 if target.exists():return read(target)
 r=read(path);source=REPO/r['wav'];assert digest(source)==r['wav_sha256'];fs,x=wavfile.read(source);assert fs==24000 and x.ndim==1
 with b.job(NAME,'dsp','同設定DIO/ACF/E0 '+r['mode']+'/'+r['id'],count=3,reserve_bytes=1000000) as j:
  f0,t=pw.dio(x.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.);f0=pw.stonemask(x.astype(float),f0,t,24000)
  freq,conf=estimate_f0(x,24000,minimum=70,maximum=800);e0=evaluate(x,{},24000)
  file=path.with_suffix('.dio.npz');b.write(file,packed(f0=f0,times=t),j)
  result=dict(r,status='completed',measurement={'E0':e0,'global_acf_f0':freq,'global_acf_confidence':conf,'dio_median_hz':float(np.median(f0[f0>0])) if np.any(f0>0) else None,'dio_voiced_fraction':float(np.mean(f0>0)),'duration_seconds':len(x)/24000,'RMS':float(np.sqrt(np.mean(x.astype(float)**2)))},E0_pass=e0['E0_pass'],DIO_file=str(file.relative_to(REPO)),DIO_sha256=digest(file),DIO_reusable_contract={'f0_floor':70.,'f0_ceil':800.,'frame_period':5.,'stonemask':True},new_DSP_calls=3,local_voiced_interval_qualification=False)
  b.save(target,result,j)
 return result
