"""波形生成前に全条件、駆動正解、既定MSD領域を固定する。"""
import re
import numpy as np
from event_io import *
import event_signal as signal
import event_metrics as metrics

def main():
    b=LocalBudget()
    with b.job('setup','24条件・駆動正解・54保存波形参照を凍結',15_000_000):
        prior=read(CRES/'protocol.json');rows=read(CRES/'next-proposal-preparation.json')['rows'];assert len(rows)==24
        tests={'signal':signal.tests(rows[0]),'metrics':metrics.tests(rows[0])}
        inputs={};refs=[];masks=[]
        def ref(path):
            path=Path(path);inputs[str(path.relative_to(REPO))]=digest(path)
        for n in ('protocol.json','render-manifest.json','timing-audit.json','next-proposal-preparation.json'):ref(CRES/n)
        for name,sha in prior['dependencies'].items():
            if '/pyworld/' in name:assert digest(REPO/name)==sha;ref(REPO/name)
        for i,row in enumerate(prior['rows']):
            source=REPO/row['source_record'];native=source.parent/'native.json'
            ref(source);ref(native);ref(REPO/row['parameter_lf0_source_npz']);ref(REPO/row['support_contract'])
            own=read(source)['state_snapshot_after'];base=read(native)['state_snapshot_after']
            assert own['duration']==base['duration'] and own['msd']==base['msd']
            mask=np.repeat(np.asarray(base['msd'])>.5,base['duration'])
            lf0=np.load(CRES/'parameters'/f'{i:02d}.npz')['lf0'][:,0];ref(CRES/'parameters'/f'{i:02d}.npz')
            assert np.array_equal(mask,lf0>0)
            support=read(REPO/row['support_contract']);indices=sorted(set(support['indices'])|set(row['focus_indices']))
            ends=np.cumsum(np.r_[0,np.asarray(base['duration']).reshape(-1,5).sum(axis=1)])
            labels=row['full_context_labels'];phones=[]
            for idx in indices:
                lo,hi=int(ends[idx]),int(ends[idx+1]);known=mask[lo:hi]
                assert known.any()
                phones.append({'index':idx,'phone':re.search(r'-(.*?)\+',labels[idx]).group(1),'frame_start':lo,'frame_end':hi,
                    'focus':idx in row['focus_indices'],'native_runs':metrics.runs(known),'known_voiced_frames':int(known.sum()),
                    'partial':bool(not known.all())})
            masks.append({'id':row['id'],'variant':row['variant'],'phase':row['phase'],'native_source':str(native.relative_to(REPO)),
                'native_source_sha256':digest(native),'frames':len(mask),'native_runs':metrics.runs(mask),'phones':phones,
                'lf0':str((CRES/'parameters'/f'{i:02d}.npz').relative_to(REPO))})
        for item in read(CRES/'render-manifest.json')['rows']:
            record=REPO/item['record'];assert digest(record)==item['sha256'];ref(record)
            d=read(record);wave=REPO/d['wav'];assert digest(wave)==d['wav_sha256'];ref(wave);ref(record.with_suffix('.npz'))
            refs.append({**item,'wav':d['wav'],'wav_sha256':d['wav_sha256'],'dio':str(record.with_suffix('.npz').relative_to(REPO)),
                'dio_sha256':digest(record.with_suffix('.npz'))})
        assert len(refs)==54 and len(masks)==18
        for row in rows:
            signal.validate(row);path=RESULT/'truth'/f"{row['id']}.npz"
            write_checked(path,npz_bytes(**signal.truth(row)));row['truth']=str(path.relative_to(REPO));row['truth_sha256']=digest(path)
        save(RESULT/'negative-tests.json',tests)
        save(RESULT/'native-mask-contract.json',{'rows':masks,'candidate_dio_used_to_select_mask':False,'japanese_vuv_truth':False})
        ref(RESULT/'native-mask-contract.json')
        save(RESULT/'protocol.json',{'rows':rows,'saved_regression':refs,'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.glob('*')) if p.is_file()},
            'input_hashes':inputs,'limits':metrics.LIMITS,'dio':{'f0_floor':70.,'f0_ceil':800.,'frame_period':5.},
            'known_boundary_frames_excluded':0,'boundary_region_frames':[86,130],'end_tick_increment_seconds':.005,
            'render_calls':24,'new_dio_measurements':24,'ai_fit_teacher_inverse_download':0,'no_retries':True,
            'signal':{'harmonics':[1.,.35,.15],'gain':.8/1.5,'noise_sigma':.02,'event_fade_seconds':.005,'whole_fade_seconds':.012},
            'runtime_neural':False,'quality_certified':False})
        save(RESULT/'entry-audit.json',{'passed':True,'fixed_rows':24,'fixed_native_masks':18,'saved_dio':54,'new_render_or_dio_calls':0})
    print({'prepared':24,'native_masks':18,'saved_dio':54},flush=True)
if __name__=='__main__':main()
