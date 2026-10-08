"""一次表の五母音共有形状と有限帯域LF駆動で独立声道の生成制御を検証する。"""
import argparse,ast,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-waveguide-vowel-mechanism-20261008-v1'
NAME='waveguide-vowel-mechanism-v1'
PREV=ROOT/'campaigns/nas-waveguide-tract-mechanism-20261008-v1'
LF=ROOT/'campaigns/nas-lf-source-mechanism-20261008-v1'
MEASURE=ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PDFPY=Path('/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
POPLER=Path('/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm')
SOURCES=[('arai-2007','https://splab.net/papers/2007/2007_01.pdf','pdf'),('arai-lab','https://splab.net/apd/g210/','html')]
# 原論文Table1の数値事実。index1は唇、16は声門。Web頁の異版で置換しない。
DIAM={'i':[24,14,12,10,10,10,16,24,32,32,32,32,32,32,12,12],
      'e':[24,22,22,20,18,16,16,18,24,28,30,30,30,30,12,12],
      'a':[32,28,30,34,38,38,34,30,26,20,14,12,16,26,12,12],
      'o':[14,22,26,32,38,38,34,28,22,16,14,16,22,30,12,12],
      'u':[16,14,20,22,24,26,22,14,18,26,30,30,30,30,12,12]}

PDF_WORKER=r'''"""原PDFのTable1を全80径で照合し、著者Web表の異版を別に記録する。"""
import sys,json,re,tempfile,os
from html.parser import HTMLParser
from pathlib import Path
from pypdf import PdfReader
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
here=Path(sys.argv[1]);expected=json.loads((here/'diameters.json').read_text());pdf=PdfReader(here/'upstream/arai-2007.pdf')
assert len(pdf.pages)==12
text=pdf.pages[3].extract_text(extraction_mode='layout')
rows={v:list(map(int,nums.split())) for v,nums in re.findall(r'/([ieaou])/\s+((?:\d+\s+){15}\d+)',text)}
assert rows==expected,(rows,expected)
class Table(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=='tr':self.row=[]
  if tag in ('td','th') and self.row is not None:self.cell=[]
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ('td','th') and self.cell is not None:self.row.append(''.join(self.cell).strip());self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
p=Table();p.feed((here/'upstream/arai-lab.html').read_text());lab={r[0].strip('/'):r[1:] for r in p.rows if r and r[0].strip('/') in expected}
assert set(lab)==set(expected) and all(len(r)==16 for r in lab.values())
different=[]
for v,row in lab.items():
 for index,(value,old) in enumerate(zip(row,expected[v]),1):
  if value!=str(old):different.append(dict(vowel=v,index_from_lips=index,paper_diameter_mm=old,lab_cell=value))
print(json.dumps(dict(passed=True,paper_pages=12,table_page_one_based=4,all_80_diameters_exact=True,glottis_is_index16=True,plate_length_mm=10,all_vowel_lengths_cm=16,lab_differences=different,paper_numeric_facts_selected_before_output=True,source_article_not_CC_license_claim=True,source_audio_or_figures_reused_as_generator=False)))
'''

MODULE=r'''"""五母音の共有径/面積、明示遷移、有限Fourier LF駆動。録音/学習/HMM/lookupなし。"""
import json,math,cmath
from pathlib import Path
import numpy as np
from scipy import signal
from waveguide_tract import render,ah
HERE=Path(__file__).resolve().parent
DIAM=json.loads((HERE/'diameters.json').read_text());COEF=json.loads((HERE/'coefficients.json').read_text())
FS=34300;OUTFS=24000;CUTOFF=8000.;GAIN=.10
AREA={v:np.pi*(np.array(d[::-1],dtype=float)/20.)**2 for v,d in DIAM.items()}
def coefficient(m):
 tp,te,ta,ep,a,e0,scale=map(float,COEF);w=math.pi/tp;omega=2*math.pi*m;length=1-te
 if m==0:return 0j
 z1=complex(a,w-omega);z2=complex(a,-w-omega)
 opened=e0*((cmath.exp(z1*te)-1.)/z1-(cmath.exp(z2*te)-1.)/z2)/(2j)
 returning=-(cmath.exp(-1j*omega*te)*(1.-cmath.exp(-complex(ep,omega)*length))/complex(ep,omega)
             -math.exp(-ep*length)*(cmath.exp(-1j*omega*te)-cmath.exp(-1j*omega))/(1j*omega))/(ep*ta)
 return scale*(opened+returning)
def driver(f0,samples):
 if not math.isfinite(f0) or not 70<=f0<=400 or not 1<=samples<=96000:raise ValueError('F0/標本数が登録範囲外')
 phase=(np.arange(samples,dtype=float)*f0/FS+.125)%1.;x=np.zeros(samples);harmonics=math.floor(CUTOFF/f0)
 for m in range(1,harmonics+1):x+=2.*np.real(coefficient(m)*np.exp(2j*np.pi*m*phase))
 return x,dict(f0=f0,phase_start=.125,harmonics=harmonics,maximum_source_harmonic_hz=harmonics*f0,continuous_LF_scale_fixed=True,truncation_RMS_renormalized=False)
def areas(first,second=None,samples=20580):
 if first not in AREA or second is not None and second not in AREA:raise ValueError('登録外の母音')
 if second is None:return np.tile(AREA[first],(samples,1))
 t=np.arange(samples)/FS;q=np.clip((t-.20)/.10,0.,1.);s=q*q*(3.-2.*q)
 return (1.-s[:,None])*AREA[first]+s[:,None]*AREA[second]
def output(raw):
 y=signal.resample_poly(raw,240,343,window=('kaiser',5.))*GAIN
 n=min(round(.012*OUTFS),len(y)//2);fade=np.sin(np.linspace(0,np.pi/2,n))**2;y[:n]*=fade;y[-n:]*=fade[::-1]
 return y
def generate(first,f0=220,second=None):
 x,source=driver(f0,20580);a=areas(first,second);before=(ah(x),ah(a));y,e=render(x,a)
 assert before==(ah(x),ah(a));audio=output(y)
 return audio,dict(source=source,geometry=dict(first=first,second=second,source_fs=FS,section_length_cm=1.,sections=16,length_cm=16.,area_sha256=ah(a)),driver_sha256=ah(x),raw_sha256=ah(y),normalized_energy_max=float(e.max()),shared_gain=GAIN,per_waveform_gain=False,recorded_audio=False,neural_inference=False),y,x,a
'''

WORKER=r'''"""共有母音生成と全方向遷移の独立数値、固定区間DIO/ACF、保存音声E0を検査。"""
import sys,json,math,tempfile,os,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;work=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
contract=json.loads((here/'measurement-package-contract.json').read_text());repo=here.parents[4]
for n,h in contract['files'].items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(repo/'research/experiments/autonomous-research-cycle/campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'))
import numpy as np
import pyworld
from scipy.integrate import quad
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0
from vowel_tract import generate,coefficient,COEF,AREA,FS,OUTFS,output
from waveguide_tract import render,ah
def scalar(t):
 tp,te,ta,ep,a,e0,scale=map(float,COEF)
 return scale*(e0*math.exp(a*t)*math.sin(math.pi*t/tp) if t<=te else -(math.exp(-ep*(t-te))-math.exp(-ep*(1-te)))/(ep*ta))
fourier=[]
for m in (1,3,7,30,72):
 real=sum(quad(lambda t:scalar(t)*math.cos(2*math.pi*m*t),lo,hi,epsabs=2e-12,epsrel=2e-12)[0] for lo,hi in [(0.,.6),(.6,1.)])
 imag=sum(quad(lambda t:-scalar(t)*math.sin(2*math.pi*m*t),lo,hi,epsabs=2e-12,epsrel=2e-12)[0] for lo,hi in [(0.,.6),(.6,1.)])
 error=abs(coefficient(m)-complex(real,imag));assert error<=3e-11
 fourier.append(dict(harmonic=m,independent_complex_error=error))
def pressure_reference(x,A):
 n=len(A);r=np.zeros(n);l=np.zeros(n);out=[]
 for drive in x:
  out.append(.15*r[-1]*math.sqrt(A[-1]));nr=np.empty(n);nl=np.empty(n);nr[0]=drive/math.sqrt(A[0])+.75*l[0];nl[-1]=-.85*r[-1]
  for j in range(n-1):
   R1=1./A[j];R2=1./A[j+1];k=(R2-R1)/(R1+R2);nr[j+1]=(1.+k)*r[j]-k*l[j+1];nl[j]=k*r[j]+(1.-k)*l[j+1]
  r=nr;l=nl
 return np.array(out)
def normalized_reference(x,areas):
 n=areas.shape[1];r=[0.]*n;l=[0.]*n;out=[]
 for at,drive in enumerate(x):
  out.append(.15*r[-1]);nr=[0.]*n;nl=[0.]*n;nr[0]=drive+.75*l[0];nl[-1]=-.85*r[-1]
  for j in range(n-1):
   k=(float(areas[at,j])-float(areas[at,j+1]))/(float(areas[at,j])+float(areas[at,j+1]));theta=math.asin(k)
   nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl
 return np.array(out)
def observe(audio,f0):
 f,t=pyworld.dio(audio.astype(float),OUTFS,f0_floor=70.,f0_ceil=800.,frame_period=5.);f=pyworld.stonemask(audio.astype(float),f,t,OUTFS)
 intervals=[]
 for lo,hi in ((.10,.25),(.25,.40),(.40,.55)):
  sel=(t>=lo)&(t<hi);valid=f[sel & (f>=70)&(f<=800)];complete=len(valid)>=3 and len(valid)>=sel.sum()*.5
  median=float(np.median(valid)) if len(valid) else None;distance=abs(12*math.log2(median/f0)) if median else None
  intervals.append(dict(bounds=[lo,hi],frames=int(sel.sum()),voiced_frames=len(valid),median_hz=median,complete=bool(complete),distance_semitones=distance))
 hz,confidence=estimate_f0(audio[2400:13200],OUTFS,minimum=70,maximum=800);allpositive=f[f>0];dio=float(np.median(allpositive)) if len(allpositive) else None
 de=abs(12*math.log2(dio/f0)) if dio else None;ae=abs(12*math.log2(hz/f0)) if hz else None
 passed=bool(de is not None and ae is not None and de<=1. and ae<=1. and confidence>=.6 and all(r['complete'] for r in intervals))
 return dict(passed=passed,dio_hz=dio,acf_hz=hz,acf_confidence=confidence,dio_error_semitones=de,acf_error_semitones=ae,predefined_support=intervals,missing=sum(not r['complete'] for r in intervals),waveform_metrics_not_naturalness=True)
def save(id,audio,meta):
 path=work/(id+'.wav');wavfile.write(path,OUTFS,audio.astype(np.float32));fs,saved=wavfile.read(path);assert fs==OUTFS and len(saved)==14400
 e0=evaluate(saved,dict(kind='vowel',f0_hz=meta['source']['f0'],expected_duration_seconds=.6),fs);p=observe(saved,meta['source']['f0'])
 return dict(id=id,wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),E0=e0,pitch=p,metadata=meta)
static=[];stored={};source_hashes={};calls=0
for v in ('a','i','u','e','o'):
 for f0 in (110,220,280):
  audio,meta,raw,x,area=generate(v,f0);reference=pressure_reference(x,AREA[v]);calls+=2
  error=float(np.max(np.abs(raw-reference)));assert error<=1e-10
  if f0 in source_hashes:assert source_hashes[f0]==meta['driver_sha256']
  else:source_hashes[f0]=meta['driver_sha256']
  row=save(f'{v}-{f0}',audio,meta);row['independent_pressure_error']=error;static.append(row)
  if f0==220:
   repeat=generate(v,f0);calls+=1;assert np.array_equal(audio,repeat[0]) and np.array_equal(raw,repeat[2]);stored[v]=raw
transition=[]
for first in ('a','i','u','e','o'):
 for second in ('a','i','u','e','o'):
  if first==second:continue
  audio,meta,raw,x,area=generate(first,220,second);reference=normalized_reference(x,area);calls+=2
  error=float(np.max(np.abs(raw-reference)));assert error<=1e-10
  assert meta['driver_sha256']==source_hashes[220] and np.array_equal(raw[:6860],stored[first][:6860])
  tail=float(np.max(np.abs(raw[17150:]-stored[second][17150:])));assert tail<=1e-7
  row=save(f'{first}-to-{second}',audio,meta);row.update(independent_normalized_error=error,initial_raw_prefix_exact=True,final_static_tail_max_error=tail);transition.append(row)
assert len(static)==15 and len(transition)==20 and calls==75
print(json.dumps(dict(mechanism_passed=True,rows=static,transitions=transition,independent_Fourier_rows=fourier,actual_valid_generation_or_reference_calls=calls,charged_render=160,charged_DSP=800,
 static_E0_pass=sum(x['E0']['E0_pass'] for x in static),static_pitch_pass=sum(x['pitch']['passed'] for x in static),static_missing=sum(x['pitch']['missing'] for x in static),static_fixed_intervals=45,
 transition_E0_pass=sum(x['E0']['E0_pass'] for x in transition),transition_pitch_pass=sum(x['pitch']['passed'] for x in transition),transition_missing=sum(x['pitch']['missing'] for x in transition),transition_fixed_intervals=60,
 all_static_source_hashes_shared=True,deterministic_repeat_exact=True,coarse_plate_shape_not_modern_MRI_truth=True,normalized_moving_wall_work_not_modeled=True,geometry_labels_not_independent_perceptual_identification=True,
 full_Japanese_content_qualified=False,perceptual_qualification=False,quality_goal_completed=False)))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert read(PREV/'aggregate-summary.json')['mechanical_fixture_passed'];review=read(ROOT/'campaigns/nas-long-horizon-review-20261008-v6/decision.json');assert review['scientific_completed']==36
    for source in (MODULE,WORKER,PDF_WORKER):ast.parse(source)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=20,audit=20,render=480,dsp=2400,download=3000000,ai=0,teacher=0,train=0,inverse=0)
    reg=dict(campaign=NAME,question=review['next_question'],diameters_from_lips_mm=DIAM,primary_table='Arai2007 Table1 p193 / PDF page4; index1 lips,16 glottis; plates10mm',
        primary_sources=SOURCES,shape_scope='Chiba/Kajiyamaの測定を粗い16径へ近似した管模型。現代MRI/全話者/現生理正解ではない。論文表と著者頁の異版を混合しない。',
        factor='5共有母音の径→π(d/20)^2 cm2→独立二方向正規化波。全20有向遷移は.20-.30秒に面積をcubic smoothstepで補間。',
        source=dict(fixed_LF_coefficients=read(LF/'fixture-audit.json')['coefficients'],source_cutoff_hz=8000,Fourier_complex_coefficients='固定LF式の区分積分から解析計算、独立quad照合',dc_harmonic=0,phase_start=.125,F0_static=[110,220,280],F0_transition=220,source_scale='旧固定連続RMS1の尺度。有限harmonicごとに再正規化しない。'),
        fixed=dict(source_fs=34300,output_fs=24000,sections=16,section_length_cm=1.,length_cm=16.,glottal_reflection=.75,lip_reflection=-.85,gain=.10,duration=.6,fade_ms=12,resample_poly_ratio=[240,343],resample_window=['kaiser',5.]),
        fixture=dict(static=15,transitions=20,deterministic_repeats=5,independent_refs=35,charged_render=160,charged_DSP=800,all_support_intervals=[[.10,.25],[.25,.40],[.40,.55]],candidate_selected_support=False),
        thresholds=dict(independent_wave_error=1e-10,independent_Fourier_error=3e-11,initial_raw_prefix_exact=True,final_static_tail_error=1e-7,E0='原evaluateの全条件変更なし',pitch='DIO/ACF±1半音,confidence≥.6,事前3区間各3以上/半数以上支持、全件分母。指令列をpitch正解観測と扱わない。'),
        gates='機構数値と工程pitch/E0を分離。工学不通過でも欠測を隠さず封印し、形状/gain/終端反射を同コホートで救済しない。内容/母音知覚/日本語自然さは未資格。',
        runtime_references=dict(waveguide_seal=digest(PREV/'artifact-seal.json'),LF_seal=digest(LF/'artifact-seal.json'),review6=digest(ROOT/'campaigns/nas-long-horizon-review-20261008-v6/decision.json'),acoustics=digest(MEASURE/'runtime-bundle/acoustics.py'),measurement_packages=digest(MEASURE/'measurement-package-contract.json')),
        scientific_outputs_before_registration=0,no_HMM=True,no_teacher=True,no_training=True,no_inverse=True,no_audio_download=True,no_utterance_lookup=True,
        estimates=dict(download_conservative=2000000,maximum_seconds=6000,temporary_peak=32000000,temporary_write=64000000,RAM_gb=8,render=160,DSP=800),limits=limits,controller_sha256=digest(Path(__file__)),
        all_prior_frozen_routes_kept=True,protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,
        next='全件の母音/遷移工学結果を封印。出力後の径/終端/gain救済なし。通過なら生成入口の通常/隔離/CLIと有限日本語音素列を別登録。未通過なら形状/放射/損失/子音機構の独立不足を次の問いへ。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','共有5形状・源・全有向遷移・全工学分母を生成前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'diameters.json',DIAM,j);b.save(HERE/'coefficients.json',reg['source']['fixed_LF_coefficients'],j)
        b.write(HERE/'vowel_tract.py',MODULE.encode(),j);b.write(HERE/'worker.py',WORKER.encode(),j);b.write(HERE/'pdf_audit.py',PDF_WORKER.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0118.json',dict(active_campaign=NAME,next='登録push→一次PDFと著者HTML保存/数値差異→PDF頁目視→有限帯域源/共有声道固定',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'download','公開一次PDFと著者管径頁の限定保存',2000000,4000000) as j:
        rows=[]
        for name,url,suffix in SOURCES:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch/1.0'}),timeout=45) as response:data=response.read(1000001);resolved=str(response.url)
            assert len(data)<=1000000
            b.write_data(HERE/'upstream'/f'{name}.{suffix}',data,j);rows.append(dict(id=name,url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        b.save(HERE/'primary-source-audit.json',dict(rows=rows,download_charged=2000000,unused_reservation_not_returned=True,third_party_code_or_audio_downloaded=False),j)
    with b.job(NAME,'setup','PDF全80径/著者頁異版を照合し、原PDF頁を外部一時領域で描画',reserve_bytes=40000000) as j:
        with b.workspace(j,'一次PDF数値照合と第4頁目視用描画',24000000,48000000) as (work,env):
            out=subprocess.run([str(PDFPY),'-B',str(HERE/'pdf_audit.py'),str(HERE)],env=env,capture_output=True,text=True,check=True,timeout=90);audit=json.loads(out.stdout)
            subprocess.run([str(POPLER),'-f','4','-l','4','-r','120','-singlefile','-png',str(HERE/'upstream/arai-2007.pdf'),str(work/'table-page')],env=env,capture_output=True,check=True,timeout=90)
            b.write_data(HERE/'source-table-page.png',(work/'table-page.png').read_bytes(),j)
        b.save(HERE/'numeric-table-audit.json',audit,j)
        bundle=HERE/'runtime-bundle'
        for name in ('waveguide_tract.py','waveguide_tract.dylib'):b.write(bundle/name,(PREV/'runtime-bundle'/name).read_bytes(),j)
        for name in ('diameters.json','coefficients.json','vowel_tract.py'):b.write(bundle/name,(HERE/name).read_bytes(),j)
        b.write(bundle/'acoustics.py',(MEASURE/'runtime-bundle/acoustics.py').read_bytes(),j);b.save(HERE/'measurement-package-contract.json',read(MEASURE/'measurement-package-contract.json'),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,audio_lookup=False),j)
    print('原PDF全80径照合・異版記録・目視頁保存、出力まだなし',flush=True)

def visual():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and read(HERE/'numeric-table-audit.json')['all_80_diameters_exact']
    with b.job(NAME,'audit','原PDF第4頁を目視し径の方向・単位・80値と抽出を照合',reserve_bytes=2000000) as j:
        b.save(HERE/'visual-table-audit.json',dict(rendered_page_sha256=digest(HERE/'source-table-page.png'),source_pdf_sha256=digest(HERE/'upstream/arai-2007.pdf'),inspected_page=4,all_80_diameters_visually_checked=True,index_from_lips=True,unit_mm=True,plate_length_mm=10,not_inferred_from_Web_variant=True,new_scientific_waveforms=0),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    print('一次表の目視と実行入口を出力前固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','共有五母音15と全20有向遷移・独立参照・再現生成',160,100000000,expected_seconds=1200)
    try:
        d=b.reserve(NAME,'dsp','独立Fourier/声道/因果前半/静的tailと全E0/固定DIO/ACF',800,2000000,expected_seconds=1200)
        try:
            with b.workspace(r,'共有母音と全遷移の科学cache/保存波形専用',32000000,64000000) as (work,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py'),str(work)],env=env,check=True,capture_output=True,text=True,timeout=1080)
                fixture=json.loads(out.stdout);manifest=[]
                for p in sorted(work.glob('*.wav')):
                    target=HERE/'render'/p.name;b.write_data(target,p.read_bytes(),r);manifest.append(dict(path=str(target.relative_to(REPO)),sha256=digest(target)))
                assert len(manifest)==35;b.save(HERE/'render-manifest.json',dict(rows=manifest,output_waves=35,actual_generation_or_reference_calls=fixture['actual_valid_generation_or_reference_calls'],charged_render=160),d);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','共有母音/全遷移の全分母・限定資格・費用と一時不存在を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['mechanism_passed']
        engineering=fixture['static_E0_pass']==15 and fixture['static_pitch_pass']==15 and fixture['static_missing']==0 and fixture['transition_E0_pass']==20 and fixture['transition_pitch_pass']==20 and fixture['transition_missing']==0
        result={k:fixture[k] for k in ('static_E0_pass','static_pitch_pass','static_missing','static_fixed_intervals','transition_E0_pass','transition_pitch_pass','transition_missing','transition_fixed_intervals')}
        result.update(mechanism_passed=True,engineering_all_required_pass=engineering,static_total=15,transition_total=20,shared_source=True,coarse_plate_shape_not_modern_MRI_truth=True,geometry_labels_not_independent_perceptual_identification=True,full_Japanese_content_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next'])
        b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 一次表の共有五母音形状と有限帯域駆動','','Arai2007 Table1の80径をPDF抽出/原頁目視で照合し、著者Web頁の異版と混合しなかった。16個の1cm区間を声門→唇の面積へ変換。形状はChiba/Kajiyama測定の粗い管模型であり現代MRI/現生理の正解ではない。','',
            '固定LFの解析Fourier係数を独立quadで確認し、8000Hz以下のharmonicだけを全形状共通で生成する。連続LF尺度は固定し、F0別や波形別RMS/利得を合わせない。源34300Hz/出力24000Hz、終端.75/-.85、共有gain.10、.6秒/12ms fade。保存/学習/HMM/音声lookupなし。','',
            '5母音×F0 110/220/280の15波と全20有向遷移を生成。静的圧力波/動的回転の独立計算、入力不変、最初.20秒のraw前半、最後.10秒の静的tail、5回のbyte一致を確認。位相連続の共有源のまま面積を.20-.30秒にsmoothstepで変える。','',
            f'工学: 静的E0 {result["static_E0_pass"]}/15、pitch {result["static_pitch_pass"]}/15、支持欠測 {result["static_missing"]}/45。遷移E0 {result["transition_E0_pass"]}/20、pitch {result["transition_pitch_pass"]}/20、欠測 {result["transition_missing"]}/60。事前3区間の全分母と原E0/DIO/ACF閾値を保持。全要求通過: {engineering}。','',
            '母音ラベルは形状制御のラベルで、独立した聞き取り正解ではない。放射/損失/移動壁の仕事/鼻腔/閉鎖/子音、実発話の内容、日本語自然さを資格付けない。工程が不通過でも同形状/gain/終端で救済しない。160生成/800DSPの保守的費用を返金しない。','',
            '[Arai2007一次論文](https://splab.net/papers/2007/2007_01.pdf)と[著者頁の異版](https://splab.net/apd/g210/)。一次PDF/原頁画像は外部媒体の参照実体で、Gitに全文/図表を再配布しない。','',result['next'],'','旧全凍結・知覚資格なし・P5未開封・品質未達を保持。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='waveguide-vowel-mechanism-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0119.json',dict(latest_completed=NAME,next=result['next'],quality_goal_completed=False,budget=b.reconcile()))
    print(dict(mechanism_passed=True,engineering_all_required_pass=engineering,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','visual','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'visual':visual,'fixture':run}[a.stage]()
