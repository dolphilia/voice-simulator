"""固定2方式で24信号を測定。開発だけで方法選択し、確認で変更しない。"""
import sys
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, REPO, PILOT, read, save, digest
from metrics import evaluate, aggregate, choose
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld


def main():
    protocol=read(RESULT/'protocol.json')
    for n,sha in protocol['source_hashes'].items():assert digest(ROOT/n)==sha
    for p,sha in protocol['world_files'].items():assert digest(REPO/p)==sha
    signals={r['id']:r for r in read(RESULT/'signal-manifest.json')['rows']}
    results=[];selected=None
    for split in ('development','confirmation'):
        for row in [r for r in protocol['rows'] if r['split']==split]:
            source=signals[row['id']]
            for method in protocol['methods']:
                path=RESULT/'measurements'/method/(row['id']+'.json')
                record={'id':row['id'],'split':split,'family':row['family'],'base_f0_hz':row['base_f0_hz'],'method':method,
                    'status':'missing','quality_certified':False,'ai_calls':0,'human_perception_qualified':False}
                if source['status']=='completed':
                    try:
                        with LocalBudget().job('audit','固定信号測定/'+method+'/'+row['id'],100000):
                            wav=ROOT/source['wav'];assert digest(wav)==source['wav_sha256']
                            fs,audio=wavfile.read(wav);assert fs==24000 and len(audio)==28800 and audio.ndim==1
                            if method=='dio':
                                f0,t=pyworld.dio(audio.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                                f0=pyworld.stonemask(audio.astype(float),f0,t,fs)
                            else:f0,t=pyworld.harvest(audio.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.)
                            metric=evaluate(row,f0,t)
                            record.update(status='completed',metrics=metric,f0=f0.tolist(),times=t.tolist(),wav_sha256=digest(wav))
                            save(path,record)
                    except Exception as exc:
                        record.update(status='failed',error=repr(exc))
                        if not path.exists():save(path,record)
                else:save(path,record)
                results.append(record)
            print(split,row['id'],'2方式測定完了',flush=True)
        phase={method:aggregate([r for r in results if r['method']==method and r['split']==split]) for method in protocol['methods']}
        if split=='development':
            selected=choose(phase)
            save(RESULT/'development-selection.json',{'methods':phase,'selected_method':selected,'confirmation_consulted':False,
                'selection_frozen_before_confirmation':True,'no_threshold_tuning':True})
        else:
            prior=read(RESULT/'development-selection.json');assert selected==prior['selected_method']
            save(RESULT/'confirmation.json',{'methods':phase,'selected_method':selected,
                'selected_method_confirmed':selected is not None and phase[selected]['all_passed'],
                'method_changed_from_confirmation':False,'unselected_methods_are_diagnostic':True})
    save(RESULT/'measurement-manifest.json',{'rows':results,'completed':sum(r['status']=='completed' for r in results),'planned':48,
        'new_ai_calls':0,'quality_certified':False})

if __name__=='__main__':main()
