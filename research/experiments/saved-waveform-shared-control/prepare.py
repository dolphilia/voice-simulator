"""保存候補を再検証し目標・診断入力・全比較設定をfit前に固定する。"""
from pathlib import Path
import sys
import numpy as np
from scipy.io import wavfile
from campaign import LocalBudget, ROOT, RESULT, REPO, TARGET, TRES, BUNDLE, LRES, read, save, digest
sys.path.insert(0,str(BUNDLE))
from japanese_frontend import analyze
from acoustics import evaluate
from objective import extract_local, centered_semitones, objective
from centered_projection import tests as projection_tests
from checks import select, enough, tests, invariant
from summarize import tests as summary_tests


def collect(value):
    if isinstance(value,dict):
        result={value['text']} if isinstance(value.get('text'),str) else set()
        for v in value.values():result|=collect(v)
        return result
    if isinstance(value,list):return set().union(*(collect(v) for v in value))
    return set()


def main():
    with LocalBudget().job('setup','保存63条件・17目標・前段・支持域・認識出典を固定',3000000):
        old=read(TRES/'protocol.json');training=old['training_rows'];targets=[];audits=[]
        for row in training+old['selection_rows']:
            for name,sha in [('source_training_input','source_sha256'),('teacher_metadata','teacher_metadata_sha256'),('teacher_wav','teacher_wav_sha256')]:assert digest(REPO/row[name])==row[sha]
            assert analyze(row['text'])['full_context_labels']==row['full_context_labels']
        for row in training:
            source=TRES/'searches'/(row['id']+'.json');s=read(source);snapshot=read(REPO/row['source_training_input'])['snapshot']
            support=read(TRES/'inverse-render'/row['id']/'support-contract.json');checked=[]
            for variant in ('native','statefit','wavefit'):
                r=s[variant];wav=TARGET/r['wav'];assert digest(wav)==r['wav_sha256']
                fs,audio=wavfile.read(wav);assert fs==24000 and audio.ndim==1 and np.isfinite(audio).all()
                assert evaluate(audio,{},24000)['E0_pass'] and r['E0_pass']
                arrays=np.load(wav.with_suffix('.npz'));invariant(snapshot,r['state_snapshot_after'],arrays['state_deltas'])
                local,missing=extract_local(arrays['dio_f0'],arrays['dio_times'],snapshot,support['indices']);assert not missing
                shape=centered_semitones([d['wave_log_f0'] for d in local]);target=np.asarray(support['teacher_shape_semitones'])
                assert np.array_equal(shape,np.asarray(r['wave_shape'])) and abs(np.mean((shape-target)**2)-r['wave_mse'])<1e-12
                assert abs(objective(target,shape,r['coefficients'])-r['objective'])<1e-12
                checked.append({'variant':variant,'wav':str(wav.relative_to(REPO)),'sha256':digest(wav),'finite_E0_support_internal':True})
            chosen=select(s['native'],s['statefit'],s['wavefit'])
            audits.append({'id':row['id'],'source':str(source.relative_to(REPO)),'source_sha256':digest(source),'checked':checked,
                'selected_variant':chosen[0] if chosen else None})
            targets.append({'id':row['id'],'text':row['text'],'length':row['length'],'qualification':chosen[2] if chosen else {'qualified':False},
                'selected_variant':chosen[0] if chosen else None,'source_search':str(source.relative_to(REPO)),'source_sha256':digest(source)})
        qualified=[r for r in targets if r['qualification']['qualified']]
        assert len(qualified)==17 and enough(qualified)
        expected={r['id']:r['variant'] for r in read(TRES/'cause-audit.json')['future_candidate_inventory']}
        assert {r['id']:r['selected_variant'] for r in qualified}==expected
        save(RESULT/'saved-wave-audit.json',{'rows':audits,'checked_conditions':63,'new_render_calls':0,'passed':True})
        save(RESULT/'target-manifest.json',{'rows':targets,'qualified_utterances':17,'minimum_required':12,'fit_supported':enough(qualified),
            'selected_before_fit_and_asr':True,'current_prior_targets_modified':False,'quality_certified':False})
        known=set();history={}
        for path in ROOT.parent.rglob('*.json'):
            if ROOT in path.parents or '.cache' in path.parts or '__pycache__' in path.parts:continue
            try:value=read(path)
            except (UnicodeDecodeError,ValueError):continue
            # 未生成の計画書protocolの新8文だけは既知生成文に数えない。
            if path==TRES/'protocol.json':value={k:v for k,v in value.items() if k!='rows'}
            texts=collect(value)
            if texts:known|=texts;history[str(path.relative_to(REPO))]=digest(path)
        newrows=old['rows'];assert not {r['text'] for r in newrows}&known
        for r in newrows:assert analyze(r['text'])['full_context_labels']==r['full_context_labels']
        assert not {r['text'] for r in training}&{r['text'] for r in old['selection_rows']+newrows}
        for name in ('local_renderer.py','local_control.py','centered_projection.py','local_hts-v2.dylib','shim.c','vendor/HTS_engine.h','objective.py'):
            assert digest(ROOT/name)==digest(TARGET/name)
        assert read(TRES/'entrance-audit.json')['passed'] and read(LRES/'runtime-audit.json')['passed']
        save(RESULT/'entry-audit.json',{'passed':True,'saved_63_waves_valid':True,'exact_renderer_and_projection':True,
            'previous_entry_sha256':digest(TRES/'entrance-audit.json'),'previous_runtime_sha256':digest(LRES/'runtime-audit.json'),
            'new_generation_calls':0,'quality_certified':False})
        save(RESULT/'negative-tests.json',{'selection':tests(),'projection':projection_tests(),'summary':summary_tests()})
        protocol={**old,'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and 'results' not in p.parts and '__pycache__' not in p.parts},
            'history':history,'old_protocol_sha256':digest(TRES/'protocol.json'),'target_kind':'資格を満たす保存実波形の状態候補／逆推定候補から固定目的で選択。',
            'diagnostic_gate':{'global_f0_limit':.05,'active_duration_limit':.03,'content_separate_splits':True,'content_groups_per_split':21,
                'selection_mse_groups':['all','short','long'],'both_conditions_required':True,'missing_allowed':0},
            'no_new_inverse':True,'exact_text_collisions':[],'extra_entry_render_calls_planned':0}
        save(RESULT/'protocol.json',protocol)
        engine=read(RESULT/'engine-contract.json');config=engine['reading_diagnostic']['contract']
        for n,sha in config['dictionary_files'].items():assert digest(Path(config['dictionary_path'])/n)==sha
        assert digest(config['library'])==config['library_sha256']
        proofs={}
        for contract in ROOT.parent.rglob('engine-contract.json'):
            if ROOT in contract.parents:continue
            original=read(contract)
            if not all(original.get(k)==v for k,v in engine.items()):continue
            oldresult=contract.parent;oldprotocol=oldresult/'protocol.json'
            if not oldprotocol.exists():continue
            for path in (oldresult/'asr').rglob('*.json'):
                previous=read(path)
                if previous.get('status')!='completed' or previous.get('protocol_sha256')!=digest(oldprotocol):continue
                wav=(oldresult.parents[1]/previous['wav']) if not Path(previous['wav']).is_absolute() else Path(previous['wav'])
                if not wav.is_file():continue
                assert digest(wav)==previous['wav_sha256']
                proofs[str(path.relative_to(REPO))]={'sha256':digest(path),'protocol_sha256':digest(oldprotocol),
                    'engine_contract_sha256':digest(contract),'wav':str(wav.relative_to(REPO))}
        save(RESULT/'asr-reuse-contract.json',{'current_engine_contract_sha256':digest(RESULT/'engine-contract.json'),
            'source_results':proofs,'no_new_ai_before_all_generation_fixed':True,'failed_calls_retried':False,'maximum_new_ai':320})
    print({'qualified_targets':17,'saved_waves_checked':63,'new_generation_calls':0,'asr_reusable_records':len(proofs)},flush=True)

if __name__=='__main__':main()
