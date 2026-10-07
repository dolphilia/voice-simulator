"""保存済み摂動波形だけでDIO支持域と別DSP推定の感度を点検する。主要判定は変えない。"""
import sys
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, REPO, PILOT, read, save, digest
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld
from objective import extract_local


def median_frequency(values):
    v=np.asarray(values);v=v[(v>=70)&(v<=800)]
    return float(np.median(v)) if len(v) else None


def main():
    with LocalBudget().job('audit','保存済み初回摂動波形のDIO・Harvest・内部LF0・境界感度を比較',2000000):
        save(RESULT/'measurement-sensitivity-contract.json',{'source_sha256':digest(ROOT/'measurement_sensitivity.py'),
            'wave_selection':'各4文の既定と初回中央差分で既に生成した波形のみ',
            'harvest_settings':{'sample_rate':24000,'f0_floor':70.,'f0_ceil':800.,'frame_period':5.,'stonemask':False},
            'boundary_offsets_seconds':[-.01,0.,.01],'primary_decisions_modified':False,
            'new_generation_calls':0,'new_ai_calls':0,'new_fit_calls':0,'human_boundaries_qualified':False,
            'scope':'同じWORLD系DSPとHMM内部値の整合診断。独立な知覚資格や日本語の測定器資格ではない。'})
        records=[];plot_inputs=[]
        for row in read(RESULT/'protocol.json')['rows']:
            source=read(REPO/row['source_training_input']);snapshot=source['snapshot']
            folder=RESULT/'render'/row['id'];support=read(folder/'support-contract.json')['indices']
            paths=[folder/'native.json',*sorted(folder.glob('iteration-0-axis-*.json'))]
            for path in paths:
                record=read(path);wav=ROOT/record['wav'];assert digest(wav)==record['wav_sha256']
                fs,audio=wavfile.read(wav);assert fs==24000
                harvest,ht=pyworld.harvest(audio.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                arrays=np.load(path.with_suffix('.npz'));dio,t=arrays['dio_f0'],arrays['dio_times'];lf0=arrays['generated_lf0']
                boundaries=np.r_[0,np.cumsum(snapshot['duration'])]
                intervals=[]
                for i in support:
                    lo,hi=boundaries[i*5],boundaries[(i+1)*5]
                    interval_mask=(t>=lo*.005)&(t<hi*.005);hmask=(ht>=lo*.005)&(ht<hi*.005)
                    dv=dio[interval_mask];hv=harvest[hmask];internal=lf0[lo:hi]
                    iv=np.exp(internal[(internal>=np.log(70))&(internal<=np.log(800))])
                    shifted={}
                    for shift in (-.01,0.,.01):
                        found,missing=extract_local(dio,t-shift,snapshot,[i]);shifted[str(shift)]={'passed':not missing,
                            'voiced_frames':found[0]['voiced_frames'] if found else int(np.sum((dio[(t>=lo*.005+shift)&(t<hi*.005+shift)]>=70)&(dio[(t>=lo*.005+shift)&(t<hi*.005+shift)]<=800)))}
                    intervals.append({'label_index':i,'engine_frames':int(hi-lo),'internal_voiced_frames':len(iv),
                        'internal_f0_median':float(np.median(iv)) if len(iv) else None,
                        'dio_frames':len(dv),'dio_voiced_frames':int(np.sum((dv>=70)&(dv<=800))),'dio_f0_median':median_frequency(dv),
                        'harvest_frames':len(hv),'harvest_voiced_frames':int(np.sum((hv>=70)&(hv<=800))),'harvest_f0_median':median_frequency(hv),
                        'harvest_support_pass':len(hv)>0 and int(np.sum((hv>=70)&(hv<=800)))>=max(3,len(hv)*.5),
                        'shifted_dio_support':shifted})
                records.append({'text_id':row['id'],'text':row['text'],'attempt':record['attempt'],'original_status':record['status'],
                    'wav_sha256':digest(wav),'intervals':intervals,'harvest_f0':harvest.tolist(),'harvest_times':ht.tolist()})
                if row['id']=='unknown-09' and path.stem in ('native','iteration-0-axis-1-minus'):
                    plot_inputs.append((path.stem,arrays,harvest,ht,snapshot))
        save(RESULT/'measurement-sensitivity.json',{'rows':records,'waveforms_remeasured':len(records),
            'primary_decisions_modified':False,'new_generation_calls':0,'new_ai_calls':0,'new_fit_calls':0,'quality_certified':False})
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(2,1,figsize=(8,5),sharex=True,sharey=True)
        for ax,(name,a,h,ht,snapshot) in zip(axes,plot_inputs):
            edges=np.r_[0,np.cumsum(snapshot['duration'])]*.005;lo,hi=edges[50],edges[55]
            mask=(a['dio_times']>=lo-.04)&(a['dio_times']<=hi+.04)
            tt=np.arange(len(a['generated_lf0']))*.005
            imask=(tt>=lo-.04)&(tt<=hi+.04)&(a['generated_lf0']>0)
            ax.plot(tt[imask],np.exp(a['generated_lf0'][imask]),label='Internal LF0',color='black')
            df=a['dio_f0'].copy();df[df==0]=np.nan
            ax.plot(a['dio_times'][mask],df[mask],'o-',markersize=3,label='DIO')
            hf=h.copy();hf[hf==0]=np.nan;hm=(ht>=lo-.04)&(ht<=hi+.04)
            ax.plot(ht[hm],hf[hm],'.-',label='Harvest')
            ax.axvspan(lo,hi,alpha=.1,color='gray');ax.set_title(name);ax.set_ylabel('F0 (Hz)');ax.grid(alpha=.3)
        axes[0].legend(loc='upper right');axes[-1].set_xlabel('Time (s)');fig.tight_layout()
        fig.savefig(RESULT/'measurement-sensitivity.png',dpi=160);plt.close(fig)
    print('保存済み',len(records),'波形の測定感度を保存。主要判定の変更なし',flush=True)

if __name__=='__main__':main()
