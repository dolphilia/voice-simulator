"""共有HMMのMCP状態分布だけを交換し、源と時間制御の保護を検証する。"""
import ast, hashlib, json, os, subprocess, urllib.request
from pathlib import Path
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-acoustic-model-mechanism-20261008-v1'
NAME='hts-acoustic-model-mechanism-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
API='https://api.github.com/repos/mmdagent-ex/example/commits/main'
UPSTREAM='https://raw.githubusercontent.com/mmdagent-ex/example/{revision}/voice/mei/{name}'

C_SOURCE=r'''/* MCPのHMM状態平均・分散だけを交換する独自shim。MLPG前に全検証する。 */
#include "HTS_hidden.h"
#include <math.h>
#include <string.h>
static int ready(const HTS_Engine *e) {
 return e && e->sss.nstream==3 && e->sss.total_state && e->sss.sstream &&
  e->sss.duration && !e->pss.total_frame && !e->gss.total_frame;
}
int mcp_transfer(HTS_Engine *dst,const HTS_Engine *src) {
 if(!ready(dst)||!ready(src)||dst->sss.total_state!=src->sss.total_state||
    dst->sss.nstate!=src->sss.nstate)return 0;
 HTS_SStream *a=&dst->sss.sstream[0];const HTS_SStream *b=&src->sss.sstream[0];
 if(a->vector_length!=35||b->vector_length!=35||a->win_size!=3||b->win_size!=3||
    a->msd||b->msd||!a->mean||!a->vari||!b->mean||!b->vari)return 0;
 for(size_t w=0;w<3;w++) {
  if(a->win_l_width[w]!=b->win_l_width[w]||a->win_r_width[w]!=b->win_r_width[w])return 0;
  for(int j=a->win_l_width[w];j<=a->win_r_width[w];j++)
   if(a->win_coefficient[w][j]!=b->win_coefficient[w][j])return 0;
 }
 for(size_t i=0;i<dst->sss.total_state;i++)for(size_t v=0;v<105;v++)
  if(!isfinite(b->mean[i][v])||!isfinite(b->vari[i][v])||b->vari[i][v]<=0.)return 0;
 for(size_t i=0;i<dst->sss.total_state;i++) {
  memcpy(a->mean[i],b->mean[i],105*sizeof(double));
  memcpy(a->vari[i],b->vari[i],105*sizeof(double));
 }
 return 1;
}
size_t mcp_gv_count(const HTS_Engine *e) {
 if(!e||!e->sss.sstream||e->sss.nstream!=3)return 0;
 size_t n=0;
 for(size_t s=0;s<3;s++) {
  const HTS_SStream *p=&e->sss.sstream[s];n+=3;
  if(p->gv_mean)n+=p->vector_length;
  if(p->gv_vari)n+=p->vector_length;
  if(p->gv_switch)n+=e->sss.total_state;
 }
 return n;
}
int mcp_gv_copy(const HTS_Engine *e,double *out,size_t n) {
 if(!out||!n||n!=mcp_gv_count(e))return 0;
 size_t k=0;
 for(size_t s=0;s<3;s++) {
  const HTS_SStream *p=&e->sss.sstream[s];
  out[k++]=p->gv_mean!=NULL;out[k++]=p->gv_vari!=NULL;out[k++]=p->gv_switch!=NULL;
  if(p->gv_mean)for(size_t j=0;j<p->vector_length;j++)out[k++]=p->gv_mean[j];
  if(p->gv_vari)for(size_t j=0;j<p->vector_length;j++)out[k++]=p->gv_vari[j];
  if(p->gv_switch)for(size_t j=0;j<e->sss.total_state;j++)out[k++]=p->gv_switch[j];
 }
 return k==n;
}
'''

