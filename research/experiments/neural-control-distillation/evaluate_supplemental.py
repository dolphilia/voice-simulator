"""補助対照の同じ正規化と、別方式ASRによる監査を行う。"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from scipy.io import wavfile
from scipy import signal
from budget import Budget,ROOT,RESULT,save,digest

OLD=ROOT.parent/'autonomous-speech-synthesis'
sys.path.insert(0,str(OLD))
from diagnostics import normalize_text,edit_distance


def supplemental_sources():
    rows=json.loads((RESULT/'splits.json').read_text())['rows']
    sources=[]
    for row in rows:
        if row['split']!='audit':continue
        for directory,variant in [('world','world'),('hts','hts')]+[
                (f'secondary-dsp/{v}',f'lf-{v}') for v in ('handwritten','direct_non_neural','neural_control','distilled_non_neural')]:
            rec=json.loads((RESULT/directory/f'{row["id"]}.json').read_text())
            sources.append({'id':row['id'],'text':row['text'],'variant':variant,'wav':str(ROOT/rec['wav']),
                            'scope':'補助対照。主比較モデルを変更しない'})
    natural=json.loads((RESULT/'natural-comparison/protocol.json').read_text())['rows']
    for row in natural:
        for name in ('natural','teacher','handwritten','direct_non_neural','distilled_non_neural'):
            rec=json.loads((RESULT/'natural-comparison'/row['id']/f'{name}.json').read_text())
            path=Path(rec['wav'])
            sources.append({'id':row['id'],'text':row['text'],'variant':'natural-pair-'+name,
                            'wav':str(path if path.is_absolute() else ROOT/path),
                            'scope':'既知の開発参照であり独立確認ではない'})
    return sources


def second_sources():
    primary=[]
    for row in json.loads((RESULT/'splits.json').read_text())['rows']:
        if row['split']!='audit':continue
        for name in ('teacher','handwritten','reference_fitted','direct_non_neural','neural_control','distilled_non_neural'):
            rec=json.loads((RESULT/'content'/name/f'{row["id"]}.json').read_text())
            primary.append({'id':row['id'],'text':row['text'],'variant':name,'wav':str(ROOT/rec['wav']),
                            'scope':'凍結後の別方式監査。新しいモデル選択には利用しない'})
    return primary+[r for r in supplemental_sources() if r['variant'] in ('world','hts','natural-pair-natural')]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--second',action='store_true')
    parser.add_argument('--transfer',action='store_true')
    parser.add_argument('--transfer-controls',action='store_true')
    parser.add_argument('--hts-runtime',action='store_true')
    parser.add_argument('--gain-repair',action='store_true')
    args=parser.parse_args()
    os.environ['HF_HUB_OFFLINE']='1'
    budget=Budget()
    import pyopenjtalk
    with budget.job('setup','補助ASRの読込',1_000_000):
        if args.second:
            sys.path.insert(0,str(ROOT/'.cache/packages'))
            import sherpa_onnx
            cache=ROOT/'.cache/reazonspeech'
            model=sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(cache/'encoder-epoch-99-avg-1.int8.onnx'),
                decoder=str(cache/'decoder-epoch-99-avg-1.int8.onnx'),
                joiner=str(cache/'joiner-epoch-99-avg-1.int8.onnx'),tokens=str(cache/'tokens.txt'),
                num_threads=2,sample_rate=16000,feature_dim=80,decoding_method='greedy_search',provider='cpu')
        else:
            from faster_whisper import WhisperModel
            model=WhisperModel('base',device='cpu',compute_type='int8',cpu_threads=4,
                               download_root=str(OLD/'.cache/ai/whisper'),local_files_only=True)
    sources=second_sources() if args.second else supplemental_sources()
    directory='second-asr' if args.second else 'supplemental-content'
    if args.transfer or args.transfer_controls:
        sources=[]
        rows=json.loads((RESULT/'hts-transfer/protocol.json').read_text())['rows']
        for row in rows:
            names=('direct_non_neural','neural_control') if args.transfer_controls else ('teacher','baseline','distilled')
            for name in names:
                record=json.loads((RESULT/'hts-transfer'/row['id']/f'{name}.json').read_text())
                sources.append({'id':row['id'],'text':row['text'],'variant':name,'wav':str(ROOT/record['wav']),
                                'scope':'HMMへの発話単位移行を新しい4文で診断。選択・調整には使用しない'})
        directory='transfer-second-asr' if args.second else 'transfer-content'
    if args.hts_runtime:
        sources=[]
        contract=json.loads((RESULT/'hts-runtime-audit-v2/contract.json').read_text())
        for model_name in contract['models']:
            for i,text in enumerate(contract['tests']):
                sources.append({'id':f'runtime-{i:02d}','text':text,'variant':model_name,
                    'wav':str(RESULT/'hts-runtime-audit-v2'/f'{model_name}-{i}-normal.wav'),
                    'scope':'出力利得修正版の内容診断。最初の文は工学修正に再利用しており独立品質確認とはしない'})
        directory='hts-runtime-second-asr' if args.second else 'hts-runtime-content'
    if args.gain_repair:
        sources=[]
        for p in sorted((RESULT/'hts-transfer-gain-v2').glob('new-*/*.json')):
            rec=json.loads(p.read_text())
            sources.append({'id':rec['id'],'text':rec['text'],'variant':p.stem,'wav':str(ROOT/rec['wav']),
                            'scope':'同じ4文の利得修正。品質の独立再確認として数えない'})
        directory='transfer-gain-second-asr' if args.second else 'transfer-gain-content'
    for row in sources:
        path=RESULT/directory/row['variant']/f'{row["id"]}.json'
        if path.exists():
            if json.loads(path.read_text())['wav_sha256']!=digest(row['wav']):
                raise ValueError('評価済み音声が変更されています')
            continue
        if args.gain_repair:
            old_dir='transfer-second-asr' if args.second else 'transfer-content'
            old_path=RESULT/old_dir/row['variant']/f'{row["id"]}.json'
            old=json.loads(old_path.read_text())
            if old['wav_sha256']==digest(row['wav']):
                save(path,{**old,**row,'reused_from':str(old_path.relative_to(ROOT)),
                    'reuse_reason':'WAVのSHA-256が完全一致。新しいAI評価・独立例として計数しない'})
                continue
        with budget.job('ai',directory+'/'+row['variant']+'/'+row['id'],500_000):
            start=time.monotonic()
            if args.second:
                fs,raw=wavfile.read(row['wav'])
                scale=32768. if raw.dtype==np.int16 else 1.
                audio=raw.astype(np.float32)/scale
                if audio.ndim!=1:raise ValueError('単一チャンネルを要求します')
                if fs!=16000:
                    from math import gcd
                    common=gcd(fs,16000)
                    audio=signal.resample_poly(audio,16000//common,fs//common).astype(np.float32)
                stream=model.create_stream()
                stream.accept_waveform(16000,audio)
                model.decode_stream(stream)
                hyp=stream.result.text
            else:
                segments,_=model.transcribe(row['wav'],language='ja',beam_size=5,initial_prompt=None,
                                            condition_on_previous_text=False,vad_filter=False)
                hyp=''.join(s.text for s in segments)
            ref=normalize_text(pyopenjtalk.g2p(row['text'],kana=True))
            pred=normalize_text(pyopenjtalk.g2p(hyp,kana=True)) if hyp else ''
            errors=edit_distance(ref,pred)
            save(path,{**row,'hypothesis':hyp,'reference_kana':ref,'predicted_kana':pred,'errors':errors,
                'characters':len(ref),'kana_cer':errors/max(1,len(ref)),'seconds':time.monotonic()-start,
                'wav_sha256':digest(row['wav']),'engine':'ReazonSpeech k2 int8 greedy' if args.second else 'Whisper base int8 beam5',
                'used_in_optimization':False,'perception_qualification':False})
            print(row['id'],row['variant'],errors/max(1,len(ref)),flush=True)


if __name__=='__main__':main()
