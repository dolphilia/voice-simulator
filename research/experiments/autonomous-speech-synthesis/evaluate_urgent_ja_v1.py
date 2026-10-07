#!/usr/bin/env python3
"""日本語の既存人手評点に対するUTMOS診断。推論回数を既存campaignへ計上する。"""
import fcntl
import os
from pathlib import Path
import random
import sys
import time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
CACHE=ROOT/'.cache/ai'
for key,value in {'HF_HOME':CACHE/'huggingface','TORCH_HOME':CACHE/'torch','NUMBA_CACHE_DIR':CACHE/'numba','UTMOSV2_CHACHE':CACHE/'utmosv2'}.items():os.environ.setdefault(key,str(value))
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
from autonomous_speech_synthesis.io import read,write_once,file_hash,append,rows,now
from cycle_campaign_v1 import CYCLE_ID,LIMITS,inventory


def main():
    import numpy as np
    import torch
    import utmosv2
    out=ROOT/'results/urgent-ja-v1';protocol=read(out/'protocol.json');manifest=read(out/'manifest.json')
    if len(manifest['rows'])>protocol['max_total_predictions']:raise RuntimeError('固定済み評価件数の上限です')
    campaign=ROOT/'results'/protocol['charge_campaign'];identity=read(campaign/'identity.json')
    if identity['config'].get('cycle_id')!=CYCLE_ID:raise ValueError('追加承認枠に属さないcampaignです')
    approval=read(ROOT/'results/cycles'/CYCLE_ID/'approval.json');records=out/'predictions';records.mkdir(exist_ok=True)
    with (campaign/'.ai.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'evaluation.json').exists():print('完了済み');return
        for row in manifest['rows']:
            if file_hash(Path(row['path']))!=row['sha256']:raise ValueError('評価原音声のハッシュ不一致です')
        pending=[r for r in manifest['rows'] if not (records/(r['sample_id']+'.json')).exists()]
        ledger=campaign/'ai-ledger.jsonl';used=sum(r['count'] for r in rows(ledger) if r['event']=='reserved')
        if used+len(pending)>identity['config']['budget']['max_ai_evaluations']:raise RuntimeError('AI評価予算を超えます')
        current=inventory(ROOT);added=sum(max(0,n-approval['baseline_inventory'].get(p,0)) for p,n in current.items())
        if added+20_000_000>=LIMITS['max_additional_bytes']:raise RuntimeError('保存量の予算を超えます')
        package=Path(utmosv2.__file__).parent
        provenance={'script_sha256':file_hash(Path(__file__)),'manifest_sha256':file_hash(out/'manifest.json'),
                    'package_version':utmosv2.__version__,'package_sources':{str(p.relative_to(package)):file_hash(p) for p in sorted(package.rglob('*.py'))},
                    'weights_sha256':file_hash(CACHE/'utmosv2/models/fusion_stage3/fold0_s42_best_model.pth'),
                    'torch':torch.__version__,'numpy':np.__version__,'device':'cpu','threads':4,'offline':True}
        write_once(out/'model-provenance.json',provenance)
        append(ledger,{'event':'reserved','count':len(pending),'utc':now(),'evaluation':'urgent-ja-v1','manifest_sha256':provenance['manifest_sha256'],'script_sha256':provenance['script_sha256']})
        torch.set_num_threads(4);random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.use_deterministic_algorithms(True)
        model=utmosv2.create_model(pretrained=True,device='cpu');start=time.monotonic()
        for row in pending:
            if time.time()-approval['unix']>LIMITS['max_cycle_seconds'] or time.time()-read(campaign/'started.json')['unix']>LIMITS['max_campaign_seconds']:raise RuntimeError('実時間の予算を超えました')
            seed=row['evaluation_seed'];random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
            result=dict(row);t=time.monotonic()
            try:
                value=float(model.predict(input_path=row['path'],device='cpu',num_workers=0,verbose=False))
                if not np.isfinite(value):raise ValueError('予測値が非有限です')
                result['prediction']=value
            except Exception as exc:result.update(prediction=None,error=repr(exc))
            result['elapsed_seconds']=time.monotonic()-t
            write_once(records/(row['sample_id']+'.json'),result);print(row['sample_id'],result['prediction'],flush=True)
        result={'status':'diagnostic-only','promotion_allowed':False,'rows':[read(records/(r['sample_id']+'.json')) for r in manifest['rows']],
                'manifest_sha256':provenance['manifest_sha256'],'provenance_sha256':file_hash(out/'model-provenance.json'),
                'seconds_this_run':time.monotonic()-start,'scope':'日本語の雑音除去出力。物理合成への資格を付与しない。'}
        write_once(out/'evaluation.json',result)
        append(ledger,{'event':'finished','count':len(pending),'utc':now(),'evaluation':'urgent-ja-v1','result_sha256':file_hash(out/'evaluation.json')})

if __name__=='__main__':main()
