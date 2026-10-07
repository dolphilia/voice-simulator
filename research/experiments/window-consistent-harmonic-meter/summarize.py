"""旧三方式の保存値と一変更を比較。採択条件は変更しない。"""
from collections import Counter
from meter_io import *

def main():
    p=verify_protocol();b=LocalBudget();manifest=read(RESULT/'measurement-manifest.json');records={r['id']:read(REPO/r['record']) for r in manifest['rows']}
    with b.job('audit','窓整合と保存旧版の同一入力対照',600_000):
        comparisons=[];groups=[]
        for row in p['rows']:
            design=row['design'];rec=records[design['id']];entry={'id':design['id'],'phase':design['phase'],'f0_hz':design['f0_hz'],
                'driving_frames':design['expected_driving_voiced_frames'],'event_start_frame':design['event_start_frame'],'event_end_frame':design['event_end_frame']}
            old={n:read(REPO/item['record']) for n,item in row['saved_alternatives'].items()};old['dio']=read(REPO/row['saved_dio_record'])
            for name,value in {**old,'window_harmonic':rec}.items():
                entry[name]={'status':value['status'],'qualification_pass':value.get('qualification_pass',value.get('metrics',{}).get('passed',False)),
                    'metrics':value.get('metrics'),'invalid_measurement_frames':value.get('invalid_measurement_frames',[])}
            if rec['status']=='completed':
                own=rec['metrics'];prior=old['harmonic']['metrics'];z=np.load(REPO/rec['npz']);oldz=np.load(REPO/old['harmonic']['npz'])
                assert np.array_equal(z['times'],oldz['times']) and np.array_equal(z['rms'],oldz['rms'])
                idx=np.arange(240);known=(idx>=design['event_start_frame'])&(idx<design['event_end_frame'])
                voiced=known&(z['f0']>0);oldvoiced=known&(oldz['f0']>0);paired=voiced&oldvoiced
                entry['changes']={'same_times_and_rms':True,'known_detected_frame_delta':own['voiced_core']['detected_known_voiced_frames']-prior['voiced_core']['detected_known_voiced_frames'],
                    'old_core_lower_search_edge_frames':int((known&(oldz['f0']==70)).sum()),'new_core_lower_search_edge_frames':int((known&(z['f0']==70)).sum()),
                    'old_core_confidence_range':[float(oldz['confidence'][known].min()),float(oldz['confidence'][known].max())],
                    'new_core_confidence_range':[float(z['confidence'][known].min()),float(z['confidence'][known].max())],
                    'old_core_f0_range_hz':[float(oldz['f0'][oldvoiced].min()),float(oldz['f0'][oldvoiced].max())] if oldvoiced.any() else None,
                    'new_core_f0_range_hz':[float(z['f0'][voiced].min()),float(z['f0'][voiced].max())] if voiced.any() else None,
                    'paired_detected_frames':int(paired.sum()),'paired_f0_change_hz':(z['f0'][paired]-oldz['f0'][paired]).tolist(),
                    'new_missing_frame_indices':np.flatnonzero(known&~voiced).tolist(),'new_invalid_measurement_frames':rec['invalid_measurement_frames']}
            comparisons.append(entry)
        for phase in ('development','confirmation'):
            for length in (24,11):
                chosen=[r for r in comparisons if r['phase']==phase and r['driving_frames']==length]
                for name in ('dio','acf','harmonic','window_harmonic'):
                    valid=[r[name] for r in chosen if r[name]['status']=='completed'];stats=[r['metrics']['voiced_core'] for r in valid]
                    med=[s['median_abs_half_tone_error'] for s in stats if s['median_abs_half_tone_error'] is not None]
                    groups.append({'phase':phase,'driving_frames':length,'method':name,'expected':len(chosen),'completed':len(valid),
                        'passed':sum(r['qualification_pass'] for r in valid),'known_voiced_frames':sum(s['known_voiced_frames'] for s in stats),
                        'detected_known_voiced_frames':sum(s['detected_known_voiced_frames'] for s in stats),
                        'missing_rate_range':[min(s['missing_rate'] for s in stats),max(s['missing_rate'] for s in stats)] if stats else None,
                        'median_abs_half_tone_error_range':[min(med),max(med)] if med else None,
                        'failed_checks':dict(Counter(k for r in valid for k,v in r['metrics']['checks'].items() if not v))})
        dev=read(RESULT/'window_harmonic-development.json');conf=read(RESULT/'window_harmonic-confirmation.json')
        save(RESULT/'summary.json',{'development':dev,'confirmation':conf,'limited_saved_signal_qualification':dev['all_passed'] and conf['all_passed'],
            'groups':groups,'comparison':comparisons,'method_selected':None,'ensemble_created':False,'settings_changed_after_freeze':False,
            'independent_new_confirmation':False,'new_japanese_analysis_or_previous_method_calls':0,
            'old_primary_gates_unchanged':True,'quality_certified':False,'all_requirements_met':False})
    print({'development':dev['passed'],'confirmation':conf['passed'],'limited_saved_signal_qualification':dev['all_passed'] and conf['all_passed']},flush=True)
if __name__=='__main__':main()
