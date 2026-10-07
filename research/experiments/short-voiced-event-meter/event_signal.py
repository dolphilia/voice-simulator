"""短い既知駆動イベントの設計と生成。自然発声の正解ではない。"""
import numpy as np
FS=24000;STEP=120;FRAMES=240;N=FS*1.2


def validate(row):
    if row['sample_rate']!=FS or row['samples_per_frame']!=STEP or row['duration_frames']!=FRAMES or row['frame_seconds']!=.005:
        raise ValueError('標本化・整数時計・長さが契約と違います')
    for n in ('event_start_frame','event_end_frame','seed'):
        if type(row[n]) is not int or row[n]<0:raise ValueError('整数時刻と非負seedを要求します')
    if (row['target_start_frame'],row['target_end_frame'])!=(96,120) or not 96<=row['event_start_frame']<row['event_end_frame']<=120:
        raise ValueError('駆動区間が空または固定領域外です')
    if row['event_end_frame']-row['event_start_frame'] not in (11,24):raise ValueError('イベント長が契約外です')
    if not np.isfinite([row['f0_hz'],row['initial_phase']]).all() or not 70<=row['f0_hz']<=800:
        raise ValueError('F0・位相が非有限または範囲外です')
    if row['expected_driving_voiced_frames']!=row['event_end_frame']-row['event_start_frame']:
        raise ValueError('駆動正解のフレーム数が不一致です')


def truth(row):
    validate(row);samples=FRAMES*STEP;index=np.arange(samples)
    f0=np.full(samples,row['f0_hz'],dtype=float)
    gate=(index>=row['event_start_frame']*STEP)&(index<row['event_end_frame']*STEP)
    phase=row['initial_phase']+2*np.pi*np.cumsum(f0)/FS
    return {'sample_index':index,'f0_hz':f0,'driving_mask':gate,'phase':phase}


def generate(row):
    ref=truth(row);index=ref['sample_index'];lo=row['event_start_frame']*STEP;hi=row['event_end_frame']*STEP
    distance=np.minimum(index-lo,hi-index)/FS
    env=np.zeros(len(index));inside=ref['driving_mask'];env[inside]=np.sin(np.minimum(1.,distance[inside]/.005)*np.pi/2)**2
    phase=ref['phase'];voice=(.8/1.5)*(np.sin(phase)+.35*np.sin(2*phase)+.15*np.sin(3*phase))*env
    noise=np.random.default_rng(row['seed']).normal(0.,.02,len(index));noise[inside]=0
    audio=voice+noise;n=round(.012*FS);fade=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=fade;audio[-n:]*=fade[::-1]
    if not np.isfinite(audio).all() or np.max(abs(audio))>=.99:raise ValueError('信号の有限性・振幅検査に不通過')
    # 駆動ゲートの回復は生成内部列の検査。音響的VUVを波形から回復したとは扱わない。
    recovered=np.repeat((np.arange(FRAMES)>=row['event_start_frame'])&(np.arange(FRAMES)<row['event_end_frame']),STEP)
    assert np.array_equal(recovered,ref['driving_mask'])
    recovered_f0=np.diff(phase,prepend=row['initial_phase'])*FS/(2*np.pi)
    error=float(np.max(abs(recovered_f0-ref['f0_hz'])));assert error<1e-6
    return audio.astype(np.float32),ref,{'phase_recovery_max_error_hz':error,'driving_gate_recovered':True,
        'gain_coefficient':.8/1.5,'noise_sigma':.02,'event_fade_samples':120,'whole_signal_fade_samples':288,
        'driving_mask_is_acoustic_vuv_truth':False,'render_calls':1,'runtime_neural':False}


def tests(row):
    validate(row);ref=truth(row);assert len(ref['driving_mask'])==28800
    bad=[{**row,'event_end_frame':row['event_start_frame']},{**row,'f0_hz':np.nan},{**row,'f0_hz':69},
        {**row,'seed':None},{**row,'sample_rate':16000},{**row,'initial_phase':float('inf')},
        {**row,'event_start_frame':96.5}]
    for r in bad:
        try:validate(r)
        except ValueError:pass
        else:raise AssertionError('不正な信号設計を拒否しません')
    return {'invalid_configuration_cases':len(bad),'integer_truth_and_shapes_valid':True,'audio_generated':False,'render_calls':0}
