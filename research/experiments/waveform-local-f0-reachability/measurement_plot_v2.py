"""保存済み測定結果を既存の描画環境で図示する。DSPを再実行しない。"""
import os
from pathlib import Path
import unicodedata
from campaign import LocalBudget, RESULT, REPO, read, save, digest
os.environ['MPLCONFIGDIR']=str(RESULT/'.matplotlib-cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


def main():
    with LocalBudget().job('audit','保存済みDIO・Harvest結果を既存Matplotlibで図示',1000000):
        font_path=next(p for p in Path('/System/Library/Fonts').glob('*.ttc') if unicodedata.normalize('NFC',p.name)=='ヒラギノ角ゴシック W3.ttc')
        font=FontProperties(fname=str(font_path));rows=read(RESULT/'measurement-sensitivity.json')['rows']
        names=['native','iteration-0-axis-1-minus'];titles=['既定波形','モーラ位置の係数 −0.25 の摂動']
        source=read(REPO/next(r for r in read(RESULT/'protocol.json')['rows'] if r['id']=='unknown-09')['source_training_input'])
        edges=np.r_[0,np.cumsum(source['snapshot']['duration'])]*.005;lo,hi=edges[50],edges[55]
        fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True,sharey=True)
        for ax,name,title in zip(axes,names,titles):
            record=next(r for r in rows if r['text_id']=='unknown-09' and r['attempt']==name)
            a=np.load(RESULT/'render/unknown-09'/(name+'.npz'));t=a['dio_times'];dio=a['dio_f0'];internal=a['generated_lf0']
            tt=np.arange(len(internal))*.005;hm=np.array(record['harvest_times']);hv=np.array(record['harvest_f0'])
            mask=(t>=lo-.04)&(t<=hi+.04);imask=(tt>=lo-.04)&(tt<=hi+.04)&(internal>0);hmask=(hm>=lo-.04)&(hm<=hi+.04)
            ax.plot(tt[imask],np.exp(internal[imask]),color='black',label='合成器内部LF0')
            df=dio.copy();df[df==0]=np.nan
            ax.plot(t[mask],df[mask],'o-',markersize=4,label='DIO')
            h=hv.copy();h[h==0]=np.nan
            ax.plot(hm[hmask],h[hmask],'.-',label='Harvest')
            absent=mask&(dio==0);ax.scatter(t[absent],np.full(absent.sum(),315.),marker='x',s=20,label='DIO未検出（315Hz位置に表示）')
            ax.axvspan(lo,hi,alpha=.1,color='gray');ax.set_title(title,fontproperties=font);ax.set_ylabel('F0（Hz）',fontproperties=font);ax.grid(alpha=.3)
            ax.set_ylim(300,825)
        axes[0].legend(loc='upper right',prop=font);axes[-1].set_xlabel('時間（秒）／灰色域は固定HMM音素区間 /a/',fontproperties=font)
        fig.tight_layout();fig.savefig(RESULT/'measurement-sensitivity-v2.png',dpi=160);plt.close(fig)
        save(RESULT/'measurement-plot-recovery.json',{'method':'既存research/.venvのMatplotlibを使用。取得なし、再推定なし。',
            'matplotlib_version':matplotlib.__version__,'source_measurements_sha256':digest(RESULT/'measurement-sensitivity.json'),
            'figure_sha256':digest(RESULT/'measurement-sensitivity-v2.png'),'failed_original_audit_retained':True,
            'new_generation_calls':0,'new_ai_calls':0,'new_fit_calls':0})
    print('保存済み測定結果の図を作成。追加推定・取得なし',flush=True)

if __name__=='__main__':main()
