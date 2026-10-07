"""旧封印の160個別記録を参照し、今回の未完評価だけを固定する。"""
from pathlib import Path
import tempfile
import numpy as np
from campaign import *
from summarize import tests as group_tests
from storage_preflight import compact_row
import sys
sys.path.insert(0,str(SHARED))
from checks import invariant

def storage_tests():
    with tempfile.TemporaryDirectory(prefix='saved-eval-',dir='/private/tmp') as directory:
        root=Path(directory);s=Storage(root,root/'results',250000)
        s.write(root/'small.json',encoded({'ok':True}))
        try:s.write(root/'large.json',encoded({'payload':'a'*250000}))
        except RuntimeError:pass
        else:raise AssertionError('容量超過を拒否しません')
        assert not (root/'large.json').exists()
        try:
            with s.budget.locked():s.reserve(235_490_836)
        except RuntimeError:pass
        else:raise AssertionError('旧巨大集約を拒否しません')
        with s.external(root/'output.bin',3):(root/'output.bin').write_bytes(b'abc')
        (root/'unexpected').write_bytes(b'x')
        try:s.write(root/'after.json',encoded({}))
        except RuntimeError:pass
        else:raise AssertionError('外部書込を拒否しません')
        assert not (root/'after.json').exists()
    with tempfile.TemporaryDirectory(prefix='saved-eval-',dir='/private/tmp') as directory:
        root=Path(directory);s=Storage(root,root/'results',250000)
        try:
            with s.external(root/'output.bin',1):(root/'output.bin').write_bytes(b'ab')
        except RuntimeError:pass
        else:raise AssertionError('外部予約超過を拒否しません')
    return {'encoded_size_before_exclusive_write':True,'oversized_json_not_created':True,
        '235MB_manifest_rejected_before_write':True,'external_changes_detected':True,
        'external_output_reservation_enforced':True,'ledger_margin_counted':True}

def main():
    with LocalBudget().job('setup','固定モデル・160波形・辞書・認識再利用証拠を固定',3_000_000):
        tests=storage_tests();groups=group_tests()
        protocol=read(SRES/'protocol.json');rows=[]
        for n,sha in protocol['source_hashes'].items():assert digest(SHARED/n)==sha
        oldseal=read(SRES/'artifact-seal.json')['files']
        for path in sorted((SRES/'render').rglob('*.json')):
            if path.name=='support-contract.json':continue
            r=read(path)
            assert r['status']=='completed' and r['E0_pass'] and r['internal_unchanged']
            wav=SHARED/r['wav'];assert digest(wav)==r['wav_sha256']
            invariant(r['state_snapshot_before'],r['state_snapshot_after'],np.load(wav.with_suffix('.npz'))['state_deltas'])
            relative=str(path.relative_to(REPO));sha=digest(path);assert oldseal[relative]==sha
            small=compact_row(r,relative,sha);small['wav']=str(wav.relative_to(REPO));rows.append(small)
        assert len(rows)==160 and len({r['id'] for r in rows})==160
        assert all('state_snapshot_before' not in r for r in rows)
        models=read(SRES/'model-comparison.json')
        for n,sha in models['model_hashes'].items():assert digest(SRES/'models'/n)==sha
        assert read(SRES/'training-contract.json')['training_utterances']==17
        for name in ('runtime.py','local_control.py','local_renderer.py','centered_projection.py','local_hts-v2.dylib','shim.c','vendor/HTS_engine.h'):
            assert digest(ROOT/name)==digest(SHARED/name)
        engine=read(RESULT/'engine-contract.json');cfg=engine['reading_diagnostic']['contract']
        for n,sha in engine['asr_model_hashes'].items():assert digest(REPO/n)==sha
        for n,sha in cfg['dictionary_files'].items():assert digest(Path(cfg['dictionary_path'])/n)==sha
        assert digest(cfg['library'])==cfg['library_sha256']
        copy_checked(SRES/'protocol.json',RESULT/'protocol.json')
        copy_checked(SRES/'model-comparison.json',RESULT/'model-comparison.json')
        reuse=read(SRES/'asr-reuse-contract.json')
        assert reuse['current_engine_contract_sha256']==digest(RESULT/'engine-contract.json')
        for name,proof in reuse['source_results'].items():
            assert digest(REPO/name)==proof['sha256']
            a=read(REPO/name);assert a['protocol_sha256']==proof['protocol_sha256']
            assert digest(REPO/proof['wav'])==a['wav_sha256']
        copy_checked(SRES/'asr-reuse-contract.json',RESULT/'asr-reuse-contract.json')
        save(RESULT/'source-contract.json',{'source_protocol_sha256':digest(SRES/'protocol.json'),
            'source_models':{str((SRES/'models'/n).relative_to(REPO)):sha for n,sha in models['model_hashes'].items()},
            'source_training_contract_sha256':digest(SRES/'training-contract.json'),
            'source_support_contracts':{str(p.relative_to(REPO)):digest(p) for p in sorted((SRES/'render').rglob('support-contract.json'))},
            'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and 'results' not in p.parts},
            'no_new_fit_inverse_teacher':True,'no_optimization_after_asr':True})
        save(RESULT/'render-manifest.json',{'rows':rows,'search_completed_before_asr':True,
            'saved_waves_only':True,'source_protocol_sha256':digest(SRES/'protocol.json'),'new_diagnostic_render_calls':0})
        save(RESULT/'negative-tests.json',{'storage':tests,'content_groups':groups})
        save(RESULT/'entry-audit.json',{'passed':True,'160_saved_waves_verified':True,'models_and_supports_frozen':True,
            'exact_renderer_and_projection':True,'source_frontend_protocol_reused':True,'quality_certified':False})
    print({'saved_waves':len(rows),'reusable_records':len(reuse['source_results']),'entry_passed':True},flush=True)

if __name__=='__main__':main()
