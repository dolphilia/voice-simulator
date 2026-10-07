#!/usr/bin/env python3
"""公式の固定revisionから原FLACを含むACR配布だけを上限内で取得する。"""
import hashlib
import sys
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,file_hash,write_once,now
from cycle_campaign_v1 import CYCLE_ID,LIMITS,inventory


def main():
    out=ROOT/'results/urgent-ja-v1';protocol=read(out/'protocol.json');release=read(out/'release_manifest.json')
    files=release['configs']['acr/test']['files']
    if sum(f['bytes'] for f in files)>protocol['download_byte_cap']:raise RuntimeError('取得予算を超えます')
    approval=read(ROOT/'results/cycles'/CYCLE_ID/'approval.json');received=[]
    for record in files:
        if time.time()-approval['unix']>LIMITS['max_cycle_seconds']:raise RuntimeError('時間予算を超えます')
        if record['path'] not in [f'data/acr/test-{i:05d}-of-00003.parquet' for i in range(3)]:raise ValueError('配布pathが想定外です')
        p=out/Path(record['path']).name
        if p.exists():
            if file_hash(p)!=record['sha256']:raise ValueError('既存配布ファイルのハッシュ不一致')
        else:
            current=inventory(ROOT);added=sum(max(0,n-approval['baseline_inventory'].get(k,0)) for k,n in current.items())
            if added+record['bytes']+20_000_000>=LIMITS['max_additional_bytes']:raise RuntimeError('追加保存量を超えます')
            url=f"https://huggingface.co/datasets/{protocol['dataset']}/resolve/{protocol['revision']}/{record['path']}"
            partial=p.with_suffix('.part');n=0;sha=hashlib.sha256()
            # 自分の未完成ファイルだけを再開時に上書きし、検証済み資産は保持する。
            with urllib.request.urlopen(url,timeout=60) as response,partial.open('wb') as dest:
                while True:
                    block=response.read(1024*1024)
                    if not block:break
                    n+=len(block)
                    if n>record['bytes']:raise RuntimeError('配布宣言より大きな応答です')
                    dest.write(block);sha.update(block)
            if n!=record['bytes'] or sha.hexdigest()!=record['sha256']:raise ValueError('配布サイズ・ハッシュ不一致')
            partial.rename(p)
        received.append({'file':p.name,'sha256':file_hash(p),'bytes':p.stat().st_size})
        print(p.name,'検証済み',flush=True)
    write_once(out/'download.json',{'utc':now(),'files':received,'revision':protocol['revision'],'source':'https://huggingface.co/datasets/urgent-challenge/urgent2026-sqa','script_sha256':file_hash(Path(__file__))})

if __name__=='__main__':main()
