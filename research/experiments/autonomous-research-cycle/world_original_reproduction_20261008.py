"""第31回：観測hookを外した一次WORLDとインストール済み原関数の再現差。"""
from contextlib import contextmanager
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];NAME='world-original-reproduction-v1'
HERE=ROOT/'campaigns/nas-world-original-reproduction-20261008-v1'
OLD=ROOT/'campaigns/nas-world-excitation-audit-20261008-v1'
PRIMARY=ROOT/'campaigns/nas-world-control-20261004-v1/upstream'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
CONVERT=ROOT/'campaigns/nas-mcp-postfilter-20261008-v1/runtime-bundle'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

CPP='''// 一次synthesis.cppの処理を変更せず、公開名だけを衝突防止のため変更する。
#define Synthesis ArcBareSynthesisV1
#include "synthesis.cpp"
#undef Synthesis
extern "C" int BareRun(const double *f0,int n,const double * const *sp,const double * const *ap,
 int fft,double frame,int fs,int length,double *wave) {
 ArcBareSynthesisV1(f0,n,sp,ap,fft,frame,fs,length,wave);
 return 1;
}
'''

WORKER=r'''"""保存済みパラメータを同じ変換で渡し、波形hashと演算差を診断する。"""
from pathlib import Path
import os,sys,io,json,hashlib,ctypes as C,argparse,sysconfig
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
CONVERT=ROOT/'campaigns/nas-mcp-postfilter-20261008-v1/runtime-bundle'
def load():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(PERIOD/'runtime-bundle/packages-v2'),str(CONVERT)]
    import numpy as np
    from scipy import signal
    from scipy.io import wavfile
    import pyworld,world_renderer2 as world
    installed=C.CDLL(str(pyworld.pyworld.__file__),mode=C.RTLD_GLOBAL)
    bare=C.CDLL(str(HERE/'original.dylib'))
    args=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p,C.c_int,C.c_double,C.c_int,C.c_int,C.c_void_p]
    installed.Synthesis.argtypes=args;installed.Synthesis.restype=None
    bare.BareRun.argtypes=args;bare.BareRun.restype=C.c_int
    return np,signal,wavfile,world,installed,bare,pyworld
def evaluate(item,lib,compat=False):
    np,signal,wavfile,world,installed,bare,pyworld=lib
    for k in ('record','parameters','wave'):assert digest(REPO/item[k])==item[k+'_sha256']
    meta=read(REPO/item['record'])['meta']
    with np.load(REPO/item['parameters']) as a:params=[a[k].copy() for k in ('mcp','lf0','lpf')]
    (f0,sp,ap),_=world.convert(params);expected=meta['conversion'];factor=float(expected.get('AP_noise_power_factor',1.))
    assert factor in (1.,.5)
    if factor!=1.:
        assert world.ah(ap)==expected['AP_before_sha256'];ap=ap.copy();ap[f0>0]*=np.sqrt(factor);np.clip(ap,.001,1.,out=ap)
    for name,value in [('f0',f0),('power',sp),('AP',ap)]:assert world.ah(value)==expected[name+'_sha256']
    hashes=[world.ah(x) for x in (f0,sp,ap)]
    pointers=lambda a:np.asarray(a.ctypes.data+np.arange(len(a),dtype=np.uintp)*a.strides[0],dtype=np.uintp)
    spp=pointers(sp);app=pointers(ap);addr=lambda a:C.c_void_p(a.ctypes.data)
    length=len(f0)*240;direct=np.zeros(length);raw=np.zeros(length)
    common=(addr(f0),len(f0),addr(spp),addr(app),4096,5.,48000,length)
    installed.Synthesis(*common,addr(direct));assert bare.BareRun(*common,addr(raw))==1
    assert hashes==[world.ah(x) for x in (f0,sp,ap)] and np.isfinite(raw).all() and np.isfinite(direct).all()
    baseline=world.pw.synthesize(f0,sp,ap,48000,frame_period=5.) if compat else None
    if compat:assert len(baseline)==length
    kept=len(params[0])*240
    def finish(x):
        a=signal.resample_poly(x[:kept],1,2);fade=min(round(.012*24000),len(a)//2);env=np.sin(np.linspace(0,np.pi/2,fade))**2
        a[:fade]*=env;a[-fade:]*=env[::-1];a=(a*meta['output_gain']).astype(np.float32)
        buf=io.BytesIO();wavfile.write(buf,24000,a)
        return a,hashlib.sha256(buf.getvalue()).hexdigest()
    final,hash_bare=finish(raw);direct_audio,hash_direct=finish(direct)
    rate,old=wavfile.read(REPO/item['wave']);assert rate==24000
    difference=raw-direct;changed=np.flatnonzero(difference!=0);final_changed=np.flatnonzero(final!=old)
    result=dict(id=item['id'],cohort=item['cohort'],condition=item['condition'],method=item['method'],
        record_sha256=item['record_sha256'],input_conversion_hashes_exact=True,input_arrays_unchanged=True,
        old_wave_sha256=item['wave_sha256'],bare_wave_sha256=hash_bare,direct_wave_sha256=hash_direct,
        direct_old_exact=hash_direct==item['wave_sha256'],bare_old_exact=hash_bare==item['wave_sha256'],
        bare_direct_raw_exact=np.array_equal(raw,direct),raw_different_samples=len(changed),
        raw_max_abs_diff=float(np.max(abs(difference))),raw_first_indices=changed[:64].tolist(),
        raw_changed_within_kept=int((changed<kept).sum()),raw_changed_after_kept=int((changed>=kept).sum()),
        final_different_samples=len(final_changed),final_max_abs_diff=float(np.max(abs(final-old))),
        final_first_indices=final_changed[:64].tolist(),
        raw_sha256=world.ah(raw),direct_raw_sha256=world.ah(direct),
        recompilation_context_is_an_experimental_factor=True,no_observer_hooks=True,
        no_actual_excitation_trace_collected=True,old_WORLD_source_still_unknown=True,
        old_gates_and_ASR_unchanged=True,quality_goal_completed=False)
    if compat:
        base,hash_base=finish(baseline);result.update(binding_old_exact=hash_base==item['wave_sha256'],
            installed_C_and_binding_raw_exact=np.array_equal(direct,baseline),binding_wave_sha256=hash_base)
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('compat','batch'));p.add_argument('--begin',type=int,default=0);p.add_argument('--end',type=int,default=0);p.add_argument('--job',required=True);a=p.parse_args()
    contract=read(HERE/'execution-contract.json')
    assert digest(HERE/'registration.json')==contract['registration_sha256'] and digest(HERE/'protocol.json')==contract['protocol_sha256']
    for name,h in contract['source_hashes'].items():assert digest(HERE/name)==h,name
    for name,h in contract['input_hashes'].items():assert digest(REPO/name)==h,name
    lib=load();b=Budget();protocol=read(HERE/'protocol.json');results=[]
    records=[protocol['records'][i] for i in protocol['compat_indices']] if a.stage=='compat' else protocol['records'][a.begin:a.end]
    for item in records:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if a.stage=='batch' and target.exists():
            saved=read(target);assert saved['record_sha256']==item['record_sha256'] and saved['bare_old_exact'] and saved['direct_old_exact'];results.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        result=evaluate(item,lib,a.stage=='compat')
        if a.stage=='compat':results.append(result)
        else:
            assert result['bare_old_exact'] and result['direct_old_exact'],'未観測原実装の旧波形完全一致が不通過'
            b.write_data(target,encode(result),a.job);results.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
    if a.stage=='compat':
        result=dict(rows=results,expected=4,all_original_bare_old_exact=all(x['bare_old_exact'] for x in results),
            all_installed_C_and_binding_old_exact=all(x['direct_old_exact'] and x['binding_old_exact'] and x['installed_C_and_binding_raw_exact'] for x in results),
            execution_environment=dict(python=sys.version,numpy=lib[0].__version__,pyworld_binary=str(lib[6].pyworld.__file__),pyworld_sha256=digest(lib[6].pyworld.__file__),python_CFLAGS=sysconfig.get_config_var('CFLAGS'),
            original_wheel_compile_flags_not_assumed=True),source_truth_qualification=False,quality_goal_completed=False)
        b.save(HERE/'compatibility-audit.json',result,a.job)
    else:b.save(HERE/'batches'/(f'{a.begin:03d}-{a.end:03d}.json'),dict(rows=results,expected=len(records),all_old_wave_exact=True),a.job)
    print('原WORLD対照',a.stage,a.begin,a.end,len(results),flush=True)
if __name__=='__main__':main()
'''


