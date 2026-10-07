#!/usr/bin/env python3
"""辞書・規則のfull-contextラベルをモーラとアクセント句へ変換する。"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
NUCLEI={'a','i','u','e','o','A','I','U','E','O','N','cl'}


def from_labels(labels):
    phrases=[];current=None
    for label in labels:
        m=re.search(r'\-([^+]+)\+',label)
        if not m:raise ValueError('音素ラベルの構文が不正です')
        phone=m.group(1)
        if phone in ('sil','pau'):
            current=None
            if phone=='pau':phrases.append({'pause':True,'phones':['pau'],'moras':[]})
            continue
        a=re.search(r'/A:(-?\d+)\+(\d+)\+(\d+)',label)
        f=re.search(r'/F:(\d+)_(\d+)#[^@]*@(\d+)_(\d+)',label)
        if not a or not f:raise ValueError('アクセント/モーラ情報が不足しています')
        mora_count,accent,index,_=map(int,f.groups());position=int(a.group(2))
        if current is None or index!=current['label_index'] or (position==1 and current['moras'] and current['moras'][-1]['position']>1):
            current={'label_index':index,'mora_count':mora_count,'accent_nucleus':accent,'phones':[],'moras':[]}
            phrases.append(current)
        mapped='Q' if phone=='cl' else phone
        if not current['moras'] or current['moras'][-1]['position']!=position:
            high=position<=accent if accent==1 else position>=2 and (accent==0 or position<=accent)
            current['moras'].append({'position':position,'phones':[],'high':high})
        current['moras'][-1]['phones'].append(mapped);current['phones'].append(mapped)
    for phrase in phrases:
        if phrase.get('pause'):continue
        if len(phrase['moras'])!=phrase['mora_count']:raise ValueError('モーラ数とラベルが一致しません')
        for mora in phrase['moras']:
            if mora['phones'][-1] not in {'Q',*NUCLEI}:raise ValueError('モーラ末尾の核が未対応です')
    return phrases


def analyze(text):
    import pyopenjtalk
    # run_frontend/make_labelは辞書・形態素解析・アクセント規則のみ。音響合成は呼ばない。
    features=pyopenjtalk.run_frontend(text)
    unknown=[f['string'] for f in features if f.get('pron') in ('*','') and f.get('mora_size',0)>0]
    if unknown:raise ValueError(f'発音未解決語: {unknown}')
    labels=pyopenjtalk.make_label(features)
    phrases=from_labels(labels)
    return {'text':text,'phrases':phrases,'phonemes':[p for phrase in phrases for p in phrase['phones']],
      'features':features,'full_context_labels':labels,'frontend_version':pyopenjtalk.__version__,'runtime_neural':False,'acoustic_model_called':False,
      'scope':'Open JTalk辞書と規則の推定。アクセントの人手正解を仮定しない。未知語・同形異音語を含む任意文品質は未保証。'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    specs=[('紫の船がゆっくり進む。','novel'),('青い空。','development'),('雨が降る。','development'),('猫が歩く。','development'),('風が吹く。','development'),('花が咲く。','development'),('水を飲む。','development'),('学校へ行く。','development'),('月が出る。','development'),('今日、東京へ行きます。','novel'),('切手を買った。','novel'),('新しい地図を机に広げた。','novel')]
    records=[]
    for text,split in specs:
        try:records.append({**analyze(text),'split':split,'status':'resolved'})
        except Exception as exc:records.append({'text':text,'split':split,'status':'unavailable','error':repr(exc)})
    result={'records':records,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'failures':sum(r['status']!='resolved' for r in records)}
    args.output.parent.mkdir(exist_ok=True,parents=True)
    with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'records':len(records),'failures':result['failures']},ensure_ascii=False))


if __name__=='__main__':main()
