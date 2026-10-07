"""WORLDの固定powerを保ち、有声APの非周期配分のみを変更する。"""
import numpy as np
from scipy import signal
from controls_v2 import ap_noise_power
import world_renderer2 as world

def synthesize(params,settings,factor):
    if factor==1.:
        audio,meta=world.synthesize(params,settings)
        meta.update(AP_noise_power_factor=1.,AP_factor_identity_delegate=True)
        return audio,meta
    assert settings['stage']==0 and settings['alpha']==world.ALPHA and settings['beta']==0 and settings['volume']==1 and settings['sampling_frequency']==world.FS and settings['fperiod']==world.PERIOD
    (f0,power,ap),meta=world.convert(params)
    original=world.ah(ap);f0_before=world.ah(f0);power_before=world.ah(power)
    scaled=ap_noise_power(f0,power,ap,factor)
    assert world.ah(f0)==f0_before and world.ah(power)==power_before and world.ah(ap)==original
    raw=world.pw.synthesize(f0,power,scaled,world.FS,frame_period=5.)
    assert len(raw)==len(f0)*world.PERIOD and np.isfinite(raw).all()
    raw=raw[:len(params[0])*world.PERIOD]
    audio=signal.resample_poly(raw,1,2)
    n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=env;audio[-n:]*=env[::-1]
    assert len(audio)==len(params[0])*120 and np.isfinite(audio).all()
    meta.update(AP_before_sha256=original,AP_sha256=world.ah(scaled),
        AP_noise_power_factor=factor,AP_amplitude_factor=float(np.sqrt(factor)),
        AP_floor=.001,unvoiced_AP_unchanged=True,power_f0_unchanged=True,
        sample_count_24k=len(audio),AP_factor_identity_delegate=False)
    return audio,meta
