"""事前予約・外部所有一時領域・再開検査を共通化する。"""
from paths import *
import sys,os,io,json,base64,subprocess,zipfile,hashlib,argparse
def verify():
    value=read(HERE/'execution-contract.json')
    for n,h in value['source_hashes'].items():assert digest(HERE/n)==h,n
    assert digest(HERE/'protocol.json')==value['protocol_sha256']
    assert digest(HERE/'registration.json')==value['registration_sha256']
    assert digest(HERE/'runtime-bundle/manifest.json')==value['runtime_manifest_sha256']
    assert digest(PREVIOUS/'artifact-seal.json')==value['previous_seal_sha256']
    return value
def profile(b, work, isolated):
    text = '(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
    text += '(allow file-write* (subpath ' + json.dumps(str(work)) + '))\n'
    if isolated:
        text += '(deny file-read* (subpath ' + json.dumps(str(REPO / 'research')) + '))\n'
        text += '(deny file-read-data (subpath ' + json.dumps(str(b.guard.root)) + '))\n'
        site = OLD / '.venv-eval/lib/python3.11/site-packages'
        allowed = [OLD / '.venv-eval', HERE / 'runtime-bundle', work]
        text += '(allow file-read* ' + ''.join('(subpath ' + json.dumps(str(p)) + ') ' for p in allowed) + ')\n'
        text += '(allow file-read-data (literal ' + json.dumps(str(b.guard.root / 'identity.json')) + '))\n'
        text += '(deny file-read* ' + ''.join('(subpath ' + json.dumps(str(site / n)) + ') '
            for n in ('torch', 'tensorflow', 'transformers', 'faster_whisper', 'ctranslate2',
                      'onnxruntime', 'sherpa_onnx')) + ')\n'
    if isolated:
        ancestors=set()
        for path in [OLD / '.venv-eval', HERE / 'runtime-bundle', work]: ancestors.update(path.parents)
        text += '(allow file-read-metadata ' + ''.join('(literal ' + json.dumps(str(p)) + ') ' for p in sorted(ancestors)) + ')\n'
    return text


def execute(command,env,profile_text=None,input_text=None,timeout=1800):
    if profile_text:command=['/usr/bin/sandbox-exec','-p',profile_text,*command]
    return subprocess.run(command,env=env,input=input_text,text=True,stdout=subprocess.PIPE,check=True,timeout=timeout).stdout
def initialized():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(HERE/'runtime-bundle'),str(HERE/'runtime-bundle/packages-v2')]
def static_worker():
    initialized()
    import runpy,contextlib
    out=io.StringIO()
    with contextlib.redirect_stdout(out):runpy.run_path(str(HERE/'test_static.py'),run_name='artificial_only')
    print(out.getvalue(),end='')
def static():
    b=Budget()
    with b.job(NAME,'audit','波形前の境界・272人工archive・欠測判定検査',reserve_bytes=12000000) as job:
        with b.workspace(job,'人工配列と受渡の生成前検査') as (_,env):
            result=json.loads(execute([str(PYTHON),'-B',str(HERE/'controller.py'),'static-worker'],env,timeout=120))
        b.save(HERE/'static-audit.json',result,job)
def save_exact(b,path,data,job):
    if path.exists():assert digest(path)==hashlib.sha256(data).hexdigest(),str(path)
    else:b.write(path,data,job)
def comparison_worker(render_job,dsp_job):
    initialized()
    import numpy as np
    from scipy.io import wavfile
    from runtime import generate,verify as verify_bundle
    from measurement import trackers,score_track,global_score
    verify_bundle();b=Budget();p=read(HERE/'protocol.json');records=[];new=0
    for spec in p['specifications']:
        base=HERE/'render'/spec['id'];path=base.with_suffix('.json')
        if path.exists():
            value=read(path);assert value['spec']==spec and value['protocol_sha256']==digest(HERE/'protocol.json')
            assert digest(base.with_suffix('.wav'))==value['wav_sha256']
        else:
            data,meta=generate(spec);new+=1;save_exact(b,base.with_suffix('.wav'),data,render_job)
            _,audio=wavfile.read(io.BytesIO(data));tracks,scalar,confidence=trackers(audio);scores={}
            arrays={}
            for method,(values,times) in tracks.items():
                scores[method]=score_track(values,times,meta['truth']);arrays[method+'_f0']=values;arrays[method+'_times']=times
            arrays['centered_acf_confidence']=confidence
            array_path=base.with_suffix('.npz')
            if array_path.exists():
                with np.load(array_path) as old:assert set(old.files)==set(arrays) and all(np.array_equal(old[n],x) for n,x in arrays.items())
            else:
                buffer=io.BytesIO();np.savez_compressed(buffer,**arrays);b.write(array_path,buffer.getvalue(),dsp_job)
            value=dict(id=spec['id'],spec=spec,status='completed',wav=str(base.with_suffix('.wav').relative_to(REPO)),wav_sha256=meta['sha256'],meta=meta,measurements=scores,global_ACF=global_score(scalar,meta['truth']),primary_domain=spec['kind']=='positive' and spec['voiced_ms']>=60 and spec['SNR']=='none',protocol_sha256=digest(HERE/'protocol.json'),fixture_not_quality_evidence=True,quality_certified=False)
            b.write_data(path,encode(value),dsp_job)
        records.append(dict(id=spec['id'],record=str(path.relative_to(REPO)),sha256=digest(path)))
        if len(records)%32==0:print('既知周期',len(records),'/272',flush=True)
    assert len(records)==272
    b.save(HERE/'render-manifest.json',dict(rows=records,new_render_calls=new,new_DSP_calls=new*5,reused_records=272-new,quality_certified=False),dsp_job)
