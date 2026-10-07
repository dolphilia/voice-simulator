"""固定24条件を一度ずつ生成し、正解配列・位相・出力を照合する。"""
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, read, save, digest
from fixtures import generate


def main():
    protocol=read(RESULT/'protocol.json')
    for n,sha in protocol['source_hashes'].items():assert digest(ROOT/n)==sha
    output=[]
    for row in protocol['rows']:
        record={'id':row['id'],'split':row['split'],'family':row['family'],'status':'failed','render_calls':1,'source':'手続き的信号。教師音声ではない。'}
        path=RESULT/'signals'/(row['id']+'.wav')
        try:
            with LocalBudget().job('render',row['id'],500000):
                stored=np.load(ROOT/row['truth_file']);assert digest(ROOT/row['truth_file'])==row['truth_sha256']
                audio,truth,detail=generate(row)
                assert all(np.array_equal(stored[k],truth[k]) for k in ('t','f0_hz','voiced_mask'))
                error=float(np.max(abs(np.diff(truth['phase'],prepend=0)*row['fs']/(2*np.pi)-truth['f0_hz'])))
                assert error<1e-6
                path.parent.mkdir(parents=True,exist_ok=True);wavfile.write(path,row['fs'],audio)
                np.savez_compressed(path.with_suffix('.npz'),phase=truth['phase'])
                record.update(status='completed',wav=str(path.relative_to(ROOT)),wav_sha256=digest(path),
                    phase_file=str(path.with_suffix('.npz').relative_to(ROOT)),phase_sha256=digest(path.with_suffix('.npz')),
                    phase_recovery_error_hz=error,output_samples=len(audio),peak=float(np.max(abs(audio))),**detail)
                save(path.with_suffix('.json'),record)
        except Exception as exc:
            if not any(e['event']=='start' and e['label']==row['id'] for e in LocalBudget().events()):raise
            record.update(status='failed',error=repr(exc))
            if not path.with_suffix('.json').exists():save(path.with_suffix('.json'),record)
        output.append(record);print(row['id'],record['status'],flush=True)
    save(RESULT/'signal-manifest.json',{'rows':output,'completed':sum(r['status']=='completed' for r in output),
        'planned':24,'no_retries':True,'independent_japanese_texts':0,'quality_certified':False})

if __name__=='__main__':main()
