"""生成経路だけを許可リストで移出し、別プロセスで再生成する。"""
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from .io import ROOT,REPO,read,write_once,file_hash,digest
from .gestures import validate_voice

STANDALONE = '''"""参照・AIなしで動作する研究用かな/音素合成CLI。"""
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
'''


def export_bundle(path):
    voice=read(path/"voice-config.json");validate_voice(voice)
    policy=read(ROOT/"config/export-policy-v1.json")
    if len(json.dumps(voice).encode())>policy["max_voice_config_bytes"]:raise ValueError("話者設定の保存量超過です")
    def count(v):
        if isinstance(v,dict):return sum(count(x) for x in v.values())
        if isinstance(v,list):return sum(count(x) for x in v)
        return int(isinstance(v,(int,float)))
    if count(voice)>policy["max_numeric_coefficients"]:raise ValueError("共有係数数の上限超過です")
    bundle=path/"bundle";package=bundle/"autonomous_speech_synthesis"
    if (bundle/"manifest.json").exists():
        audit_bundle(bundle)
        return bundle
    package.mkdir(parents=True,exist_ok=True)
    for name in policy["allow_modules"]:
        source=ROOT/"src/autonomous_speech_synthesis"/name
        shutil.copyfile(source,package/name)
    write_once(bundle/"voice-config.json",voice)
    (bundle/"synthesize.py").write_text(STANDALONE)
    (bundle/"requirements.txt").write_text("numpy=="+__import__("numpy").__version__+"\nscipy=="+__import__("scipy").__version__+"\n")
    files={str(p.relative_to(bundle)):file_hash(p) for p in sorted(bundle.rglob("*")) if p.is_file()}
    write_once(bundle/"manifest.json",{"files":files,"voice_numeric_coefficients":count(voice),"source":"解析LFと共有音素規則のみ","status":"research-only-inconclusive","dependencies":["numpy","scipy"],"recorded_source":False,"neural_runtime":False,"license":"新規実装は本リポジトリ条件。VTLコード・モデルは移出しない"})
    audit_bundle(bundle)
    return bundle


def audit_bundle(bundle):
    manifest=read(bundle/"manifest.json")
    for name,expected in manifest["files"].items():
        if file_hash(bundle/name)!=expected:raise ValueError(f"bundleのハッシュ不一致: {name}")
    allowed=set(manifest["files"])|{"manifest.json","sandbox-profile.sb"}
    for p in bundle.rglob("*"):
        if not p.is_file():continue
        name=str(p.relative_to(bundle))
        if name not in allowed and "__pycache__" not in p.parts:
            raise ValueError(f"bundle内の未許可ファイル: {name}")
    imports=set()
    for p in (bundle/"autonomous_speech_synthesis").glob("*.py"):
        tree=ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node,ast.ImportFrom) and node.level==0:imports.add(node.module.split(".")[0])
            elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ("open","eval","exec","__import__"):
                raise ValueError("生成モジュールに外部I/Oまたは動的実行があります")
    if imports-{"copy","unicodedata","numpy","scipy","functools"}:raise ValueError("生成依存が許可リスト外です")
    return {"passed":True,"imports":sorted(imports),"manifest_sha256":file_hash(bundle/"manifest.json")}


def isolated_check(path):
    bundle=export_bundle(path)
    result_path=path/"isolation.json"
    if result_path.exists():return read(result_path)
    from .generator import render
    from .gestures import kana_to_phonemes
    text="むらさきのふねがゆっくりすすむ"
    voice=read(path/"voice-config.json")
    x,_=render(kana_to_phonemes(text),{"f0_hz":180.,"speed":1.2},voice,1009)
    expected=hashlib.sha256(x.astype("<f8").tobytes()).hexdigest()
    output=path/"isolated-unknown.wav"
    command=[sys.executable,"-I",str(bundle/"synthesize.py"),"--text",text,"--f0","180","--speed","1.2","--seed","1009","--audit","--output",str(output)]
    run=subprocess.run(command,cwd=bundle,env={"PATH":"/usr/bin:/bin","OPENBLAS_NUM_THREADS":"1","PYTHONDONTWRITEBYTECODE":"1"},capture_output=True,text=True,timeout=120)
    result={"command":command,"returncode":run.returncode,"stderr":run.stderr,"static_audit":audit_bundle(bundle),"isolation_method":"Python監査フック（生成開始後の外部open/socketを拒否）。OS制約の結果は別ファイルで保存。","expected_sha256_float64":expected,"passed":False}
    if run.returncode==0:
        child=json.loads(run.stdout);result["child"]=child;result["passed"]=child["sha256_float64"]==expected
    write_once(result_path,result)
    # OSのSeatbelt検査用。システムと数値ライブラリだけを読み取り許可。
    allowed=["/System","/usr/lib","/usr/share","/Library/Apple", "/opt/homebrew",str(Path(sys.prefix)),str(bundle)]
    profile="(version 1)\n(deny default)\n(allow process-exec process-fork sysctl-read mach-lookup)\n"
    profile+="(allow file-read* "+" ".join("(subpath "+json.dumps(p)+")" for p in allowed)+" (literal \"/dev/urandom\") (literal \"/dev/null\"))\n"
    profile+="(allow file-write* (literal "+json.dumps(str(path/"os-isolated-unknown.wav"))+"))\n"
    (bundle/"sandbox-profile.sb").write_text(profile)
    return result
