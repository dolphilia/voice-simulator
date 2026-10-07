"""旧支持域・出典・認識器設定を生成前に固定する。"""
from pathlib import Path
import sys
from campaign import LocalBudget, ROOT, RESULT, REPO, WAVE, WRES, BUNDLE, OLD, read, save, digest
sys.path.insert(0,str(BUNDLE))
from japanese_frontend import analyze
from objective import tests
from guarded_derivative import tests as guard_tests
from integration_tests import tests as integration_tests


def main():
    with LocalBudget().job('setup','固定出典・旧支持域・認識再利用・正例負例',1000000):
        old=read(WRES/'protocol.json')
        for row in old['rows']:
            for key,sha in [('source_training_input','source_sha256'),('teacher_metadata','teacher_metadata_sha256'),('teacher_wav','teacher_wav_sha256')]:
                assert digest(REPO/row[key])==row[sha]
            assert analyze(row['text'])['full_context_labels']==row['full_context_labels']
            source=WRES/'render'/row['id']/'support-contract.json'
            save(RESULT/'render'/row['id']/'support-contract.json',read(source))
            assert digest(RESULT/'render'/row['id']/'support-contract.json')==digest(source)
        for n in ['local_renderer.py','local_control.py','centered_projection.py','shim.c','local_hts-v2.dylib','vendor/HTS_engine.h','objective.py']:
            assert digest(ROOT/n)==digest(WAVE/n)
        assert digest(RESULT/'engine-contract.json')==digest(WRES/'engine-contract.json')
        engine=read(RESULT/'engine-contract.json');config=engine['reading_diagnostic']['contract']
        for n,sha in config['dictionary_files'].items():assert digest(Path(config['dictionary_path'])/n)==sha
        assert digest(config['library'])==config['library_sha256']
        assert digest(OLD/'diagnostics.py')==engine['normalizer_source_sha256']
        save(RESULT/'negative-tests.json',tests());save(RESULT/'guard-tests.json',guard_tests())
        save(RESULT/'integration-tests.json',integration_tests())
        p={**old,'old_protocol_sha256':digest(WRES/'protocol.json'),'old_protocol':str((WRES/'protocol.json').relative_to(REPO)),
            'wave_inverse':{**old['wave_inverse'],'derivatives':'central if both valid, otherwise forward/backward; unavailable stops',
                'shrink_factors':[.5,.25],'maximum_extra_renders_per_text':3,'maximum_render_calls':128},
            'support_reused_exactly':True,'all_eight_baselines_match_before_search':True,
            'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and 'results' not in p.parts and '__pycache__' not in p.parts}}
        save(RESULT/'protocol.json',p)
        save(RESULT/'asr-reuse-contract.json',{'old_protocol_sha256':digest(WRES/'protocol.json'),
            'old_engine_contract_sha256':digest(WRES/'engine-contract.json'),'current_engine_contract_sha256':digest(RESULT/'engine-contract.json'),
            'exact_text_wav_settings_normalizer_dictionary_required':True,'source_results':{
                str(path.relative_to(REPO)):digest(path) for path in sorted((WRES/'asr').rglob('*.json'))},
            'no_new_calls_for_baselines':True,'maximum_new_ai':8,'failed_new_ai_retried':False})
    print('旧支持域・入力・再利用契約・負例検査を固定しました',flush=True)

if __name__=='__main__':main()
