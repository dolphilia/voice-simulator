"""同じ共有制御を日本語HMMへ発話単位で移す、追加の未知文比較。"""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy import signal
from scipy.io import wavfile
from budget import Budget,ROOT,RESULT,save,digest
from shared_control import predict
from acoustics import evaluate
from fit_controls import measure,loss

OLD=ROOT.parent/'autonomous-speech-synthesis'
sys.path.insert(0,str(OLD))
from japanese_frontend import analyze
TEXTS=['池に石を落とす。','太い竹を切る。','森で虫が鳴く。','白い布を広げる。']


def render_hts(analysis,voice_path,speed=1.,half_tone=0.):
    import pyopenjtalk
    engine=pyopenjtalk.HTSEngine(str(voice_path).encode())
    try:
        engine.set_speed(float(speed));engine.add_half_tone(float(half_tone))
        raw=engine.synthesize(analysis['full_context_labels'])
        fs=engine.get_sampling_frequency()
    finally:
        engine.clear()
    if fs!=48000:raise ValueError('HTS標本化周波数が想定と異なります')
    audio=signal.resample_poly(np.asarray(raw,dtype=float)/32768,1,2)
    n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio


def aggregate_settings(analysis,model,base_measurement):
    d,f,bounds=predict(model,analysis)
    desired={'active_seconds':float(sum(d)),'f0_hz':float(np.exp(np.sum(d*np.log(f))/sum(d)))}
    speed=base_measurement['active_seconds']/desired['active_seconds']
    half_tone=12*np.log2(desired['f0_hz']/base_measurement['f0_hz'])
    return {'speed':float(np.clip(speed,.6,1.6)),'half_tone':float(np.clip(half_tone,-6.,6.)),
            'unbounded_speed':float(speed),'unbounded_half_tone':float(half_tone),
            'desired':desired,'phone_bounds':bounds}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    out=RESULT/'hts-transfer'
    budget=Budget()
    if args.prepare_only:
        with budget.job('setup','HMMへの制御移行・新規4文の契約固定',2_000_000):
            old=json.loads((RESULT/'splits.json').read_text())['rows']
            if set(TEXTS)&{r['text'] for r in old}:raise ValueError('新しい文が既存分割と重複しています')
            save(out/'protocol.json',{
                'rows':[{'id':f'new-{i:02d}',**analyze(text)} for i,text in enumerate(TEXTS)],
                'reason':'VTLでは韻律の改善が内容保持へ結び付かず、HMM対照は共有VTLより低誤りだったため生成器を切り分ける。ただしHMMにもASR間の差と誤りが残る',
                'source_model_sha256':digest(RESULT/'models/distilled_non_neural.json'),
                'model_retrained':False,'new_teacher_generations':4,'primary_render_calls':8,
                'new_asr_evaluations':24,'hard_campaign_limits_unchanged':True,
                'allocation':'主比較と補助対照で246 AI評価、追加24で270予定。初期予定250との差20は上限300内の残枠を使用し、新campaignへ延長しない',
                'comparison':['neural_teacher','hts_baseline','hts_distilled_global_controls'],
                'held_out_before_generation':True,
                'unknown_scope':'4つの新規文。共有語と既知音素は含む。広範な日本語の認定ではない',
                'controller_mapping':'予測音素時間の和と、時間重み付き対数F0平均をHMMの速度・半音補正へ移す',
                'native_contour':'HMMの句内F0と状態時間は残る。音素ごとの軌跡全体の移植とは呼ばない',
                'selection':'パラメータ・モデルをこの4文で調整しない。両ASRの内容悪化を記録し、品質認定へ昇格しない',
                'source_is_not_recording':'HMMは小さい共有統計モデル。基準波形は自身で一時生成し、最終音声は補正指定で再生成する。波形加工・検索再生はしない'})
        return
    protocol=json.loads((out/'protocol.json').read_text())
    model_path=RESULT/'models/distilled_non_neural.json'
    if digest(model_path)!=protocol['source_model_sha256']:raise ValueError('共有モデルが変わりました')
    model=json.loads(model_path.read_text())
    import pyopenjtalk
    voice_path=Path(pyopenjtalk.__file__).parent/'htsvoice/mei_normal.htsvoice'
    from teacher import load_teacher
    import torch
    with budget.job('setup','追加4文の教師読込',1_000_000):
        teacher,voice,g2p=load_teacher()
    for row in protocol['rows']:
        path=out/row['id']/'teacher.json'
        if path.exists():continue
        with budget.job('teacher','追加未知文/'+row['id'],3_000_000):
            phones,_=g2p(row['text'])
            if set(phones)-set(teacher.vocab):raise ValueError('教師の未対応記号です')
            torch.manual_seed(20261002)
            audio=teacher(phones,voice[len(phones)-1],speed=1.).numpy()
            path.parent.mkdir(parents=True,exist_ok=True)
            wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
            save(path,{'id':row['id'],'text':row['text'],'phonemes':phones,'measurement':measure(audio),
                       'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                       'research_only':True,'seed':20261002})
    del teacher
    for row in protocol['rows']:
        teacher_record=json.loads((out/row['id']/'teacher.json').read_text())
        base_path=out/row['id']/'baseline.json'
        if not base_path.exists():
            with budget.job('render','追加未知文HTS基準/'+row['id'],3_000_000):
                audio=render_hts(row,voice_path)
                base_measurement=measure(audio)
                wavfile.write(base_path.with_suffix('.wav'),24000,audio.astype(np.float32))
                save(base_path,{'id':row['id'],'text':row['text'],'measurement':base_measurement,
                    'evaluation':evaluate(audio,{},24000),'objective':loss(base_measurement,teacher_record['measurement']),
                    'wav':str(base_path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(base_path.with_suffix('.wav'))})
        base=json.loads(base_path.read_text())
        path=out/row['id']/'distilled.json'
        if path.exists():continue
        settings=aggregate_settings(row,model,base['measurement'])
        with budget.job('render','追加未知文HTS蒸留制御/'+row['id'],3_000_000):
            audio=render_hts(row,voice_path,settings['speed'],settings['half_tone'])
            measured=measure(audio)
            wavfile.write(path.with_suffix('.wav'),24000,audio.astype(np.float32))
            save(path,{'id':row['id'],'text':row['text'],'settings':settings,'measurement':measured,
                'evaluation':evaluate(audio,{},24000),'objective':loss(measured,teacher_record['measurement']),
                'wav':str(path.with_suffix('.wav').relative_to(ROOT)),'sha256':digest(path.with_suffix('.wav')),
                'reference_used_by_controller':False,'runtime_neural':False,
                'baseline_waveform_replayed_or_modified':False})
            print(row['id'],base['objective'],loss(measured,teacher_record['measurement']),flush=True)


if __name__=='__main__':main()
