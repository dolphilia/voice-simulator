"""不一致の発生段階を保存する。互換ゲートは緩和しない。"""
from paths import *
import subprocess
PROGRAM=r'''
from paths import *
import observe,io,hashlib
mods=observe.load();np,signal,wavfile,world,lib=mods
source=(HERE/'observe.py').read_text()
needle="wavehash=hashlib.sha256(buf.getvalue()).hexdigest();assert wavehash==item['wave_sha256'],('旧波形不一致',item['id'],wavehash,item['wave_sha256'])"
replacement="""wavehash=hashlib.sha256(buf.getvalue()).hexdigest()
    baseline=world.pw.synthesize(f0,sp,ap,48000,frame_period=5.)
    baseaudio=(finish(baseline)*meta['output_gain']).astype(np.float32);basebuf=io.BytesIO();wavfile.write(basebuf,24000,baseaudio)
    rate,oldaudio=wavfile.read(REPO/item['wave'])
    diagnostic=dict(id=item['id'],baseline_length=len(baseline),observed_length=len(raw),
        baseline_wave_sha256=hashlib.sha256(basebuf.getvalue()).hexdigest(),old_wave_sha256=item['wave_sha256'],
        observed_wave_sha256=wavehash,baseline_old_exact=np.array_equal(baseaudio,oldaudio),
        observed_old_exact=np.array_equal(audio,oldaudio),raw_max_abs_diff=float(np.max(abs(raw-baseline))),
        raw_different_samples=int((raw!=baseline).sum()),float32_max_abs_diff=float(np.max(abs(audio-oldaudio))),
        float32_different_samples=int((audio!=oldaudio).sum()),gate_unchanged=True)
    return diagnostic,{}"""
assert source.count(needle)==1
scope=dict(__name__='diagnostic_module');exec(compile(source.replace(needle,replacement),str(HERE/'observe.py'),'exec'),scope)
b=Budget();p=read(HERE/'protocol.json');rows=[]
for index in p['compat_indices']:
    d,_=scope['evaluate'](p['records'][index],mods);rows.append(d);print(d,flush=True)
b.save(HERE/'compatibility-failure-diagnosis.json',dict(rows=rows,scientific_gate_unchanged=True,old_sources_not_overwritten=True),sys.argv[1])
'''
def main():
    b=Budget();b.recover()
    with b.job(NAME,'dsp','波形不一致の発生段階を診断',count=16,reserve_bytes=1000000):
        with b.job(NAME,'render','観測4/既存PW4の同一入力不一致段階検査',count=8,reserve_bytes=20000000) as j:
            with b.workspace(j,'不一致診断の外部専用cache') as (_,env):
                subprocess.run([str(PYTHON),'-B','-c',PROGRAM,j],cwd=HERE,env=env,check=True,timeout=600)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
