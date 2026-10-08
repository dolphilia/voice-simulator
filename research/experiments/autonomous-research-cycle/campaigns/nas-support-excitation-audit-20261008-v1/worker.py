"""全992の固定支持を保持し、励振源・測定欠測・未知を診断する。"""
from paths import *
import argparse,io,sys,os,re
def libraries():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(PERIOD/'runtime-bundle'),str(PERIOD/'runtime-bundle/packages-v2')]
    import numpy as np
    return np
def hts(job):
    np=libraries();import observer
    b=Budget();records=read(HERE/'protocol.json')['records'];results=[]
    for item in records:
        if item['cohort']!='nas-vocoder-f0' or not item['method'].startswith('hts'):continue
        target=HERE/'new-hts-diagnostic'/(item['id']+'.json')
        if target.exists():
            d=read(target);assert digest(REPO/d['trace_path'])==d['trace_sha256'];results.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        assert digest(REPO/item['record'])==item['record_sha256'] and digest(REPO/item['parameters'])==item['parameters_sha256']
        old=read(REPO/item['record']);assert old['meta']['output_gain']==.25
        with np.load(REPO/item['parameters']) as a:params=[a[k].copy() for k in ['mcp','lf0','lpf']]
        data,traces,meta=observer.observe(params,old['meta']['settings'],params[0][0],False)
        assert meta['sha256']==item['wave_sha256']==digest(REPO/item['wave'])
        tp=HERE/'new-hts-trace'/(item['id']+'.npz');buf=io.BytesIO();np.savez_compressed(buf,**traces)
        if tp.exists():
            with np.load(tp) as a:assert set(a.files)==set(traces) and all(np.array_equal(a[k],v) for k,v in traces.items())
        else:b.write(tp,buf.getvalue(),job)
        d=dict(id=item['id'],trace_path=str(tp.relative_to(REPO)),trace_sha256=digest(tp),old_wave_sha256=item['wave_sha256'],
            wave_byte_exact=True,trace_kind='HTS周期・counter・発生前pulse。LPF後の周期成分/知覚pitchは未資格。',meta=meta)
        b.write_data(target,encode(d),job);results.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
        print('HTS追加観測',len(results),'/96',flush=True)
    assert len(results)==96
    b.save(HERE/'new-hts-manifest.json',dict(rows=results,expected=96,all_wave_byte_exact=True,new_audio_saved=0),job)
