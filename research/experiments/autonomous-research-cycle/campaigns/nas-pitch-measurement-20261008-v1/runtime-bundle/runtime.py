"""周期既知の人工信号。音声品質や日本語の知覚資格には使わない。"""
from pathlib import Path
import sys,json,hashlib,io,argparse
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
from scipy.io import wavfile
from acoustics import evaluate
FS=24000
PROFILES={'a':[(730,90,1.),(1090,110,.55),(2440,160,.35)],'u':[(300,70,1.),(870,90,.6),(2240,140,.3)]}
def verify():
    root=Path(__file__).resolve().parent
    for n,h in json.loads((root/'manifest.json').read_text())['files'].items():
        assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
def validated(s):
    required={'id','kind','f0','voiced_ms','harmonic','vowel','SNR','ramp_ms','seed'}
    if set(s)!=required or s['kind'] not in ['positive','white_noise','formant_noise']:raise ValueError('固定人工仕様が不正')
    if s['voiced_ms'] not in [35,60,120,240] or s['ramp_ms'] not in [2,8] or s['harmonic'] not in ['all','missing_fundamental'] or s['vowel'] not in PROFILES or s['SNR'] not in ['none',10]:raise ValueError('未登録条件')
    if s['kind']=='positive' and s['f0'] not in [110,220,280,440]:raise ValueError('未登録周期')
    if s['kind']!='positive' and s['f0'] is not None:raise ValueError('否定条件に周期を指定')
    if not isinstance(s['seed'],int) or not 0<=s['seed']<2**32:raise ValueError('seedが不正')
    if not isinstance(s['id'],str) or len(s['id'])>64:raise ValueError('人工IDが不正')
    return s
def generate(spec):
    s=validated(spec);n=round(s['voiced_ms']*.001*FS);offset=round(.08*FS);total=n+offset*2
    rng=np.random.Generator(np.random.PCG64(s['seed']))
    audio=rng.standard_normal(total)*.02
    if s['kind']=='formant_noise':
        frequencies=np.fft.rfftfreq(total,1/FS);response=np.full(len(frequencies),.05)
        for center,bw,gain in PROFILES[s['vowel']]:response+=gain/(1+((frequencies-center)/bw)**2)
        audio=np.fft.irfft(np.fft.rfft(audio)*response,n=total)
    if s['kind']=='positive':
        t=np.arange(n)/FS;harm=np.arange(1,min(25,int(FS/2/s['f0'])-1)+1,dtype=float)
        assert len(harm)>=3
        if s['harmonic']=='missing_fundamental':harm=harm[1:]
        frequencies=harm*s['f0']
        weights=np.full(len(harm),.05)
        for center,bw,gain in PROFILES[s['vowel']]:
            weights+=gain/(1+((frequencies-center)/bw)**2)
        weights/=harm
        periodic=np.sum(weights[:,None]*np.sin(2*np.pi*frequencies[:,None]*t),axis=0)
        periodic-=periodic.mean()
        periodic*=.1/np.sqrt(np.mean(periodic**2))
        ramp=round(s['ramp_ms']*.001*FS);envelope=np.ones(n);fade=np.sin(np.linspace(0,np.pi/2,ramp))**2
        envelope[:ramp]=fade;envelope[-ramp:]=fade[::-1]
        noise=np.zeros(n) if s['SNR']=='none' else rng.standard_normal(n)*(.1/np.sqrt(10.))
        audio[offset:offset+n]=(periodic+noise)*envelope
    audio-=audio.mean()
    peak=np.max(np.abs(audio))
    if peak>0:audio*=.4/peak
    fade=np.sin(np.linspace(0,np.pi/2,round(.012*FS)))**2
    audio[:len(fade)]*=fade;audio[-len(fade):]*=fade[::-1]
    audio=audio.astype(np.float32)
    e0=evaluate(audio,{},FS)
    assert np.isfinite(audio).all()
    buf=io.BytesIO();wavfile.write(buf,FS,audio);data=buf.getvalue()
    forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']]
    assert not forbidden
    return data,dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,E0=e0,E0_pass=e0['E0_pass'],forbidden_imports=forbidden,truth=dict(f0=s['f0'],voiced_start=.08,voiced_end=.08+n/FS,core_start=.09,core_end=.08+n/FS-.01,voiced=s['kind']=='positive',unvoiced_boundary_erosion_seconds=.02),actual_render_calls=1,fixture_not_quality_evidence=True,quality_certified=False,phase_and_formula_shared=True,recorded_or_teacher_audio=0,neural_model=False)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--spec',required=True);args=parser.parse_args()
    import base64
    verify();data,meta=generate(json.loads(args.spec))
    print(json.dumps(dict(meta=meta,wav_base64=base64.b64encode(data).decode()),allow_nan=False))
if __name__=='__main__':main()