MODULE=r'''"""共有文脈HMMのMCP分布だけを交換する。波形や教師から係数を推定しない。"""
import ctypes as C
from pathlib import Path
import numpy as np
from timing_engine import Engine as NativeEngine
from hts_arrays import ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'mcp_model.dylib'))
_transfer=_lib.mcp_transfer;_transfer.restype=C.c_int;_transfer.argtypes=[C.c_void_p,C.c_void_p]
_count=_lib.mcp_gv_count;_count.restype=C.c_size_t;_count.argtypes=[C.c_void_p]
_copy=_lib.mcp_gv_copy;_copy.restype=C.c_int;_copy.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_size_t]
def gv(engine):
 n=_count(engine.pointer);assert n>0;x=np.empty(n);assert _copy(engine.pointer,x.ctypes.data_as(C.POINTER(C.c_double)),n);assert np.isfinite(x).all();return x
class Engine(NativeEngine):
 def transfer_mcp(self,donor):
  before=self.snapshot();variance=self.variance();protected_gv=gv(self);settings=self.get_settings()
  source=donor.snapshot();source_variance=donor.variance();source_gv=gv(donor);source_settings=donor.get_settings()
  if self.layout[0]!=(35,3) or self.layout!=donor.layout or self.count!=donor.count:raise ValueError('MCP状態・window互換性が不足')
  n=self.count*105
  if not _transfer(self.pointer,donor.pointer):raise ValueError('MLPG前のMCP分布交換を内部検査が拒否')
  after=self.snapshot();new_variance=self.variance()
  for key in ('duration','msd','layout'):assert before[key]==after[key]
  assert before['means'][1:]==after['means'][1:] and after['means'][0]==source['means'][0]
  assert np.array_equal(new_variance[:n],source_variance[:n]) and np.array_equal(new_variance[n:],variance[n:])
  assert np.array_equal(protected_gv,gv(self)) and self.get_settings()==settings
  assert donor.snapshot()==source and np.array_equal(donor.variance(),source_variance) and np.array_equal(gv(donor),source_gv) and donor.get_settings()==source_settings
  return dict(state_MCP_donor_exact=True,other_state_distributions_exact=True,duration_MSD_windows_exact=True,GV_and_settings_exact=True,donor_unmodified=True,
   before_MCP_mean_sha256=ah(before['means'][0]),after_MCP_mean_sha256=ah(after['means'][0]),before_MCP_variance_sha256=ah(variance[:n]),after_MCP_variance_sha256=ah(new_variance[:n]),
   donor_MCP_mean_sha256=ah(source['means'][0]),donor_MCP_variance_sha256=ah(source_variance[:n]),fixed_shared_HMM=True,neural_model=False,utterance_lookup=False)
def tests():
 assert not _transfer(None,None) and not _count(None) and not _copy(None,None,0)
 return dict(null_rejected=True,actual_render=0)
'''

