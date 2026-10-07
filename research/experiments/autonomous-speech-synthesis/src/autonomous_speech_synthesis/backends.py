"""研究専用の旧方式とVTLアダプタ。移出bundleには含めない。"""
import ctypes as ct
import sys
import subprocess
import numpy as np
from scipy import signal
from .io import ROOT,read,file_hash
from .generator import render


def legacy_render(kind,vowel,f0,seed=401):
    root=ROOT.parent/"synthetic-vowel-baseline"
    sys.path.insert(0,str(root/"src"))
    from synthetic_vowel_baseline.synthesis import render_corrected_variation_candidates,render_onset_secondary_candidates
    spec=read(root/"config/experiment.json")
    quality=read(root/"config/voice-quality-experiment.json")
    correction=read(root/"config/voice-quality-correction.json")
    onset=read(root/"config/onset-secondary-experiment.json")
    profile=read(root/"config/vowel-generalization.json")["profiles"][vowel]
    spec.update(f0_hz=f0,formants_hz=profile["formants_hz"],bandwidths_hz=profile["bandwidths_hz"])
    correction["seed_offset"]=seed
    correction["conditions"]=correction["conditions"][:1]
    if kind=="B9":
        result=render_corrected_variation_candidates(spec,quality,correction)[0]
    else:
        onset.update(gain_attack_ms=40.,canonical_seed_offset=seed)
        result=render_onset_secondary_candidates(spec,quality,correction,onset)[1]
    return result["audio"],spec["sample_rate"],result["condition"]


class VTL:
    """公式C ABI。例外と戻り値を必ず確認する。プロセス内で直列に使用。"""
    def __init__(self):
        root=ROOT/".cache/VocalTractLabBackend-dev"
        self.library=root/"lib/Release/libVocalTractLabApi.dylib"
        self.speaker=root/"resources/JD3.speaker"
        self.lib=ct.CDLL(str(self.library))
        pointer=ct.POINTER(ct.c_double)
        self.lib.vtlInitialize.argtypes=[ct.c_char_p]
        self.lib.vtlGetTractParams.argtypes=[ct.c_char_p,pointer]
        self.lib.vtlGetGlottisParams.argtypes=[ct.c_char_p,pointer]
        self.lib.vtlSynthesisAddTract.argtypes=[ct.c_int,pointer,pointer,pointer]
        self.check(self.lib.vtlInitialize(str(self.speaker).encode()))
        vals=[ct.c_int() for _ in range(5)]; rate=ct.c_double()
        self.check(self.lib.vtlGetConstants(*(ct.byref(v) for v in vals),ct.byref(rate)))
        self.fs,self.ntube,self.ntract,self.nglottis,self.step=[v.value for v in vals]
        self.version=ct.create_string_buffer(256);self.lib.vtlGetVersion(self.version)
        self.metadata={"version":self.version.value.decode(),"library_sha256":file_hash(self.library),"speaker_sha256":file_hash(self.speaker),
                       "git_commit":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"license":"GPL-3.0-or-later","fs":self.fs}

    @staticmethod
    def check(result):
        if result!=0: raise RuntimeError(f"VTL APIが失敗しました: {result}")

    def render(self,vowel,f0,duration=.4,seed=11,setting=None):
        setting=setting or {}
        tract=(ct.c_double*self.ntract)();glottis=(ct.c_double*self.nglottis)()
        self.check(self.lib.vtlGetTractParams(vowel.encode(),tract))
        self.check(self.lib.vtlGetGlottisParams(b"modal",glottis))
        tract[8]=np.clip(tract[8]+setting.get("tongue_x_cm",0.),-3.,4.)
        tract[4]=np.clip(tract[4]+setting.get("lip_protrusion_cm",0.),-1.,1.)
        glottis[0]=f0
        # 頻度・圧・声門形状を意味のある低次元制御として扱う。
        glottis[1]*=setting.get("pressure_scale",1.)
        # VTLの内部乱数はC標準rand。毎回seedをリセットする。
        ct.CDLL(None).srand(ct.c_uint(seed))
        self.check(self.lib.vtlSynthesisReset())
        empty=(ct.c_double*1)()
        self.check(self.lib.vtlSynthesisAddTract(0,empty,tract,glottis))
        count=round(duration*self.fs)
        chunks=[]
        for start in range(0,count,self.step):
            n=min(self.step,count-start);buffer=(ct.c_double*n)()
            self.check(self.lib.vtlSynthesisAddTract(n,buffer,tract,glottis))
            chunks.append(np.array(buffer))
        audio=np.concatenate(chunks)
        # APIはフルスケール音声を返す。固定提示係数のみ、毎回の正規化なし。
        audio*=setting.get("gain",.5)
        fade=min(round(.012*self.fs),len(audio)//2)
        e=np.sin(np.linspace(0,np.pi/2,fade))**2
        audio[:fade]*=e;audio[-fade:]*=e[::-1]
        audio=signal.resample_poly(audio,80,147) # 44100 -> 24000
        audio[0]=0.;audio[-1]=0.
        return audio

    def close(self):
        self.check(self.lib.vtlClose())