@contextmanager
def job(b,kind,label,count,reserve_bytes,seconds):
    token=b.reserve(NAME,kind,label,count,reserve_bytes,expected_seconds=seconds)
    try:yield token
    except BaseException as e:b.finish(token,repr(e));raise
    else:b.finish(token)


def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and NAME not in b.snapshot()['campaigns']
    ast.parse(WORKER);protocol=read(OLD/'protocol.json');assert len(protocol['records'])==768
    limits=dict(seconds=14400,bytes=1200000000,write_bytes=1800000000,render=3000,dsp=12000,ai=0,teacher=0,train=0,inverse=0,download=0,setup=40,audit=60)
    reg=dict(campaign=NAME,status='registered_before_output',question='observerなしの一次synthesis.cppは旧WAVを再現できるか。インストール済みC直呼び/PyWORLD bindingを対照に観測buildと演算環境の影響を分離する。',
        causal_factors=['旧observerと同じO2/SDKで観測hookを全部外した原実装','installed SynthesisのC ABI直呼び対binding（固定4例）'],
        limitations='公開名/呼出ABI/build contextも差の要因に含む。元wheelの実compile flagsはPython CFLAGSから断定しない。旧768件の励振truthをこの再構成で埋めない。',
        source_commit='8d79b88b7dd92e8a132996cf74080b2d6f881b98',source_sha256=digest(PRIMARY/'synthesis.cpp'),
        input='前回の全WORLD768登録入力。固定compat4例をそのまま引継ぐ。4例完全一致の場合だけ全768へ進む。',
        split='全6コホートを各native対照で保持。新入力選別/P5本文読取なし。',
        gates=dict(compat4_all_byte_exact=True,installed_C_binding_raw_exact=True,all768_bare_and_direct_old_byte_exact=True),
        missing='不通過なら全768の旧実励振unknownと欠測155を保持。全件を一部例で資格化しない。',
        output='raw/float32差の件数・最大差・最初64index・kept前後を診断。波形自体は保存しない。',
        normalization='旧convert入力hash・AP factor・resample_poly・12ms fade・固定gain・float32を完全一致。係数/公差の探索なし。',
        limits=limits,estimates=dict(compat_render=12,full_render=1536,maximum_render_with10_batch_retries=2188,
            compat_DSP=32,full_DSP=6144,maximum_DSP_with10_batch_retries=8736,
            temporary_peak=16000000,data_and_retry_peak=300000000,metadata_and_Git_included=True,
            worst_seconds=7340,batch_size=32,batch_timeout=120,compat_timeout=300),
        technical_retry_per_job=2,technical_retry_campaign=10,ram_gb=8,parallel_max=2,
        no_NEW_observer_flags_retry=True,no_human_response_required=True,new_AI_teacher_train_inverse_download=0,
        old_gates_ASR_qualification_unchanged=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','原WORLDの対照・全入力・費用を固定',reserve_bytes=2500000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'protocol.json',dict(records=protocol['records'],compat_indices=protocol['compat_indices'],old_protocol_sha256=digest(OLD/'protocol.json')),j)
        b.write(HERE/'analysis.py',WORKER.encode(),j);b.write(HERE/'wrapper.cpp',CPP.encode(),j)
        b.write(HERE/'synthesis.cpp',(PRIMARY/'synthesis.cpp').read_bytes(),j)
        for p in (OLD/'vendor/world').glob('*.h'):b.write(HERE/'vendor/world'/p.name,p.read_bytes(),j)
        b.write(HERE/'LICENSE-WORLD.txt',(OLD/'LICENSE-WORLD.txt').read_bytes(),j)
    tool=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    cmd=[str(tool),'-dynamiclib','-O2','-std=c++11','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),'-I'+str(HERE/'vendor'),'-I'+str(HERE),str(HERE/'wrapper.cpp'),'-o',str(HERE/'original.dylib')]
    with job(b,'setup','hookなし原実装buildと一時回収',1,20000000,120) as j:
        with b.workspace(j,'clang中間物/cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'original.dylib',200000,j):
                result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=result.stderr,original_source_byte_exact=digest(HERE/'synthesis.cpp')==digest(PRIMARY/'synthesis.cpp'),
             no_observer_hooks=True,symbol_renamed_only=True,binary_sha256=digest(HERE/'original.dylib'),temporary_removed=True),j)
    inputs={str((OLD/n).relative_to(REPO)):digest(OLD/n) for n in ('artifact-seal.json','aggregate-summary.json','compatibility-failure-diagnosis.json','build-audit.json')}
    inputs[str((CONVERT/'world_renderer2.py').relative_to(REPO))]=digest(CONVERT/'world_renderer2.py')
    for name,h in read(PERIOD/'runtime-bundle/manifest.json')['files'].items():inputs[str((PERIOD/'runtime-bundle'/name).relative_to(REPO))]=h
    b.save(HERE/'execution-contract.json',dict(registration_sha256=digest(HERE/'registration.json'),protocol_sha256=digest(HERE/'protocol.json'),
        source_hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.name not in ('registration.json','protocol.json')},input_hashes=inputs,
        controller_sha256=digest(Path(__file__)),all_conditions_fixed_before_output=True))
    with b.locked():
        s=b._load();s['continuation_checkpoint_history'].append(s['continuation_checkpoint']);s['continuation_checkpoint']=dict(id='world-original-prepared',active_campaign=NAME,next='登録commit/push→固定4compat→条件付き全768→集計/封印',quality_goal_completed=False,protected_confirmation_opened=False,git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0045.json',dict(active_campaign=NAME,source_truth_unknown_768_retained=True,new_scientific_outputs=0,quality_goal_completed=False,next='保存後compat4の原実装/installed C/binding比較',budget=b.reconcile()))
    print(b.reconcile(),flush=True)


def run(stage):
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    if stage=='compat':
        assert not (HERE/'compatibility-audit.json').exists()
        with job(b,'render','原実装/installed C/bindingの固定4対照',12,20000000,300) as r:
            with job(b,'dsp','固定4の変換hash・raw/float32差分',32,1000000,300) as d:
                with b.workspace(r,'対照実装と数値ライブラリ初期化') as (work,env):
                    subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'compat','--job',d],env=env,check=True,timeout=300)
    else:
        c=read(HERE/'compatibility-audit.json')
        if not c['all_original_bare_old_exact'] or not c['all_installed_C_and_binding_old_exact']:
            raise RuntimeError('固定4の原実装対照不通過。全768の再構成へ進まない')
        for begin in range(0,768,32):
            end=begin+32;target=HERE/'batches'/f'{begin:03d}-{end:03d}.json'
            if target.exists():continue
            count=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in read(HERE/'protocol.json')['records'][begin:end])
            if count==0:
                with job(b,'audit',f'保存済み原WORLD manifest回復 {begin}:{end}',1,20000000,120) as d:
                    with b.workspace(d,'保存済みhash照合の初期化') as (work,env):
                        subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'batch','--begin',str(begin),'--end',str(end),'--job',d],env=env,check=True,timeout=120)
                continue
            with job(b,'render',f'原WORLD未観測対照 {begin}:{end}',count*2,20000000,120) as r:
                with job(b,'dsp',f'原WORLD演算差 {begin}:{end}',count*8,5000000,120) as d:
                    with b.workspace(r,'原WORLD対照初期化') as (work,env):
                        subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'batch','--begin',str(begin),'--end',str(end),'--job',d],env=env,check=True,timeout=120)
    print(b.reconcile(),flush=True)


