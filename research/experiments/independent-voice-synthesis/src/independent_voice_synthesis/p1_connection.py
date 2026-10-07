"""解析LFの倍音だけを合成し、流量から音圧へ一度だけ微分する。"""
import numpy as np
from scipy.optimize import brentq
from .models import response, FS


def exponential_integral(rate, length):
    if abs(rate) < 1e-12:
        return length
    return np.expm1(rate*length)/rate


def lf_constants(cfg):
    tp,te,ta = (cfg[k] for k in ('tp','te','ta'))
    if not 0 < tp < te < min(2*tp,1) or not 0 < ta < 1-te:
        raise ValueError('LF時間定数が不正です')
    eps = brentq(lambda e: -np.expm1(-e*(1-te))-e*ta,1e-5,1/ta,xtol=1e-12)
    omega = np.pi/tp
    tail_area = -(exponential_integral(-eps,1-te)-(1-te)*np.exp(-eps*(1-te)))/(eps*ta)
    def constants(alpha):
        e0 = -np.exp(-alpha*te)/np.sin(omega*te)
        return e0, e0*exponential_integral(alpha+1j*omega,te).imag+tail_area
    alpha = brentq(lambda a: constants(a)[1],0.,100.,xtol=1e-12)
    return dict(epsilon=eps,alpha=alpha,E0=constants(alpha)[0],omega=omega,area_error=constants(alpha)[1])


def lf_derivative(u,cfg,c):
    u = np.asarray(u)
    te,ta = cfg['te'],cfg['ta']
    return np.where(u <= te,c['E0']*np.exp(c['alpha']*u)*np.sin(c['omega']*u),
                    -(np.exp(-c['epsilon']*(u-te))-np.exp(-c['epsilon']*(1-te)))/(c['epsilon']*ta))


def lf_flow(u,cfg,c):
    """微分式の原始関数。独立した積分整合テストにも用いる。"""
    u = np.asarray(u)
    te,ta = cfg['te'],cfg['ta']
    rate = c['alpha']+1j*c['omega']
    opening = c['E0']*np.imag(np.expm1(rate*u)/rate)
    at_te = c['E0']*np.imag(np.expm1(rate*te)/rate)
    length = u-te
    tail = at_te-((-np.expm1(-c['epsilon']*length)/c['epsilon'])-length*np.exp(-c['epsilon']*(1-te)))/(c['epsilon']*ta)
    return np.where(u <= te,opening,tail)


def source_coefficients(cfg):
    c = lf_constants(cfg)
    f = np.arange(1,int(np.ceil((FS/2)/cfg['F0_hz'])))*cfg['F0_hz']
    f = f[f < FS/2]
    harmonics = f/cfg['F0_hz']
    te,ta = cfg['te'],cfg['ta']
    values=[]
    for n in harmonics:
        k=2*np.pi*n
        opening = c['E0']/(2j)*(exponential_integral(c['alpha']+1j*(c['omega']-k),te)-exponential_integral(c['alpha']-1j*(c['omega']+k),te))
        tail = -np.exp(-1j*k*te)/(c['epsilon']*ta)*(exponential_integral(-c['epsilon']-1j*k,1-te)-np.exp(-c['epsilon']*(1-te))*exponential_integral(-1j*k,1-te))
        values.append((opening+tail)*cfg['U0_m3_per_s']*cfg['F0_hz'])
    derivative = np.asarray(values)
    flow = derivative/(2j*np.pi*f)
    return f,flow,derivative,c


def window(f):
    a = np.abs(np.asarray(f))
    w = np.zeros_like(a,dtype=float)
    up=(a>100)&(a<200)
    down=(a>4500)&(a<5000)
    w[up]=.5-.5*np.cos(np.pi*(a[up]-100)/100)
    w[(a>=200)&(a<=4500)]=1.
    w[down]=.5+.5*np.cos(np.pi*(a[down]-4500)/500)
    return w


def pressure(p,f,flow,cfg):
    return cfg['rho_air_kg_m3']/(4*np.pi*cfg['distance_m'])*(2j*np.pi*f)*response(p,f)*flow*window(f)


def synthesize(coefficients,f,cfg):
    if cfg['Fs'] != FS or np.any(np.asarray(f) >= FS/2):
        raise ValueError('作業レートまたは倍音周波数が不正です')
    t = np.arange(round(FS*cfg['duration_seconds']))/FS
    y = np.zeros_like(t)
    for v,nu in zip(coefficients,f,strict=True):
        y += 2*np.real(v*np.exp(2j*np.pi*nu*t))
    return y


def presentation(signals,cfg):
    outputs,logs=[],[]
    nfade=round(cfg['fade_seconds']*FS)
    for y in signals:
        y=y.copy()
        fade=.5-.5*np.cos(np.linspace(0,np.pi,nfade))
        y[:nfade]*=fade
        y[-nfade:]*=fade[::-1]
        rms=float(np.sqrt(np.mean(y*y)))
        if not np.isfinite(rms) or rms <= 0:
            raise ValueError('提示信号のRMSが不正です')
        scalar=cfg['target_rms']/rms
        outputs.append(y*scalar)
        logs.append(dict(pre_scalar_rms_pa=rms,rms_scalar=scalar))
    down=min(1.,cfg['peak_ceiling']/max(float(np.max(abs(y))) for y in outputs))
    for i,y in enumerate(outputs):
        outputs[i]=y*down
        logs[i].update(common_downscale=down,final_rms=float(np.sqrt(np.mean(outputs[i]**2))),final_peak=float(np.max(abs(outputs[i]))))
    return outputs,logs
