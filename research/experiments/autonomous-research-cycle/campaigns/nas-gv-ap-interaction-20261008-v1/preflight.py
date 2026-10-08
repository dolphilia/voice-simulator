"""波形前のGV実内部検査と旧3波形とAP半減2対の互換検査。"""
from paths import *
import argparse,subprocess,json,base64,os,sys,math,io,hashlib,zipfile,contextlib
from contextlib import ExitStack
def static_worker():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0,str(HERE/'runtime-bundle'))
    import numpy as np
    from runtime import verify,analyze,Engine,DISABLED,VOICES,ah
    from gv_control import status,_fn
    verify();assert not _fn(None,None,0)
    import measurement,period_measurement,asr_worker,voicing_world
    from controls_v2 import ap_noise_power
    import runpy
    with contextlib.redirect_stdout(io.StringIO()):
        fixture=runpy.run_path(str(HERE/'test_controls.py'))
    assert callable(measurement.secondary) and callable(period_measurement.frame_acf)

    row=read(PREVIOUS/'protocol.json')['rows'][0]
    pairs=[]
    for condition,q in read(PREVIOUS/'protocol.json')['conditions'].items():
        kw=dict(speed=q['speed'],half_tone=12*math.log2(q['requested_f0']/220))
        with Engine(row,HERE/'runtime-bundle/mei_normal.htsvoice',**kw) as e:
            before=e.snapshot();v=e.variance();settings=e.get_settings();status(e,[]);native=e.parameters();status(e,[],True)
        for disabled in [[],['MCP'],['LF0'],['MCP','LF0']]:
            with Engine(row,HERE/'runtime-bundle'/VOICES[tuple(disabled)],**kw) as e:
                assert e.snapshot()==before and np.array_equal(e.variance(),v) and e.get_settings()==settings
                prior=status(e,disabled);params=e.parameters();after=status(e,disabled,True)
                assert e.snapshot()==before and np.array_equal(e.variance(),v)
            unchanged=[np.array_equal(a,z) for a,z in zip(native,params)]
            assert all(unchanged[i] for i,n in enumerate(['MCP','LF0','LPF']) if n not in disabled)
            assert np.array_equal(native[1]>0,params[1]>0)
            assert np.array_equal(native[1][native[1]<=0],params[1][params[1]<=0])
            pairs.append(dict(condition=condition,disabled=disabled,before=prior,after=after,
                parameter_hashes=[ah(x) for x in params],baseline_hashes=[ah(x) for x in native],
                unchanged_streams=unchanged,state_variance_MSD_settings_preserved=True))
    import runtime_batch as rb
    rows=[dict(id='fixture/'+str(i),text='人工入力',method='native',speed=1.,pitch=220.) for i in range(160)]
    def fake(*a):
        b=b'artificial-no-wave'
        return b,dict(sha256=hashlib.sha256(b).hexdigest(),synthesis_calls=1,E0_calls=1,forbidden_imports=[])
    old=(rb.generate,rb.verify,sys.stdin);rb.generate=fake;rb.verify=lambda:None;sys.stdin=io.StringIO(json.dumps(rows))
    try:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):rb.main()
    finally:rb.generate,rb.verify,sys.stdin=old
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(out.getvalue().strip(),validate=True))) as a:
        assert len(a.namelist())==321 and len(json.loads(a.read('manifest.json'))['records'])==160
    return dict(parameter_engine_checks=pairs,all_dependency_imports_pass=True,AP_boundary_fixture_pass=True,actual_render_calls=0,actual_AI_calls=0,
        static_model_and_archive_checks_only=True,fixture_not_quality_evidence=True,quality_certified=False)
def compat_worker():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0,str(HERE/'runtime-bundle'))
    from runtime import verify,generate
    verify();p=read(PREVIOUS/'protocol.json');row=p['rows'][0];q=p['conditions']['neutral'];items=[]
    for m in ['native','voicing_no_lf0_gv','voicing_no_gv']:
        data,meta=generate(row['text'],m,q['speed'],q['requested_f0'])
        old=read(PREVIOUS/'render'/row['id']/'neutral'/(m+'.json'));assert meta['sha256']==old['wav_sha256']
        items.append(dict(name=m,sha256=meta['sha256'],bit_match=True,wav_base64=base64.b64encode(data).decode()))
    import numpy as np
    from scipy.io import wavfile
    from voicing_world import synthesize
    from acoustics import evaluate
    for m in ['voicing_no_lf0_gv_ap_half','voicing_no_gv_ap_half']:
        data,meta,params,analyzed=generate(row['text'],m,q['speed'],q['requested_f0'],full=True)
        raw,conversion=synthesize(params,meta['settings'],.5)
        audio=(raw*.25).astype(np.float32);assert evaluate(audio,{},24000)['E0_pass']
        out=io.BytesIO();wavfile.write(out,24000,audio);reference=out.getvalue();assert reference==data
        items.append(dict(name=m,sha256=meta['sha256'],bit_match=True,wav_base64=base64.b64encode(data).decode()))
        items.append(dict(name=m+'_existing_reference',sha256=hashlib.sha256(reference).hexdigest(),
            bit_match=True,wav_base64=base64.b64encode(reference).decode()))
    return dict(results=items,actual_render_calls=7,fixture_not_quality_evidence=True,
        baseline_old3_byte_exact=True,AP_existing_reference_pairs=2,quality_certified=False)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['static','compat','static-worker','compat-worker']);a=p.parse_args()
    if a.stage.endswith('-worker'):
        print(json.dumps(static_worker() if a.stage=='static-worker' else compat_worker(),ensure_ascii=False,allow_nan=False));return
    from controller import verify
    verify();b=Budget();b.recover()
    assert not (HERE/('preflight-'+a.stage+'-audit.json')).exists()
    kind='audit' if a.stage=='static' else 'render'
    with ExitStack() as stack:
        job=stack.enter_context(b.job(NAME,kind,'GV '+a.stage+' 生成前検査',count=1 if a.stage=='static' else 7,reserve_bytes=12_000_000))
        if a.stage=='compat':stack.enter_context(b.job(NAME,'dsp','7互換波形のE0/hash',count=7,reserve_bytes=100_000))
        with b.workspace(job,'GV内部・旧波形互換のライブラリ初期化') as (_,env):
            x=subprocess.run([str(PYTHON),'-B',str(HERE/'preflight.py'),a.stage+'-worker'],env=env,text=True,stdout=subprocess.PIPE,check=True,timeout=300)
        result=json.loads(x.stdout)
        if a.stage=='compat':
            for item in result['results']:
                data=base64.b64decode(item.pop('wav_base64'),validate=True);assert hashlib.sha256(data).hexdigest()==item['sha256']
                b.write(HERE/'fixtures'/(item['name']+'.wav'),data,job)
        b.save(HERE/('preflight-'+a.stage+'-audit.json'),result,job)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
