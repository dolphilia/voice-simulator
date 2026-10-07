"""計画書に対応する無人CLI。"""
import argparse
import copy
import json
import hashlib
from .io import ROOT,read,write_once,rows,file_hash,digest
from .inventory import inventory
from .data import reference_features
from .qualification import qualify
from .runner import Campaign,BudgetExhausted
from .search import run_vowels,run_speech
from .generator import render
from .gestures import kana_to_phonemes
from .export import export_bundle,isolated_check
from .reporting import report


def confirm(campaign):
    path=campaign.path
    if (path/"confirmation.json").exists():return read(path/"confirmation.json")
    voice=read(path/"voice-config.json")
    write_once(path/"frozen-candidates.json",{"candidates":[{"id":"speech-gestures","voice_sha256":file_hash(path/"voice-config.json")}],"order":["speech-gestures"],"comparison_correction":"Bonferroni","max_candidates":2})
    qualification=read(path/"evaluator-qualification.json")
    qualified=all(qualification["metrics"][key]["status"]=="qualified" for key in qualification["mandatory"])
    # 資格不足なら人間参照の最終確認集合を浪費しない。
    token=None
    if qualified:
        registry=ROOT/"results/confirmation-consumed.json"
        split_hash=digest(read(path/"splits.json")["groups"]["confirmation"])
        if registry.exists():raise RuntimeError("独立確認群は既に開封済みです")
        write_once(registry,{"campaign":path.name,"split_hash":split_hash})
        token=split_hash
        write_once(path/"confirmation-reference.json",reference_features(read(path/"splits.json"),"confirmation",token))
    texts=["むらさきのふねがゆっくりすすむ","ちいさなとりがなく","あしたのあさわさむい","みんなでおちゃをのむ"]
    outcomes=[]
    for i,text in enumerate(texts):
        for f0 in campaign.config["confirm"]["f0_hz"]:
            for speed in campaign.config["confirm"]["speeds"]:
                task={"id":f"unknown-{i}-{f0}-{speed}","kind":"sentence","phonemes":kana_to_phonemes(text),"text":text,"prosody":{"f0_hz":f0,"speed":speed}}
                for seed in campaign.config["confirm"]["seeds"]:
                    def execute(task=task,seed=seed):
                        audio,log=render(task["phonemes"],task["prosody"],voice,seed)
                        return audio,log,24000
                    result=campaign.trial("speech-gestures","dsp","P5",task,seed,voice,execute,save=seed==campaign.config["confirm"]["seeds"][0])
                    outcomes.append({"task":task["id"],"seed":seed,"E0_pass":result["evaluation"]["E0_pass"],"trial_id":result["trial_id"]})
    result={"quality_confirmation_opened":token is not None,"engineering_unknown_inputs":outcomes,"quality_state":"inconclusive",
            "reason":"未使用文脈・seed・F0/速度で信号検査のみ。独立人間参照・知覚/内容ゲート通過ではない。"}
    write_once(path/"confirmation.json",result)
    return result


def main():
    parser=argparse.ArgumentParser(description="無人非ニューラル音声研究")
    parser.add_argument("command",choices=["inventory","qualify","benchmark-cost","run","diagnose","confirm","export","status"])
    parser.add_argument("--campaign",default="ans-pilot-v1")
    args=parser.parse_args()
    if args.command=="status":
        path=ROOT/"results"/args.campaign
        result=read(path/"decision.json") if (path/"decision.json").exists() else {"state":"running-or-unstarted","events":len(rows(path/"ledger.jsonl"))}
        print(json.dumps({k:v for k,v in result.items() if k!="selected"},ensure_ascii=False,indent=2));return
    campaign=Campaign(args.campaign)
    try:
        inventory(campaign.path)
        if args.command=="inventory":return
        generator_qualification=qualify(campaign.path)
        if args.command in ("qualify","benchmark-cost"):return
        qualification=read(campaign.path/"evaluator-qualification.json")
        if not generator_qualification["lf"]["passed"] or qualification["metrics"]["signal"]["status"]!="qualified":
            raise RuntimeError("生成器またはE0評価器の数値点検が不通過です。探索を開始しません")
        if args.command=="diagnose":
            failed=[r for r in campaign.results() if not r["evaluation"]["E0_pass"]]
            write_once(campaign.path/"diagnostics.json",{"failed":failed,"next":"数値破綻を切り分け、同一確認集合を使う再調整は行わない"});return
        if args.command in ("confirm","export"):
            if args.command=="confirm":confirm(campaign)
            else:isolated_check(campaign.path)
            return
        splits=read(campaign.path/"splits.json")
        refs={}
        for group in ("development","selection"):
            file=campaign.path/f"reference-{group}.json"
            if file.exists():refs[group]=read(file)
            else:
                refs[group]=reference_features(splits,group);write_once(file,refs[group])
            print(f"P0/P1 {group}: 有効母音{len(refs[group]['rows'])}、除外率{refs[group]['exclusion_rate']}",flush=True)
        search=run_vowels(campaign,refs["development"],refs["selection"])
        run_speech(campaign,search)
        confirm(campaign)
        isolated_check(campaign.path)
        decision=report(campaign)
        print(json.dumps({"campaign":args.campaign,"state":decision["state"],"quality_goal_achieved":False},ensure_ascii=False))
    except BudgetExhausted as exc:
        write_once(campaign.path/"budget-stop.json",{"reason":str(exc),"goal_achieved":False,"state":"inconclusive","resume":"予算を自動追加しない"})
        print(str(exc))
    finally:campaign.close()


if __name__=="__main__":main()