def comparison():
    b=Budget();p=read(HERE/'protocol.json')
    assert read(HERE/'static-audit.json')['actual_render_calls']==0
    count=sum(not (HERE/'render'/s['id']).with_suffix('.json').exists() for s in p['specifications'])
    assert count>0 and not (HERE/'render-manifest.json').exists()
    with b.job(NAME,'render','周期既知の272人工条件',count=count,reserve_bytes=60000000) as render_job:
        with b.job(NAME,'dsp','4測定器とE0の固定検査',count=count*5,reserve_bytes=30000000) as dsp_job:
            with b.workspace(render_job,'人工信号の生成・測定初期化') as (_,env):
                execute([str(PYTHON),'-B',str(HERE/'controller.py'),'comparison-worker','--render-job',render_job,'--dsp-job',dsp_job],env)
    print('272条件保存完了',flush=True)
def isolate():
    b=Budget();requests=read(HERE/'protocol.json')['specifications']
    expected={r['id']:read(REPO/r['record'])['wav_sha256'] for r in read(HERE/'render-manifest.json')['rows']}
    outputs={};profiles={}
    for mode in ['normal','isolated']:
        with b.job(NAME,'render','全272人工条件 '+mode,count=272,reserve_bytes=60000000) as job:
            with b.job(NAME,'dsp','全272 E0 '+mode,count=272,reserve_bytes=100000):
                with b.workspace(job,mode+' 生成初期化') as (work,env):
                    sb=profile(b,work,mode=='isolated')
                    text=execute([str(PYTHON),'-I','-B',str(HERE/'runtime-bundle/runtime_batch.py')],env,sb,json.dumps(requests))
                    archive_data=base64.b64decode(text.strip(),validate=True);profiles[mode]=sb
                b.write(HERE/'runtime-archives'/(mode+'.zip'),archive_data,job)
                with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
                    manifest=json.loads(archive.read('manifest.json'));assert len(manifest['records'])==272 and len(archive.namelist())==545
                    assert manifest['synthesis_calls']==manifest['E0_calls']==272
                    records={}
                    for record in manifest['records']:
                        data=archive.read(record['id']+'.wav')
                        assert hashlib.sha256(data).hexdigest()==record['sha256']==expected[record['id']]
                        assert not record['forbidden_imports'] and record['synthesis_calls']==record['E0_calls']==1
                        records[record['id']]=record
                b.write_data(HERE/('runtime-batch-'+mode+'.json'),encode(dict(records=records,all_hash_match=True,profile=sb)),job)
                outputs[mode]=records
        print(mode,'272件のhash一致',flush=True)
    cli=[]
    for spec in [requests[0],requests[-1]]:
        for mode in ['normal','isolated']:
            with b.job(NAME,'render','CLI '+mode+'/'+spec['id'],reserve_bytes=10000000) as job:
                with b.job(NAME,'dsp','CLI E0 '+mode,reserve_bytes=100000):
                    with b.workspace(job,'単独CLI 初期化') as (work,env):
                        result=json.loads(execute([str(PYTHON),'-I','-B',str(HERE/'runtime-bundle/runtime.py'),'--spec',json.dumps(spec)],env,profile(b,work,mode=='isolated')))
                    data=base64.b64decode(result['wav_base64'],validate=True)
                    assert hashlib.sha256(data).hexdigest()==result['meta']['sha256']==expected[spec['id']]
                    b.write(HERE/'runtime-cli'/mode/(spec['id']+'.wav'),data,job)
                    cli.append(dict(id=spec['id'],mode=mode,sha256=expected[spec['id']],bit_match=True))
    logical=HERE/'render/periodic-000.wav'
    blocked=[logical,logical.resolve(),HERE/'protocol.json',HERE/'registration.json',PREVIOUS/'protocol.json',HERE/'runtime-archives/normal.zip',(HERE/'runtime-archives/normal.zip').resolve()]
    code='import json,socket; paths='+repr([str(p) for p in blocked])+'; a=[]\n'
    code+="for p in paths:\n try:\n  open(p,'rb').close();a.append(False)\n except PermissionError:a.append(True)\n"
    code+="s=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps(dict(read_denied=a,network_denied=net)))"
    with b.job(NAME,'audit','資料・外部実体・通信の拒否probe',reserve_bytes=10000000) as job:
        with b.workspace(job,'実拒否probe') as (work,env):
            proof=json.loads(execute([str(PYTHON),'-I','-B','-c',code],env,profile(b,work,True)))
        assert all(proof['read_denied']) and proof['network_denied']
        b.save(HERE/'denial-probe.json',dict(proof,paths=[str(x) for x in blocked]),job)
        pairs=[dict(id=s['id'],bit_match=outputs['normal'][s['id']]['sha256']==outputs['isolated'][s['id']]['sha256']) for s in requests]
        assert len(pairs)==272 and all(x['bit_match'] for x in pairs)
        b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,CLI=cli,new_render_calls=548,new_DSP_calls=548,denial_probe=proof,research_artificial_signals_only=True,quality_certified=False),job)
