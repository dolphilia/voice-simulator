"""限定測定資格と日本語診断を別集計する。"""
from collections import Counter
from event_io import *

def main():
    verify_protocol();b=LocalBudget()
    with b.job('audit','短イベントと保存回帰の集計',400_000):
        manifest=read(RESULT/'measurement-manifest.json');rows=[read(REPO/r['record']) for r in manifest['rows']]
        groups=[]
        for phase in ('development','confirmation'):
            for length in (24,11):
                subset=[r for r in rows if r['phase']==phase and r['design']['expected_driving_voiced_frames']==length]
                complete=[r for r in subset if r['status']=='completed'];stats=[r['metrics']['voiced_core'] for r in complete]
                med=[s['median_abs_half_tone_error'] for s in stats if s['median_abs_half_tone_error'] is not None]
                groups.append({'phase':phase,'driving_frames':length,'expected':len(subset),'completed':len(complete),
                    'passed':sum(r['metrics']['passed'] for r in complete),'missing_rate_range':[min(s['missing_rate'] for s in stats),max(s['missing_rate'] for s in stats)] if stats else None,
                    'median_abs_half_tone_error_range':[min(med),max(med)] if med else None,
                    'whole_phone_original_passed':sum(r['metrics']['whole_phone']['original_50_percent_pass'] for r in complete),
                    'failed_checks':dict(Counter(k for r in complete for k,v in r['metrics']['checks'].items() if not v))})
        regression=read(RESULT/'regression.json')['rows'];rg=[]
        for mode in ('baseline','flat_spectrum','simple_excitation'):
            for partial in (False,True):
                subset=[r for r in regression if r['mode']==mode and r['focus'] and r['partial']==partial]
                rg.append({'mode':mode,'partial':partial,'focus_intervals':len(subset),'whole_phone_original_missing':sum(not r['whole_phone']['original_support_complete'] for r in subset),
                    'known_voiced_frames':sum(r['metrics']['known_voiced_frames'] for r in subset),'missing_known_voiced_frames':sum(r['metrics']['missing_known_voiced_frames'] for r in subset),
                    'detected_known_voiced_frames':sum(r['metrics']['detected_known_voiced_frames'] for r in subset),
                    'clipped_boundary_missing':sum(not r['observed_events_in_phone'] for r in subset)})
        save(RESULT/'summary.json',{'development':read(RESULT/'development-summary.json'),'confirmation':read(RESULT/'confirmation-summary.json'),
            'limited_synthetic_qualification':manifest['limited_synthetic_qualification'],'signal_groups':groups,'regression_focus_groups':rg,
            'signal_failures':[r for r in rows if r['status']!='completed' or not r['metrics']['passed']],
            'new_japanese_generation_or_estimation':0,'old_primary_gates_unchanged':True,'runtime_neural':False,'quality_certified':False,'all_requirements_met':False})
    print({'development_passed':read(RESULT/'development-summary.json')['passed'],'confirmation_passed':read(RESULT/'confirmation-summary.json')['passed'],'limited_qualification':manifest['limited_synthetic_qualification']},flush=True)
if __name__=='__main__':main()