def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];compat=read(HERE/'compatibility-audit.json')
    full=[]
    for p in sorted((HERE/'batches').glob('*.json')) if (HERE/'batches').exists() else []:
        for x in read(p)['rows']:
            assert digest(REPO/x['path'])==x['sha256'];full.append(read(REPO/x['path']))
    allowed=compat['all_original_bare_old_exact'] and compat['all_installed_C_and_binding_old_exact']
    assert len(full)==(768 if allowed else 0)
    with job(b,'audit','原実装差分・旧未知・全費用と封印',1,3000000,300) as j:
        summary=dict(compatibility=compat,full_reproductions=len(full),expected_WORLD=768,
            full_bare_old_exact=sum(x['bare_old_exact'] for x in full),full_direct_old_exact=sum(x['direct_old_exact'] for x in full),
            full_bare_direct_raw_exact=sum(x['bare_direct_raw_exact'] for x in full),
            old_actual_excitation_unknown=768,old_missing_source_unknown=155,no_actual_excitation_trace_collected=True,
            old_observer_nonpass_preserved=True,old_gates_ASR_and_denominators_unchanged=True,
            no_compiler_flag_repetition=True,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            next='原実装が一致すればobserverの観測箇所/演算効果を別因子で検証。不一致なら旧768を未知のまま閉じ、独立に検証できる別版と有効なHTS測定/生成へ進む。')
        b.save(HERE/'aggregate-summary.json',summary,j)
        lines=['# 未観測原WORLDと旧PyWORLDの再現対照','',
            f'固定4例のhookなし原実装の旧波形一致: {sum(x["bare_old_exact"] for x in compat["rows"])}/4。installed C直呼びと旧bindingの一致: {sum(x["direct_old_exact"] and x["binding_old_exact"] and x["installed_C_and_binding_raw_exact"] for x in compat["rows"])}/4。',
            f'全768対照の実施件数: {len(full)}。完全一致条件を緩和せず、4例不通過なら全件へ進まない。','',
            '原synthesis.cppをbyte不変で同じO2/SDK条件へ再buildした。公開関数名とwrapper ABI/build contextは差の要因に含む。元wheelのcompile flagsは断定しない。rawと最終float32の差、差の位置、切捨て前後を保持した。','',
            '今回は観測hookなしの再構成対照で、内部の実励振traceはない。旧WORLD768件の実励振unknownと固定支持欠測155を保持する。旧observerの3attempt不通過やASR/採否は上書きしない。','',
            summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],
            all_temporary_absent=all(v['status']=='removed' and not os.path.lexists(v['path']) for v in s['temporary_work'].values()),new_AI_teacher_fit_inverse_download=0,new_audio_saved=0),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,
            quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='world-original-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0046.json',dict(latest_completed=NAME,full_original_reproductions=len(full),old_actual_source_unknown=768,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print(b.reconcile(),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','compat','full','close'));a=p.parse_args()
    prepare() if a.stage=='prepare' else close() if a.stage=='close' else run(a.stage)
