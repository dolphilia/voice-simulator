"""波形前の境界検査と、登録済み4生成だけの互換fixture。"""
from paths import *
import argparse,subprocess,json,base64,io,hashlib,os,sys,runpy,contextlib,zipfile,math
def static_worker():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0,str(HERE/'runtime-bundle'))
    import numpy as np
    import hts_arrays as h
    import runtime_batch as rb
    assert not h._fn(None,None,None,0,0,0,None,0)
    cfg=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
    valid=[np.zeros((5,35)),np.full((5,1),np.log(220.)),np.tile([0.,1.,0.],(5,1))]
    assert all(np.array_equal(a,z) for a,z in zip(h.validated(valid,cfg),valid))
    bad=[]
    for stream in range(3):
        p=[x.copy() for x in valid];p[stream][0,0]=np.nan;bad.append((p,cfg))
    for stream,cols in [(0,34),(1,2),(2,2)]:
        p=[x.copy() for x in valid];p[stream]=np.zeros((5,cols));bad.append((p,cfg))
    for f0 in [-1.,0.,np.log(50.),np.log(900.)]:
        p=[x.copy() for x in valid];p[1][0,0]=f0;bad.append((p,cfg))
    changed=dict(cfg);changed['alpha']=.5;bad.append((valid,changed))
    p=[x.copy() for x in valid];p[2]=p[2][:-1];bad.append((p,cfg))
    for p,c in bad:
        try:h.validated(p,c)
        except ValueError:pass
        else:raise AssertionError('不正HTS入力を受理')
    before=[x.tobytes() for x in valid]
    out=np.zeros(5*240,dtype=float)
    assert not h._fn(*(x.ctypes.data_as(h.P) for x in valid),5,34,3,out.ctypes.data_as(h.P),len(out))
    assert [x.tobytes() for x in valid]==before
    rows=[dict(id='fixture/'+str(i),text='人工入力',method='native',speed=1.,pitch=220.) for i in range(192)]
    def fake(text,method,speed,pitch):
        data=b'artificial-no-wave'
        return data,dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,forbidden_imports=[],nested={'integer':1,'boolean':True,'indices':[1,2]})
    old=(rb.generate,rb.verify,sys.stdin)
    rb.generate=fake;rb.verify=lambda:None;sys.stdin=io.StringIO(json.dumps(rows))
    try:
        result=io.StringIO()
        with contextlib.redirect_stdout(result):rb.main()
    finally:rb.generate,rb.verify,sys.stdin=old
    data=base64.b64decode(result.getvalue().strip(),validate=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert len(archive.namelist())==385 and len(manifest['records'])==192
        assert manifest['synthesis_calls']==manifest['E0_calls']==192
        for row in manifest['records']:
            assert hashlib.sha256(archive.read(row['id']+'.wav')).hexdigest()==row['sha256']
            assert json.loads(archive.read(row['id']+'.json'))['nested']['boolean'] is True
    controls=io.StringIO()
    with contextlib.redirect_stdout(controls):runpy.run_path(str(HERE/'test_controls.py'),run_name='fixture_only')
    return dict(null_and_invalid_shapes_rejected=True,negative_cases=len(bad),settings_fixed=True,input_streams_preserved=True,batch192_roundtrip=True,base64_valid=True,controls=json.loads(controls.getvalue()),actual_render_calls=0,fixture_not_quality_evidence=True)
def compat_worker():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path.insert(0,str(HERE/'runtime-bundle'))
    import numpy as np
    from scipy.io import wavfile
    from runtime import generate,verify,analyze,Engine
    verify()
    prior=read(PREVIOUS/'protocol.json');row=prior['rows'][0];q=prior['conditions']['neutral']
    results=[]
    for method in ['native','calibrated']:
        data,meta=generate(row['text'],method,q['speed'],q['requested_f0'])
        expected=read(PREVIOUS/'render'/row['id']/'neutral'/method+'.json') if False else read((PREVIOUS/'render'/row['id']/'neutral'/method).with_suffix('.json'))
        assert meta['sha256']==expected['wav_sha256']
        json.dumps(meta,allow_nan=False)
        results.append(dict(name='world-'+method,sha256=meta['sha256'],bit_match=True,wav_base64=base64.b64encode(data).decode(),meta=meta))
    data,meta,params,analyzed=generate(row['text'],'hts_native',q['speed'],q['requested_f0'],full=True)
    with Engine(analyzed,HERE/'runtime-bundle/mei_normal.htsvoice',speed=q['speed'],half_tone=12*math.log2(q['requested_f0']/220)) as engine:
        original=engine.parameters()
        assert all(np.array_equal(a,z) for a,z in zip(params,original))
        raw,hashes=engine.synthesize(original,0)
        stream_hashes=[hashlib.sha256(x.astype('<f8').tobytes()).hexdigest() for x in params]
        assert hashes==stream_hashes==meta['conversion']['input_parameter_hashes']
        buf=io.BytesIO();wavfile.write(buf,24000,(raw*.25).astype(np.float32));old=buf.getvalue()
    assert data==old
    json.dumps(meta,allow_nan=False)
    results.extend([dict(name='hts-array-native',sha256=hashlib.sha256(data).hexdigest(),bit_match=True,wav_base64=base64.b64encode(data).decode(),meta=meta),dict(name='hts-engine-native',sha256=hashlib.sha256(old).hexdigest(),bit_match=True,wav_base64=base64.b64encode(old).decode())])
    return dict(results=results,actual_render_calls=4,world_previous_native_calibrated_byte_exact=True,hts_engine_array_byte_exact=True,fixture_not_quality_evidence=True,quality_certified=False)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['static','compat','static-worker','compat-worker']);args=p.parse_args()
    if args.stage.endswith('-worker'):
        result=static_worker() if args.stage=='static-worker' else compat_worker()
        print(json.dumps(result,ensure_ascii=False,allow_nan=False));return
    from controller import verify
    verify();b=Budget();b.recover()
    if args.stage=='static':
        with b.job(NAME,'audit','C入力境界・192件人工archive・制御メタデータ',reserve_bytes=12000000) as job:
            with b.workspace(job,'波形前の人工境界検査') as (_,env):
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'preflight.py'),'static-worker'],env=env,text=True,stdout=subprocess.PIPE,check=True,timeout=120)
            b.save(HERE/'preflight-static-audit.json',json.loads(out.stdout),job)
    else:
        assert read(HERE/'preflight-static-audit.json')['actual_render_calls']==0
        with b.job(NAME,'render','登録済み旧WORLD/HTS全frame互換fixture',count=4,reserve_bytes=12000000) as job:
            with b.job(NAME,'dsp','4互換fixtureのstream/hash比較',count=4,reserve_bytes=100000) as dspjob:
                with b.workspace(job,'互換fixtureの生成・pipe受渡') as (_,env):
                    out=subprocess.run([str(PYTHON),'-B',str(HERE/'preflight.py'),'compat-worker'],env=env,text=True,stdout=subprocess.PIPE,check=True,timeout=300)
                result=json.loads(out.stdout)
                for item in result['results']:
                    audio=base64.b64decode(item.pop('wav_base64'),validate=True)
                    assert hashlib.sha256(audio).hexdigest()==item['sha256']
                    b.write(HERE/'fixtures'/(item['name']+'.wav'),audio,job)
                b.save(HERE/'compatibility-fixture-audit.json',result,dspjob)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
