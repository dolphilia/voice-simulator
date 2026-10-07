"""凍結済み制御を既存LF DSPでも再生し、生成機構の差を診断する。"""
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest
from acoustics import evaluate
from fit_controls import measure,loss
sys.path.insert(0,str(ROOT.parent/'autonomous-speech-synthesis/src'))
from autonomous_speech_synthesis import generator


def render_controlled(phones,durations,frequencies):
    original=generator.make_gestures
    def make_tracks(phonemes,prosody,voice,sample_rate):
        tracks,events=original(phonemes,prosody,voice,sample_rate)
        centers=np.array([(r['start_seconds']+r['end_seconds'])/2 for r in events])
        tracks['f0_hz']=np.interp(np.arange(len(tracks['f0_hz']))/sample_rate,centers,frequencies)
        return tracks,events
    generator.make_gestures=make_tracks
    try:
        return generator.render(phones,{'durations_seconds':durations,'f0_hz':220.,'intonation':False},seed=20261002)
    finally:
        generator.make_gestures=original


def main():
    rows=[r for r in json.loads((RESULT/'splits.json').read_text())['rows'] if r['split']=='audit']
    budget=Budget()
    for row in rows:
        fit=json.loads((RESULT/'fitted'/row['id']/'summary.json').read_text())
        for name in ('handwritten','direct_non_neural','neural_control','distilled_non_neural'):
            path=RESULT/'secondary-dsp'/name/row['id']
            if path.with_suffix('.json').exists():continue
            primary=fit['handwritten'] if name=='handwritten' else json.loads((RESULT/'comparisons'/name/f'{row["id"]}.json').read_text())
            control=primary['controls']
            with budget.job('render','LF対照/'+name+'/'+row['id'],3_000_000):
                start=time.monotonic()
                audio,log=render_controlled(row['phonemes'],control['durations_seconds'],control['f0_hz'])
                evaluation=evaluate(audio,{},24000)
                measured=measure(audio)
                path.parent.mkdir(parents=True,exist_ok=True)
                wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
                save(path.with_suffix('.json'),{'id':row['id'],'split':'audit','variant':name,
                    'seconds':time.monotonic()-start,'evaluation':evaluation,'measurement':measured,
                    'objective':loss(measured,fit['target']),'controls':control,
                    'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                    'scope':'同じ音素時間/F0標的、LF DSPの固定声道。F0は音素中心間の線形補間',
                    'adopted':False})
                print(row['id'],name,evaluation['E0_pass'],flush=True)


if __name__=='__main__':
    main()