def diagnosis(job):
    np=libraries();from pulse_ground import ground
    b=Budget();protocol=read(HERE/'protocol.json');traces={}
    for x in read(PERIOD/'diagnostic-manifest.json')['rows']:
        assert digest(REPO/x['path'])==x['sha256'];d=read(REPO/x['path']);traces['nas-mcp-postfilter/'+d['id']]=d
    for x in read(HERE/'new-hts-manifest.json')['rows']:
        assert digest(REPO/x['path'])==x['sha256'];d=read(REPO/x['path']);traces[d['id']]=d
    assert len(traces)==224 and read(WORLD/'aggregate-summary.json')['unknown_actual_excitation_cases']==768
    cohorts={}
    for name in protocol['cohorts']:
        p=read(ROOT/'campaigns'/(name+'-20261008-v1')/'protocol.json');cohorts[name]={r['id']:r for r in p['rows']}
    results=[]
    for item in protocol['records']:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if target.exists():
            assert read(target)['source_record_sha256']==item['record_sha256'];results.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        assert digest(REPO/item['record'])==item['record_sha256'] and digest(REPO/item['parameters'])==item['parameters_sha256']
        old=read(REPO/item['record']);m=old['measurement'];row=cohorts[item['cohort']][item['row_id']]
        with np.load(REPO/item['parameters']) as a:
            lf0=a['lf0'][:,0].copy();duration=a['duration'].copy()
        assert np.array_equal(duration,np.asarray(old['meta']['duration']))
        bounds=np.r_[0,np.cumsum(duration)];assert bounds[-1]==len(lf0)
        with np.load(REPO/item['dio']) as a:f0=a['f0'].copy();times=a['times'].copy()
        assert digest(REPO/item['dio'])==item['dio_sha256']
        local={x['index']:x for x in m['local']}
        assert list(local)==m['support']
        actual=traces.get(item['id']);period=pulse=None;window={}
        if actual:
            tp=REPO/actual['trace_path'];assert digest(tp)==actual['trace_sha256']
            assert actual.get('old_wav_sha256',actual.get('old_wave_sha256'))==item['wave_sha256']
            with np.load(tp) as a:period=a['period'].copy();pulse=a['pulse'].copy();counter=a['counter_before'].copy()
            assert len(period)==len(lf0)*240 and np.array_equal(pulse.astype(bool),(period>0)&(counter+1>=period))
            for width in [20,40,60]:window[width]=ground(np,period,pulse,times,width)
        intervals=[]
        for index in m['support']:
            lo,hi=int(bounds[index*5]),int(bounds[(index+1)*5]);mask=(times>=lo*.005)&(times<hi*.005)
            values=f0[mask&(f0>=70)&(f0<=800)];n=int(mask.sum())
            supported=bool(n>0 and len(values)>=3 and len(values)>=n*.5)
            assert n==local[index]['interval_frames'] and len(values)==local[index]['voiced_frames'] and supported==local[index]['support_complete']
            missing=index in m['missing_support'];assert missing==not_supported(supported)
            phone=re.search(r'\-([^+]+)\+',row['full_context_labels'][index]).group(1)
            drive=int((lf0[lo:hi]>-1e9).sum())
            d=dict(index=index,phone=phone,start_frame=lo,end_frame=hi,duration_ms=(hi-lo)*5,
                old_clock_frames=n,old_DIO_voiced_frames=len(values),old_DIO_support_complete=supported,
                old_fixed_support_missing=missing,driving_voiced_frames=drive,driving_total_frames=hi-lo,
                driving_state='unvoiced' if drive==0 else ('fully_voiced' if drive==hi-lo else 'partly_voiced'),
                drive_is_not_actual_excitation=True)
            if actual:
                segment=period[lo*240:hi*240];count=int(pulse[lo*240:hi*240].sum())
                category='source_unvoiced' if not (segment>0).any() else ('no_pulse_in_interval' if count==0 else ('fewer_than_four_pulses' if count<4 else 'pulse_present_acoustic_ambiguity'))
                d.update(actual_source_state=category,actual_periodic_source_samples=int((segment>0).sum()),actual_sample_count=len(segment),actual_pulse_count=count,
                    no_source_pulse_does_not_exclude_filter_ringing=True,pulse_does_not_guarantee_periodic_energy_or_perceived_voicing=True)
                wd={}
                for width,(k,h,c) in window.items():
                    positive=mask&((k==4)|(k==5));accepted=(f0>=70)&(f0<=800)
                    correct=positive&accepted&(abs(12*np.log2(np.maximum(f0,1)/np.where(np.isfinite(h),h,1)))<=1)
                    wd[str(width)]=dict(stable=int((mask&(k==4)).sum()),dynamic=int((mask&(k==5)).sum()),
                        boundary=int((mask&(k==1)).sum()),source_unvoiced=int((mask&(k==2)).sum()),
                        insufficient_pulses=int((mask&(k==3)).sum()),edge=int((mask&(k==0)).sum()),
                        DIO_missing_on_pulse_targets=int((positive&~accepted).sum()),DIO_correct_on_pulse_targets=int(correct.sum()),
                        diagnostic_mean_pulse_rate_not_perceived_pitch=True)
                d['pulse_window_counts']=wd
            else:d.update(actual_source_state='WORLD_unknown_compatibility_nonpass',actual_pulse_count=None,actual_periodic_source_samples=None)
            intervals.append(d)
        assert [d['index'] for d in intervals if d['old_fixed_support_missing']]==m['missing_support']
        result=dict(id=item['id'],cohort=item['cohort'],row_id=item['row_id'],condition=item['condition'],method=item['method'],length=row['length'],
            source_record_sha256=item['record_sha256'],wave_sha256=item['wave_sha256'],all_fixed_support_intervals=intervals,
            fixed_support_count=len(m['support']),missing_support_count=len(m['missing_support']),source_trace_sha256=actual['trace_sha256'] if actual else None,
            actual_source_known=actual is not None,old_support_and_DIO_exact=True,causal_or_perceptual_claim=False,old_qualification_unchanged=True)
        b.write_data(target,encode(result),job);results.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
        if len(results)%32==0:print('固定支持診断',len(results),'/992',flush=True)
    assert len(results)==992
    b.save(HERE/'diagnostic-manifest.json',dict(rows=results,expected=992,actual_source_known=224,WORLD_source_unknown=768,old_DIO_support_exact=True,quality_goal_completed=False),job)
def not_supported(value):return not value
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['hts','diagnose']);p.add_argument('--job',required=True);a=p.parse_args()
    hts(a.job) if a.stage=='hts' else diagnosis(a.job)
if __name__=='__main__':main()
