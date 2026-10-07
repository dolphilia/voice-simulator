#!/usr/bin/env python3
"""追加した評価資料のOS読み取り拒否を検査する。音声生成・AI推論は行わない。"""
import json
from pathlib import Path
import socket
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,file_hash,write_once


def main():
    out=ROOT/'results/extension-isolation-v1'
    inputs=read(out/'probe-inputs.json');denied=[]
    for row in inputs['files']:
        try:
            with Path(row['path']).open('rb') as f:f.read(1)
            blocked=False;error=None
        except PermissionError as exc:blocked=True;error=repr(exc)
        except Exception as exc:blocked=False;error=repr(exc)
        denied.append({'label':row['label'],'blocked':blocked,'error':error})
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1',0));network=False
    except PermissionError:network=True
    finally:s.close()
    bundle_files=[ROOT/'results/ans-pilot-v1/bundle/synthesize.py',ROOT/'results/vtl-bundle-v2/synthesize.py']
    readable=[]
    for p in bundle_files:
        try:
            with p.open('rb') as f:f.read(1)
            readable.append({'path':str(p),'readable':True})
        except Exception as exc:readable.append({'path':str(p),'readable':False,'error':repr(exc)})
    result={'passed':all(r['blocked'] for r in denied) and network and all(r['readable'] for r in readable),
            'denials':denied,'network_denied':network,'bundles':readable,'audio_renders':0,'AI_evaluations':0,
            'profile_sha256':file_hash(out/'profile.sb'),'script_sha256':file_hash(Path(__file__)),
            'scope':'更新されたOS拒否設定のアクセス検査のみ。既存bundleの波形一致証拠は旧試験にあり、この検査では音声を再生成していない。'}
    write_once(out/'verification.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
