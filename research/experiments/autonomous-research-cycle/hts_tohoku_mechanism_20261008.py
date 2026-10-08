"""別の公開共有HMM全体の互換性を、候補選別や係数探索なしで確認する。"""
import ast,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-tohoku-mechanism-20261008-v1'
NAME='hts-tohoku-mechanism-v1'
PARENT=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
API='https://api.github.com/repos/icn-lab/htsvoice-tohoku-f01/commits/master'
UPSTREAM='https://raw.githubusercontent.com/icn-lab/htsvoice-tohoku-f01/{revision}/{name}'

WORKER=r'''"""共有HMM全モデルの状態・生成列・源と素の一次vocoderを照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;bundle=here/'runtime-bundle';sys.path.insert(0,str(bundle))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from japanese_frontend import analyze
from timing_engine import Engine
from controls_v2 import transform
from hts_arrays import synthesize as bare,ah,validated
from shape_arrays import synthesize as observed
texts=['紫の船がゆっくり進む。','雨が降る。','切手を買った。','新しい地図を机に広げた。']
rows=[]
for index,text in enumerate(texts):
 for speed,pitch in ((1.,220.),(1.15,280.)):
  row=analyze(text)
  for model,filename in (('mei','mei_normal.htsvoice'),('tohoku','tohoku-f01-neutral.htsvoice')):
   with Engine(row,bundle/filename,speed=speed,half_tone=12*np.log2(pitch/220.)) as engine:
    before=engine.snapshot();variance=engine.variance();settings=engine.get_settings()
    assert engine.layout[0]==(35,3) and engine.layout[1]==(1,3) and 1<=engine.layout[2][0]<=63 and engine.layout[2][0]%2
    native=engine.parameters();params,control,error,invariants=transform('calibrated',native,row['full_context_labels'],before['duration'],pitch)
    validated(params,settings);assert invariants and np.isfinite(params[0]).all()
    assert np.array_equal(params[0],native[0]) and np.array_equal(params[2],native[2])
    assert np.array_equal(params[1][:,0]>0,native[1][:,0]>0)
    voiced=params[1][:,0]>0;median=float(np.exp(np.median(params[1][voiced,0])));assert abs(median-pitch)<=1e-9
    assert engine.snapshot()==before and np.array_equal(engine.variance(),variance) and engine.get_settings()==settings
    a,ma=bare(params,settings);z,mz=observed(params,settings,'native')
    assert np.array_equal(a,z) and np.isfinite(z).all() and len(z)==len(params[0])*120
    assert mz['original_excitation_sha256']==mz['processed_excitation_sha256']
    rows.append(dict(text=text,speed=speed,pitch=pitch,model=model,frames=len(params[0]),layout=engine.layout,settings=settings,
     duration=before['duration'],native_parameter_hashes=[ah(v) for v in native],output_parameter_hashes=[ah(v) for v in params],
     original_HMM_states_unmodified=True,MCP_LPF_and_voicing_mask_preserved=True,relative_LF0_error=error,calibrated_LF0_median_hz=median,
     bare_observed_wave_byte_exact=True,wave_sha256=ah(z),source_clock_hashes=mz['source_clock_hashes'],original_excitation_sha256=mz['original_excitation_sha256'],finite_wave=True,passed=True))
assert len(rows)==16
print(json.dumps(dict(rows=rows,passed=True,render=32,dsp=80,models=['mei','tohoku'],full_model_factor=True,
 model_duration_MCP_LF0_LPF_GV_may_differ=True,acoustic_or_source_clock_identity_between_models_not_claimed=True,
 source_period_observation_is_not_perceived_pitch_truth=True,real_Japanese_comparison_qualified=False,quality_certified=False),allow_nan=False))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    for n,h in contract.get('inherited_files',{}).items():assert digest(REPO/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    previous=ROOT/'campaigns/nas-hts-acoustic-model-comparison-20261008-v1'
    assert not read(previous/'aggregate-summary.json')['research_protection_gates']['happy_mcp']
    ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=16,audit=16,render=96,dsp=240,ai=0,teacher=0,train=0,inverse=0,download=10000000)
    reg=dict(campaign=NAME,question='公開Tohoku-F01 neutralの共有HMM全体が既存非ニューラル生成の固定設定へ互換であり、制御と一次vocoderの対応を保持するか。',
        candidate='公式icn-lab/htsvoice-tohoku-f01 neutral一つに事前固定。別感情/style/共有係数/補間探索を行わない。',
        factor='全共有HMMを交換。文脈別MCP/LF0/LPF/duration/MSD/GVはモデル固有で、元Meiとの源時計や列一致を主張しない。辞書/labels、F0中央値制御、速度指定、MLPG/vocoder/gainを共通化する。',
        controls='各モデル内でMCP/LPF・duration/MSD/voicingと相対LF0を保持し、指定中央値220/280へ一様logF0補正。alpha.55/stage0/48k/240/原HTS/24k resample/12msfade/gain.25固定。',
        compatibility='同full-context label体系、5state/3stream/MCP35×window3/LF01×window3/奇数LPF≤63。元固定設定との不一致は停止し係数を合わせて救済しない。',
        resource=dict(repository='https://github.com/icn-lab/htsvoice-tohoku-f01',API=API,revision_resolved_once_before_model_download=True,files=['COPYRIGHT.txt','README.md','tohoku-f01-neutral.htsvoice'],license='Creative Commons Attribution 4.0',
            copyright_url='https://github.com/icn-lab/htsvoice-tohoku-f01/blob/master/COPYRIGHT.txt',license_url='https://creativecommons.org/licenses/by/4.0/'),
        fixture=dict(texts=['紫の船がゆっくり進む。','雨が降る。','切手を買った。','新しい地図を机に広げた。'],conditions=[[1.,220.],[1.15,280.]],models=['mei','tohoku'],all_16_required=True,
            bare_and_pure_observation_native_wave_byte_exact=True,model_states_unmodified=True,MCP_LPF_voicing_preserved=True,calibrated_LF0_median_abs_error_at_most=1e-9,finite_wave=True),
        estimates=dict(render=32,dsp=80,dsp_breakdown='16 MLPGと16条件×4の状態/制御/列/一次波形照合',conservative_download_reserved_bytes=4259840,asset_cap=4194304,metadata_cap=65536,
            temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),limits=limits,worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        source=dict(parent_seal_sha256=digest(PARENT/'artifact-seal.json'),previous_seal_sha256=digest(previous/'artifact-seal.json')),
        next='互換性/限定機構通過なら未使用16文×2条件のMei/Tohoku全モデル比較を登録。支持はnativeの音素indexで固定し、candidate固有の時間軸へ適用。未通過を同voice係数で救済しない。',
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,no_waveform_or_model_download_yet=True)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','別共有HMM全モデルの互換性・因子・取得/機構費用を事前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'worker.py',WORKER.encode(),j)
        seal=read(PARENT/'artifact-seal.json')['files'];inherited={}
        for n in ('local_renderer.py','local_hts-v2.dylib','source_renderer.py','counter.dylib','timing_engine.py','timing.dylib','hts_arrays.py','hts_arrays.dylib','shape_arrays.py','shape.dylib','japanese_frontend.py','controls_v2.py','calibration.py','mei_normal.htsvoice','LICENSE-HTSVOICE','HTS-BSD-NOTICE.txt'):
            p=PARENT/'runtime-bundle'/n;assert digest(p)==seal[str(p.relative_to(REPO))];inherited[str(p.relative_to(REPO))]=digest(p)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},inherited_files=inherited,controller_sha256=digest(Path(__file__)),no_download_or_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0098.json',dict(active_campaign=NAME,new_waveforms=0,new_download=0,next='登録push→公式neutralモデル取得/固定header互換性→一次vocoderと限定全モデル機構',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0,new_download=0),flush=True)

def get(url,maximum):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch','Accept':'application/vnd.github+json'}),timeout=45) as response:
        data=response.read(maximum+1);assert len(data)<=maximum and response.status==200
        return data,str(response.url)

def acquire():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'download','公式Tohokuのrevisionをモデル取得前に一度固定',65536,2000000) as j:
        data,url=get(API,65536);info=json.loads(data);revision=info['sha'];assert len(revision)==40 and all(c in '0123456789abcdef' for c in revision)
        b.write(HERE/'revision-metadata.json',data,j);b.save(HERE/'revision-contract.json',dict(revision=revision,url=url,actual_download_bytes=len(data),metadata_sha256=hashlib.sha256(data).hexdigest(),conservative_charged_bytes=65536),j)
    revision=read(HERE/'revision-contract.json')['revision']
    with b.job(NAME,'download','固定revisionのneutralモデルと利用条件だけ取得',4194304,20000000) as j:
        rows=[];total=0
        for name in ('COPYRIGHT.txt','README.md','tohoku-f01-neutral.htsvoice'):
            url=UPSTREAM.format(revision=revision,name=name);data,resolved=get(url,4194304-total);total+=len(data)
            if name.endswith('.htsvoice'):
                assert data.startswith(b'[GLOBAL]') and b'[DATA]' in data[:20000];b.write_data(HERE/'upstream'/name,data,j)
            else:
                assert b'Creative Commons' in data and b'4.0' in data;b.write(HERE/'upstream'/name,data,j)
            rows.append(dict(name=name,url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        raw=(HERE/'upstream/tohoku-f01-neutral.htsvoice').read_bytes();header=raw[:raw.index(b'[DATA]')].decode('ascii')
        b.save(HERE/'resource-audit.json',dict(revision=revision,rows=rows,actual_download_bytes=total,conservative_charged_bytes=4194304,unused_reservations_not_returned=True,header=header,
            attribution='HTS voice tohoku-f01, Copyright 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University.',
            license='Creative Commons Attribution 4.0',license_url='https://creativecommons.org/licenses/by/4.0/',changes='配布モデル不改変。研究生成では指定中央値への一様LF0制御と共通resample/fade/gainを適用。提供者の推奨を主張しない。',
            audio_or_neural_model_downloaded=False),j)
    print(dict(downloaded=total,revision=revision),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'source-contract.json');verify(contract)
    for row in read(HERE/'resource-audit.json')['rows']:assert digest(HERE/'upstream'/row['name'])==row['sha256']
    with b.job(NAME,'setup','固定Tohoku共有HMMと既存生成入口のbundleを構築',reserve_bytes=20000000) as j:
        bundle=HERE/'runtime-bundle'
        for n in contract['inherited_files']:p=REPO/n;b.write(bundle/p.name,p.read_bytes(),j)
        b.write_data(bundle/'tohoku-f01-neutral.htsvoice',(HERE/'upstream/tohoku-f01-neutral.htsvoice').read_bytes(),j)
        for name in ('COPYRIGHT.txt','README.md'):b.write(bundle/('TOHOKU-'+name),(HERE/'upstream'/name).read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},no_neural_inference=True,no_utterance_lookup=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},inherited_files=contract['inherited_files'],controller_sha256=digest(Path(__file__)),no_waveform_generated_yet=True),j)
    print('固定全モデルbundleを出力前に保存',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','全16モデル条件の素HTS/純粋観測生成',32,20000000,expected_seconds=600)
    try:
        d=b.reserve(NAME,'dsp','全16MLPGと全モデル条件の状態/制御/列/一次波形照合',80,2000000,expected_seconds=600)
        try:
            with b.workspace(r,'Tohoku共有HMM互換性の科学ライブラリ初期化',8000000,16000000) as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=540)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','別共有HMM全モデルの限定資格・費用・一時回収を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['passed'] and len(fixture['rows'])==16
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,full_model_factor=True,model_specific_states_and_streams_retained=True,bare_observation_wave_exact=True,
            source_clock_identity_between_models=False,real_Japanese_comparison_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# 公開Tohoku共有HMM全モデルの限定機構\n\nneutral一つを事前固定して取得し、全共有HMMをMeiと対比した。MCP/LF0/LPF/duration/MSD/GVはモデル固有で、二モデル間の源時計や音響列の一致を主張しない。辞書・ラベル、指定中央値への一様logF0制御、速度、MLPG/vocoder・48k/240/alpha.55、24k resample/12msfade/gain.25を共通化する。\n\n4文×2条件×2モデルの16機構条件で、状態保持・MCP/LPF/voicing保持・指定LF0中央値・有限性・素の一次HTSと純粋観測版の波形完全一致を確認した。32生成・80DSP。日本語内容/自然さ/pitchの資格ではない。\n\nHTS voice tohoku-f01、Copyright 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University。[公式配布](https://github.com/icn-lab/htsvoice-tohoku-f01)・[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。モデルは不改変、研究生成の一様LF0制御とresample/fade/gainを変更として表示する。提供者の推奨を主張しない。\n\n次は未使用日本語の全モデル比較を生成前登録する。nativeの音素index支持を固定し、candidate固有の時間軸へ適用する。旧凍結/欠測を保持。日本語知覚資格なし・P5未開封・品質未達。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,unused_download_reservations_not_returned=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='tohoku-mechanism-completed',active_campaign=None,next='未使用日本語のMei/Tohoku全モデル比較を出力前登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0099.json',dict(latest_completed=NAME,quality_goal_completed=False,next='新日本語全モデル64比較を事前登録',review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,mechanism_only=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','acquire','prepare','fixture']);a=p.parse_args();{'register':register,'acquire':acquire,'prepare':prepare,'fixture':run}[a.stage]()
