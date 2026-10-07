"""旧開発群の3自然参照と同文の教師・非ニューラル出力を診断する。"""
import argparse
import json
import sys
import time
import numpy as np
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest
from renderer import baseline,render
from shared_control import predict
from acoustics import evaluate
from fit_controls import measure

OLD=ROOT.parent/'autonomous-speech-synthesis'
REPO=ROOT.parents[2]
sys.path.insert(0,str(OLD))
sys.path.insert(0,str(OLD/'src'))
from japanese_frontend import analyze
from autonomous_speech_synthesis.backends import VTL


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    out=RESULT/'natural-comparison'
    budget=Budget()
    if args.prepare_only:
        with budget.job('setup','自然参照の事前選択',2_000_000):
            split=json.loads((OLD/'results/ans-pilot-v1/splits.json').read_text())
            speakers,sentences,rows=set(),set(),[]
            for row in split['groups']['development']['records']:
                if row['speaker'] in speakers or row['sentence'] in sentences:continue
                path=REPO/row['wav']
                transcript=path.parent.parent/'transcripts_utf8.txt'
                texts=dict(line.split(':',1) for line in transcript.read_text().splitlines() if ':' in line)
                if digest(path)!=row['sha256']:
                    raise ValueError('自然参照のhashが不一致です')
                rows.append({**row,'text':texts[row['sentence']], 'analysis':analyze(texts[row['sentence']])})
                speakers.add(row['speaker']);sentences.add(row['sentence'])
                if len(rows)==3:break
            save(out/'protocol.json',{'rows':rows,'source_manifest_sha256':digest(OLD/'results/ans-pilot-v1/splits.json'),
                'license_url':split['license_url'],'selection':'開発群の登録順から話者・文が重複しない最初の3件',
                'purpose':'既知の自然参照による測定と教師の偏りの点検。独立確認の件数へ加算しない',
                'paired_content':True,'voice_matched':False,'models_frozen_before_comparison':True})
        return
    rows=json.loads((out/'protocol.json').read_text())['rows']
    from teacher import load_teacher
    import torch
    with budget.job('setup','自然参照対照の教師を読み込む',1_000_000):
        teacher,voice,g2p=load_teacher()
    for row in rows:
        path=out/row['id']/'teacher.json'
        if path.exists():continue
        with budget.job('teacher','自然参照と同文/'+row['id'],10_000_000):
            phonemes,_=g2p(row['text'])
            if set(phonemes)-set(teacher.vocab):raise ValueError('教師の音素記号が未対応です')
            torch.manual_seed(20261002)
            start=time.monotonic()
            audio=teacher(phonemes,voice[len(phonemes)-1],speed=1.).numpy()
            path.parent.mkdir(parents=True,exist_ok=True)
            wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
            save(path,{'id':row['id'],'text':row['text'],'phonemes':phonemes,'seconds':time.monotonic()-start,
                       'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                       'human_recording':False,'research_only':True})
    del teacher
    vtl=VTL()
    try:
        for row in rows:
            fs,raw=wavfile.read(REPO/row['wav'])
            audio=raw.astype(float)/32768
            source=out/row['id']/'natural.json'
            if not source.exists():
                save(source,{'id':row['id'],'text':row['text'],'wav':str(REPO/row['wav']),
                     'sha256':digest(REPO/row['wav']),'measurement':measure(audio,fs),
                     'human_recording':True,'historically_used_development_reference':True})
            for name in ('handwritten','direct_non_neural','distilled_non_neural'):
                path=out/row['id']/f'{name}.json'
                if path.exists():continue
                if name=='handwritten':d,f=baseline(row['analysis']);bounds={}
                else:d,f,bounds=predict(json.loads((RESULT/'models'/f'{name}.json').read_text()),row['analysis'])
                with budget.job('render','自然参照対照/'+name+'/'+row['id'],10_000_000):
                    start=time.monotonic()
                    audio,log=render(vtl,row['analysis']['phonemes'],d,f)
                    wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
                    save(path,{'id':row['id'],'text':row['text'],'variant':name,'evaluation':evaluate(audio,{},24000),
                        'seconds':time.monotonic()-start,'controls':log,'bounds':bounds,
                        'measurement':measure(audio),'wav':str(path.with_suffix('.wav').relative_to(ROOT)),
                        'sha256':digest(path.with_suffix('.wav'))})
                    print(row['id'],name,flush=True)
    finally:vtl.close()


if __name__=='__main__':
    main()
