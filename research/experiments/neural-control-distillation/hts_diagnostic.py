"""日本語HMM音声合成を古典的な非ニューラル対照として測定する。"""
import json
import sys
from pathlib import Path
import time
import numpy as np
from scipy.io import wavfile
from scipy import signal
import pyopenjtalk
from budget import Budget,ROOT,RESULT,save,digest
from acoustics import evaluate
from fit_controls import measure


def main():
    rows=[r for r in json.loads((RESULT/'splits.json').read_text())['rows'] if r['split']=='audit']
    budget=Budget()
    for row in rows:
        path=RESULT/'hts'/row['id']
        if path.with_suffix('.json').exists():continue
        with budget.job('render','HTS対照/'+row['id'],3_000_000):
            start=time.monotonic()
            raw,fs=pyopenjtalk.synthesize(row['full_context_labels'],speed=1.,half_tone=0.)
            if fs!=48000:raise ValueError('HTSの標本化周波数が想定と異なります')
            y=signal.resample_poly(raw.astype(float)/32768,1,2)
            n=min(round(.012*24000),len(y)//2)
            e=np.sin(np.linspace(0,np.pi/2,n))**2;y[:n]*=e;y[-n:]*=e[::-1]
            path.parent.mkdir(exist_ok=True)
            wavfile.write(path.with_suffix('.wav'),24000,y.astype(np.float32))
            save(path.with_suffix('.json'),{'id':row['id'],'text':row['text'],'split':'audit','variant':'hts',
                'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                'seconds':time.monotonic()-start,'measurement':measure(y),'evaluation':evaluate(y,{},24000),
                'research_only':True,'runtime_neural':False,'shared_controller_adopted':False})
    package=Path(pyopenjtalk.__file__).parent
    save(RESULT/'hts-provenance.json',{'engine':'Open JTalk / HTS','pyopenjtalk':pyopenjtalk.__version__,
        'voice':'Mei normal','copyright':'2009-2013 Nagoya Institute of Technology, Department of Computer Science',
        'voice_license':'CC BY 3.0','license_sha256':digest(package/'htsvoice/LICENSE_mei_normal.htsvoice'),
        'voice_sha256':digest(package/'htsvoice/mei_normal.htsvoice'),'voice_bytes':(package/'htsvoice/mei_normal.htsvoice').stat().st_size,
        'scope':'既存の日本語HMM声の対照。今回の蒸留成功として数えない',
        'frontend':'同じ凍結済みfull-contextラベル。ニューラルアクセント推定なし'})


if __name__=='__main__':main()
