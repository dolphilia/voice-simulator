"""凍結した既定MSDと保存DIOの回帰診断。再生成・再推定しない。"""
from event_io import *
from event_metrics import grid,coverage,runs

def main():
    p=verify_protocol();b=LocalBudget();rows=[];contracts={r['id']:r for r in read(RESULT/'native-mask-contract.json')['rows']}
    with b.job('audit','保存54波形の固定領域診断',3_000_000):
        for item in p['saved_regression']:
            c=contracts[item['id']];ref=np.load(REPO/c['lf0'])['lf0'][:,0];hz=np.zeros(len(ref));valid=ref>0;hz[valid]=np.exp(ref[valid])
            mask=np.zeros(c['frames'],bool)
            for lo,hi in c['native_runs']:mask[lo:hi]=True
            assert np.array_equal(mask,valid)
            old=read(REPO/item['record']);observations=np.load(REPO/item['dio']);f=observations['dio_f0'];t=observations['dio_times'];values,details=grid(f,t,c['frames'])
            detected=np.isfinite(values)&(values>=70)&(values<=800)
            for phone in c['phones']:
                lo,hi=phone['frame_start'],phone['frame_end'];known=mask[lo:hi];stats=coverage(values[lo:hi],known,hz[lo:hi])
                flo=(t>=lo*.005)&(t<hi*.005);whole=(f[flo]>=70)&(f[flo]<=800)
                oldlocal=next(a for a in old['measurement']['local'] if a['index']==phone['index'])
                original_pass=bool(whole.sum()>=3 and whole.mean()>=.5) if len(whole) else False
                assert original_pass==oldlocal['support_complete']
                observed=runs(detected[lo:hi]);native=phone['native_runs'];begin=observed[0][0] if observed else None;end=observed[-1][1] if observed else None
                rows.append({'id':item['id'],'variant':c['variant'],'mode':item['mode'],**phone,'metrics':stats,'grid':details,
                    'whole_phone':{'integer_voiced_frames':int(detected[lo:hi].sum()),'integer_frames':hi-lo,
                        'integer_fraction':float(detected[lo:hi].mean()),'original_float_frames':int(flo.sum()),
                        'original_float_voiced_frames':int(whole.sum()),'original_support_complete':original_pass},
                    'native_events':native,'observed_events_in_phone':observed,'event_run_count':len(observed),
                    'clipped_start_error_ms':None if begin is None else abs(begin-native[0][0])*5,
                    'clipped_end_error_ms':None if end is None else abs(end-native[-1][1])*5,
                    'boundary_scope':'音素内に切り詰めた診断。隣接有声の連結はイベント正解にしない。','quality_certified':False})
        assert len(rows)==861
        save(RESULT/'regression.json',{'rows':rows,'saved_waves':54,'fixed_native_schedules':18,'new_render_dio_fit_ai':0,
            'original_gates_unchanged':True,'candidate_selected_mask':False,'quality_certified':False})
    print({'regression_phone_rows':len(rows),'new_render_dio':0},flush=True)
if __name__=='__main__':main()
