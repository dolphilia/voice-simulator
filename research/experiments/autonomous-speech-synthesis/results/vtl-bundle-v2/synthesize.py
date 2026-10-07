#!/usr/bin/env python3
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
def kana_to_phonemes(text):
    """かな表記に限定した辞書非依存前段。未知文字は黙って捨てない。"""
    text = unicodedata.normalize('NFKC', text)
    text = ''.join((chr(ord(c) - 96) if 'ァ' <= c <= 'ヶ' else c for c in text))
    table = dict(zip('あいうえお', VOWELS))
    for chars, onset in [('かきくけこ', 'k'), ('がぎぐげご', 'g'), ('さしすせそ', 's'), ('ざじずぜぞ', 'z'), ('たちつてと', 't'), ('だぢづでど', 'd'), ('なにぬねの', 'n'), ('はひふへほ', 'h'), ('ばびぶべぼ', 'b'), ('ぱぴぷぺぽ', 'p'), ('まみむめも', 'm'), ('らりるれろ', 'r')]:
        table.update({c: onset + ' ' + v for c, v in zip(chars, VOWELS)})
    table.update({'し': 'sh i', 'じ': 'j i', 'ち': 'ch i', 'つ': 'ts u', 'ぢ': 'j i', 'づ': 'z u', 'ふ': 'f u', 'や': 'y a', 'ゆ': 'y u', 'よ': 'y o', 'わ': 'w a', 'を': 'o', 'ん': 'N', 'っ': 'Q'})
    result = []
    for index, c in enumerate(text):
        if c in 'ゃゅょ':
            if len(result) < 2 or result[-1] != 'i':
                raise ValueError(f'拗音の前段を解釈できません: {index}')
            result.pop()
            base = result.pop()
            result.extend([{'k': 'ky', 'g': 'gy', 'n': 'ny', 'h': 'hy', 'm': 'my', 'r': 'ry', 'sh': 'sh', 'ch': 'ch', 'j': 'j'}.get(base, base), {'ゃ': 'a', 'ゅ': 'u', 'ょ': 'o'}[c]])
        elif c == 'ー':
            if not result or result[-1] not in VOWELS:
                raise ValueError('長音の直前に母音が必要です')
            result.append(result[-1])
        elif c in ' 、。，,.!?！？\n':
            if result and result[-1] != 'pau':
                result.append('pau')
        elif c in table:
            result.extend(table[c].split())
        else:
            raise ValueError(f'未対応文字: {c}。かな、または明示音素で指定してください')
    return result

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
