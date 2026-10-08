"""第25回の純時計ground関数を変更せず使用する。"""
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
