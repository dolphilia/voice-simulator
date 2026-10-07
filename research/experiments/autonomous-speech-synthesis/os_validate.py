#!/usr/bin/env python3
"""macOS Seatbeltで参照・モデル・ネットワークを拒否した実行検査。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash,REPO


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-pilot-v1");parser.add_argument("--attempt",type=int,default=1);args=parser.parse_args()
    path=ROOT/"results"/args.campaign;bundle=path/"bundle"
    expected=read(path/"isolation.json")
    probe=ROOT/"os_isolation_probe.py"
    profile=(bundle/"sandbox-profile.sb").read_text()
    profile+='(allow file-read-metadata)\n(allow file-read* (literal '+json.dumps(str(probe))+'))\n'
    profile+='(allow file-write* (literal "/dev/null"))\n'
    suffix="" if args.attempt==1 else f"-v{args.attempt}"
    if args.attempt>1:
        denied=[str(REPO/"research/data"),str(ROOT/".cache"),str(ROOT/".venv-eval"),str(Path.home()/".cache")]
        profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+" ".join('(subpath '+json.dumps(p)+')' for p in denied)+')\n'
    target=path/("os-isolation"+suffix+".sb")
    if target.exists() and target.read_text()!=profile:raise FileExistsError("隔離条件の上書きは禁止です")
    target.write_text(profile)
    command=["/usr/bin/sandbox-exec","-f",str(target),sys.executable,"-I",str(bundle/"synthesize.py"),"--text","むらさきのふねがゆっくりすすむ","--f0","180","--speed","1.2","--seed","1009","--audit","--output",str(path/("os-isolated-unknown"+suffix+".wav"))]
    run=subprocess.run(command,cwd=bundle,capture_output=True,text=True,timeout=120)
    natural=REPO/read(path/"splits.json")["groups"]["development"]["records"][0]["wav"]
    model=ROOT/".cache/ai/utmosv2/models/fusion_stage3/fold0_s42_best_model.pth"
    probe_cmd=["/usr/bin/sandbox-exec","-f",str(target),sys.executable,"-I",str(probe),str(natural),str(model)]
    checked=subprocess.run(probe_cmd,cwd=bundle,capture_output=True,text=True,timeout=30)
    result={"method":"macOS Seatbelt参照/モデル/ネットワーク拒否 + Python生成I/O許可リスト" if args.attempt>1 else "macOS Seatbelt deny-default","profile_sha256":file_hash(target),"command":command,"returncode":run.returncode,"stderr":run.stderr,"probe_returncode":checked.returncode,"probe_stderr":checked.stderr,"passed":False}
    if run.returncode==0 and checked.returncode==0:
        output=json.loads(run.stdout);checks=json.loads(checked.stdout)
        result.update(output=output,denial_probes=checks,passed=output["sha256_float64"]==expected["expected_sha256_float64"] and all(v is True for v in checks.values()))
    write_once(path/("os-isolation"+suffix+".json"),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
