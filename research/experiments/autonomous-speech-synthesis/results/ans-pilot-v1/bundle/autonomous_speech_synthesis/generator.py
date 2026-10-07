"""帯域制限した解析LF励起と連続した声道・局所雑音モデル。"""
from functools import lru_cache
import numpy as np
from scipy.optimize import brentq
from scipy import signal
from .gestures import make_gestures, voice_config


def exp_integral(rate, length):
    return length if abs(rate)<1e-12 else np.expm1(rate*length)/rate


@lru_cache(maxsize=64)
def lf_constants(tp=.4, te=.6, ta=.05):
    """旧P1の解析式を独立実装へ移植。旧実験の資格は継承しない。"""
    if not 0<tp<te<min(2*tp,1) or not 0<ta<1-te:
        raise ValueError("LF時間定数が範囲外です")
    epsilon=brentq(lambda e:-np.expm1(-e*(1-te))-e*ta,1e-5,1/ta,xtol=1e-12)
    omega=np.pi/tp
    tail=-(exp_integral(-epsilon,1-te)-(1-te)*np.exp(-epsilon*(1-te)))/(epsilon*ta)
    def area(alpha):
        e0=-np.exp(-alpha*te)/np.sin(omega*te)
        return e0*exp_integral(alpha+1j*omega,te).imag+tail
    alpha=brentq(area,-100.,100.,xtol=1e-12)
    return epsilon,omega,alpha,-np.exp(-alpha*te)/np.sin(omega*te)


def lf_derivative(phase, tp=.4, te=.6, ta=.05):
    epsilon,omega,alpha,e0=lf_constants(tp,te,ta)
    phase=np.asarray(phase)
    return np.where(phase<=te,e0*np.exp(alpha*phase)*np.sin(omega*phase),
                    -(np.exp(-epsilon*(phase-te))-np.exp(-epsilon*(1-te)))/(epsilon*ta))


@lru_cache(maxsize=128)
def lf_coefficients(harmonics,tp,te,ta):
    epsilon,omega,alpha,e0=lf_constants(tp,te,ta)
    result=[]
    for n in range(1,harmonics+1):
        k=2*np.pi*n
        opening=e0/(2j)*(exp_integral(alpha+1j*(omega-k),te)-exp_integral(alpha-1j*(omega+k),te))
        tail=-np.exp(-1j*k*te)/(epsilon*ta)*(exp_integral(-epsilon-1j*k,1-te)-np.exp(-epsilon*(1-te))*exp_integral(-1j*k,1-te))
        result.append(opening+tail)
    return np.array(result)


def lf_source(f0, sample_rate, source):
    # Nyquist直前を切り、変動時にも最高F0で帯域制限する。
    harmonics=int(.45*sample_rate/np.max(f0))
    coeff=lf_coefficients(harmonics,source["tp"],source["te"],source["ta"])
    phase=2*np.pi*np.cumsum(f0)/sample_rate
    y=np.zeros(len(f0))
    for harmonic,c in enumerate(coeff,1):
        y+=2*np.real(c*np.exp(1j*harmonic*phase))
    # dU/duからdU/dtへ。基準F0で相対利得を固定し、放射微分はこれ一度だけ。
    return y*f0/220


def render(phonemes, prosody=None, voice=None, seed=0, sample_rate=24000):
    if sample_rate not in (16000,24000,48000):
        raise ValueError("対応サンプルレートは16000/24000/48000 Hzです")
    voice=voice_config() if voice is None else voice
    tracks,events=make_gestures(phonemes,prosody or {},voice,sample_rate)
    rng=np.random.default_rng(seed)
    count=len(tracks["f0_hz"])
    source=lf_source(tracks["f0_hz"],sample_rate,voice["source"])
    source*=tracks["voicing"]*tracks["gain"]
    source+=rng.standard_normal(count)*voice["source"]["aspiration"]*tracks["voicing"]*tracks["gain"]
    output=np.zeros(count)
    states=[np.zeros(2) for _ in range(3)]
    noise_state=np.zeros(2)
    noise=rng.standard_normal(count)
    block=max(1,round(.005*sample_rate))
    for start in range(0,count,block):
        stop=min(count,start+block); middle=(start+stop)//2
        for j in range(3):
            freq=tracks["formants_hz"][middle,j]
            bw=voice["bandwidths_hz"][j]*voice["bandwidth_scale"]
            b,a=signal.iirpeak(freq,freq/bw,fs=sample_rate)
            y,states[j]=signal.lfilter(b,a,source[start:stop],zi=states[j])
            output[start:stop]+=voice["formant_gains"][j]*y
        center=min(tracks["noise_center_hz"][middle],sample_rate*.4)
        b,a=signal.iirpeak(center,1.2,fs=sample_rate)
        y,noise_state=signal.lfilter(b,a,noise[start:stop],zi=noise_state)
        output[start:stop]+=voice["noise_gain"]*tracks["noise"][start:stop]*y
    # 鼻腔分岐の近似: 低域共鳴と反共鳴。解剖学的な面積関数ではない。
    b,a=signal.iirpeak(280,2.,fs=sample_rate)
    nasal=signal.lfilter(b,a,source)
    b,a=signal.iirnotch(1000,3.,fs=sample_rate)
    notched=signal.lfilter(b,a,output)
    n=tracks["nasal"]
    output=(1-n)*output+n*(.65*notched+.6*nasal)
    output*=voice["gain"]
    fade=min(round(.012*sample_rate),len(output)//2)
    envelope=np.sin(np.linspace(0,np.pi/2,fade))**2
    output[:fade]*=envelope; output[-fade:]*=envelope[::-1]
    # 波形の正規化やclipで破綻を隠さない。
    stride=max(1,round(.01*sample_rate))
    log={"generator_version":voice["version"],"sample_rate_hz":sample_rate,"seed":seed,
         "events":events,"control_step_seconds":stride/sample_rate,
         "f0_hz":tracks["f0_hz"][::stride].tolist(),
         "formants_hz":tracks["formants_hz"][::stride].tolist(),
         "units":voice["units"],"contains_recording":False,"runtime_neural_inference":False}
    return output,log
