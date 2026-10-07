"""同予算の共有制御探索と無作為対照。採点だけで自然さへ昇格しない。"""
import copy
import numpy as np
from scipy.stats import qmc
from .io import read,write_once
from .data import target_bands
from .generator import render
from .gestures import voice_config
from .backends import VTL,legacy_render
from .evaluation import grouped_bootstrap


def parameters(backend,point):
    if backend=="dsp":
        return {"tract_scale":.9+.2*point[0],"bandwidth_scale":.7+.7*point[1],"ta":.03+.06*point[2]}
    return {"tongue_x_cm":-.2+.4*point[0],"lip_protrusion_cm":-.15+.3*point[1],"pressure_scale":.85+.3*point[2]}


def configured_voice(params):
    voice=voice_config()
    for key in ("tract_scale","bandwidth_scale"):
        if key in params:voice[key]=params[key]
    if "ta" in params:voice["source"]["ta"]=params["ta"]
    return voice


def renderer(backend,task,seed,params,vtl=None):
    def execute():
        if backend=="dsp":
            audio,log=render(task["phonemes"],task["prosody"],configured_voice(params),seed)
            return audio,log,24000
        if backend=="vtl":
            audio=vtl.render(task["phonemes"][0],task["f0_hz"],seed=seed,setting=params)
            return audio,{"parameters":params,"backend":vtl.metadata,"task":task,"seed":seed},24000
        audio,fs,condition=legacy_render(backend,task["phonemes"][0],task["f0_hz"],seed)
        return audio,{"condition":condition,"legacy_status":"旧認定を継承しない"},fs
    return execute


def residual(result,target):
    if not result["evaluation"]["E0_pass"]:return None
    features=result["evaluation"].get("E1",{}).get("features",{})
    bands=features.get("band_energy_fractions")
    if target is None or bands is None:return None
    return float(np.mean((np.log10(np.maximum(bands,1e-6))-np.log10(np.maximum(target,1e-6)))**2))


def run_vowels(campaign,reference,selection):
    path=campaign.path
    if (path/"p2-search.json").exists():return read(path/"p2-search.json")
    tasks=[t for t in read(path/"task-suite.json")["tasks"] if t["stage"]=="P2"]
    targets={t["id"]:target_bands(reference,t["phonemes"][0],t["f0_hz"]) for t in tasks}
    settings=read(path/"cost-pilot.json")["settings_per_arm"]
    frozen={"settings_per_arm":settings,"seeds":campaign.config["vowel_seeds"],"targets":{key:{"bands":None if t[0] is None else t[0].tolist(),"coverage":t[1]} for key,t in targets.items()},
            "objective":"対数帯域エネルギー残差（機構診断のみ）","adaptive_schedule":"最初の3設定は音源のみ、次3設定は声道のみ、残りは共同。最良点周囲の範囲縮小。","free_fit":"全共有試行から条件ごとに選ぶ非共有oracle。追加の自然音声波形適合ではない。"}
    write_once(path/"p2-frozen-search.json",frozen)
    all_settings=[];baseline=[];vtl=None
    try:vtl=VTL()
    except Exception:pass
    try:
        for backend in ("B9","G40"):
            for task in tasks:
                for seed in (401,411,421):
                    legacy_task={**task,"expected_duration_seconds":.8}
                    result=campaign.trial(backend,backend,"P2",legacy_task,seed,{},renderer(backend,task,seed,{}),save=seed==401)
                    baseline.append({"backend":backend,"task":task["id"],"seed":seed,"residual":residual(result,targets[task["id"]][0]),"trial_id":result["trial_id"],"E0_pass":result["evaluation"]["E0_pass"]})
        for backend in ("dsp","vtl"):
            if backend=="vtl" and vtl is None:continue
            random=qmc.LatinHypercube(3,seed=campaign.config["seed"]).random(settings)
            for arm in ("adaptive","random"):
                best=np.array([.5,.5,1/3]);best_loss=float("inf")
                for index in range(settings):
                    point=random[index].copy()
                    if arm=="adaptive":
                        radius=.5*(.75**max(0,index-1))
                        point=np.clip(best+(point-.5)*2*radius,0,1)
                    # 両群とも段階ごとの同じ自由度を探索する。
                    if index<3:point[:2]=.5
                    elif index<6:point[2]=best[2] if arm=="adaptive" else 1/3
                    params=parameters(backend,point); values=[];cells=[];valid=True
                    candidate=f"{backend}-{arm}-{index:02}"
                    for task in tasks:
                        for seed in campaign.config["vowel_seeds"]:
                            result=campaign.trial(candidate,backend,"P2",task,seed,params,renderer(backend,task,seed,params,vtl))
                            error=residual(result,targets[task["id"]][0])
                            if error is not None:values.append(error)
                            valid &= result["evaluation"]["E0_pass"]
                            cells.append({"task":task["id"],"seed":seed,"residual":error,"trial_id":result["trial_id"],"E0_pass":result["evaluation"]["E0_pass"]})
                    loss=float(np.mean(values)) if values and valid else None
                    item={"candidate_id":candidate,"backend":backend,"arm":arm,"index":index,"parameters":params,"loss":loss,"E0_all":bool(valid),"coverage":len(values)/len(cells),"cells":cells}
                    all_settings.append(item)
                    if loss is not None and loss<best_loss:best=point;best_loss=loss
                    print(f"P2 {candidate}: 残差={loss}, coverage={item['coverage']:.2f}",flush=True)
        chosen=[]
        for backend in ("dsp","vtl"):
            viable=[r for r in all_settings if r["backend"]==backend and r["loss"] is not None]
            if not viable:continue
            winner=min(viable,key=lambda r:r["loss"])
            confirmation=[]
            for task in tasks:
                target,coverage=target_bands(selection,task["phonemes"][0],task["f0_hz"])
                for seed in campaign.config["recheck_seeds"]:
                    result=campaign.trial(winner["candidate_id"],backend,"P2-recheck",task,seed,winner["parameters"],renderer(backend,task,seed,winner["parameters"],vtl),save=seed==campaign.config["recheck_seeds"][0])
                    confirmation.append({"task":task["id"],"seed":seed,"residual":residual(result,target),"reference_coverage":coverage,"E0_pass":result["evaluation"]["E0_pass"],"trial_id":result["trial_id"]})
            chosen.append({**{k:v for k,v in winner.items() if k!="cells"},"selection":confirmation,"promotion":"mechanism-research-only"})
        oracle={}
        for backend in ("dsp","vtl"):
            cells=[c for s in all_settings if s["backend"]==backend for c in s["cells"] if c["residual"] is not None]
            oracle[backend]={t["id"]:min((c["residual"] for c in cells if c["task"]==t["id"]),default=None) for t in tasks}
        summary={"settings":all_settings,"fixed_controls":baseline,"chosen":chosen,"sampled_nonshared_oracle":oracle,"quality_status":"inconclusive",
                 "uncertainty":{"state":"diagnostic-only","reason":"母音/F0条件やseedを独立話者として再標本化しない。現残差だけでは改善の統計認定なし"},"shared_parameter_count":3,"model_limit_claim":False}
        write_once(path/"p2-search.json",summary)
        return summary
    finally:
        if vtl:vtl.close()


