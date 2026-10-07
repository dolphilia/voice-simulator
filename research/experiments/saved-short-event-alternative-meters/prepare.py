"""保存24信号の参照と二測定の仕様を測定前に固定する。"""
import scipy
from meter_io import *
from local_meters import SPEC,tests

def main():
    b=LocalBudget()
    with b.job('setup','旧評価・保存24信号・二測定仕様を凍結',1_000_000):
        source=read(QRES/'protocol.json');renders={r['id']:r for r in read(QRES/'render-manifest.json')['rows']}
        dio={r['id']:r for r in read(QRES/'measurement-manifest.json')['rows']};inputs={};rows=[]
        def ref(path):
            path=Path(path);inputs[str(path.relative_to(REPO))]=digest(path)
        for name in ('protocol.json','render-manifest.json','measurement-manifest.json','development-summary.json','confirmation-summary.json'):ref(QRES/name)
        ref(SHORT/'event_metrics.py');ref(REPO/'docs/plans/saved-short-event-alternative-meters-proposal-2026-10-03.md')
        for row in source['rows']:
            r=renders[row['id']];assert digest(REPO/r['record'])==r['sha256'];ref(REPO/r['record']);d=read(REPO/r['record'])
            assert d['status']=='completed' and digest(REPO/d['wav'])==d['wav_sha256'];ref(REPO/d['wav'])
            assert digest(REPO/row['truth'])==row['truth_sha256'];ref(REPO/row['truth'])
            dm=dio[row['id']];assert digest(REPO/dm['record'])==dm['sha256'];ref(REPO/dm['record']);dd=read(REPO/dm['record'])
            assert dd['status']=='completed' and digest(REPO/dd['npz'])==dd['npz_sha256'];ref(REPO/dd['npz'])
            rows.append({'design':row,'wav':d['wav'],'wav_sha256':d['wav_sha256'],'saved_dio_record':dm['record'],'saved_dio_sha256':dm['sha256']})
        assert len(rows)==24 and sum(r['design']['phase']=='development' for r in rows)==12
        m=load_metrics();negative={'meter':tests(),'evaluation':m.tests(rows[0]['design'])};save(RESULT/'negative-tests.json',negative)
        save(RESULT/'protocol.json',{'rows':rows,'methods':['acf','harmonic'],'specification':SPEC,
            'source_hashes':{p.name:digest(p) for p in sorted(ROOT.iterdir()) if p.is_file()},'input_hashes':inputs,
            'evaluation_code':str((SHORT/'event_metrics.py').relative_to(REPO)),'evaluation_sha256':digest(SHORT/'event_metrics.py'),
            'versions':{'numpy':np.__version__,'scipy':scipy.__version__},'thresholds':m.LIMITS,'planned_measurements':48,
            'source_audio_used_before_freeze':False,'masks_and_known_f0_are_evaluation_only':True,
            'new_render_ai_fit_teacher_inverse_download':0,'no_retries':True,'quality_certified':False})
        save(RESULT/'entry-audit.json',{'passed':True,'waves':24,'methods':2,'evaluation_same_hash':True,'new_measurement_calls':0})
    print({'prepared':24,'methods':2,'evaluation_sha256':digest(SHORT/'event_metrics.py')},flush=True)
if __name__=='__main__':main()
