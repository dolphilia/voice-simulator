def ground(np,period,pulse,times,width_ms):
    # 複数の実パルス間隔による窓内平均発生率。駆動LF0/知覚pitchへ読み替えない。
    kinds=np.zeros(len(times),dtype=np.uint8);target=np.full(len(times),np.nan)
    counts=np.zeros(len(times),dtype=np.int32);positions=np.flatnonzero(pulse)
    half=round(width_ms*48/2)
    for i,t in enumerate(times):
        c=round(float(t)*48000);a,z=c-half,c+half
        if a<0 or z>len(period):continue
        segment=period[a:z]
        if (segment==0).all():kinds[i]=2;continue
        if not (segment>0).all():kinds[i]=1;continue
        left,right=np.searchsorted(positions,[a,z]);selected=positions[left:right];counts[i]=len(selected)
        if len(selected)<4:kinds[i]=3;continue
        target[i]=48000*(len(selected)-1)/(selected[-1]-selected[0])
        spread=12*np.log2(segment.max()/segment.min())
        kinds[i]=4 if spread<=1. else 5
    return kinds,target,counts

def score(np,values,kinds,target,kind):
    positive=kinds==kind;negative=kinds==2;accepted=(values>=70)&(values<=800)
    errors=np.full(len(values),np.inf)
    chosen=positive&accepted
    errors[chosen]=abs(12*np.log2(values[chosen]/target[chosen]))
    p=int(positive.sum());n=int(negative.sum());correct=int((positive&accepted&(errors<=1.)).sum())
    coverage=correct/p if p else 0.;false=int((negative&accepted).sum());uv=false/n if n else 1.
    median=float(np.median(errors[positive])) if p else None
    finite_median=median if median is not None and np.isfinite(median) else None
    return dict(positive_windows=p,negative_windows=n,correct_positive=correct,
        missing_positive=int((positive&~accepted).sum()),coverage=coverage,
        median_error_semitones=finite_median,negative_false_accept=false,negative_false_accept_rate=uv,
        inadequate_positive=p<3,inadequate_negative=n<3,
        passed=bool(p>=3 and n>=3 and coverage>=.9 and finite_median is not None and finite_median<=1. and uv<=.05),
        total_clock_points=len(kinds),exclusions={name:int((kinds==i).sum()) for i,name in enumerate(['edge','boundary','source_unvoiced','insufficient_pulses','stable','dynamic'])},
        source_pulse_rate_diagnostic_only=True,independent_vote=False,perceived_pitch_truth=False)
