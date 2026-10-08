"""文章指令に対する固定Fujisaki応答。録音・教師・発話lookup・学習を使わない。"""
import math,re,hashlib
import numpy as np
ALPHA=3.;BETA=20.;GAMMA=.9;AP=.15;AA=.25;LEAD=.2;DT=.005
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def gp(t):
 x=np.asarray(t,dtype=float);u=np.maximum(x,0.)
 return np.where(x>=0.,ALPHA**2*u*np.exp(-ALPHA*u),0.)
def ga(t):
 x=np.asarray(t,dtype=float);u=np.maximum(x,0.)
 return np.where(x>=0.,np.minimum(-np.expm1(-BETA*u)-BETA*u*np.exp(-BETA*u),GAMMA),0.)
def contour(times,phrases,accents):
 t=np.asarray(times,dtype=float)
 if t.ndim!=1 or not len(t) or not np.isfinite(t).all():raise ValueError('有限非空の時刻列が必要')
 p=np.zeros_like(t);a=np.zeros_like(t)
 for onset in phrases:
  if not math.isfinite(onset):raise ValueError('句指令時刻が有限でない')
  p+=AP*gp(t-float(onset))
 for onset,offset in accents:
  if not math.isfinite(onset+offset) or onset>=offset:raise ValueError('アクセント指令の開始/終了が不正')
  a+=AA*(ga(t-float(onset))-ga(t-float(offset)))
 if not np.isfinite(p+a).all():raise ValueError('応答が有限でない')
 return p+a,p,a
def commands(labels,duration):
 d=np.asarray(duration)
 if d.ndim!=1 or len(d)!=len(labels)*5 or not np.isfinite(d).all() or np.any(d<1) or np.any(d!=np.floor(d)):
  raise ValueError('各音素5状態の正整数durationが必要')
 bounds=np.r_[0,np.cumsum(d.reshape(-1,5).sum(axis=1))].astype(int);groups=[];current=None
 for i,label in enumerate(labels):
  phone=re.search(r'\-([^+]+)\+',label)
  if phone is None:raise ValueError('音素ラベル構文が不正')
  if phone.group(1) in ('sil','pau'):current=None;continue
  a=re.search(r'/A:(-?\d+)\+(\d+)\+(\d+)',label)
  f=re.search(r'/F:(\d+)_(\d+)#(\d+)_xx@(\d+)_(\d+)\|(\d+)_(\d+)',label)
  breath=re.search(r'/I:(\d+)-(\d+)@(\d+)\+(\d+)&',label)
  if not a or not f or not breath:raise ValueError('A/F/I文脈が不足')
  count,accent,emotion,ap_index,ap_back,mora_start,mora_back=map(int,f.groups());position=int(a.group(2));bg=int(breath.group(3));key=(bg,ap_index)
  if emotion!=0 or not 1<=accent<=count or not 1<=position<=count:raise ValueError('登録外の疑問/アクセント文脈')
  if current is None or current['key']!=key:
   current=dict(key=key,mora_count=count,encoded_accent=accent,terminal_accent_ambiguous=accent==count,moras=[]);groups.append(current)
  if (current['mora_count'],current['encoded_accent'])!=(count,accent):raise ValueError('句内の文脈が不一致')
  if not current['moras'] or current['moras'][-1]['position']!=position:
   current['moras'].append(dict(position=position,start_frame=int(bounds[i]),end_frame=int(bounds[i+1])))
  else:current['moras'][-1]['end_frame']=int(bounds[i+1])
 if not groups:raise ValueError('アクセント句がない')
 phrases=[];accents=[];seen=set()
 for g in groups:
  m=g['moras'];n=g['mora_count'];accent=g['encoded_accent'];bg=g['key'][0]
  if [v['position'] for v in m]!=list(range(1,n+1)):raise ValueError('句の全モーラ順序が不一致')
  if bg not in seen:phrases.append(m[0]['start_frame']*DT-LEAD);seen.add(bg)
  first=0 if accent==1 or n==1 else 1
  accents.append([m[first]['start_frame']*DT,m[accent-1]['end_frame']*DT])
 return dict(phrase_times=phrases,accent_times=accents,groups=groups,frames=int(d.sum()),
             rule='一breath groupの先頭-.2秒に句指令。アクセント1は第1モーラ開始、それ以外は第2開始。終了はencoded accentモーラ末。',
             encoded_final_or_unaccented_not_distinguished=True,phonological_accent_truth_claimed=False)
def transform(native,labels,duration,pitch):
 if len(native)!=3 or not math.isfinite(pitch) or not 70<=pitch<=800:raise ValueError('3streamと登録Hz範囲が必要')
 x=[np.asarray(v) for v in native]
 if any(v.ndim!=2 or not v.size or not np.isfinite(v).all() for v in x) or len({len(v) for v in x})!=1 or x[1].shape[1]!=1:raise ValueError('3streamの形状が不正')
 voiced=x[1][:,0]>0
 if not voiced.any() or np.any(x[1][~voiced]!=-1e10):raise ValueError('有声mask/sentinelが不正')
 c=commands(labels,duration)
 if c['frames']!=len(x[1]):raise ValueError('duration総和と全frameが不一致')
 times=np.arange(len(x[1]),dtype=float)*DT;shape,p,a=contour(times,c['phrase_times'],c['accent_times'])
 center=float(np.median(shape[voiced]));offset=math.log(float(pitch))-center;out=[v.copy() for v in x];out[1][voiced,0]=shape[voiced]+offset
 hz=np.exp(out[1][voiced,0])
 if np.any((hz<70)|(hz>800)):raise ValueError('共有応答LF0が範囲外。clipせず拒否')
 assert out[0].tobytes()==x[0].tobytes() and out[2].tobytes()==x[2].tobytes() and out[1][~voiced].tobytes()==x[1][~voiced].tobytes()
 assert np.array_equal(out[1][:,0]>0,voiced) and abs(np.median(out[1][voiced,0])-math.log(pitch))<=2e-15
 return out,dict(model='fixed-Fujisaki-command-response',commands=c,parameters=dict(alpha=ALPHA,beta=BETA,gamma=GAMMA,Ap_seconds=AP,Aa=AA,phrase_lead_seconds=LEAD),
                 phrase_response_sha256=ah(p),accent_response_sha256=ah(a),uncentered_response_sha256=ah(shape),log_offset=offset,
                 native_LF0_values_used_for_shape=False,generated_voiced_mask_used=True,whole_utterance_voiced_median_calibration=True,
                 causal_response_before_global_calibration=True,whole_utterance_calibration_is_not_streaming_causal=True,
                 MCP_LPF_duration_and_MSD_unchanged=True,original_voiced_contour_preserved=False,AP_noise_power_factor=1.,
                 generated_median_hz=float(np.exp(np.median(out[1][voiced,0]))),waveform_pitch_verified=False,per_waveform_gain_rescue=False)
