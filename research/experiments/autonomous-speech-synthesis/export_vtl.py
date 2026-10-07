#!/usr/bin/env python3
"""VTLの共有物理モデルと規則だけを研究用bundleへ移出する。"""
import ast
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import file_hash,write_once


def definitions(path,names):
    tree=ast.parse(path.read_text())
    found=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    if {n.name for n in found}!=set(names):raise ValueError('必要な生成定義が不足しています')
    return '\n\n'.join(ast.unparse(n) for n in found)


def main():
    base=ROOT/'.cache/VocalTractLabBackend-dev'
    bundle=ROOT/'results/vtl-bundle-v2';bundle.mkdir(exist_ok=True)
    for source,name in [(base/'lib/Release/libVocalTractLabApi.dylib','libVocalTractLabApi.dylib'),(base/'resources/JD3.speaker','JD3.speaker'),(base/'LICENSE','LICENSE-VTL')]:
        if not source.exists() and name=='LICENSE-VTL':source=base/'LICENSE.md'
        if (bundle/name).exists():raise FileExistsError('既存bundleを上書きしません')
        shutil.copyfile(source,bundle/name)
    module='''"""共有物理モデルと実行時のジェスチャ規則。参照・AI評価を含めない。"""
import ctypes as ct
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

'''+definitions(ROOT/'vtl_speech.py',{'sampa_segments'})+'\n\n'+definitions(ROOT/'vtl_japanese.py',{'timed_segments','patch_taps','render_japanese'})+'''

class Backend:
    def __init__(self):
        root=Path(__file__).resolve().parent
        self.lib=ct.CDLL(str(root/'libVocalTractLabApi.dylib'))
        self.lib.vtlInitialize.argtypes=[ct.c_char_p]
        self.check(self.lib.vtlInitialize(str(root/'JD3.speaker').encode()))
        self.metadata={'model':'VocalTractLab/JD3','runtime':'non-neural','shared_physical_model':True}
    @staticmethod
    def check(value):
        if value!=0:raise RuntimeError(f'VTL APIの失敗: {value}')
    def close(self):self.check(self.lib.vtlClose())
'''
    (bundle/'generator.py').write_text(module)
    kana=definitions(ROOT/'src/autonomous_speech_synthesis/gestures.py',{'kana_to_phonemes'})
    entry='''#!/usr/bin/env python3
"""かな/明示音素とアクセント指定から未知文を生成する研究版。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import unicodedata
import numpy as np
from scipy.io import wavfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from generator import Backend,render_japanese
VOWELS='aiueo'
'''+kana+'''

def analysis_from_phones(phones,accent):
    phrases=[];moras=[];pending=[]
    nuclei=set('aiueo')|{'I','U','N','Q'}
    allowed=nuclei|{'m','n','s','sh','h','f','p','t','k','b','d','g','z','j','ts','ch','r','w','y','ky','gy','ny','hy','my','ry','pau'}
    if not phones or any(p not in allowed for p in phones):raise ValueError('空入力または未対応音素です')
    def finish():
        if pending:raise ValueError('母音核のない音節です')
        if not moras:return
        nucleus=accent[len([p for p in phrases if not p.get('pause')])] if accent else 0
        if not 0<=nucleus<=len(moras):raise ValueError('アクセント核がモーラ数を超えています')
        for i,m in enumerate(moras,1):m['high']=i<=nucleus if nucleus==1 else i>=2 and (nucleus==0 or i<=nucleus)
        phrases.append({'moras':list(moras),'accent_nucleus':nucleus,'mora_count':len(moras)})
        moras.clear()
    for p in phones:
        if p=='pau':finish();phrases.append({'pause':True});continue
        pending.append(p)
        if p in nuclei:
            if len(pending)>2:raise ValueError('未対応の子音連続です')
            moras.append({'phones':list(pending)});pending.clear()
    finish()
    count=len([p for p in phrases if not p.get('pause')])
    if accent and len(accent)!=count:raise ValueError('アクセント指定と句数が一致しません')
    return {'phonemes':phones,'phrases':phrases}


def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--text');group.add_argument('--phones')
    parser.add_argument('--accent',default='');parser.add_argument('--variant',choices=['mora','accent','accent-tap'],default='accent')
    parser.add_argument('--seed',type=int,default=1009);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('出力は上書きしません')
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'manifest.json').read_text())
    for name,expected in manifest['files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('bundle内容が変更されています')
    phones=args.phones.split() if args.phones else kana_to_phonemes(args.text)
    accent=[int(x) for x in args.accent.split(',')] if args.accent else []
    analysis=analysis_from_phones(phones,accent)
    if sum(len(p.get('moras',[])) for p in analysis['phrases'])>140:raise ValueError('最大140モーラです')
    backend=Backend();start=time.monotonic()
    try:audio,log,fs=render_japanese(backend,analysis,args.variant,args.seed)
    finally:backend.close()
    wavfile.write(args.output,fs,audio.astype(np.float32))
    print(json.dumps({'sha256_float64':hashlib.sha256(audio.astype('<f8').tobytes()).hexdigest(),'samples':len(audio),'sample_rate':fs,'rtf':(time.monotonic()-start)/(len(audio)/fs),'phonemes':phones,'variant':args.variant,'quality_state':'inconclusive'},ensure_ascii=False))


if __name__=='__main__':main()
'''
    (bundle/'synthesize.py').write_text(entry)
    (bundle/'README.md').write_text('''# VTL研究用生成bundle\n\nかなまたは音素列と明示アクセントを入力する非ニューラル生成器。固定160Hz・0.20秒/モーラ。日本語の明瞭性・自然さは未資格。`--variant accent-tap` は短い舌尖閉鎖の研究比較。録音、AI重み、発話辞書、保存済み軌跡を含まない。\n\nNumPy/SciPyとmacOS arm64環境が必要。辞書前段は含めない。`JD3.speaker` は全発話で共有する声道形状と音素標的であり、参照録音から生成した発話制御列ではない。\n\nVocalTractLabはGPL-3.0-or-later。添付のLICENSE-VTLとSOURCE.jsonを参照。APIライブラリは公式ソースを変更せずReleaseで構築。\n''')
    (bundle/'SOURCE.json').write_text(json.dumps({'upstream':'https://github.com/TUD-STKS/VocalTractLabBackend-dev','commit':'df30392f18dc5e175b577c3ba734caaa65a3927f','license':'GPL-3.0-or-later','source_changes':False,'build':'cmake Release; CMAKE_POLICY_VERSION_MINIMUM=3.5','physical_model':'共有のJD3声道形状・音素標的と声門モデル','rules_source_hashes':{p:file_hash(ROOT/p) for p in ('vtl_japanese.py','vtl_speech.py','export_vtl.py')}},ensure_ascii=False,indent=2))
    allowed={'generator.py','synthesize.py','libVocalTractLabApi.dylib','JD3.speaker','LICENSE-VTL','README.md','SOURCE.json'}
    if {p.name for p in bundle.iterdir()}!=allowed:raise ValueError('移出許可リスト外のファイルです')
    write_once(bundle/'manifest.json',{'files':{p.name:file_hash(p) for p in sorted(bundle.iterdir())},'allowed_types':'生成コード・共有物理モデル・共有規則・来歴・ライセンス','contains_recording':False,'contains_neural_weights':False,'export_source':file_hash(Path(__file__))})
    print(bundle)


if __name__=='__main__':main()
