#!/usr/bin/env python3
"""明瞭性残差に対する低F0/低速度の事前固定比較。自然さ昇格はしない。"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash
from autonomous_speech_synthesis.runner import Campaign
from autonomous_speech_synthesis.backends import VTL
from vtl_speech import render_vtl


def main():
    parent=ROOT/"results/ans-vtl-speech-v1"
    config=read(ROOT/"config/campaign-v1.json")
    config.update(branch="VTLで短文のかなCERが大きいため、男性声道に対するF0と速度の不一致を切り分ける",branch_source_sha256=file_hash(Path(__file__)),parent_source_sha256=file_hash(ROOT/"vtl_speech.py"),model_version="vtl-jd3-gesture-v1")
    campaign=Campaign("ans-vtl-control-v1",config);vtl=VTL()
    try:
        suite=read(parent/"task-suite.json")
        tasks=[t for t in suite["tasks"] if t["stage"]=="P4"][:8]
        configs=[{"id":"f160-s100","f0":160.,"speed":1.},{"id":"f160-s085","f0":160.,"speed":.85}]
        write_once(campaign.path/"model-registry.json",{"id":"vtl-jd3-gesture-v1","parent_campaign":parent.name,"allowed_control_changes":["f0_hz","speed"],"perceptual_adoption":False})
        write_once(campaign.path/"task-suite.json",suite)
        write_once(campaign.path/"splits.json",read(parent/"splits.json"))
        write_once(campaign.path/"frozen-config.json",{"settings":configs,"task_ids":[t["id"] for t in tasks],"seeds":[41,43],"reason":config["branch"],"selection_method":"別保存の音響・CER診断のみ。知覚資格を変更しない","confirmation_opened":False})
        rows=[]
        for cfg in configs:
            for task in tasks:
                for seed in (41,43):
                    out=campaign.trial(cfg["id"],"vtl","P4",task,seed,cfg,
                        lambda t=task,s=seed,c=cfg:render_vtl(vtl,t["phonemes"],f0=c["f0"],speed=c["speed"],seed=s),save=seed==41)
                    rows.append({"variant":cfg["id"],"task":task["id"],"kind":"sentence","seed":seed,"trial_id":out["trial_id"],"evaluation":out["evaluation"],"wav":out.get("wav")})
                print(cfg["id"],task["id"],flush=True)
        write_once(campaign.path/"p34-speech.json",{"rows":rows,"quality_status":"inconclusive","backend":"vtl","purpose":config["branch"]})
        write_once(campaign.path/"decision.json",{"state":"inconclusive","quality_goal_achieved":False,"reason":"明瞭性の原因診断。知覚の必須資格不足は継続。","renders":len(rows)})
    finally:vtl.close();campaign.close()


if __name__=="__main__":main()
