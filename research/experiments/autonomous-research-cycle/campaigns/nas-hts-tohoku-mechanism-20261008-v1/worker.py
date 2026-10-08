"""共有HMM全モデルの状態・生成列・源と素の一次vocoderを照合する。"""
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