FIXTURE=r'''"""元モデル恒等交換と別モデル交換の保護を全件確認する限定機構試験。"""
import sys,json,os,tempfile,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;bundle=here/'runtime-bundle';sys.path.insert(0,str(bundle))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from japanese_frontend import analyze
from acoustic_model import Engine,tests
from controls_v2 import transform
from shape_arrays import raw
from hts_arrays import ah
texts=['紫の船がゆっくり進む。','雨が降る。','切手を買った。','新しい地図を机に広げた。']
rows=[];tests()
for index,text in enumerate(texts):
 for speed,pitch in ((1.,220.),(1.15,280.)):
  row=analyze(text);tone=12*np.log2(pitch/220.);saved={};transfers={}
  for method in ('original','identity','happy_mcp'):
   with Engine(row,bundle/'mei_normal.htsvoice',speed=speed,half_tone=tone) as engine:
    original=engine.snapshot();settings=engine.get_settings()
    if method!='original':
     voice='mei_normal.htsvoice' if method=='identity' else 'mei_happy.htsvoice'
     with Engine(row,bundle/voice,speed=speed,half_tone=tone) as donor:transfers[method]=engine.transfer_mcp(donor)
    after=engine.snapshot();params=engine.parameters();converted,control,error,invariants=transform('calibrated',params,row['full_context_labels'],original['duration'],pitch)
    audio,source=raw(converted,settings,'native');assert np.isfinite(audio).all() and invariants
    assert engine.snapshot()==after
    saved[method]=dict(params=converted,audio=audio,source=source,duration=original['duration'])
  a=saved['original'];i=saved['identity'];z=saved['happy_mcp']
  assert all(np.array_equal(x,y) for x,y in zip(a['params'],i['params'])) and np.array_equal(a['audio'],i['audio'])
  assert all(np.array_equal(a['params'][k],z['params'][k]) for k in (1,2)) and a['duration']==z['duration']
  assert not np.array_equal(a['params'][0],z['params'][0]) and not np.array_equal(a['audio'],z['audio'])
  keys=('period','counter','event','original_excitation','processed_excitation')
  assert all(np.array_equal(a['source'][k],i['source'][k]) and np.array_equal(a['source'][k],z['source'][k]) for k in keys)
  assert transfers['identity']['before_MCP_mean_sha256']==transfers['identity']['after_MCP_mean_sha256']
  rows.append(dict(text=text,speed=speed,pitch=pitch,frames=len(a['params'][0]),original_wave_sha256=ah(a['audio']),identity_wave_sha256=ah(i['audio']),candidate_wave_sha256=ah(z['audio']),
   native_identity_byte_exact=True,LF0_LPF_duration_exact=True,all_source_clock_and_excitation_exact=True,MCP_and_wave_intentionally_changed=True,
   source_hashes={k:ah(a['source'][k]) for k in keys},transfers=transfers,passed=True))
assert len(rows)==8
print(json.dumps(dict(rows=rows,passed=True,render=24,dsp=72,limited_mechanism_only=True,real_Japanese_comparison_qualified=False,quality_certified=False),allow_nan=False))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    for n,h in contract.get('inherited_files',{}).items():assert digest(REPO/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    prior=ROOT/'campaigns/nas-hts-lattice-projection-20261008-v1'
    assert not read(prior/'aggregate-summary.json')['all_required_pass']
    ast.parse(MODULE);ast.parse(FIXTURE)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=16,audit=16,render=72,dsp=216,ai=0,teacher=0,train=0,inverse=0,download=20000000)
    reg=dict(campaign=NAME,question='共有HMMの文脈別MCP状態平均/分散を一つの別配布モデルへ交換し、元時間・源時計・LF0/LPF・GVを機械的に保持できるか。',
        candidate='公式Mei1.4 happyを一つに事前固定。angry/bashful/sadや同コホート係数探索をしない。',
        factor='同full-contextラベルからhappy共有HMMを評価したMCP state平均/分散105列だけをnativeへコピー。元duration/MSD/LF0/LPF/GV/window/settings/MLPG/vocoderを保持。',
        interpretation='全happy話者モデルを使う対比ではなく、normalの時間/源/GVを持つMCP emission分布交換。モデル学習は行わず非ニューラルHMM/MLPG。既存全極/FIR/warp/gain救済ではない。',
        resource=dict(repository='https://github.com/mmdagent-ex/example',revision_resolution=API,resolve_once_before_model_download=True,
            files=['COPYRIGHT.txt','README.txt','mei_normal.htsvoice','mei_happy.htsvoice'],license='公式voice/meiのCC BY 3.0表記を保存し、提供者/変更因子を帰属表示する。元ファイルは不改変。',
            copyright_url='https://github.com/mmdagent-ex/example/blob/main/voice/mei/COPYRIGHT.txt',README_url='https://github.com/mmdagent-ex/example/blob/main/voice/mei/README.txt'),
        fixture=dict(texts=['紫の船がゆっくり進む。','雨が降る。','切手を買った。','新しい地図を机に広げた。'],conditions=[[1.,220.],[1.15,280.]],
            native_identity_byte_exact=True,donor_state_distributions_exact=True,other_columns_GV_settings_exact=True,source_clock_and_excitation_exact=True,candidate_MCP_changes_required=True,null_rejected=True),
        thresholds='全8条件で恒等交換のparams/波形byte完全一致、別MCP交換の源時計/励振とLF0/LPF/duration完全一致。GV/他状態分布保持。有限出力。自然さ/内容/pitchの合格とはしない。',
        estimates=dict(render=24,dsp=72,conservative_download_reserved_bytes=8519680,asset_bytes_cap=8388608,metadata_bytes_cap=131072,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8),limits=limits,
        c_sha256=hashlib.sha256(C_SOURCE.encode()).hexdigest(),module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        inherited=dict(parent_seal_sha256=digest(PARENT/'artifact-seal.json'),prior_seal_sha256=digest(prior/'artifact-seal.json')),
        next='機構通過なら、未使用16文×2条件のnative/happy_MCPを全件生成前登録してE0/旧工学支持/二ASR/隔離を比較。未通過なら条件救済せず別の文脈/調音制御へ移る。',
        no_waveform_generated_yet=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','共有MCP分布交換とモデル取得の全費用を取得/出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'mcp_model.c',C_SOURCE.encode(),j);b.write(HERE/'acoustic_model.py',MODULE.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        inherited={}
        seal=read(PARENT/'artifact-seal.json')['files']
        for n in ('local_renderer.py','local_hts-v2.dylib','source_renderer.py','counter.dylib','timing_engine.py','timing.dylib','hts_arrays.py','hts_arrays.dylib','shape_arrays.py','shape.dylib','japanese_frontend.py','controls_v2.py','calibration.py','mei_normal.htsvoice','LICENSE-HTSVOICE','HTS-BSD-NOTICE.txt'):
            p=PARENT/'runtime-bundle'/n;assert digest(p)==seal[str(p.relative_to(REPO))];inherited[str(p.relative_to(REPO))]=digest(p)
        for n in ('HTS_hidden.h','HTS_engine.h'):p=BASE/'vendor'/n;inherited[str(p.relative_to(REPO))]=digest(p)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},inherited_files=inherited,controller_sha256=digest(Path(__file__)),no_download_or_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0094.json',dict(active_campaign=NAME,new_waveforms=0,new_download=0,next='登録push→固定revisionの公式4ファイル取得→MCP交換shim build→全8機構条件',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0,new_download=0),flush=True)

def get(url,maximum):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch','Accept':'application/vnd.github+json'}),timeout=45) as response:
        data=response.read(maximum+1);assert len(data)<=maximum;assert response.status==200
        return data,str(response.url)

def acquire():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'download','公式repositoryのrevisionをモデル取得前に一度固定',131072,2000000) as j:
        data,url=get(API,131072);info=json.loads(data);revision=info['sha'];assert len(revision)==40 and all(c in '0123456789abcdef' for c in revision)
        b.write(HERE/'revision-metadata.json',data,j);b.save(HERE/'revision-contract.json',dict(revision=revision,url=url,metadata_sha256=hashlib.sha256(data).hexdigest(),actual_download_bytes=len(data),conservative_charged_bytes=131072,selected_before_voice_download=True),j)
    revision=read(HERE/'revision-contract.json')['revision']
    with b.job(NAME,'download','固定revisionのMei happy/normalと利用条件を取得',8388608,20000000) as j:
        total=0;rows=[]
        for name in ('COPYRIGHT.txt','README.txt','mei_normal.htsvoice','mei_happy.htsvoice'):
            url=UPSTREAM.format(revision=revision,name=name);data,resolved=get(url,8388608-total);total+=len(data)
            if name.endswith('.txt'):
                assert b'Creative Commons Attribution 3.0' in data
                b.write(HERE/'upstream'/name,data,j)
            else:
                assert data.startswith(b'[GLOBAL]') and b'[DATA]' in data[:20000]
                b.write_data(HERE/'upstream'/name,data,j)
            rows.append(dict(name=name,url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        old=PARENT/'runtime-bundle/mei_normal.htsvoice'
        b.save(HERE/'resource-audit.json',dict(revision=revision,rows=rows,actual_download_bytes=total,conservative_charged_bytes=8388608,unused_reservations_not_returned=True,
            official_normal_matches_inherited=digest(HERE/'upstream/mei_normal.htsvoice')==digest(old),inherited_normal_sha256=digest(old),
            attribution='HTS Voice Mei v1.4, MMDAgent Project Team / Nagoya Institute of Technology, Department of Computer Science, Copyright 2009–2013.',
            license='Creative Commons Attribution 3.0',license_url='https://creativecommons.org/licenses/by/3.0/',changes='元配布ファイルは不改変。happyのMCP state平均/分散だけをnormalの生成状態へコピーする研究用派生。提供者の推奨を主張しない。',
            audio_or_neural_model_downloaded=False),j)
    print(dict(downloaded=total,revision=revision),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'source-contract.json');verify(contract)
    for row in read(HERE/'resource-audit.json')['rows']:assert digest(HERE/'upstream'/row['name'])==row['sha256']
    assert read(HERE/'resource-audit.json')['official_normal_matches_inherited']
    with b.job(NAME,'setup','MCP状態分布交換shim buildと共有モデル固定',reserve_bytes=30000000) as j:
        bundle=HERE/'runtime-bundle'
        for name in contract['inherited_files']:
            p=REPO/name
            if p.parent.name=='runtime-bundle':b.write(bundle/p.name,p.read_bytes(),j)
        b.write(bundle/'acoustic_model.py',MODULE.encode(),j)
        b.write_data(bundle/'mei_happy.htsvoice',(HERE/'upstream/mei_happy.htsvoice').read_bytes(),j)
        for n in ('COPYRIGHT.txt','README.txt'):b.write(bundle/('MEI-'+n),(HERE/'upstream'/n).read_bytes(),j)
        with b.workspace(j,'MCP shim build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',sdk,'-I'+str(BASE/'vendor'),str(HERE/'mcp_model.c'),'-o',str(bundle/'mcp_model.dylib')]
            with b.external_output(bundle/'mcp_model.dylib',100000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'mcp_model.c'),binary_sha256=digest(bundle/'mcp_model.dylib'),all_temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},no_neural_inference=True,no_utterance_lookup=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},inherited_files=contract['inherited_files'],controller_sha256=digest(Path(__file__)),no_waveform_generated_yet=True),j)
    print('固定共有モデルとMCP状態交換の実行契約を生成前に保存',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','全8機構条件の原/恒等交換/別MCP交換',24,20000000,expected_seconds=600)
    try:
        d=b.reserve(NAME,'dsp','全24MLPGと全8条件の状態/列/源/時計/恒等照合',72,2000000,expected_seconds=600)
        try:
            with b.workspace(r,'共有HMM機構試験の科学ライブラリ初期化',8000000,16000000) as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,capture_output=True,text=True,timeout=540)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','共有モデル交換の限定範囲・全費用・hash・一時回収を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['passed'] and len(fixture['rows'])==8
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,native_identity_exact=True,MCP_state_emissions_intended_factor=True,
            LF0_LPF_duration_GV_and_source_exact=True,real_Japanese_comparison_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# 共有HMMのMCP状態分布交換\n\n公式Mei v1.4 happy一つを事前固定し、同じfull-contextラベルのMCP状態平均/分散だけをnormalへ交換した。元の時間配分・LF0/LPF・GV・window・MLPG・vocoderは保持する。発話固有表・教師・ニューラル推論・波形からの係数推定は含まない。\n\n4文×2条件の機構試験で、元モデルへの恒等交換の列/波形完全一致、別MCPへの交換と源時計/励振・他状態分布・GVの完全保持を確認した。全24生成と72DSPを課した。比較音声の内容・自然さ・pitchの資格とはしない。\n\nHTS Voice Mei v1.4、MMDAgent Project Team、Nagoya Institute of Technology Department of Computer Science、Copyright 2009–2013。公式配布モデルは不改変、MCP分布交換が研究の変更因子。[公式配布](https://github.com/mmdagent-ex/example/tree/main/voice/mei)・[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)。提供者の推奨を主張しない。\n\n次は未使用16文×2条件のnative/happy_MCPを出力前登録して工学・二ASR・隔離を比較する。旧凍結/欠測を保持。日本語知覚資格なし・P5未開封・品質未達。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,unused_download_reservations_not_returned=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='acoustic-model-mechanism-completed',active_campaign=None,next='未使用16文native/happy_MCPの比較を出力前登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0095.json',dict(latest_completed=NAME,quality_goal_completed=False,next='新日本語64波形の共有MCP分布比較を登録',review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,mechanism_only=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','acquire','prepare','fixture']);a=p.parse_args();{'register':register,'acquire':acquire,'prepare':prepare,'fixture':run}[a.stage]()
