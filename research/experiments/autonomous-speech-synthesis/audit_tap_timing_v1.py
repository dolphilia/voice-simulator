#!/usr/bin/env python3
"""接触時刻の変更範囲と、実際の管断面応答を既存親と比較する。"""
import ctypes as ct
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.backends import VTL
from autonomous_speech_synthesis.io import read,write_once,file_hash
from calibrate_tap_geometry import geometry


def intervals(tree):
    t=0;result=[]
    for g in tree.find("gesture_sequence[@type='tongue-tip-gestures']"):
        d=float(g.get('duration_s'))
        if g.get('value')=='tt-alveolar-closure' and abs(d-.042)<1e-6 and abs(float(g.get('time_constant_s'))-.007)<1e-9:
            result.append((t,t+d))
        t+=d
    return result


def main():
    path=ROOT/'results/ans-vtl-tap-timing-v1';parent=ROOT/'results/ans-vtl-calibrated-v3'
    original={r['task']:parent/r['wav'] for r in read(parent/'p34-speech.json')['rows'] if r['variant']=='mora-tap-calibrated' and r.get('wav')}
    vtl=VTL();pointer=ct.POINTER(ct.c_double)
    vtl.lib.vtlGesturalScoreToTractSequence.argtypes=[ct.c_char_p,ct.c_char_p]
    vtl.lib.vtlTractToTube.argtypes=[pointer,pointer,pointer,ct.POINTER(ct.c_int),pointer,pointer,pointer]
    controls=[];measurements=[];parents=set()
    try:
        for row in read(path/'p34-speech.json')['rows']:
            if not row.get('wav'):continue
            wave=path/row['wav'];score=read(wave.with_suffix('.controls.json'))['gestural_score_generated_at_runtime']
            old=read(original[row['task']].with_suffix('.controls.json'))['gestural_score_generated_at_runtime']
            tree=ET.fromstring(score);oldtree=ET.fromstring(old)
            active=intervals(tree);baseline=intervals(oldtree)
            unchanged=all(ET.tostring(s)==ET.tostring(oldtree.find(f"gesture_sequence[@type='{s.get('type')}']")) for s in tree if s.get('type')!='tongue-tip-gestures')
            shift=-.008 if row['variant']=='early' else .008
            differences=[a[0]-b[0] for a,b in zip(active,baseline)]
            valid=len(active)==len(baseline) and all(abs(d-shift)<1e-6 for d in differences)
            controls.append({'task':row['task'],'variant':row['variant'],'non_tongue_tip_sequences_equal':unchanged,
                             'command_shifts_seconds':differences,'expected_shift_applied':valid,
                             'non_r_wave_equal':file_hash(wave)==file_hash(original[row['task']]) if not active else None})
            if not active:continue
            for kind,gs,iv in [(row['variant'],score,active)]+([('center',old,baseline)] if row['task'] not in parents else []):
                data=geometry(vtl,gs,iv)
                for d in data:
                    closed=[f['seconds'] for f in d['frames'] if f['area_cm2']<=.01]
                    measurements.append({'task':row['task'],'variant':kind,**d,'closure_onset':min(closed) if closed else None,'closure_release':max(closed)+110/44100 if closed else None})
            parents.add(row['task'])
    finally:vtl.close()
    result={'passed':all(r['non_tongue_tip_sequences_equal'] and r['expected_shift_applied'] and r['non_r_wave_equal'] is not False for r in controls),
            'controls':controls,'geometry':measurements,'source_sha256':file_hash(Path(__file__)),
            'scope':'内部幾何と変更範囲のみ。日本語弾音・知覚の資格は未取得。'}
    write_once(path/'timing-audit.json',result)
    print('変更範囲',result['passed'],'接触区間数',len(measurements),flush=True)
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
