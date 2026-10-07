"""保存したLF0/LPFと固定支持を診断する。品質判定や波形は変更しない。"""
from paths import *
import numpy as np
p=read(HERE/'protocol.json');data=[];bad=[];good=[]
for row in p['rows']:
 for condition in p['conditions']:
  value=read(HERE/'render'/row['id']/condition/'calibrated.json')
  (bad if value['measurement']['missing_support'] else good).append((row,condition))
selected=bad+good[:4]
assert len(bad)==12 and len(selected)==16
for row,condition in selected:
 outputs={}
 for method in ['native','calibrated']:
  base=HERE/'render'/row['id']/condition/method;record=read(base.with_suffix('.json'))
  with np.load(base.with_suffix('.npz')) as arrays:
   lf0=arrays['lf0'][:,0];lpf=arrays['lpf'];duration=arrays['duration'];bounds=np.r_[0,np.cumsum(duration)];positions=np.arange(lpf.shape[1])-(lpf.shape[1]-1)//2;phones=[]
   for local in record['measurement']['local']:
    index=local['index'];lo,hi=bounds[index*5],bounds[(index+1)*5];mask=np.arange(lo,hi);mask=mask[lf0[mask]>0];count=hi-lo
    ratio=[]
    if len(mask):
     hz=np.exp(lf0[mask]);response=np.sum(lpf[mask]*np.exp(-1j*2*np.pi*hz[:,None]*positions[None,:]/48000),axis=1);periodic=abs(response)**2;noise=abs(1-response)**2;ratio=noise/(periodic+noise)
    label=row['full_context_labels'][index];phone=label.split('-')[1].split('+')[0]
    phones.append(dict(index=index,phone=phone,frames=int(count),driving_voiced_fraction=float(len(mask)/count),driving_median_hz=float(np.exp(np.median(lf0[mask]))) if len(mask) else None,LPF_derived_noise_power_fraction_at_driving_F0_median=float(np.median(ratio)) if len(ratio) else None,DIO_supported=local['support_complete'],DIO_voiced_frames=local['voiced_frames']))
   outputs[method]=phones
 data.append(dict(id=row['id']+'/'+condition,calibrated_support_missing=read(HERE/'render'/row['id']/condition/'calibrated.json')['measurement']['missing_support'],variants=outputs))
print(__import__('json').dumps(dict(rows=data,selection='全12欠損条件とID順の先頭4通過条件。結果を用いた診断選択であり独立品質証拠ではない。',parameter_DSP=32,new_render=0,not_used_to_change_current_gate=True,AP_definition_source_sha256=digest(WORLD/'upstream/synthesis.cpp')),ensure_ascii=False,allow_nan=False))
