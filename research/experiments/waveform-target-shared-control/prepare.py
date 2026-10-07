"""21訓練文・12旧診断文・新8文と履歴、教師、分岐を固定する。"""
from pathlib import Path
import sys
from campaign import LocalBudget, ROOT, RESULT, REPO, GRES, GUARD, REV, BUNDLE, PILOT, EXT, LRES, read, save, digest
sys.path.insert(0,str(BUNDLE))
from japanese_frontend import analyze
from objective import tests
from guarded_derivative import tests as guard_tests
from integration_tests import tests as integration_tests
from centered_projection import tests as projection_tests


def collect(value):
    if isinstance(value,dict):
        result={value['text']} if isinstance(value.get('text'),str) else set()
        for v in value.values():result|=collect(v)
        return result
    if isinstance(value,list):return set().union(*(collect(v) for v in value))
    return set()


def main():
    with LocalBudget().job('setup','訓練・診断・履歴・出典・停止条件を生成前に固定',2000000):
        proposal=read(GRES/'next-proposal-inputs.json');targets=read(REV/'targets.json')['rows'];rows={}
        for split,items in proposal['inputs'].items():
            output=[]
            for i,item in enumerate(items):
                source=REPO/item['path'];assert digest(source)==item['sha256']
                r=read(source);assert r['status']=='available' and r['split']==split
                t=next(s for s in targets if s['id']==r['id'] and s['text']==r['text'])
                meta=Path(t['source']);m=read(meta);wav=(PILOT if 'nas-pilot' in str(meta) else EXT)/m['wav']
                assert digest(meta)==r['teacher_source_sha256'] and digest(wav)==r['teacher_wav_sha256']==m['wav_sha256']
                row=analyze(r['text']);assert row['full_context_labels']==r['row']['full_context_labels']
                output.append({**row,'id':r['id'],'split':split,'length':'short' if r['id'].startswith(('development','selection')) else 'long',
                    'challenge_group':i%4,'source_training_input':item['path'],'source_sha256':item['sha256'],
                    'teacher_metadata':str(meta.relative_to(REPO)),'teacher_metadata_sha256':digest(meta),
                    'teacher_wav':str(wav.relative_to(REPO)),'teacher_wav_sha256':digest(wav)})
            rows[split]=output
        known=set();history={}
        for path in (ROOT.parent).rglob('*.json'):
            if ROOT in path.parents or '.cache' in path.parts or '__pycache__' in path.parts:continue
            try:value=read(path)
            except (UnicodeDecodeError,ValueError):continue
            texts=collect(value)
            if texts:known|=texts;history[str(path.relative_to(REPO))]=digest(path)
        newtexts=proposal['new_texts'];assert not set(newtexts)&known
        challenges=[(180.,.85),(180.,1.15),(260.,.85),(260.,1.15)]
        newrows=[]
        for i,text in enumerate(newtexts):
            row=analyze(text);newrows.append({**row,'id':f'wave-new-{i:02d}','split':'diagnostic','length':'short' if i<4 else 'long','challenge_group':i%4})
        for row in rows['selection']+newrows:
            f0,speed=challenges[row['challenge_group']]
            row['requests']={'neutral':{'requested_f0':220.,'speed':1.},'challenge':{'requested_f0':f0,'speed':speed}}
        knownrows=[];unresolved_history=[]
        for text in sorted(known):
            try:knownrows.append(analyze(text))
            except ValueError as exc:unresolved_history.append({'text':text,'error':repr(exc)})
        vocabulary={f['string'] for row in knownrows for f in row['features']}
        contexts={tuple(row['phonemes'][i:i+3]) for row in knownrows for i in range(max(0,len(row['phonemes'])-2))}
        overlap=[]
        for row in newrows:
            words={f['string'] for f in row['features']};trigrams={tuple(row['phonemes'][i:i+3]) for i in range(len(row['phonemes'])-2)}
            overlap.append({'id':row['id'],'word_types':len(words),'known_word_types':len(words&vocabulary),'new_word_types':sorted(words-vocabulary),
                'phone_trigram_types':len(trigrams),'known_phone_trigram_types':len(trigrams&contexts),'new_phone_trigrams':[list(x) for x in sorted(trigrams-contexts)]})
        for row in rows['development']:
            source=GRES/'render'/row['id']/'support-contract.json'
            if source.exists():save(RESULT/'inverse-render'/row['id']/'support-contract.json',read(source))
        for name in ['local_renderer.py','local_control.py','centered_projection.py','local_hts-v2.dylib','shim.c','vendor/HTS_engine.h','objective.py','guarded_derivative.py']:
            assert digest(ROOT/name)==digest(GUARD/name)
        audits={str((GRES/'entrance-audit.json').relative_to(REPO)):digest(GRES/'entrance-audit.json'),
            str((LRES/'entry-audit.json').relative_to(REPO)):digest(LRES/'entry-audit.json'),
            str((LRES/'runtime-audit.json').relative_to(REPO)):digest(LRES/'runtime-audit.json')}
        assert read(GRES/'entrance-audit.json')['all_eight_matched'] and read(LRES/'entry-audit.json')['passed'] and read(LRES/'runtime-audit.json')['passed']
        save(RESULT/'reused-entry-audits.json',{'audits':audits,'exact_fixed_sources':True,'additional_runtime_calls':0})
        save(RESULT/'negative-tests.json',{'objective':tests(),'guard':guard_tests(),'integration':integration_tests(),'projection':projection_tests()})
        save(RESULT/'protocol.json',{'training_rows':rows['development'],'selection_rows':rows['selection'],'rows':newrows,
            'variants':['native','direct_non_neural','neural','distilled_non_neural'],'basis_indices':[10,11,12,13],
            'wave_inverse':{'max_iterations':3,'difference_width':.25,'maximum_step':.5,'coefficient_bound':3.,'regularization':.1,'shrink_factors':[.5,.25],'extra_shrink_per_text':3},
            'minimum_target_utterances':12,'both_lengths_required':True,'failed_target_fill':'禁止。欠損として保存',
            'training_rule':{'ridge_lambda':10.,'mlp_width':16,'hidden_layers':2,'steps':500,'learning_rate':.005,'weight_decay':.001,'seed':20261003,'utterance_equal_weight':True},
            'source_hashes':{str(path.relative_to(ROOT)):digest(path) for path in sorted(ROOT.rglob('*')) if path.is_file() and 'results' not in path.parts and '__pycache__' not in path.parts},
            'history':history,'unresolved_history_frontend':unresolved_history,'exact_text_collisions':[],'context_overlap':overlap,'extra_entry_render_calls_planned':0,
            'no_optimization_after_asr':True,'independent_final_confirmation':False,'quality_certified':False,
            'new_support':'新8文は教師なし。各条件の既定DIOとHMM対象区間で固定し、候補側で再選択しない。',
            'selection_support':'各条件の既定DIOと旧教師採用区間の積集合。全12文の欠損を保持。'})
    print('21訓練・12旧診断・新8文、前段・履歴・停止条件を固定しました',flush=True)

if __name__=='__main__':main()
