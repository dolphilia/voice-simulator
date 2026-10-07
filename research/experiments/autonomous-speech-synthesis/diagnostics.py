#!/usr/bin/env python3
"""探索から独立した評価監査と、辞書規則による日本語前段。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"src"))
from autonomous_speech_synthesis.io import read,write_once,file_hash,REPO


def prepare_ai(path):
    import numpy as np
    from scipy.io import wavfile
    from scipy import signal
    directory=path/"ai-input";directory.mkdir(exist_ok=True)
    rows=[]
    records=read(path/"splits.json")["groups"]["development"]["records"]
    chosen=[];seen=set()
    for r in records:
        if r["speaker"] not in seen:chosen.append(r);seen.add(r["speaker"])
        if len(chosen)==3:break
    for i,r in enumerate(chosen):
        fs,x=wavfile.read(REPO/r["wav"]);x=x.astype(float)/32768
        variants={"natural":x,"level-half":x*.5,"shift-5ms":np.r_[np.zeros(round(fs*.005)),x][0:len(x)],
                  "resampled":signal.resample_poly(signal.resample_poly(x,2,3),3,2)[:len(x)],
                  "clipped":np.clip(x*20,-.1,.1),"dropout":x.copy()}
        variants["dropout"][len(x)//3:len(x)//2]=0.
        # 同一入力の再実行を別行で記録する。
        variants["natural-repeat"]=x.copy()
        for name,data in variants.items():
            wav=directory/f"natural-{i}-{name}.wav"
            if not wav.exists():wavfile.write(wav,fs,data.astype(np.float32))
            rows.append({"id":f"natural-{i}-{name}","path":str(wav),"group":"natural" if name in ("natural","natural-repeat") else "perturbed","variant":name,"speaker":r["speaker"],"source_hash":r["sha256"],"sha256":file_hash(wav),"duration_seconds":len(data)/fs})
    if (path/"p34-speech.json").exists():
        speech=read(path/"p34-speech.json")
        for row in speech["rows"]:
            if row["kind"]=="sentence" and row["variant"] in ("gestures","gesture-prosody","flat-prosody") and row.get("wav"):
                wav=path/row["wav"]
                rows.append({"id":row["task"]+"-"+row["variant"],"path":str(wav),"group":"generated","variant":row["variant"],"sha256":file_hash(wav)})
        # 元波形の診断とは別に、候補・参照へ共通のレベル変換を適用する。
        normalized=[]
        for row in rows:
            if row["variant"]!="natural" and row["group"]!="generated":continue
            fs,x=wavfile.read(row["path"])
            x=x.astype(float)
            scalar=(10**(-23/20))/max(np.sqrt(np.mean(x*x)),1e-12)
            scalar=min(scalar,.95/max(np.max(abs(x)),1e-12))
            target=directory/(row["id"]+"-normalized.wav")
            if not target.exists():wavfile.write(target,fs,(x*scalar).astype(np.float32))
            normalized.append({**row,"id":row["id"]+"-normalized","path":str(target),"sha256":file_hash(target),"processing":"common-rms-minus23dBFS-peak-ceiling0.95","level_scalar":float(scalar)})
        rows.extend(normalized)
    manifest_name="ai-manifest.json" if (path/"p34-speech.json").exists() else "ai-calibration-manifest.json"
    write_once(path/manifest_name,rows)
    write_once(path/(manifest_name+".provenance.json"),{"script_sha256":file_hash(Path(__file__)),"policy":"採否に使用しない。短母音の反復なし。自然音声は開発群のみ。","omitted":{"B9_G40":"短い孤立母音、文章評価器の適用資格外","TTSDS2":"多依存の別環境未導入、同一話者を仮定する成分は適用外。未実行を良好値へ置換しない","public_ratings":"発話単位の日本語物理合成ラベル未取得。Krug 2021はドイツ語で資格転用不可"}})
    return {"items":len(rows),"manifest":str(path/manifest_name)}


def summarize_ai(path):
    import numpy as np
    scores=read(path/"ai-evaluation.json")
    natural={r["speaker"]:r["prediction"] for r in scores["rows"] if r.get("variant")=="natural" and not r.get("processing") and r.get("prediction") is not None}
    sensitivity=[]
    for r in scores["rows"]:
        if r.get("speaker") in natural and not r.get("processing") and r.get("prediction") is not None:
            sensitivity.append({"speaker":r["speaker"],"variant":r["variant"],"prediction":r["prediction"],"delta":r["prediction"]-natural[r["speaker"]]})
    groups={}
    for processing in ("raw","normalized"):
        for key in ("natural","perturbed","generated"):
            values=[r["prediction"] for r in scores["rows"] if r.get("group")==key and bool(r.get("processing"))==(processing=="normalized") and r.get("prediction") is not None]
            groups[processing+"/"+key]={"count":len(values),"median":float(np.median(values)) if values else None,"min":min(values) if values else None,"max":max(values) if values else None}
    result={"groups":groups,"sensitivity":sensitivity,"status":"diagnostic-only","promotion_allowed":False,"rank_correlation_with_human_ratings":None,"missing":sum(r.get("prediction") is None for r in scores["rows"]),"reason":"人間評点の対応資料なし。人工劣化の順位を自然さ一般化の証拠とみなさない"}
    write_once(path/"ai-qualification.json",result)
    return result


def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def normalize_text(text):
    return "".join(c for c in unicodedata.normalize("NFKC",text) if not unicodedata.category(c).startswith(("P","Z","C")))


def asr(path,natural_only=False):
    import importlib.metadata
    cache=ROOT/".cache/ai"
    os.environ.setdefault("HF_HOME",str(cache/"huggingface"))
    from faster_whisper import WhisperModel
    start=time.monotonic()
    model=WhisperModel("base",device="cpu",compute_type="int8",cpu_threads=4,download_root=str(cache/"whisper"))
    rows=[]
    tasks={t["id"]:t for t in read(path/"task-suite.json")["tasks"]}
    for r in ([] if natural_only else read(path/"p34-speech.json")["rows"]):
        if r["kind"]=="sentence" and r.get("wav"):
            rows.append({"id":r["task"],"group":"generated","variant":r["variant"],"path":str(path/r["wav"]),"reference_text":tasks[r["task"]]["text"]})
    records=read(path/"splits.json")["groups"]["development"]["records"]
    seen=set()
    for r in records:
        if r["speaker"] in seen:continue
        seen.add(r["speaker"])
        transcript=REPO/r["wav"];transcript=transcript.parent.parent/"transcripts_utf8.txt"
        texts=dict(line.split(":",1) for line in transcript.read_text().splitlines() if ":" in line)
        rows.append({"id":r["id"],"group":"natural","path":str(REPO/r["wav"]),"reference_text":texts[r["sentence"]]})
        if len(seen)==3:break
    for row in rows:
        try:
            segments,info=model.transcribe(row["path"],language="ja",beam_size=5,initial_prompt=None,condition_on_previous_text=False,vad_filter=False)
            hypothesis="".join(s.text for s in segments)
            # 正解テキストはtranscribeへ渡さず、デコード後だけ使用する。
            reference=normalize_text(row["reference_text"]);predicted=normalize_text(hypothesis)
            errors=edit_distance(reference,predicted)
            row.update(hypothesis=hypothesis,normalization="NFKC、Unicode句読点/区切り/制御を除去",errors=errors,reference_characters=len(reference),CER=errors/max(1,len(reference)))
            try:
                import pyopenjtalk
                ref_kana=normalize_text(pyopenjtalk.g2p(reference,kana=True))
                hyp_kana=normalize_text(pyopenjtalk.g2p(predicted,kana=True)) if predicted else ""
                row.update(kana_reference=ref_kana,kana_hypothesis=hyp_kana,kana_errors=edit_distance(ref_kana,hyp_kana),kana_characters=len(ref_kana),kana_CER=edit_distance(ref_kana,hyp_kana)/max(1,len(ref_kana)))
            except Exception as exc:row["kana_error"]=repr(exc)
        except Exception as exc:row["error"]=repr(exc)
        print(row["id"],row.get("CER"),flush=True)
    groups={}
    for group in ("natural","generated"):
        data=[r for r in rows if r["group"]==group]
        valid=[r for r in data if "CER" in r]
        denominator=sum(r["reference_characters"] for r in valid)
        kana=[r for r in data if "kana_CER" in r]
        groups[group]={"attempts":len(data),"available":len(valid),"CER":sum(r["errors"] for r in valid)/denominator if denominator else None,
                       "kana_CER":sum(r["kana_errors"] for r in kana)/sum(r["kana_characters"] for r in kana) if kana else None}
    weights=[]
    for p in sorted((cache/"whisper").rglob("*")):
        if p.is_file() and not p.is_symlink():weights.append({"path":str(p.relative_to(ROOT)),"sha256":file_hash(p)})
    result={"model":"faster-whisper/base","version":importlib.metadata.version("faster-whisper"),"status":"diagnostic-only","groups":groups,"rows":rows,"weights":weights,"seconds":time.monotonic()-start,"script_sha256":file_hash(Path(__file__)),"reference_text_hint_used":False,"independent_phoneme_recognizer":"unavailable","promotion_allowed":False}
    write_once(path/("asr-natural-calibration.json" if natural_only else "asr-evaluation.json"),result)
    return groups


def frontend(path,text):
    import pyopenjtalk
    from autonomous_speech_synthesis.gestures import PHONES
    from autonomous_speech_synthesis.generator import render
    from scipy.io import wavfile
    import numpy as np
    # g2pだけを利用し、HTS音源もmarineも呼ばない。
    phones=pyopenjtalk.g2p(text).split()
    phones=[{"cl":"Q","sil":"pau"}.get(p,p) for p in phones]
    unsupported=[p for p in phones if p not in PHONES]
    row={"text":text,"phonemes":phones,"unsupported":unsupported,"frontend":"Open JTalk dictionary/rules","neural_accent":False,"acoustic_model_called":False,"version":pyopenjtalk.__version__}
    if not unsupported:
        audio,log=render(phones,{},read(path/"voice-config.json"),1999)
        output=path/"dictionary-frontend.wav"
        if output.exists():raise FileExistsError("前段の出力は上書きしません")
        wavfile.write(output,24000,audio.astype(np.float32))
        row.update(wav=str(output),sha256=file_hash(output),accent_status="辞書アクセント核の接続は未実施、既定句内F0")
    write_once(path/"dictionary-frontend.json",row)
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["prepare-ai","summarize-ai","asr","asr-natural","frontend"])
    parser.add_argument("--campaign",default="ans-pilot-v1")
    parser.add_argument("--text",default="紫の船がゆっくり進む。")
    args=parser.parse_args();path=ROOT/"results"/args.campaign
    function={"prepare-ai":prepare_ai,"summarize-ai":summarize_ai,"asr":asr,"asr-natural":lambda p:asr(p,True),"frontend":lambda p:frontend(p,args.text)}[args.command]
    print(json.dumps(function(path),ensure_ascii=False,indent=2))


if __name__=="__main__":main()
