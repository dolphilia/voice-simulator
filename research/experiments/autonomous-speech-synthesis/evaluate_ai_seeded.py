#!/usr/bin/env python3
"""UTMOS推論時の区間抽出乱数を固定し、再現性とseed感度を切り分ける。"""
import hashlib
import json
import os
from pathlib import Path
import random
import time

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'.cache/ai'
for key,value in {'HF_HOME':CACHE/'huggingface','TORCH_HOME':CACHE/'torch','NUMBA_CACHE_DIR':CACHE/'numba','UTMOSV2_CHACHE':CACHE/'utmosv2'}.items():os.environ.setdefault(key,str(value))


def main():
    import numpy as np
    import torch
    import utmosv2
    path=ROOT/'results/evaluator-seeded-v1'
    path.mkdir(exist_ok=True)
    output=path/'evaluation.json'
    if output.exists():raise FileExistsError('評価結果は上書きしません')
    base=json.loads((ROOT/'results/ans-pilot-v1/ai-calibration-manifest.json').read_text())
    items=[{**r,'evaluation_seed':20261002} for r in base]
    for seed in (7,19):items.extend({**r,'id':r['id']+f'-seed{seed}','evaluation_seed':seed} for r in base if r['variant']=='natural')
    for cid in ('ans-pilot-v1','ans-vtl-speech-v1'):
        manifest=json.loads((ROOT/'results'/cid/'ai-manifest.json').read_text())
        items.extend({**r,'id':cid+'-'+r['id'],'evaluation_seed':20261002} for r in manifest if r['group']=='generated' and not r.get('processing') and r['id'] in ('sentence-00-gestures','sentence-01-gestures','sentence-00-gesture-prosody','sentence-01-gesture-prosody'))
    policy={'items':items,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'推論再現性診断。人間評点との転移資格を付与しない。','max_predictions':31}
    with (path/'frozen-manifest.json').open('x') as f:json.dump(policy,f,ensure_ascii=False,indent=2)
    assert len(items)<=31
    torch.set_num_threads(4)
    random.seed(42);np.random.seed(42);torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    model=utmosv2.create_model(pretrained=True,device='cpu')
    results=[];start=time.monotonic()
    for row in items:
        seed=row['evaluation_seed'];random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
        entry=dict(row)
        try:entry['prediction']=float(model.predict(input_path=row['path'],device='cpu',num_workers=0,verbose=False))
        except Exception as exc:entry.update(prediction=None,error=repr(exc))
        results.append(entry);print(row['id'],entry['prediction'],flush=True)
    diffs=[]
    for speaker in sorted({r['speaker'] for r in base}):
        pair=[r for r in results if r.get('speaker')==speaker and r['evaluation_seed']==20261002 and r['variant'] in ('natural','natural-repeat')]
        if len(pair)==2 and all(r['prediction'] is not None for r in pair):diffs.append(abs(pair[0]['prediction']-pair[1]['prediction']))
    result={'status':'diagnostic-only','promotion_allowed':False,'rows':results,'repeat_max_absolute_error':max(diffs) if len(diffs)==3 else None,'seconds':time.monotonic()-start,'source_sha256':policy['source_sha256'],
      'explanation':'上流dataset/ssl.pyとmulti_spec.pyのselect_random_startは推論時にもNumPy乱数を使用。各入力で同じseedへ戻す。seed依存も別行で保存。','version':utmosv2.__version__}
    package=Path(utmosv2.__file__).parent
    result['upstream_source_hashes']={str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (package/'dataset/ssl.py',package/'dataset/multi_spec.py',package/'dataset/_utils.py')}
    with output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':main()
