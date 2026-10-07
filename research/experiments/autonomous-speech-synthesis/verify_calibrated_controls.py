#!/usr/bin/env python3
"""校正値の適用と、対象音素のない文が変化していないことを検査する。"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash


def main():
    path=ROOT/'results/ans-vtl-calibrated-v3';parent=ROOT/'results/ans-vtl-japanese-v2'
    tasks={t['id']:t for t in read(path/'task-suite.json')['tasks']}
    original={(r['task'],r['variant']):parent/r['wav'] for r in read(parent/'p34-speech.json')['rows'] if r.get('wav')}
    unchanged=[];closures=[]
    for r in read(path/'p34-speech.json')['rows']:
        if not r.get('wav'):continue
        wave=path/r['wav'];control=read(wave.with_suffix('.controls.json'))
        comparison='mora' if r['variant']=='mora-tap-calibrated' else 'accent-tap'
        if not any(p in ('r','ry') for p in tasks[r['task']]['phonemes']):
            unchanged.append({'task':r['task'],'variant':r['variant'],'same_wav':file_hash(wave)==file_hash(original[(r['task'],comparison)])})
        tree=ET.fromstring(control['gestural_score_generated_at_runtime'])
        for g in tree.find("gesture_sequence[@type='tongue-tip-gestures']"):
            if g.get('value')=='tt-alveolar-closure':
                closures.append({'task':r['task'],'variant':r['variant'],'duration_seconds':float(g.get('duration_s')),'tau_seconds':float(g.get('time_constant_s'))})
    # /t,d,n/の閉鎖も同じ記号を使うため、校正の42ms条件を満たすものを区別する。
    calibrated=[r for r in closures if abs(r['duration_seconds']-.042)<1e-6 and abs(r['tau_seconds']-.007)<1e-9]
    expected=2*sum(sum(p in ('r','ry') for p in t['phonemes']) for t in tasks.values())
    result={'passed':all(r['same_wav'] for r in unchanged) and len(calibrated)==expected,'unchanged_non_r_sentences':unchanged,'calibrated_tap_count':len(calibrated),'expected_count':expected,'calibrated':calibrated,'scope':'制御変更の範囲。知覚品質を意味しない。','source_sha256':file_hash(Path(__file__))}
    write_once(path/'control-change-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('unchanged_non_r_sentences','calibrated')},ensure_ascii=False,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
