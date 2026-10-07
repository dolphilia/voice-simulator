"""参照・AIなしで動作する研究用かな/音素合成CLI。"""
import argparse, json, sys, hashlib, time
from pathlib import Path
import numpy as np
from scipy.io import wavfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from autonomous_speech_synthesis.generator import render
from autonomous_speech_synthesis.gestures import kana_to_phonemes

parser=argparse.ArgumentParser()
parser.add_argument("--text")
parser.add_argument("--phonemes")
parser.add_argument("--f0",type=float,default=220.)
parser.add_argument("--speed",type=float,default=1.)
parser.add_argument("--seed",type=int,default=1009)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--audit",action="store_true")
args=parser.parse_args()
root=Path(__file__).resolve().parent
voice=json.loads((root/"voice-config.json").read_text())
access=[]
def audit(event,values):
    if event.startswith("socket."):
        raise PermissionError("生成中のネットワークは禁止です")
    if event=="open" and isinstance(values[0],(str,bytes)):
        p=Path(values[0]).resolve()
        access.append(str(p))
        if p!=args.output.resolve() and root not in p.parents:
            raise PermissionError("生成中の外部ファイル参照は禁止です")
if args.audit:sys.addaudithook(audit)
if bool(args.text)==bool(args.phonemes):raise ValueError("textかphonemesのどちらか一方が必要です")
phones=args.phonemes.split() if args.phonemes else kana_to_phonemes(args.text)
start=time.monotonic()
x,log=render(phones,{"f0_hz":args.f0,"speed":args.speed},voice,args.seed)
elapsed=time.monotonic()-start
if args.output.exists():raise FileExistsError("既存WAVは上書きしません")
wavfile.write(args.output,24000,x.astype(np.float32))
print(json.dumps({"sha256_float64":hashlib.sha256(x.astype("<f8").tobytes()).hexdigest(),"seconds":elapsed,"rtf":elapsed/(len(x)/24000),"samples":len(x),"access_log":access,"contains_recording":False},ensure_ascii=False))
