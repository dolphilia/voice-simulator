"""日本語HMMと固定回帰だけで文章を生成する、二段の研究用実行入口。"""
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
from japanese_frontend import analyze
from hts_core import render_hts,aggregate_settings,measure
from acoustics import evaluate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--text',required=True)
    parser.add_argument('--model',choices=['direct_non_neural','distilled_non_neural'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('出力は上書きしません')
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:raise ValueError('bundleのハッシュ不一致: '+name)
    analysis=analyze(args.text)
    if not 1<=len(analysis['phonemes'])<=120:raise ValueError('1〜120音素の研究版です')
    model=json.loads((ROOT/f'{args.model}.json').read_text())
    start=time.monotonic()
    base=render_hts(analysis,ROOT/'mei_normal.htsvoice')
    base_measurement=measure(base)
    settings=aggregate_settings(analysis,model,base_measurement)
    del base
    audio=render_hts(analysis,ROOT/'mei_normal.htsvoice',settings['speed'],settings['half_tone'])
    raw_peak=float(np.max(np.abs(audio)))
    output_gain=min(1.,.95/raw_peak) if raw_peak>0 else 1.
    # 全区間に同じ利得を掛ける。波形の切り詰めや局所コンプレッションは行わない。
    audio=audio*output_gain
    evaluation=evaluate(audio,{},24000)
    if not evaluation['E0_pass']:raise ValueError('生成波形の工学条件を満たしません')
    forbidden=[name for name in sys.modules if name.split('.')[0] in
               ('torch','transformers','onnxruntime','tensorflow','faster_whisper','ctranslate2','sherpa_onnx')]
    if forbidden:raise RuntimeError('ニューラルモジュールを検出しました')
    wavfile.write(args.output,24000,audio.astype(np.float32))
    print(json.dumps({'text':args.text,'model':args.model,'settings':settings,
        'sha256_float64':hashlib.sha256(audio.astype('<f8').tobytes()).hexdigest(),
        'samples':len(audio),'sample_rate':24000,'seconds':time.monotonic()-start,
        'max_rss_bytes_macos':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'synthesis_calls':2,'runtime_neural':False,'forbidden_imports':forbidden,
        'raw_peak':raw_peak,'output_gain':output_gain,
        'control_generated_at_runtime':True,'baseline_replayed':False,'E0_pass':evaluation['E0_pass'],
        'quality_status':'未認定'},ensure_ascii=False))


if __name__=='__main__':main()
