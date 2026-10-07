#!/usr/bin/env python3
"""評点を選択条件に使わず、事前の規則で日本語の原FLACを抽出する。"""
import hashlib
import io
from pathlib import Path
import re
import sys
import pyarrow.parquet as pq
import soundfile as sf
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash


def rank(s):return hashlib.sha256(s.encode()).hexdigest()


def main():
    out=ROOT/'results/urgent-ja-v1';protocol=read(out/'protocol.json');download=read(out/'download.json')
    meta=[];columns=['sample_id','utterance_id','system_id','speaker_id','language','text','duration','mos','listener_scores','is_simulated','sample_rate']
    for f in download['files']:
        p=out/f['file']
        if file_hash(p)!=f['sha256']:raise ValueError('配布ファイルのハッシュが変わりました')
        meta.extend(pq.read_table(p,columns=columns,filters=[('language','==','jpn')]).to_pylist())
    utterances={}
    for row in meta:
        if not re.fullmatch(r'acr_fileid_[0-9]+_[0-9]+',row['sample_id']):raise ValueError('音声IDの書式が想定外です')
        if not row['listener_scores'] or abs(sum(row['listener_scores'])/len(row['listener_scores'])-row['mos'])>.00051:raise ValueError('個票と公開MOSが整合しません')
        utterances.setdefault(row['utterance_id'],[]).append(row)
    speakers={};excluded=[]
    for uid,group in utterances.items():
        first=group[0]
        ok=len(group)==6 and len({r['system_id'] for r in group})==6 and len({r['speaker_id'] for r in group})==1
        ok=ok and all(2<=r['duration']<=12 for r in group) and bool(re.search('[ぁ-んァ-ヶ一-龯]',first['text']))
        if not ok:excluded.append(uid);continue
        speakers.setdefault(first['speaker_id'],[]).append(uid)
    chosen=[min(speakers[sp],key=rank) for sp in sorted(speakers,key=rank)[:16]]
    selected={row['sample_id']:row for uid in chosen for row in utterances[uid]}
    if not selected:raise RuntimeError('対象範囲内の音声を選べません')
    selection={'utterances':chosen,'speakers':[utterances[u][0]['speaker_id'] for u in chosen],
               'selected_sample_ids':sorted(selected),'eligible_speaker_count':len(speakers),'japanese_samples':len(meta),
               'japanese_utterances':len(utterances),'excluded_utterances':excluded,'protocol_sha256':file_hash(out/'protocol.json'),
               'selection_used_mos':False,'script_sha256':file_hash(Path(__file__))}
    write_once(out/'selection.json',selection)
    audio_dir=out/'audio';audio_dir.mkdir(exist_ok=True);items={}
    for f in download['files']:
        table=pq.read_table(out/f['file'],columns=['sample_id','audio','language'],filters=[('language','==','jpn')])
        for row in table.to_pylist():
            key=row['sample_id']
            if key not in selected:continue
            payload=row['audio']['bytes']
            if not payload.startswith(b'fLaC'):raise ValueError('原FLACではない音声です')
            path=audio_dir/(key+'.flac')
            if path.exists():
                if path.read_bytes()!=payload:raise ValueError('抽出済み原音声の不一致')
            else:path.write_bytes(payload)
            audio,fs=sf.read(io.BytesIO(payload))
            if audio.ndim!=1 or abs(len(audio)/fs-selected[key]['duration'])>2/fs:raise ValueError('配布音声とメタデータの長さが不一致です')
            items[key]={**selected[key],'path':str(path),'sha256':file_hash(path),'decoded_sample_rate':fs,'decoded_samples':len(audio),'evaluation_seed':20261002,'kind':'primary'}
    if set(items)!=set(selected):raise ValueError('選択された音声の欠落があります')
    primary=[items[k] for uid in chosen for k in sorted(items) if items[k]['utterance_id']==uid]
    repeat=[{**r,'kind':'repeat','sample_id':r['sample_id']+'-repeat'} for r in primary[:6]]
    varied=[{**r,'kind':'seed7','sample_id':r['sample_id']+'-seed7','evaluation_seed':7} for r in primary[:6]]
    manifest={'rows':primary+repeat+varied,'primary_count':len(primary),'total_count':len(primary+repeat+varied),
              'protocol_sha256':file_hash(out/'protocol.json'),'selection_sha256':file_hash(out/'selection.json'),
              'source_revision':protocol['revision'],'raw_audio_transformation':'埋め込みFLACのbytesを変更せず抽出','license':'CC-BY-4.0',
              'attribution':'Li et al., ICASSP 2026 URGENT Speech Enhancement Challenge; urgent-challenge/urgent2026-sqa'}
    if manifest['total_count']>protocol['max_total_predictions']:raise RuntimeError('事前の評価件数を超えます')
    write_once(out/'manifest.json',manifest)
    print({k:v for k,v in selection.items() if k not in ('selected_sample_ids','utterances','speakers')});print('推論予定',manifest['total_count'])

if __name__=='__main__':main()
