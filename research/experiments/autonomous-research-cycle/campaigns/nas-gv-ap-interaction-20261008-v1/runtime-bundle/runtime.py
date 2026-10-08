"""MCP/LF0のGVだけを除く直接非ニューラル比較。発話表を参照しない。"""
import argparse,base64,hashlib,io,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from timing_engine import Engine
from voicing_world import synthesize
from controls_v2 import transform
from gv_control import status
from acoustics import evaluate
METHODS=['native','voicing_no_lf0_gv','voicing_no_lf0_gv_ap_half','voicing_no_gv','voicing_no_gv_ap_half']
DISABLED={'native':[],'voicing_no_lf0_gv':['LF0'],'voicing_no_lf0_gv_ap_half':['LF0'],
          'voicing_no_gv':['MCP','LF0'],'voicing_no_gv_ap_half':['MCP','LF0']}
VOICES={(): 'mei_normal.htsvoice',('MCP',):'mei_no_mcp_gv.htsvoice',
        ('LF0',):'mei_no_lf0_gv.htsvoice',('MCP','LF0'):'mei_no_gv.htsvoice'}
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def verify():
    for name,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
def generate(text,method,speed,pitch,full=False):
    if method not in METHODS:raise ValueError('未登録のGV方式')
    row=analyze(text);disabled=DISABLED[method]
    kwargs=dict(speed=speed,half_tone=12*math.log2(pitch/220))
    with Engine(row,ROOT/'mei_normal.htsvoice',**kwargs) as engine:
        before=engine.snapshot();variance=engine.variance();settings=engine.get_settings()
        baseline_status=status(engine,[])
        native=engine.parameters();baseline_after=status(engine,[],True)
        assert engine.snapshot()==before and np.array_equal(engine.variance(),variance)
    if disabled:
        with Engine(row,ROOT/VOICES[tuple(disabled)],**kwargs) as engine:
            assert engine.snapshot()==before and np.array_equal(engine.variance(),variance) and engine.get_settings()==settings
            gv_before=status(engine,disabled)
            generated=engine.parameters();gv_after=status(engine,disabled,True)
            assert engine.snapshot()==before and np.array_equal(engine.variance(),variance)
            assert engine.get_settings()==settings
    else:generated=[x.copy() for x in native];gv_before=baseline_status;gv_after=baseline_after
    unchanged=[]
    for s,name in enumerate(['MCP','LF0','LPF']):
        same=np.array_equal(generated[s],native[s])
        if name not in disabled:assert same,name
        unchanged.append(same)
    assert np.array_equal(generated[1]>0,native[1]>0) and np.array_equal(generated[1][generated[1]<=0],native[1][native[1]<=0])
    lf0_method='native' if method=='native' else ('combined' if method.endswith('_ap_half') else 'voicing')
    params,control,relative_error,invariants=transform(lf0_method,generated,row['full_context_labels'],before['duration'],pitch)
    control.update(GV=dict(disabled=disabled,enabled_before=gv_before,enabled_after=gv_after,
        weight_changed=False,stream_unchanged_before_LF0_control=unchanged,header_only=True),
        MCP_postfilter_beta=0.,LF0_method=lf0_method)
    raw,conversion=synthesize(params,settings,control['AP_noise_power_factor']);conversion.update(renderer='WORLD',AP_noise_power_factor=control['AP_noise_power_factor'],input_streams_unchanged=True)
    audio=(raw*.25).astype(np.float32);e0=evaluate(audio,{},24000)
    forbidden=[n for n in sys.modules if n.split('.')[0] in ('torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx')]
    assert not forbidden
    output=io.BytesIO();wavfile.write(output,24000,audio);data=output.getvalue();voiced=params[1][:,0]>0
    meta=dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,
        E0=e0,E0_pass=e0['E0_pass'],invariants_pass=bool(invariants),
        relative_LF0_max_abs_error=relative_error,control=control,duration=before['duration'],msd=before['msd'],settings=settings,
        state_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        variance_sha256=ah(variance),native_parameter_hashes=[ah(x) for x in native],
        GV_parameter_hashes=[ah(x) for x in generated],output_parameter_hashes=[ah(x) for x in params],
        voice_sha256=hashlib.sha256((ROOT/VOICES[tuple(disabled)]).read_bytes()).hexdigest(),
        output_gain=.25,conversion=conversion,forbidden_imports=forbidden,runtime_neural=False,
        teacher_audio=0,utterance_tables=0,generated_lf0_median_hz=float(np.exp(np.median(params[1][voiced,0]))))
    return (data,meta,params,row) if full else (data,meta)
def main():
    p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=METHODS,required=True)
    p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);a=p.parse_args()
    verify();data,meta=generate(a.text,a.method,a.speed,a.pitch)
    print(json.dumps(dict(meta=meta,wav_base64=base64.b64encode(data).decode()),allow_nan=False))
if __name__=='__main__':main()
