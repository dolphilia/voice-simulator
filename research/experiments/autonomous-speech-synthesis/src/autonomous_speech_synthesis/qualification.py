"""探索前の数値点検・評価器の適用資格・実測費用。"""
import time
import sys
import numpy as np
from scipy import signal,optimize
from scipy.io import wavfile
from .io import ROOT,read,write_once,digest,file_hash
from .generator import render,lf_derivative,lf_coefficients
from .gestures import voice_config
from .evaluation import evaluate,estimate_f0
from .backends import legacy_render,VTL


def qualify(output):
    if (output/"generator-qualification.json").exists():
        return read(output/"generator-qualification.json")
    fs=24000; t=np.arange(fs)/fs
    sine=.1*np.sin(2*np.pi*220*t); sine[:240]*=np.linspace(0,1,240);sine[-240:]*=np.linspace(1,0,240)
    corrupt={"nan":sine.copy(),"infinite":sine.copy(),"clip":sine*20,"dc":sine+.1,"silence":np.zeros(fs),"missing":sine[:fs//2],"endpoint":sine.copy()}
    corrupt["nan"][100]=np.nan;corrupt["infinite"][100]=np.inf;corrupt["endpoint"][-1]=.1
    fixtures=[]
    for name,audio in corrupt.items():
        result=evaluate(audio,{"expected_duration_seconds":1.},fs)
        fixtures.append({"name":name,"detected":not result["E0_pass"],"checks":result["checks"]})
    pitch=[]
    for frequency in (160,220,300):
        for gain,shift,resampling in [(1.,0,False),(.5,17,False),(1.,0,True)]:
            x=gain*.1*np.sin(2*np.pi*frequency*(t+shift/fs))
            if resampling:x=signal.resample_poly(signal.resample_poly(x,2,3),3,2)
            value,confidence=estimate_f0(x,fs)
            pitch.append({"target_hz":frequency,"measured_hz":value,"confidence":confidence,"gain":gain,"shift_samples":shift,"resampled":resampling,"relative_error":abs(value/frequency-1) if value else None})
    q=read(ROOT/"config/evaluator-contract-v1.json")
    q["fixtures"]=fixtures;q["f0_sensitivity"]=pitch
    q["metrics"]["signal"].update(status="qualified" if all(x["detected"] for x in fixtures) else "rejected",scope="数値破綻・全体無音・全体欠落。音素欠落検出は未資格")
    q["metrics"]["f0"].update(status="qualified" if all(x["relative_error"]<.03 for x in pitch) else "rejected",scope="160/220/300 Hzの既知周期音、60ms以上")
    write_once(output/"evaluator-qualification.json",q)
    u=np.linspace(0,1,100001);d=lf_derivative(u)
    area=float(np.trapezoid(d,u));at_close=abs(float(lf_derivative(.6-1e-9)-lf_derivative(.6+1e-9)))
    coeff=lf_coefficients(32,.4,.6,.05)
    numeric=np.array([np.trapezoid(d*np.exp(-2j*np.pi*n*u),u) for n in range(1,33)])
    lf={"area_error":abs(area),"closure_jump":at_close,"periodic_endpoint_error":abs(float(d[0]-d[-1])),"analytic_fourier_error":float(np.max(abs(coeff-numeric)))}
    lf["passed"]=lf["area_error"]<1e-7 and at_close<1e-6 and lf["analytic_fourier_error"]<1e-7
    # 並列極のインパルス応答をfreqzと照合する。音響応答の自己回復も同じ式から検査。
    b,a=signal.iirpeak(800,800/90,fs=fs)
    impulse=np.zeros(fs);impulse[0]=1
    response=signal.lfilter(b,a,impulse)
    freq=np.fft.rfftfreq(fs,1/fs); _,analytic=signal.freqz(b,a,worN=freq,fs=fs)
    response_error=float(np.max(abs(np.fft.rfft(response)-analytic)))
    grid=np.linspace(200,4000,128)
    def transfer(z):
        bb,aa=signal.iirpeak(z[0],z[0]/z[1],fs=fs)
        return 20*np.log10(np.maximum(abs(signal.freqz(bb,aa,worN=grid,fs=fs)[1]),1e-8))
    target=transfer([800.,90.]); recovery=[]
    for kind,initial in [("near",[790,95]),("far",[1800,300])]:
        fit=optimize.least_squares(lambda z:transfer(z)-target,initial,bounds=([200,20],[3500,500]),max_nfev=100)
        error=float(np.sqrt(np.mean((transfer(fit.x)-target)**2)))
        recovery.append({"start":kind,"initial":initial,"solution":fit.x.tolist(),"response_rmse_db":error,"evaluations":fit.nfev,"passed":error<.01,"scope":"既知単一共鳴器。多極・自然音声への回復を意味しない"})
    costs=[];renders=[];vtl=None
    try:
        vtl=VTL();vtl_status={"status":"available",**vtl.metadata}
    except Exception as exc:vtl_status={"status":"unavailable","reason":repr(exc)}
    for backend in ("dsp","vtl","B9","G40"):
        if backend=="vtl" and vtl is None:continue
        repeated=[]
        for repetition in range(2):
            before=time.monotonic()
            if backend=="dsp":x,_=render(["a"],{"durations_seconds":[.4]});rate=fs
            elif backend=="vtl":x=vtl.render("a",220,seed=11);rate=fs
            else:x,rate,_=legacy_render(backend,"a",220,401)
            elapsed=time.monotonic()-before
            evaluated=evaluate(x,{"kind":"vowel","f0_hz":220},rate)
            repeated.append(digest(x.tolist()))
            costs.append({"backend":backend,"seconds":elapsed,"duration_seconds":len(x)/rate,"rtf":elapsed/(len(x)/rate)})
            renders.append({"backend":backend,"repetition":repetition,"sha256_float64":repeated[-1],"evaluation":evaluated})
        renders[-1]["deterministic"]=repeated[0]==repeated[1]
        if backend in ("B9","G40"):
            expected=read(ROOT.parent/"synthetic-vowel-baseline/config/vowel-generalization.json")["frozen_a220_hashes"][f"V-a-{backend}-"+("sustain" if backend=="B9" else "onset")]
            temp=output/f"legacy-{backend}-canonical.wav";wavfile.write(temp,rate,x.astype(np.float32))
            renders[-1]["canonical_wav_hash"]=file_hash(temp)
            renders[-1]["canonical_expected_hash"]=expected
            renders[-1]["canonical_match"]=file_hash(temp)==expected
    if vtl:vtl.close()
    result={"lf":lf,"filter_response_error":response_error,"self_recovery":recovery,"renders":renders,"vtl":vtl_status,"render_count":len(renders),"source_coupling":"LF微分励起から相対音圧へ。追加の微分なし。Pa校正なし",
            "bandlimit":"解析倍音を0.45Fs/最高F0まで。変動側帯波の厳密な無折返し保証ではない"}
    write_once(output/"generator-qualification.json",result)
    write_once(output/"cost-pilot.json",{"rows":costs,"render_count":len(renders),"AI_cost":"別環境で計測","settings_per_arm":8,"frozen_before_search":True,"reason":"両backend同数、8設定×2探索群×15条件×3seedの縮小pilot。上限128設定以内"})
    return result
