"""固定サイズの共有回帰とVTLだけによる未知文章の生成入口。"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import numpy as np
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from backend import Backend
from japanese_frontend import analyze
from shared_control import predict
from renderer import render


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--text',required=True)
    parser.add_argument('--model',choices=['direct_non_neural','distilled_non_neural'],required=True)
    parser.add_argument('--f0',type=float,default=220.)
    parser.add_argument('--speed',type=float,default=1.)
    parser.add_argument('--seed',type=int,default=20261002)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError('出力は上書きしません')
    if not 120<=args.f0<=300 or not .8<=args.speed<=1.25:
        raise ValueError('この研究版の入力範囲はF0 120〜300 Hz、速度0.8〜1.25です')
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:
            raise ValueError(f'bundle内のファイルが変更されています: {name}')
    analysis=analyze(args.text)
    if not 1<=len(analysis['phonemes'])<=120:
        raise ValueError('この研究版は1〜120音素の入力を対象とします')
    model=json.loads((ROOT/f'{args.model}.json').read_text())
    start=time.monotonic()
    durations,f0,bounds=predict(model,analysis,args.f0,args.speed)
    backend=Backend()
    try:
        audio,log=render(backend,analysis['phonemes'],durations,f0,args.seed)
    finally:
        backend.close()
    wavfile.write(args.output,24000,audio.astype(np.float32))
    forbidden=[name for name in sys.modules if name.split('.')[0] in
               ('torch','transformers','onnxruntime','tensorflow','faster_whisper','ctranslate2')]
    if forbidden:
        raise RuntimeError(f'ニューラル推論モジュールが読み込まれました: {forbidden}')
    print(json.dumps({'text':args.text,'model':args.model,'f0':args.f0,'speed':args.speed,
        'sha256_float64':hashlib.sha256(audio.astype('<f8').tobytes()).hexdigest(),
        'samples':len(audio),'sample_rate':24000,'seconds':time.monotonic()-start,
        'max_rss_bytes_macos':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'bounds':bounds,'runtime_neural':False,'forbidden_imports':forbidden,
        'control_generated_at_runtime':True,'quality_status':'未認定'},ensure_ascii=False))


if __name__=='__main__':
    main()