def diagnose_worker(job):
    initialized()
    import numpy as np
    import pyworld
    from scipy.io import wavfile
    from measurement import frame_acf,local
    b=Budget();references=read(HERE/'protocol.json')['diagnostic_references'];rows=[]
    for item in references:
        record=read(REPO/item['record']);assert digest(REPO/item['record'])==item['sha256']
        assert digest(REPO/record['wav'])==record['wav_sha256']
        fs,audio=wavfile.read(REPO/record['wav']);assert fs==24000 and audio.dtype==np.float32
        values,times=pyworld.harvest(audio.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
        acf,at,confidence=frame_acf(audio)
        support=record['measurement']['support'];scores={}
        for name,f,t in [('harvest',values,times),('centered_acf',acf,at)]:
            intervals=local(f,t,record['meta']['duration'],support)
            scores[name]=dict(local=intervals,missing_support=[x['index'] for x in intervals if not x['support_complete']],global_median_hz=float(np.median(f[f>0])) if (f>0).any() else None)
        array=io.BytesIO();np.savez_compressed(array,harvest_f0=values,harvest_times=times,acf_f0=acf,acf_times=at,acf_confidence=confidence)
        base=HERE/'diagnostic'/record['id'];b.write(base.with_suffix('.npz'),array.getvalue(),job)
        result=dict(id=record['id'],condition=record['condition'],variant=record['variant'],source_record=item['record'],source_sha256=item['sha256'],source_wave_sha256=record['wav_sha256'],measurements=scores,reused_legacy_measurement=record['measurement'],reused_legacy_pitch_gate=record['pitch_gate'],new_render=0,new_AI=0,new_DSP=2,source_wave_has_no_independent_period_ground_truth=True,diagnostic_only=True,old_decision_unchanged=True,quality_certified=False)
        b.write_data(base.with_suffix('.json'),encode(result),job)
        rows.append(dict(id=record['id'],path=str(base.with_suffix('.json').relative_to(REPO)),sha256=digest(base.with_suffix('.json'))))
        if len(rows)%32==0:print('旧192追加診断',len(rows),'/192',flush=True)
    assert len(rows)==192
    b.save(HERE/'diagnostic-manifest.json',dict(rows=rows,new_render=0,new_AI=0,new_DSP=384,old_DIO_ACF_ASR_reused=True,diagnostic_only=True,quality_certified=False),job)
def diagnose():
    b=Budget();assert read(HERE/'runtime-audit.json')['passed']
    with b.job(NAME,'dsp','封印済み192件へHarvest/中心ACF追加診断',count=384,reserve_bytes=30000000) as job:
        with b.workspace(job,'追加測定初期化') as (_,env):
            execute([str(PYTHON),'-B',str(HERE/'controller.py'),'diagnose-worker','--dsp-job',job],env)
    print('旧192診断保存完了',flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['static','comparison','isolate','diagnose','static-worker','comparison-worker','diagnose-worker']);parser.add_argument('--render-job');parser.add_argument('--dsp-job');args=parser.parse_args();verify()
    if args.stage=='static-worker':static_worker();return
    if args.stage=='comparison-worker':comparison_worker(args.render_job,args.dsp_job);return
    if args.stage=='diagnose-worker':diagnose_worker(args.dsp_job);return
    b=Budget();b.recover();globals()[args.stage]();print(b.reconcile(),flush=True)
if __name__=='__main__':main()
