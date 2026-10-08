"""保存済みパラメータを同じ変換で渡し、波形hashと演算差を診断する。"""
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
