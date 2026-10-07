"""凍結分割と境界不確実性を保持した参照測定。"""
import numpy as np
from scipy.io import wavfile
from .io import REPO,file_hash
from .evaluation import acoustic_features


def reference_features(splits,group,confirmation_token=None):
    if group=="confirmation" and confirmation_token is None:
        raise PermissionError("最終確認群は専用confirm処理だけが開封できます")
    results=[]; excluded=[]; total=0
    for record in splits["groups"][group]["records"]:
        path=REPO/record["wav"]; lab=REPO/record["lab"]
        if file_hash(path)!=record["sha256"] or file_hash(lab)!=record["label_sha256"]:
            raise ValueError("参照音声または境界ラベルのハッシュが変わりました")
        fs,raw=wavfile.read(path)
        audio=raw.astype(float)/(max(abs(np.iinfo(raw.dtype).min),np.iinfo(raw.dtype).max) if np.issubdtype(raw.dtype,np.integer) else 1.)
        if audio.ndim==2:audio=audio.mean(axis=1)
        for index,line in enumerate(lab.read_text().splitlines()):
            start,end,phone=line.split(); start=float(start);end=float(end)
            if phone not in "aiueo" or len(phone)!=1:continue
            total+=1
            if end-start<.095:
                excluded.append({"id":record["id"],"segment":index,"reason":"境界摂動後の有効長が不足"});continue
            measures=[]
            for delta in (-.01,0,.01):
                lo=round((start+.015+delta)*fs);hi=round((end-.015+delta)*fs)
                measures.append(acoustic_features(audio[lo:hi],fs))
            f0s=[m["f0_hz"] for m in measures]
            stable=all(v is not None for v in f0s) and all(m["f0_confidence"]>=.65 for m in measures) and max(f0s)/min(f0s)<1.06
            if not stable:
                excluded.append({"id":record["id"],"segment":index,"reason":"F0/境界摂動の不一致"});continue
            m=measures[1]
            results.append({"id":record["id"],"speaker":record["speaker"],"sentence":record["sentence"],"vowel":phone,
                            "start_seconds":start,"end_seconds":end,"alignment_confidence":None,"boundary_perturbation_seconds":.01,
                            "boundary_f0_relative_spread":max(f0s)/min(f0s)-1,"features":m})
    return {"split":group,"rows":results,"excluded":excluded,"total_vowel_segments":total,
            "exclusion_rate":len(excluded)/total if total else None,"scope":"自動境界の安定部分のみ。ラベルの正確性は未検証"}


def target_bands(reference,vowel,f0):
    # F0が30%以内の話者群のみ。各話者一票で平均する。
    groups={}
    for row in reference["rows"]:
        value=row["features"]["f0_hz"]
        if row["vowel"]==vowel and value is not None and abs(np.log(value/f0))<np.log(1.3):
            groups.setdefault(row["speaker"],[]).append(row["features"]["band_energy_fractions"])
    if len(groups)<2:
        return None,{"state":"out-of-domain","speaker_count":len(groups),"reason":"近いF0の参照話者が2未満"}
    target=np.mean([np.mean(rows,axis=0) for rows in groups.values()],axis=0)
    return target,{"state":"diagnostic-only","speaker_count":len(groups),"speakers":sorted(groups),"note":"声道長の厳密一致は未実施。自然さ目的には使わない"}
