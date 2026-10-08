"""JSONの共有母音列だけから生成する独立CLI。過去波形/台帳/教師を参照しない。"""
import argparse,json,sys,hashlib
from pathlib import Path
from scipy.io import wavfile
from sequence_tract import generate,OUTFS
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();request=json.loads(sys.stdin.read());audio,meta,*_=generate(request)
path=Path(a.output);wavfile.write(path,OUTFS,audio.astype('float32'));meta.update(wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),request=request,HMM=False,neural_inference=False,recorded_audio=False,utterance_lookup=False,quality_certified=False)
print(json.dumps(meta,ensure_ascii=False))
