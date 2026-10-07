#!/usr/bin/env python3
"""台帳、保存結果、参照分割、ソース版と最終成果物を横断検証する。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,rows,digest,file_hash,write_once,code_manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-pilot-v1");args=parser.parse_args()
    path=ROOT/"results"/args.campaign
    identity=read(path/"identity.json");expected=digest(identity)
    events=rows(path/"ledger.jsonl");errors=[]
    completed=set();counts=Counter()
    for event in events:
        if event["event"]=="started":counts[event["budget_key"]]+=1
        elif event["event"]=="finished":
            key=(event["trial_id"],event["attempt"])
            if key in completed:errors.append(f"完了の重複: {key}")
            completed.add(key)
            trial=read(path/event["result"])
            if trial["identity"]!=expected:errors.append(f"版の不一致: {key}")
            request={k:trial[k] for k in ("candidate_id","backend","stage","task","seed","parameters","identity")}
            if digest(request)[:24]!=trial["trial_id"]:errors.append(f"試行IDの不一致: {key}")
            if not any(e["event"]=="started" and e["trial_id"]==key[0] and e["attempt"]==key[1] for e in events):errors.append(f"開始記録なし: {key}")
            if trial["status"]=="signal-qualified" and not trial["evaluation"]["E0_pass"]:errors.append(f"誤昇格: {key}")
    splits=read(path/"splits.json")
    names=list(splits["groups"])
    for i,a in enumerate(names):
        for b in names[i+1:]:
            if set(splits["groups"][a]["speakers"])&set(splits["groups"][b]["speakers"]):errors.append("話者分割の重複")
            if set(splits["groups"][a]["sentence_ids"])&set(splits["groups"][b]["sentence_ids"]):errors.append("文分割の重複")
    for key,used in counts.items():
        # P2はbackendごと、その他はcampaign合計。
        if key=="max_p2_per_backend":
            for backend in ("dsp","vtl"):
                n=sum(e["event"]=="started" and e.get("budget_key")==key and e["backend"]==backend for e in events)
                if n>identity["config"]["budget"][key]:errors.append("P2予算超過")
        elif used>identity["config"]["budget"][key]:errors.append(f"予算超過: {key}")
    current=code_manifest()
    if current!=identity["code"]:errors.append("実行時から生成・探索ソースが変更されている")
    files={str(p.relative_to(path)):file_hash(p) for p in sorted(path.rglob("*")) if p.is_file() and p.name not in (".run.lock","artifact-seal.json","audit.json") and "__pycache__" not in p.parts}
    result={"passed":not errors,"errors":errors,"finished_trials":len(completed),"started_attempts":sum(e["event"]=="started" for e in events),"counts":dict(counts),"source_identity_unchanged":current==identity["code"],"scope":"構造・来歴・分割・予算の監査。知覚品質の資格ではない。","script_sha256":file_hash(Path(__file__))}
    write_once(path/"artifact-seal.json",{"files":files,"count":len(files)})
    write_once(path/"audit.json",result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)


if __name__=="__main__":main()
