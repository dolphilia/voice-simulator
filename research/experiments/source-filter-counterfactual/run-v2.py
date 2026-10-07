"""最初の18一致を必須にし、固定の対照だけを54回以内で生成する。"""
import io,json,sys,time
import numpy as np
from scipy.io import wavfile
from campaign import *
sys.path.insert(0,str(ROOT))
from counter_renderer import CounterEngine
from counter_diagnostics import measure,tests as diagnostic_tests
from checks import invariant


def array_hash(array):
    import hashlib
    return hashlib.sha256(np.asarray(array,dtype='<f8').tobytes()).hexdigest()

def npz_bytes(**values):
    memory=io.BytesIO();np.savez_compressed(memory,**values);return memory.getvalue()


def main():
    b=LocalBudget();protocol=read(RESULT/'protocol.json')
    for name,sha in protocol['source_hashes'].items():assert digest(ROOT/name)==sha
    for name,sha in protocol['dependencies'].items():assert digest(REPO/name)==sha
    assert read(RESULT/'entry-audit.json')['passed']
    with b.job('audit','境界・欠損・OSネットワーク遮断を生成前に検査',200000):
        import socket
        try:
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.close()
        except PermissionError:network_denied=True
        else:network_denied=False
        assert network_denied
        save(RESULT/'execution-preflight.json',{'network_denied':network_denied,'negative_measurement_tests':diagnostic_tests(),
            'actual_generation_calls':0,'source_protocol_sha256':digest(RESULT/'protocol.json')})
    completed=[]
    for mode in protocol['modes']:
        if mode!='baseline':assert read(RESULT/'baseline-gate.json')['passed']
        for i,row in enumerate(protocol['rows']):
            path=RESULT/'render'/mode/f'{i:02d}.json';started=time.monotonic()
            result={'id':row['id'],'mode':mode,'phase':row['phase'],'source_record_sha256':row['source_record_sha256'],
                'status':'failed','synthesis_calls':1,'quality_certified':False,'runtime_neural':False}
            try:
                with b.job('render',mode+'/'+row['id'],2_000_000):
                    source=REPO/row['source_record'];assert digest(source)==row['source_record_sha256']
                    old=read(source);saved=np.load(REPO/row['parameter_lf0_source_npz']);delta=saved['state_deltas']
                    support=read(REPO/row['support_contract']);assert digest(REPO/row['support_contract'])==row['support_contract_sha256']
                    with CounterEngine(row,BUNDLE/'mei_normal.htsvoice',**row['settings']) as engine:
                        before=json.loads(json.dumps(engine.snapshot()));assert before==old['state_snapshot_before']
                        engine.modify(delta);after=json.loads(json.dumps(engine.snapshot()))
                        assert after==old['state_snapshot_after'];invariant(before,after,delta)
                        parameters=engine.parameters();settings=engine.get_settings()
                        assert np.array_equal(parameters[1][:,0],saved['generated_lf0'])
                        if mode=='baseline':
                            write_checked(RESULT/'parameters'/f'{i:02d}.npz',npz_bytes(spectrum=parameters[0],lf0=parameters[1],lpf=parameters[2]))
                        else:
                            baseline=np.load(RESULT/'parameters'/f'{i:02d}.npz')
                            assert all(np.array_equal(a,baseline[k]) for a,k in zip(parameters,('spectrum','lf0','lpf')))
                            assert settings==read(RESULT/'render/baseline'/f'{i:02d}.json')['vocoder_settings']
                        audio=engine.synthesize(parameters,mode)
                        assert after==json.loads(json.dumps(engine.snapshot()))
                    peak=float(np.max(abs(audio)));gain=min(1.,.95/peak) if peak else 1.;audio=(audio*gain).astype(np.float32)
                    buffer=io.BytesIO();wavfile.write(buffer,24000,audio);write_checked(path.with_suffix('.wav'),buffer.getvalue())
                    measurements=measure(audio,parameters[1][:,0],after['duration'],support['indices'],row['focus_indices'])
                    write_checked(path.with_suffix('.npz'),npz_bytes(dio_f0=measurements.pop('f0'),dio_times=measurements.pop('times')))
                    result.update(status='completed',wav=str(path.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(path.with_suffix('.wav')),
                        measurement=measurements,finite=bool(np.isfinite(audio).all()),E0_pass=measurements['E0']['E0_pass'],
                        duration_msd_dynamic_means_unchanged=True,generated_lf0_identical=True,
                        vocoder_settings=settings,parameters_sha256={k:array_hash(a) for a,k in zip(parameters,('spectrum','lf0','lpf'))},
                        actual_input_streams=2 if mode=='simple_excitation' else 3,flat_preserves_c0=mode!='baseline',
                        raw_peak=peak,output_gain=gain,seconds=time.monotonic()-started,
                        focus_indices=row['focus_indices'],source_parameters_npz_sha256=row['parameter_lf0_source_npz_sha256'])
                    forbidden=[n for n in sys.modules if n.split('.')[0] in ('torch','tensorflow','transformers','onnxruntime','faster_whisper','ctranslate2','sherpa_onnx')]
                    assert not forbidden;result['forbidden_imports']=forbidden
                    if mode=='baseline':
                        result['same_wav_sha256']=result['wav_sha256']==row['wav_sha256']==digest(REPO/row['wav'])
                        assert result['same_wav_sha256'] and result['E0_pass'] and result['finite']
                        assert np.array_equal(np.load(path.with_suffix('.npz'))['dio_f0'],saved['dio_f0'])
                        assert np.array_equal(np.load(path.with_suffix('.npz'))['dio_times'],saved['dio_times'])
                    save(path,result)
                completed.append({'id':row['id'],'mode':mode,'record':str(path.relative_to(REPO)),'sha256':digest(path)})
            except BaseException as exc:
                result.update(error=repr(exc),seconds=time.monotonic()-started)
                if not path.exists():save(path,result)
                save(RESULT/'stop.json',{'mode':mode,'id':row['id'],'error':repr(exc),'additional_contrasts_started':mode!='baseline',
                    'failed_calls_retried':False,'render_calls_started':sum(e['count'] for e in b.events() if e['event']=='start' and e['kind']=='render')})
                raise
            print(mode,i+1,'/18',flush=True)
        if mode=='baseline':save(RESULT/'baseline-gate.json',{'passed':True,'same_wav_hashes':18,'same_lf0_sequences':18,
            'same_saved_dio_sequences':18,'E0_passed':18,'no_contrasts_before_all_18_passed':True})
    save(RESULT/'render-manifest.json',{'rows':completed,'render_calls':54,'dsp_f0_measurements':54,'ai_calls':0,
        'protocol_sha256':digest(RESULT/'protocol.json'),'quality_certified':False})

if __name__=='__main__':main()
