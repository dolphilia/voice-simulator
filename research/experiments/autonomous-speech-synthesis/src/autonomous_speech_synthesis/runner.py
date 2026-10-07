"""予算に失敗・中断も含め、同一コード/設定のcampaignだけを再開する。"""
import fcntl
import hashlib
import os
import re
import time
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from .io import ROOT,read,write_once,append,rows,digest,code_manifest,environment,now
from .evaluation import evaluate


class BudgetExhausted(RuntimeError):pass


class Campaign:
    def __init__(self,campaign_id,config=None):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,80}",campaign_id):
            raise ValueError("campaign IDの書式が不正です")
        self.config=config or read(ROOT/"config/campaign-v1.json")
        self.path=ROOT/"results"/campaign_id
        self.path.mkdir(parents=True,exist_ok=True)
        self.lock=(self.path/".run.lock").open("a+")
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity={"code":code_manifest(),"config":self.config,"environment":environment()}
        write_once(self.path/"identity.json",identity)
        self.identity_hash=digest(identity)
        if not (self.path/"started.json").exists():
            campaigns=list((ROOT/"results").glob("*/started.json"))
            if len(campaigns)>=self.config["budget"]["max_campaigns"]:raise BudgetExhausted("研究サイクルのcampaign数上限です")
            write_once(self.path/"started.json",{"utc":now(),"unix":time.time()})
        self.events=rows(self.path/"ledger.jsonl")
        self.storage_estimate=None
        self.storage_trials=0

    def close(self):
        fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close()

    def budget_check(self,stage,backend):
        limits=self.config["budget"]
        age=time.time()-read(self.path/"started.json")["unix"]
        if age>limits["max_campaign_seconds"]:raise BudgetExhausted("campaign実時間上限です")
        root=self.path.parent
        starts=[read(p)["unix"] for p in root.glob("*/started.json")]
        if starts and time.time()-min(starts)>limits["max_cycle_seconds"]:raise BudgetExhausted("研究サイクル実時間上限です")
        # 結果領域だけでなく導入済みモデル等も保存量へ計上する。
        if self.storage_estimate is None or self.storage_trials>=32:
            self.storage_estimate=sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file() and not p.is_symlink())
            self.storage_trials=0
        # 各試行30秒以下で、WAV/JSONの増分を10MBとして保守的に予約する。
        total=self.storage_estimate+self.storage_trials*10_000_000
        self.storage_trials+=1
        own=sum(p.stat().st_size for p in self.path.rglob("*") if p.is_file())
        if total+10_000_000>=limits["max_cycle_bytes"] or own+10_000_000>=limits["max_campaign_bytes"]:raise BudgetExhausted("保存量上限です")
        started=[e for e in self.events if e["event"]=="started"]
        key="max_legacy_renders" if backend in ("B9","G40") else "max_recheck_renders" if stage=="P2-recheck" else "max_p2_per_backend" if stage=="P2" else "max_confirm_renders" if stage=="P5" else "max_p34_renders"
        count=sum(e["budget_key"]==key and (key!="max_p2_per_backend" or e["backend"]==backend) for e in started)
        if count>=limits[key]:raise BudgetExhausted(f"レンダー上限です: {key}")
        return key

    def trial(self,candidate_id,backend,stage,task,seed,parameters,renderer,save=False):
        request={"candidate_id":candidate_id,"backend":backend,"stage":stage,"task":task,"seed":seed,"parameters":parameters,"identity":self.identity_hash}
        trial_id=digest(request)[:24]
        finished=[e for e in self.events if e.get("trial_id")==trial_id and e["event"]=="finished"]
        if finished:return read(self.path/finished[-1]["result"])
        budget_key=self.budget_check(stage,backend)
        attempt=sum(e.get("trial_id")==trial_id and e["event"]=="started" for e in self.events)+1
        event={"event":"started","trial_id":trial_id,"attempt":attempt,"backend":backend,"stage":stage,"budget_key":budget_key,"utc":now()}
        append(self.path/"ledger.jsonl",event);self.events.append(event)
        before=time.monotonic()
        result={**request,"trial_id":trial_id,"attempt":attempt,"parent":None,"reason":"事前登録された無人比較","data_split":"confirmation" if stage=="P5" else "development","scope":self.config["scope"]}
        try:
            audio,log,fs=renderer()
            audio=np.asarray(audio,dtype=np.float64)
            result.update(evaluation=evaluate(audio,task,fs),audio_sha256=hashlib.sha256(audio.astype("<f8").tobytes()).hexdigest(),sample_rate=fs,samples=len(audio))
            if save or not result["evaluation"]["E0_pass"]:
                wav=self.path/"audio"/f"{trial_id}-{attempt}.wav";wav.parent.mkdir(exist_ok=True)
                if wav.exists():raise FileExistsError("同じ試行のWAVは上書きしません")
                wavfile.write(wav,fs,audio.astype(np.float32))
                result["wav"]=str(wav.relative_to(self.path))
                write_once(wav.with_suffix(".controls.json"),log)
            result["status"]="signal-qualified" if result["evaluation"]["E0_pass"] else "rejected"
        except Exception as exc:
            result.update(status="unavailable",error=repr(exc),evaluation={"E0_pass":False,"error":repr(exc)})
        result["elapsed_seconds"]=time.monotonic()-before
        if result.get("samples"):result["rtf"]=result["elapsed_seconds"]/(result["samples"]/result["sample_rate"])
        relative=f"trials/{trial_id}-{attempt}.json"
        write_once(self.path/relative,result)
        event={"event":"finished","trial_id":trial_id,"attempt":attempt,"result":relative,"utc":now()}
        append(self.path/"ledger.jsonl",event);self.events.append(event)
        return result

    def results(self):
        return [read(self.path/e["result"]) for e in self.events if e["event"]=="finished"]
