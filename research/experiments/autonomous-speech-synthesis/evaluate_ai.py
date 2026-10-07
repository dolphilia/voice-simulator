#!/usr/bin/env python3
"""専用環境でのみ実行する診断器。採否資格を自動付与しない。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

root=Path(__file__).resolve().parent
cache=root/".cache/ai"
os.environ.setdefault("HF_HOME",str(cache/"huggingface"))
os.environ.setdefault("TORCH_HOME",str(cache/"torch"))
os.environ.setdefault("NUMBA_CACHE_DIR",str(cache/"numba"))
os.environ.setdefault("UTMOSV2_CHACHE",str(cache/"utmosv2"))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError("既存のAI評価結果は上書きしません")
    start=time.monotonic()
    result={"model":"UTMOSv2","status":"unavailable","adoption_authority":False,"reason":"日本語物理合成に対応した公開人間評点の校正なし","rows":[]}
    try:
        import torch
        torch.set_num_threads(4)
        import utmosv2
        result["version"]=utmosv2.__version__
        model=utmosv2.create_model(pretrained=True,device="cpu")
        result["status"]="diagnostic-only"
        if args.manifest:
            manifest=json.loads(args.manifest.read_text())
            if len(manifest)>300:raise ValueError("AI評価300件の予算上限を超えます")
            for row in manifest:
                item=dict(row)
                try:
                    before=time.monotonic()
                    item.update(prediction=float(model.predict(input_path=str(row["path"]),device="cpu",num_workers=0,verbose=False)),seconds=time.monotonic()-before)
                except Exception as exc:item.update(prediction=None,error=repr(exc))
                result["rows"].append(item)
    except Exception as exc:
        result["error"]=repr(exc)
    result["elapsed_seconds"]=time.monotonic()-start
    result["script_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if result["rows"] and all(r.get("prediction") is None for r in result["rows"]):
        result["status"]="unavailable"
    result["weights"]=[]
    for p in sorted(cache.rglob("*")):
        if p.is_file() and p.stat().st_size>1_000_000:
            h=hashlib.sha256()
            with p.open("rb") as f:
                for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
            result["weights"].append({"path":str(p.relative_to(root)),"sha256":h.hexdigest(),"bytes":p.stat().st_size})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x") as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows","weights")},ensure_ascii=False))


if __name__=="__main__":main()
