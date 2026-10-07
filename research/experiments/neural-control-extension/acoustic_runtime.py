"""固定回帰と非ニューラルHMMによる3回生成の研究用入口。"""
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
from acoustic_control import predict,measure_wide,map_to_hts,refine_hts
from japanese_frontend import analyze
from hts_core import render_hts
from acoustics import evaluate


def normalize(audio):
    peak=float(np.max(abs(audio)));gain=min(1.,.95/peak) if peak else 1.
    return (audio*gain).astype(np.float32),peak,gain


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--text',required=True)
    parser.add_argument('--model',choices=['direct_non_neural','distilled_non_neural'],required=True)
    parser.add_argument('--pitch-reference',type=float,default=220.)
    parser.add_argument('--speed',type=float,default=1.)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('既存の出力を上書きしません')
    for name,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('bundleハッシュ不一致')
    start=time.monotonic();row=analyze(args.text)
    model=json.loads((ROOT/(args.model+'.json')).read_text())
    target=predict(model,row,args.pitch_reference,args.speed)
    base=measure_wide(render_hts(row,ROOT/'mei_normal.htsvoice'))
    initial=map_to_hts(target,base)
    first,_,_=normalize(render_hts(row,ROOT/'mei_normal.htsvoice',initial['speed'],initial['half_tone']))
    settings=refine_hts(target,initial,measure_wide(first))
    audio,peak,gain=normalize(render_hts(row,ROOT/'mei_normal.htsvoice',settings['speed'],settings['half_tone']))
    evaluation=evaluate(audio,{},24000)
    if not evaluation['E0_pass']:raise ValueError('信号の健全性検査に不通過')
    forbidden=[name for name in sys.modules if name.split('.')[0] in ('torch','tensorflow','transformers','onnxruntime','faster_whisper','ctranslate2','sherpa_onnx')]
    if forbidden:raise RuntimeError('ニューラル依存の読込を検出')
    wavfile.write(args.output,24000,audio)
    print(json.dumps({'text':args.text,'model':args.model,'target':target,'initial_settings':initial,'settings':settings,
        'measurement':measure_wide(audio),'E0_pass':True,'runtime_neural':False,'forbidden_imports':forbidden,
        'synthesis_calls':3,'seconds':time.monotonic()-start,'max_rss_bytes_macos':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'sha256_float32':hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest(),'raw_peak':peak,'output_gain':gain,
        'quality_status':'内容と自然さは未検証の研究版'},ensure_ascii=False))


if __name__=='__main__':main()
