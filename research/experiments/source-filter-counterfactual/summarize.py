"""各条件の固定支持域を比較し、機構候補を観測として記録する。"""
from collections import Counter
from campaign import *

def classification(baseline,flat,simple):
    if baseline: return 'baseline_retained' if flat and simple else 'counterfactual_lost_support'
    if flat and simple:return 'spectral_path_recovery'
    if flat and not simple:return 'nonmonotonic_recovery'
    if not flat and simple:return 'lpf_mixing_path_recovery'
    return 'unresolved_time_source_or_meter'


def tests():
    assert classification(False,True,True)=='spectral_path_recovery'
    assert classification(False,False,True)=='lpf_mixing_path_recovery'
    assert classification(False,False,False)=='unresolved_time_source_or_meter'
    assert classification(False,True,False)=='nonmonotonic_recovery'
    assert classification(True,True,False)=='counterfactual_lost_support'
    return {'mixed_nonmonotonic_not_single_cause':True,'unresolved_not_passed':True,'render_ai_calls':0}


def main():
    with LocalBudget().job('audit','18列を開発・機構確認に分け、固定区間を対照する',1000000):
        p=read(RESULT/'protocol.json');manifest=read(RESULT/'render-manifest.json');assert len(manifest['rows'])==54
        records={}
        for row in manifest['rows']:
            path=REPO/row['record'];assert digest(path)==row['sha256'];r=read(path)
            assert r['status']=='completed' and r['generated_lf0_identical'] and r['duration_msd_dynamic_means_unchanged']
            assert digest(REPO/r['wav'])==r['wav_sha256'];records[(r['id'],r['mode'])]=r
        pairs=[]
        for row in p['rows']:
            allm=[records[(row['id'],mode)] for mode in p['modes']]
            assert all(r['vocoder_settings']==allm[0]['vocoder_settings'] and r['parameters_sha256']==allm[0]['parameters_sha256'] for r in allm)
            for index in row['focus_indices']:
                local=[next(x for x in r['measurement']['local'] if x['index']==index) for r in allm]
                assert all(r['generated_lf0_voiced_frames']==local[0]['generated_lf0_voiced_frames'] and r['generated_lf0_interval_frames']==local[0]['generated_lf0_interval_frames'] for r in local)
                pairs.append({'id':row['id'],'variant':row['variant'],'phase':row['phase'],'index':index,
                    'classification':classification(*(r['support_complete'] for r in local)),
                    'baseline':local[0],'flat_spectrum':local[1],'simple_excitation':local[2],
                    'E0_by_mode':{r['mode']:r['E0_pass'] for r in allm},'all_finite':all(r['finite'] for r in allm)})
        phases={}
        for phase in ('development','mechanism_confirmation'):
            selected=[r for r in pairs if r['phase']==phase and r['variant']!='native']
            phases[phase]={'candidate_conditions':len(selected),'classes':dict(Counter(r['classification'] for r in selected)),
                'baseline_missing':sum(not r['baseline']['support_complete'] for r in selected),
                'flat_missing':sum(not r['flat_spectrum']['support_complete'] for r in selected),
                'simple_missing':sum(not r['simple_excitation']['support_complete'] for r in selected)}
        mode_summary={mode:{'waves':18,'E0_failed':sum(not r['E0_pass'] for (identity,m),r in records.items() if m==mode),
            'support_missing_conditions':sum(bool(r['measurement']['missing_support']) for (identity,m),r in records.items() if m==mode),
            'missing_intervals':sum(len(r['measurement']['missing_support']) for (identity,m),r in records.items() if m==mode)} for mode in p['modes']}
        save(RESULT/'negative-summary-tests.json',tests())
        save(RESULT/'summary.json',{'pairs':pairs,'phases':phases,'modes':mode_summary,
            'baseline_gate_passed':read(RESULT/'baseline-gate.json')['passed'],'parameters_controlled_before_generation':True,
            'counterfactuals_are_japanese_quality_candidates':False,'old_primary_metrics_or_support_changed':False,
            'any_new_content_evaluation':False,'quality_certified':False,'all_requirements_met':False,
            'interpretation':'同じMLPG列での観測経路の対照。駆動LF0の保持は自然発声の正解ではない。回復は機構候補であり原因の確定・日本語測定資格・内容改善ではない。'})
    print({'phases':phases,'modes':mode_summary},flush=True)

if __name__=='__main__':main()
