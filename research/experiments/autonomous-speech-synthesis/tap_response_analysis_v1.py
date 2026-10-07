#!/usr/bin/env python3
"""保存済み管断面から指令と実応答の時間差を可視化する。追加レンダーは行わない。"""
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash


def main():
    source=ROOT/'results/ans-vtl-tap-timing-v1/timing-audit.json'
    data=read(source)['geometry'];groups={}
    for row in data:groups.setdefault((row['task'],row['variant']),[]).append(row)
    pairs=[]
    for (task,variant),group in groups.items():
        if variant!='center':continue
        for index,center in enumerate(group):
            shifts=[]
            for kind in ('early','late'):
                other=groups[(task,kind)][index]
                shifts.append({'variant':kind,'command_ms':(other['start']-center['start'])*1000,
                    'closure_onset_shift_ms':(other['closure_onset']-center['closure_onset'])*1000,
                    'closure_release_shift_ms':(other['closure_release']-center['closure_release'])*1000,
                    'closure_duration_change_ms':(other['near_closure_seconds']-center['near_closure_seconds'])*1000})
            pairs.append({'task':task,'tap_index':index,'center_closure_duration_ms':center['near_closure_seconds']*1000,'shifts':shifts})
    output=ROOT/'results/tap-response-analysis-v1';output.mkdir(exist_ok=True)
    result={'rows':pairs,'geometry_sample_ms':110/44100*1000,'audio_renders':0,'new_AI_evaluations':0,
            'source_sha256':file_hash(source),'script_sha256':file_hash(Path(__file__)),
            'scope':'内部の管断面応答のみ。実測の日本語舌尖運動との一致や知覚的因果は未検証。'}
    write_once(output/'response.json',result)
    # 図中は環境依存の日本語フォントを避け、量記号と課題IDで表示する。
    fig,axes=plt.subplots(2,4,figsize=(12,5.5),sharex=True,sharey=True)
    colors={'early':'#1678A5','center':'#555555','late':'#D36C23'}
    for axis,pair in zip(axes.flat,pairs):
        task=pair['task'];i=pair['tap_index'];center=groups[(task,'center')][i]
        for kind in ('early','center','late'):
            row=groups[(task,kind)][i]
            t=np.array([f['seconds'] for f in row['frames']]);area=[f['area_cm2'] for f in row['frames']]
            axis.plot(1000*(t-center['start']),area,label=kind,color=colors[kind],lw=1.5)
        axis.axhline(.01,color='#9A3567',ls=':',lw=1)
        axis.set_title(f'{task} / r{i+1}',fontsize=10);axis.set_yscale('log');axis.set_ylim(5e-5,5);axis.set_xlim(-30,110)
        axis.grid(alpha=.15)
    for ax in axes[-1]:ax.set_xlabel('t - center command onset [ms]')
    for ax in axes[:,0]:ax.set_ylabel('min. alveolar area [cm²]')
    axes[0,0].legend(fontsize=8);fig.suptitle('VTL tube response: fixed 42 ms command, onset shift ±8 ms',fontsize=12)
    fig.tight_layout()
    for suffix in ('png','svg'):
        target=output/f'tap-response.{suffix}'
        if target.exists():raise FileExistsError('図を上書きしません')
        fig.savefig(target,dpi=150)
    plt.close(fig)
    print(result)

if __name__=='__main__':main()
