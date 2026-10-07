"""同じ24信号・旧三測定・一変更・同一評価を凍結する。"""
import scipy
from meter_io import *
from window_meter import SPEC,tests,parent,WindowConsistentHarmonic

def main():
    b=LocalBudget()
    with b.job('setup','保存24信号と窓整合の一変更を凍結',1_000_000):
        prior=read(ARES/'protocol.json');inputs={};rows=[]
        def ref(path):
            path=Path(path);inputs[str(path.relative_to(REPO))]=digest(path)
        for name in ('protocol.json','measurement-manifest.json','summary.json'):ref(ARES/name)
        ref(ALT/'local_meters.py');ref(SHORT/'event_metrics.py');ref(REPO/'docs/plans/window-consistent-harmonic-meter-proposal-2026-10-03.md')
        old={(r['id'],r['method']):r for r in read(ARES/'measurement-manifest.json')['rows']}
        for row in prior['rows']:
            d=row['design'];assert digest(REPO/row['wav'])==row['wav_sha256'];ref(REPO/row['wav'])
            assert digest(REPO/d['truth'])==d['truth_sha256'];ref(REPO/d['truth']);ref(REPO/row['saved_dio_record'])
            dio=read(REPO/row['saved_dio_record']);ref(REPO/dio['npz']);saved={}
            for method in ('acf','harmonic'):
                item=old[(d['id'],method)];assert digest(REPO/item['record'])==item['sha256'];ref(REPO/item['record'])
                rec=read(REPO/item['record']);assert rec['status']=='completed' and digest(REPO/rec['npz'])==rec['npz_sha256'];ref(REPO/rec['npz'])
                saved[method]={'record':item['record'],'sha256':item['sha256']}
            rows.append({**row,'saved_alternatives':saved})
        assert len(rows)==24
        m=load_metrics();save(RESULT/'negative-tests.json',{'meter':tests(),'evaluation':m.tests(rows[0]['design'])})
        assert WindowConsistentHarmonic.measure is parent.LocalHarmonic.measure
        unchanged=[k for k in prior['specification'] if k!='harmonic_basis_windowed']
        assert all(SPEC[k]==prior['specification'][k] for k in unchanged)
        save(RESULT/'protocol.json',{'rows':rows,'methods':['window_harmonic'],'specification':SPEC,
            'source_hashes':{p.name:digest(p) for p in sorted(ROOT.iterdir()) if p.is_file()},'input_hashes':inputs,
            'evaluation_code':str((SHORT/'event_metrics.py').relative_to(REPO)),'evaluation_sha256':digest(SHORT/'event_metrics.py'),
            'parent_measurement_source':str((ALT/'local_meters.py').relative_to(REPO)),'parent_measurement_sha256':digest(ALT/'local_meters.py'),
            'measurement_body_identical':True,'non_basis_specification_unchanged':True,'thresholds':m.LIMITS,
            'versions':{'numpy':np.__version__,'scipy':scipy.__version__},'planned_measurements':24,
            'masks_and_known_f0_are_evaluation_only':True,'confirmation_is_previously_observed':True,
            'new_render_ai_control_fit_waveform_inverse_teacher_download':0,'no_retries':True,'quality_certified':False})
        save(RESULT/'entry-audit.json',{'passed':True,'waves':24,'one_basis_transform_change':True,'new_measurement_calls':0})
    print({'prepared':24,'evaluation_sha256':digest(SHORT/'event_metrics.py'),'one_change':True},flush=True)
if __name__=='__main__':main()
