"""固定DIOとStoneMaskを24信号に一回ずつ適用。"""
from scipy.io import wavfile
from event_io import *
from event_metrics import evaluate,aggregate
sys.path.append(str(PILOT/'.cache/packages'))
import pyworld

def main():
    p=verify_protocol();assert pyworld.__version__=='0.3.5';b=LocalBudget();records=[]
    manifest={r['id']:r for r in read(RESULT/'render-manifest.json')['rows']}
    for phase in ('development','confirmation'):
        part=[]
        for row in [r for r in p['rows'] if r['phase']==phase]:
            src=manifest[row['id']];assert digest(REPO/src['record'])==src['sha256'];render=read(REPO/src['record'])
            rec={'id':row['id'],'phase':phase,'status':'missing_render','new_dio_calls':0,'design':row}
            if render['status']=='completed':
                try:
                    with b.job('audit','DIO一回 '+row['id'],80_000):
                        path=REPO/render['wav'];assert digest(path)==render['wav_sha256'];fs,audio=wavfile.read(path);assert fs==24000
                        x=np.ascontiguousarray(audio,dtype=np.float64);rec['new_dio_calls']=1
                        f0,times=pyworld.dio(x,fs,**p['dio']);f0=pyworld.stonemask(x,f0,times,fs)
                        dest=RESULT/'measurement'/f"{row['id']}.npz";write_checked(dest,npz_bytes(dio_f0=f0,dio_times=times))
                        rec.update(status='completed',metrics=evaluate(row,f0,times),npz=str(dest.relative_to(REPO)),npz_sha256=digest(dest))
                except Exception as exc:rec.update(status='failed',error=repr(exc))
            dest=RESULT/'measurement'/f"{row['id']}.json";save(dest,rec);part.append(rec);records.append({'id':row['id'],'record':str(dest.relative_to(REPO)),'sha256':digest(dest),'new_dio_calls':rec['new_dio_calls']})
            print({'measurement':row['id'],'status':rec['status'],'passed':rec.get('metrics',{}).get('passed',False)},flush=True)
        save(RESULT/f'{phase}-summary.json',aggregate(part))
    dev=read(RESULT/'development-summary.json');confirm=read(RESULT/'confirmation-summary.json')
    save(RESULT/'measurement-manifest.json',{'rows':records,'new_dio_calls':sum(r['new_dio_calls'] for r in records),
        'limited_synthetic_qualification':dev['all_passed'] and confirm['all_passed'],'japanese_quality_certified':False})
if __name__=='__main__':main()
