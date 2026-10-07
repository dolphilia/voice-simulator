"""高密度な分析再合成を補助対照とし、最終共有モデルと区別する。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest
from acoustics import evaluate
from fit_controls import measure,loss


def main():
    sys.path.insert(0,str(ROOT/'.cache/packages'))
    import pyworld as pw
    rows=[r for r in json.loads((RESULT/'splits.json').read_text())['rows'] if r['split']=='audit']
    budget=Budget()
    for row in rows:
        path=RESULT/'world'/row['id']
        if path.with_suffix('.json').exists():continue
        teacher=json.loads((RESULT/'teacher'/f'{row["id"]}.json').read_text())
        fs,x=wavfile.read(ROOT/teacher['wav'])
        x=x.astype(np.float64)
        with budget.job('render','WORLD分析再合成/'+row['id'],10_000_000):
            start=time.monotonic()
            raw_f0,t=pw.dio(x,fs,f0_floor=70,f0_ceil=450,frame_period=5.)
            f0=pw.stonemask(x,raw_f0,t,fs)
            sp=pw.cheaptrick(x,f0,t,fs)
            ap=pw.d4c(x,f0,t,fs)
            y=pw.synthesize(f0,sp,ap,fs,frame_period=5.)
            # 元波形の評価用の端点変換と同様、12msだけfade。レベル正規化はしない。
            n=min(round(.012*fs),len(y)//2)
            envelope=np.sin(np.linspace(0,np.pi/2,n))**2
            y[:n]*=envelope;y[-n:]*=envelope[::-1]
            path.parent.mkdir(exist_ok=True)
            np.savez_compressed(path.with_suffix('.npz'),f0=f0,spectrum=sp,aperiodicity=ap)
            wavfile.write(path.with_suffix('.wav'),fs,y.astype(np.float32))
            measured=measure(y,fs)
            save(path.with_suffix('.json'),{'id':row['id'],'text':row['text'],'split':'audit',
                'seconds':time.monotonic()-start,'version':pw.__version__,
                'source_sha256':teacher['wav_sha256'],'evaluation':evaluate(y,{},fs),
                'measurement':measured,'objective':loss(measured,measure(x,fs)),
                'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                'coefficient_count':int(f0.size+sp.size+ap.size),
                'research_only':True,'eligible_as_final_shared_model':False,
                'reason':'目標音声由来の高密度スペクトルと非周期性を使用。未知文の制御生成ではない'})
            print(row['id'],flush=True)
    save(RESULT/'world-provenance.json',{'package':'pyworld 0.3.5','wrapper_license':'MIT',
         'upstream':'https://github.com/mmorise/World','world_license':'modified BSD',
         'method_source':'https://github.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder',
         'purpose':'教師の同文再合成。VTLの制御/機構の切り分けにだけ使用'})


if __name__=='__main__':
    main()
