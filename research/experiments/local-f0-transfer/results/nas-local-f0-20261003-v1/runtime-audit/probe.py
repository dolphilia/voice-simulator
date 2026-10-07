"""隔離環境で禁止ファイル・推論エンジン・ネットワークの拒否を確認する。"""
import argparse
import importlib
import json
from pathlib import Path
import socket


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs',type=Path,required=True)
    args=parser.parse_args()
    spec=json.loads(args.inputs.read_text())
    results=[]
    for path in spec['files']:
        try:
            with Path(path).open('rb') as f:f.read(1)
            denied=False
        except PermissionError:
            denied=True
        results.append({'path':path,'denied':denied})
    modules=[]
    for name in ('torch','transformers','faster_whisper','ctranslate2'):
        try:
            importlib.import_module(name)
            denied=False
        except (PermissionError,ImportError,ModuleNotFoundError):
            denied=True
        modules.append({'name':name,'denied':denied})
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:s.bind(('127.0.0.1',0));network=False
        finally:s.close()
    except PermissionError:
        network=True
    print(json.dumps({'files':results,'modules':modules,'network_denied':network,
                     'passed':all(r['denied'] for r in results+modules) and network},ensure_ascii=False))


if __name__=='__main__':
    main()
