"""共有母音係数と有限k/t/s規則からVTL状態を入力時に計算。保存軌跡を読まない。"""
import ctypes as ct,hashlib,io,json,math,unicodedata
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
from vtl_runtime import VTL
ROOT=Path(__file__).resolve().parent
KANA=dict(zip('あいうえお',[(None,v) for v in 'aiueo']))
for chars,c in [('かきくけこ','k'),('たちつてと','t'),('さしすせそ','s')]:
 KANA.update({ch:(c,v) for ch,v in zip(chars,'aiueo')})
KANA.update({'ち':('ch','i'),'つ':('ts','u'),'し':('sh','i')})
def parse(text):
 text=unicodedata.normalize('NFKC',text);text=''.join(chr(ord(c)-96) if 'ァ'<=c<='ヶ' else c for c in text)
 if not text or len(text)>24 or any(c not in KANA for c in text):raise ValueError('対象は五母音とカ/タ/サ行のかな24モーラ以内')
 return [dict(kana=c,onset=KANA[c][0],vowel=KANA[c][1]) for c in text]
def smooth(x):
 x=min(1.,max(0.,x));return x*x*(3.-2.*x)
class CV(VTL):
 def __init__(self):
  super().__init__();self.model=json.loads((ROOT/'shared-model.json').read_text());self.cache={}
 def tract(self,name):
  if name not in self.cache:
   a=(ct.c_double*self.ntract)();self.check(self.lib.vtlGetTractParams(name.encode(),a));self.cache[name]=np.array(a)
  return self.cache[name].copy()
 def glottis(self,name,f0):
  a=(ct.c_double*self.nglottis)();self.check(self.lib.vtlGetGlottisParams(name.encode(),a));a[0]=f0;return np.array(a)
 def vowel_target(self,v,learned):
  a=self.tract(v)
  if learned:
   c=self.model['vowels'][v];a[8]+=c['TCX_delta_cm'];a[9]+=c['TCY_delta_cm']
  for j,name in enumerate(self.names):
   if not self.bounds[name][0]<=a[j]<=self.bounds[name][1]:raise ValueError('共有母音標的のAPI範囲外')
  return a
 def onset_targets(self,c,v,f0):
  context='a' if v in 'ae' else 'i' if v=='i' else 'u'
  if c in ['k','t']:
   name='tb-velar-closure' if c=='k' else 'tt-alveolar-closure';a=self.tract(name+'('+context+')');g=self.glottis('voiceless-plosive',f0);return a,g,a,g
  if c in ['s','sh']:
   name='tt-alveolar-fricative' if c=='s' else 'tt-postalveolar-fricative';a=self.tract(name+'('+context+')');g=self.glottis('voiceless-fricative',f0);return a,g,a,g
  if c in ['ch','ts']:
   place='postalveolar' if c=='ch' else 'alveolar';a=self.tract('tt-'+place+'-closure('+context+')');z=self.tract('tt-'+place+'-fricative('+context+')');return a,self.glottis('voiceless-plosive',f0),z,self.glottis('voiceless-fricative',f0)
  raise ValueError('子音規則対象外')
 def render_vowel(self,v,f0,learned=True):
  c=self.model['vowels'][v] if learned else dict(TCX_delta_cm=0.,TCY_delta_cm=0.)
  return super().render(v,f0,.32,41,c['TCX_delta_cm'],c['TCY_delta_cm'])
 def render_text(self,text,f0=140.,speed=1.,learned=False,seed=41):
  if not 70<=f0<=400 or not .5<=speed<=2.:raise ValueError('F0/速度の登録範囲外')
  moras=parse(text);duration=.1+len(moras)*.32/speed
  if duration>8.:raise ValueError('八秒を超える入力')
  modal=self.glottis('modal',f0);states=[];intervals=[]
  for i,m in enumerate(moras):
   v=self.vowel_target(m['vowel'],learned);c=m['onset'];onset=self.onset_targets(c,m['vowel'],f0) if c else (v,modal,v,modal);states.append((v,*onset))
   start=.05+i*.32/speed;vstart=start+(.08/speed if c else 0.)
   intervals.append(dict(index=i,kana=m['kana'],phone=c,vowel=m['vowel'],source_schedule_vowel_interval=[vstart,start+.32/speed],boundary_not_observed_truth=True))
  def target(t):
   if t<=.05:
    a,g=states[0][1].copy(),states[0][2].copy();g[1]=0.;return a,g
   end=.05+len(moras)*.32/speed
   if t>=end:
    a=states[-1][0].copy();g=modal.copy();g[1]*=1.-smooth((t-end)/.05);return a,g
   i=min(int((t-.05)*speed/.32),len(moras)-1);local=(t-.05)*speed-i*.32;v,a,g,z,h=states[i];c=moras[i]['onset']
   previous=states[i-1][0] if i else a;previous_g=modal.copy() if i else g.copy()
   if i==0:previous_g[1]=0.
   if c and local<.08:
    if local<.02:
     w=smooth(local/.02);return previous*(1-w)+a*w,previous_g*(1-w)+g*w
    w=smooth((local-.055)/.025) if c in ['ch','ts'] else 0.
    return a*(1-w)+z*w,g*(1-w)+h*w
   elapsed=local-(.08 if c else 0.)
   if c:old_a,old_g=z,h
   else:old_a,old_g=previous,previous_g
   w=smooth(elapsed/(.04 if c else .02));return old_a*(1-w)+v*w,old_g*(1-w)+modal*w
  ct.CDLL(None).srand(ct.c_uint(seed));self.check(self.lib.vtlSynthesisReset());a,g=target(0.)
  empty=(ct.c_double*1)();self.check(self.lib.vtlSynthesisAddTract(0,empty,(ct.c_double*self.ntract)(*a),(ct.c_double*self.nglottis)(*g)))
  count=round(duration*self.fs);blocks=[];calls=0
  for start in range(0,count,self.step):
   n=min(self.step,count-start);a,g=target((start+n)/self.fs)
   for j,name in enumerate(self.names):
    if not self.bounds[name][0]-1e-12<=a[j]<=self.bounds[name][1]+1e-12:raise ValueError('補間制御がAPI範囲外')
   out=(ct.c_double*n)();self.check(self.lib.vtlSynthesisAddTract(n,out,(ct.c_double*self.ntract)(*a),(ct.c_double*self.nglottis)(*g)));blocks.append(np.array(out));calls+=1
  audio=signal.resample_poly(np.concatenate(blocks)*.5,80,147);fade=min(round(.012*24000),len(audio)//2);e=np.sin(np.linspace(0,np.pi/2,fade))**2;audio[:fade]*=e;audio[-fade:]*=e[::-1];audio[0]=audio[-1]=0.;audio=audio.astype(np.float32)
  buf=io.BytesIO();wavfile.write(buf,24000,audio);data=buf.getvalue()
  return data,dict(text=text,moras=moras,learned=learned,requested_F0_Hz=f0,speed=speed,seed=seed,gain=.5,duration_seconds=duration,phone_intervals=intervals,source_samples=count,render_calls=calls+3,internal_AddTract_audio_calls=calls,reset_calls=1,initial_zero_AddTract_calls=1,outer_waveform_calls=1,wav_sha256=hashlib.sha256(data).hexdigest(),model_sha256=hashlib.sha256((ROOT/'shared-model.json').read_bytes()).hexdigest(),neural=False,recorded_audio_or_saved_trajectory_read=False,Japanese_devoicing_not_implemented=True,full_geometry_constraints_not_qualified=True,source_pressure_unit='dPa',control_ramps_seconds=dict(consonant=.02,affricate=.025,vowel=.04))
