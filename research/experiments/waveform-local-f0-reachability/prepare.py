"""承認済み4文と教師の出典、入口・評価設定を生成前に固定する。"""
from pathlib import Path
import sys
from campaign import LocalBudget, ROOT, RESULT, REPO, PRES, REV, BUNDLE, PILOT, EXT, read, save, digest
sys.path.insert(0,str(BUNDLE))
from japanese_frontend import analyze
from objective import tests


def main():
    with LocalBudget().job('setup','入力・教師出典・損失・負例を生成前に固定',1000000):
        source=PRES/'next-proposal-inputs.json'; prior=read(source)
        targets=read(REV/'targets.json')['rows']; rows=[]
        for i, item in enumerate(prior['rows']):
            path=REPO/item['source']; assert digest(path)==item['source_sha256']
            r=read(path); assert r['split']=='development' and r['status']=='available'
            t=next(s for s in targets if s['id']==r['id'] and s['text']==r['text'])
            metadata=Path(t['source']); m=read(metadata)
            wav=(PILOT if 'nas-pilot' in str(metadata) else EXT)/m['wav']
            assert digest(metadata)==r['teacher_source_sha256']==item['teacher_metadata_sha256']
            assert digest(wav)==r['teacher_wav_sha256']==item['teacher_wav_sha256']==m['wav_sha256']
            row=analyze(r['text']); assert row['full_context_labels']==r['row']['full_context_labels']
            rows.append({**row, 'id':r['id'], 'split':'development', 'length':'short' if i<2 else 'long',
                'challenge_group':i, 'source_training_input':item['source'],'source_sha256':item['source_sha256'],
                'teacher_metadata':str(metadata.relative_to(REPO)),'teacher_metadata_sha256':digest(metadata),
                'teacher_wav':str(wav.relative_to(REPO)),'teacher_wav_sha256':digest(wav)})
        reuse={'entry':PRES/'entry-audit.json','runtime':PRES/'runtime-audit.json'}
        assert all(read(p)['passed'] for p in reuse.values())
        for n in ['local_renderer.py','local_control.py','centered_projection.py','shim.c','local_hts-v2.dylib','vendor/HTS_engine.h']:
            assert digest(ROOT/n)==digest(PRES.parents[1]/n)
        save(RESULT/'reused-engine-audit.json',{'audits':{k:{'path':str(p.relative_to(REPO)),'sha256':digest(p)} for k,p in reuse.items()},
            'exact_renderer_and_projection_reused':True,'new_runtime_calls':0,'quality_certified':False})
        save(RESULT/'negative-tests.json',tests())
        save(RESULT/'protocol.json',{'rows':rows,'variants':['native','statefit','wavefit'],
            'basis_indices':[10,11,12,13],'coefficient_bound':3.,'half_tone_limit':3.,
            'requests':{'pitch_reference':220.,'speed':1.,'half_tone':0.},
            'local_support_rule':{'f0_floor':70.,'f0_ceil':800.,'frame_period':5.,'minimum_voiced_frames':3,'minimum_voiced_fraction':.5,
                'frozen_from_native_intersection':True,'missing_candidate_intervals':'失敗。補間・削除・支持域再選択なし'},
            'state_inverse':{'method':'scipy least_squares trf','max_nfev':200,'ftol':1e-10,'xtol':1e-10,'gtol':1e-10,'regularization':.1},
            'wave_inverse':{'max_iterations':3,'central_difference':.25,'maximum_step_per_coefficient':.5,'regularization':.1,
                'start':[0.,0.,0.,0.],'stop_on_non_improvement':True,'no_candidate_regeneration':True},
            'diagnostic_gate':{'all_four_wave_mse_below_native':True,'all_four_wave_mse_at_most_statefit':True,
                'global_f0_relative_difference_limit':.05,'active_duration_difference_limit':.03,
                'content_groups':['all','short','long'],'asr_both_required':True,'missing_allowed':0},
            'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and 'results' not in p.parts and '__pycache__' not in p.parts},
            'previous_inputs_sha256':digest(source),'no_optimization_after_asr':True,'generalization_evaluated':False,
            'independent_final_confirmation':False,'quality_certified':False})
    print('4文・教師・入口と損失を固定。負例検査通過',flush=True)

if __name__=='__main__':main()
