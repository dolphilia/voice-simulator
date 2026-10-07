"""旧DIO値だけと比較し、二方式を独立に報告する。"""
from collections import Counter
from meter_io import *

def main():
    p=verify_protocol();b=LocalBudget();manifest=read(RESULT/'measurement-manifest.json');records=[read(REPO/r['record']) for r in manifest['rows']]
    with b.job('audit','二方式を独立集計し旧保存DIOと比較',500_000):
        groups=[];methods={}
        for method in p['methods']:
            dev=read(RESULT/f'{method}-development.json');confirm=read(RESULT/f'{method}-confirmation.json')
            methods[method]={'development':dev,'confirmation':confirm,'limited_synthetic_qualification':dev['all_passed'] and confirm['all_passed']}
            for phase in ('development','confirmation'):
                for length in (24,11):
                    chosen=[r for r in records if r['method']==method and r['phase']==phase and next(s['design']['expected_driving_voiced_frames'] for s in p['rows'] if s['design']['id']==r['id'])==length]
                    completed=[r for r in chosen if r['status']=='completed'];s=[r['metrics']['voiced_core'] for r in completed]
                    vals=[v['median_abs_half_tone_error'] for v in s if v['median_abs_half_tone_error'] is not None]
                    groups.append({'method':method,'phase':phase,'driving_frames':length,'expected':len(chosen),'completed':len(completed),
                        'passed':sum(r['qualification_pass'] for r in completed),
                        'known_voiced_frames':sum(v['known_voiced_frames'] for v in s),'detected_known_voiced_frames':sum(v['detected_known_voiced_frames'] for v in s),
                        'missing_rate_range':[min(v['missing_rate'] for v in s),max(v['missing_rate'] for v in s)] if s else None,
                        'median_abs_half_tone_error_range':[min(vals),max(vals)] if vals else None,
                        'failed_checks':dict(Counter(k for r in completed for k,v in r['metrics']['checks'].items() if not v)),
                        'whole_phone_original_passed':sum(r['metrics']['whole_phone']['original_50_percent_pass'] for r in completed)})
        comparison=[]
        for row in p['rows']:
            d=row['design'];old=read(REPO/row['saved_dio_record']);entry={'id':d['id'],'phase':d['phase'],'f0_hz':d['f0_hz'],
                'event_start_frame':d['event_start_frame'],'event_end_frame':d['event_end_frame'],'driving_frames':d['expected_driving_voiced_frames'],
                'dio':{'status':old['status'],'qualification_pass':old['metrics']['passed'],'metrics':old['metrics']}}
            for method in p['methods']:
                rec=next(r for r in records if r['id']==d['id'] and r['method']==method)
                entry[method]={k:rec[k] for k in ('status','qualification_pass','metrics','invalid_measurement_frames') if k in rec}
            comparison.append(entry)
        save(RESULT/'summary.json',{'methods':methods,'groups':groups,'comparison':comparison,
            'method_selected':None,'ensemble_created':False,'settings_changed':False,'new_dio_or_japanese_analysis':0,
            'old_primary_gates_unchanged':True,'quality_certified':False,'all_requirements_met':False})
    print({n:{'development':v['development']['passed'],'confirmation':v['confirmation']['passed'],'qualified':v['limited_synthetic_qualification']} for n,v in methods.items()},flush=True)
if __name__=='__main__':main()
