"""既知F0・有声マスクの手続き的信号設計と生成。音声品質の正解ではない。"""
import numpy as np
from scipy import signal
FS=24000
SECONDS=1.2
N=28800
FAMILIES=['stationary','glide','interrupted','filtered_noise']


def filter_design():
    result=[]
    for center,width,gain in [(800.,80.,1.),(1200.,100.,.6),(2500.,150.,.3)]:
        b,a=signal.iirpeak(center/(FS/2),center/width)
        result.append({'center':center,'width':width,'gain':gain,'b':b.tolist(),'a':a.tolist()})
    return result


def catalog():
    result=[]
    filters=filter_design()
    for split,f0s,snr in [('development',[180.,300.,420.],20.),('confirmation',[220.,360.,520.],15.)]:
        for family_index,family in enumerate(FAMILIES):
            for pitch_index,base in enumerate(f0s):
                result.append({'id':f'{split}-{family_index}-{pitch_index}','split':split,'family':family,
                    'fs':FS,'seconds':SECONDS,'samples':N,'base_f0_hz':base,
                    'f0_endpoints_hz':[base*.85,base*1.15] if family=='glide' else [base,base],
                    'voiced_intervals':[[.1,.5],[.7,1.1]] if family=='interrupted' else [[.1,1.1]],
                    'fade_seconds':.01,'seed':2026100300+(0 if split=='development' else 100)+family_index*3+pitch_index,
                    'noise_snr_db':snr if family in ('interrupted','filtered_noise') else None,
                    'harmonic_count':min(40,int(11000/base)) if family=='filtered_noise' else 3,
                    'filters':filters if family=='filtered_noise' else [],'max_abs_amplitude':.8,
                    'scope':'既知手続き的信号。独立日本語文数0。'})
    return result


def truth(row):
    validate(row)
    t=np.arange(row['samples'])/row['fs']
    lo,hi=row['f0_endpoints_hz'];f0=lo+(hi-lo)*t/row['seconds']
    mask=np.zeros(len(t),dtype=bool)
    for a,b in row['voiced_intervals']:mask|=(t>=a)&(t<b)
    return t,f0,mask


def validate(row):
    if row['family'] not in FAMILIES or row['fs']!=FS or row['samples']!=N or row['seconds']!=SECONDS:
        raise ValueError('信号系列・標本化・長さが固定契約と一致しません')
    values=[row['base_f0_hz'],*row['f0_endpoints_hz'],row['fade_seconds'],row['max_abs_amplitude']]
    if not np.isfinite(values).all() or not 70<=min(row['f0_endpoints_hz'])<=max(row['f0_endpoints_hz'])<=800:
        raise ValueError('F0が非有限または範囲外です')
    if type(row['seed']) is not int or row['seed']<0:raise ValueError('雑音seedを固定します')
    if row['family']!='filtered_noise' and row['harmonic_count']!=3:
        raise ValueError('非共鳴系列の調波数は3本に固定します')
    if type(row['harmonic_count']) is not int or not 1<=row['harmonic_count']<=40 or max(row['f0_endpoints_hz'])*row['harmonic_count']>11000:
        raise ValueError('調波が11kHzまたはNyquist条件に不通過です')
    if not 0<row['max_abs_amplitude']<=.8 or not 0<row['fade_seconds']<=.01:
        raise ValueError('振幅・遷移長が範囲外です')
    previous=0.
    if not row['voiced_intervals']:raise ValueError('有声区間を非空にします')
    for a,b in row['voiced_intervals']:
        if not np.isfinite([a,b]).all() or not previous<=a<b<=row['seconds'] or b-a<2*row['fade_seconds']:
            raise ValueError('有声区間が不正です')
        previous=b
    if row['family'] in ('interrupted','filtered_noise') and (row['noise_snr_db'] is None or not np.isfinite(row['noise_snr_db'])):
        raise ValueError('雑音のSNRを固定します')
    for filt in row['filters']:
        if not np.isfinite(filt['a']+filt['b']).all() or np.max(abs(np.roots(filt['a'])))>=1:
            raise ValueError('フィルタが非有限または不安定です')


def validate_truth(row,t,f0,mask):
    if t.shape!=f0.shape or mask.shape!=t.shape or len(t)!=row['samples'] or mask.dtype!=np.bool_:
        raise ValueError('正解配列の形状・型が不正です')
    if not np.isfinite(t).all() or not np.isfinite(f0).all() or not mask.any() or not np.all(np.diff(t)>0):
        raise ValueError('正解配列の有限性・単調性・有声区間が不正です')


def generate(row):
    t,f0,mask=truth(row);validate_truth(row,t,f0,mask)
    # 右端で積分した位相の後退差分は、指定F0と各サンプルで一致する。
    phase=2*np.pi*np.cumsum(f0)/row['fs']
    weights=np.arange(1,row['harmonic_count']+1,dtype=float)**-1.5 if row['family']=='filtered_noise' else np.array([1.,.35,.15])
    periodic=np.sum([weight*np.sin(k*phase) for k,weight in enumerate(weights,1)],axis=0)
    env=np.zeros(len(t))
    for a,b in row['voiced_intervals']:
        inside=(t>=a)&(t<b)
        distance=np.minimum(t-a,b-t)
        env[inside]=np.sin(np.minimum(1.,distance[inside]/row['fade_seconds'])*np.pi/2)**2
    voice=periodic*env
    if row['filters']:
        voice=sum(f['gain']*signal.lfilter(f['b'],f['a'],voice) for f in row['filters'])
    noise=np.zeros(len(t));snr=None
    if row['noise_snr_db'] is not None:
        raw=np.random.default_rng(row['seed']).standard_normal(len(t));raw-=raw.mean()
        voice_rms=np.sqrt(np.mean(voice[mask]**2));raw_rms=np.sqrt(np.mean(raw[mask]**2))
        noise=raw/raw_rms*voice_rms/(10**(row['noise_snr_db']/20))
        if row['family']=='interrupted':noise[mask]=0
        else:snr=float(20*np.log10(voice_rms/np.sqrt(np.mean(noise[mask]**2))))
    output=voice+noise;peak=float(np.max(abs(output)))
    if not np.isfinite(output).all() or peak<1e-8:raise ValueError('信号の有限性・振幅が不正です')
    gain=row['max_abs_amplitude']/peak;output=(output*gain).astype(np.float32)
    assert np.max(abs(output))<=.8000001
    return output,{'t':t,'f0_hz':f0,'voiced_mask':mask,'phase':phase}, {'raw_peak':peak,'output_gain':gain,'measured_active_snr_db':snr}


def tests():
    row=catalog()[0];t,f0,mask=truth(row);validate_truth(row,t,f0,mask)
    bad=[{**row,'base_f0_hz':np.nan},{**row,'f0_endpoints_hz':[69.,180.]},{**row,'voiced_intervals':[]},
        {**row,'seed':None},{**row,'harmonic_count':40},{**row,'voiced_intervals':[[.5,.4]]}]
    rejected=0
    for r in bad:
        try:validate(r)
        except ValueError:rejected+=1
    assert rejected==6
    try:validate_truth(row,t,f0,mask[:-1])
    except ValueError:pass
    else:raise AssertionError('正解マスクの形状違いを拒否しません')
    for r in catalog():validate(r)
    return {'catalog_cases':24,'negative_configurations_rejected':6,'mask_shape_rejected':True,
        'filters_stable':True,'no_audio_generated':True,'new_render_calls':0}