def run_speech(campaign,search):
    if (campaign.path/"p34-speech.json").exists():return read(campaign.path/"p34-speech.json")
    chosen=next((x for x in search["chosen"] if x["backend"]=="dsp"),None)
    if not chosen:raise RuntimeError("DSPのE0通過候補がありません")
    voice=configured_voice(chosen["parameters"])
    tasks=[t for t in read(campaign.path/"task-suite.json")["tasks"] if t["stage"] in ("P3","P4")]
    outputs=[]
    # 40発話を1batchとし、全音素を分母に残す。共有3規則×全136課題でも予算内。
    for variant in ("gestures","abrupt-transition","flat-prosody"):
        current=copy.deepcopy(voice)
        if variant=="abrupt-transition":current["transition_seconds"]=0.
        for task in tasks:
            local=copy.deepcopy(task)
            if variant=="flat-prosody":local["prosody"].update(intonation=False,accent_nucleus=0,devoice=False)
            for seed in campaign.config["sentence_seeds"]:
                def generate(task=local,seed=seed,voice=current):
                    x,log=render(task["phonemes"],task["prosody"],voice,seed)
                    return x,log,24000
                row=campaign.trial(f"speech-{variant}","dsp",task["stage"],local,seed,current,generate,save=variant=="gestures" and seed==campaign.config["sentence_seeds"][0])
                outputs.append({"variant":variant,"task":task["id"],"kind":task["kind"],"family":task.get("family"),"seed":seed,"trial_id":row["trial_id"],"evaluation":row["evaluation"],"wav":row.get("wav")})
        print(f"P3/P4 {variant}: {len(tasks)}課題を検査",flush=True)
    result={"rows":outputs,"voice_config":voice,"content_recognition":{"status":"unavailable","CER":None,"confusion_matrix":None,"reason":"独立した日本語認識器の校正未実施"},
            "perception":{"status":"inconclusive"},"unsupported":["漢字入力","未知語アクセント推定","日本語音素としてのVTL資格"],"ablation_interpretation":"工学・波形差の診断。音素明瞭性や自然さ改善の証拠とはしない"}
    write_once(campaign.path/"p34-speech.json",result)
    write_once(campaign.path/"voice-config.json",voice)
    return result
