"""信号正解、測定・判定、93既存波形の出典を生成前に凍結する。"""
import sys
from pathlib import Path
import numpy as np
import scipy
from campaign import LocalBudget, ROOT, RESULT, REPO, WAVE, WRES, PILOT, read, save, digest
from fixtures import catalog, truth, validate_truth, tests as fixture_tests
from metrics import tests as metric_tests, LIMITS
sys.path.insert(0,str(PILOT/'.cache/packages'))
import pyworld


def main():
    with LocalBudget().job('setup','24信号正解・測定器・判定・93波形の出典を固定',3000000):
        rows=catalog();save(RESULT/'negative-tests.json',{'fixtures':fixture_tests(),'metrics':metric_tests()})
        for row in rows:
            t,f0,mask=truth(row);validate_truth(row,t,f0,mask)
            path=RESULT/'truth'/(row['id']+'.npz');path.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(path,t=t,f0_hz=f0,voiced_mask=mask)
            row['truth_file']=str(path.relative_to(ROOT));row['truth_sha256']=digest(path)
        old=read(WRES/'render-contract.json');sources=[]
        cached=read(WRES/'measurement-sensitivity.json')['rows'];cache={(r['text_id'],r['attempt']):r for r in cached}
        oldprotocol=read(WRES/'protocol.json')
        for path in sorted((WRES/'render').rglob('*.json')):
            r=read(path)
            if 'wav' not in r:continue
            wav=WAVE/r['wav'];assert digest(wav)==r['wav_sha256']
            row=next(p for p in oldprotocol['rows'] if p['id']==r['text_id'])
            source=REPO/row['source_training_input'];assert digest(source)==row['source_sha256']
            key=(r['text_id'],r['attempt'])
            if key in cache:assert cache[key]['wav_sha256']==r['wav_sha256']
            sources.append({'id':r['text_id']+'/'+r['attempt'],'text_id':r['text_id'],'attempt':r['attempt'],
                'metadata':str(path.relative_to(REPO)),'metadata_sha256':digest(path),'wav':str(wav.relative_to(REPO)),
                'wav_sha256':digest(wav),'npz':str(path.with_suffix('.npz').relative_to(REPO)),'npz_sha256':digest(path.with_suffix('.npz')),
                'snapshot_source':str(source.relative_to(REPO)),'snapshot_sha256':digest(source),
                'support_contract':str((path.parent/'support-contract.json').relative_to(REPO)),
                'support_contract_sha256':digest(path.parent/'support-contract.json'),'harvest_reused':key in cache})
        assert len(sources)==93 and sum(r['harvest_reused'] for r in sources)==32
        save(RESULT/'regression-inputs.json',{'rows':sources,'source_protocol_sha256':digest(WRES/'protocol.json'),
            'source_ledger_sha256':digest(WRES/'ledger.jsonl'),'source_render_manifest_sha256':digest(WRES/'render-manifest.json'),
            'cached_harvest_file':str((WRES/'measurement-sensitivity.json').relative_to(REPO)),
            'cached_harvest_sha256':digest(WRES/'measurement-sensitivity.json')})
        save(RESULT/'protocol.json',{'rows':rows,'methods':['dio','harvest'],'settings':{'f0_floor':70.,'f0_ceil':800.,'frame_period':5.,
            'dio_stonemask':True,'harvest_stonemask':False},'limits':LIMITS,'interior_boundary_exclusion_seconds':.05,
            'boundary_matching':'検出有声の連結区間で正解区間との重複最大。同値は最初。各開始終了誤差を30ms以内に保護。',
            'selection':'開発12条件の全必須条件通過方式。最悪1半音超率最小、同値DIO。確認で方式変更・救済なし。',
            'confirmation_if_no_method_eligible':'選択なしの診断として保存。方法の資格・選択に使わない。',
            'versions':{'numpy':np.__version__,'scipy':scipy.__version__,'pyworld':pyworld.__version__},
            'world_files':{str(p.relative_to(REPO)):digest(p) for p in Path(pyworld.__file__).parent.glob('*.so')},
            'source_hashes':{p.name:digest(p) for p in ROOT.glob('*.py')},'human_perception_qualified':False,
            'independent_japanese_texts':0,'quality_certified':False,'all_requirements_met':False})
    print('24正解・負例・93波形（Harvest再利用32）を生成前に固定',flush=True)

if __name__=='__main__':main()
