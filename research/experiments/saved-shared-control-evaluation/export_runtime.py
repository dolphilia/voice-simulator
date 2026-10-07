"""固定16係数bundleを隔離し、新8文32条件を保存済み通常実行と照合する。"""
import json
import shutil
import subprocess
import sys
from campaign import LocalBudget, ROOT, RESULT, REPO, BUNDLE, PILOT, OLD, LRES, TRES, SRES, SHARED, Storage, write_checked, copy_checked, read, save, digest


def main():
    b=LocalBudget();bundle=RESULT/'bundle';out=RESULT/'runtime-audit';p=read(RESULT/'protocol.json')
    normal={r['id']:r for r in read(RESULT/'render-manifest.json')['rows']}
    with b.job('setup','非ニューラルbundle・禁止依存・32照合条件を固定',3000000):
        bundle.mkdir(exist_ok=False);out.mkdir(exist_ok=False)
        for n in ('acoustics.py','acoustic_control.py','japanese_frontend.py','mei_normal.htsvoice','LICENSE-HTSVOICE','HTS-PROVENANCE.json'):copy_checked(BUNDLE/n,bundle/n)
        for n in ('local_control.py','local_renderer.py','centered_projection.py','local_hts-v2.dylib','runtime.py','shim.c'):copy_checked(ROOT/n,bundle/n)
        copy_checked(ROOT/'vendor/HTS_engine.h',bundle/'HTS_engine.h')
        for n in ('direct_non_neural','distilled_non_neural'):copy_checked(SRES/'models'/(n+'.json'),bundle/(n+'.json'))
        write_checked(bundle/'README.md', ('# 保存実波形目標から学習した非ニューラル研究版\n\n文章の辞書・アクセント規則、固定16係数共有回帰、HMM＋手続き的合成で音を作る。直接方式と蒸留方式を同じ入口で比較する。発話別係数・録音・教師・ニューラル重みは同梱しない。\n\n`runtime.py --text TEXT --model direct_non_neural --pitch-reference 220 --speed 1 --output output.wav`。学生は`distilled_non_neural`。macOS arm64、固定pyopenjtalk0.4.1・辞書、NumPy、SciPyが必要。1実行1生成。範囲はF0参照140〜320、速度0.75〜1.3、1〜120音素。対応版HTSヘッダのBSD通知とMeiモデルのCC BY3.0通知を同梱。自然さ・広い日本語の品質は未認定。\n').encode('utf8'))
        save(bundle/'PROVENANCE.json',{'coefficients_per_model':16,'teacher_audio_included':False,'neural_weights_included':False,
            'per_utterance_lookup':False,'model_size_not_proportional_to_training_texts':True,
            'training_contract_sha256':digest(SRES/'training-contract.json'),'runtime_neural':False,'quality_certified':False})
        provenance=read(LRES/'source-provenance.json')
        files={f.name:digest(f) for f in bundle.iterdir() if f.is_file()}
        save(bundle/'manifest.json',{'files':files,'bytes':sum((bundle/n).stat().st_size for n in files),
            'required_runtime':{'pyopenjtalk_version':'0.4.1','hts_binary_sha256':provenance['binary_sha256']},'quality_certified':False})
        profile=(PILOT/'results/nas-pilot-20261002-v1/hts-runtime-audit-v2/profile.sb').read_text()
        denied=[directory for directory in ROOT.parent.iterdir() if directory.is_dir() and directory not in (ROOT,OLD)]
        denied+=list(ROOT.glob('*.py'));denied+=[path for path in RESULT.iterdir() if path not in (bundle,out)]
        profile+='\n(deny file-read* '+''.join('(subpath '+json.dumps(str(path))+') ' for path in denied)+')\n'
        write_checked(out/'profile.sb',profile.encode('utf8'));copy_checked(PILOT/'runtime_probe.py',out/'probe.py')
        forbidden=[SRES/'models/neural.pt',REPO/p['training_rows'][0]['source_training_input'],REPO/p['training_rows'][0]['teacher_wav'],SHARED/'train.py',RESULT/'protocol.json']
        assert all(path.is_file() for path in forbidden)
        save(out/'probe-inputs.json',{'files':[str(path) for path in forbidden]})
        tests=[]
        for row in p['rows']:
            for condition,requested in row['requests'].items():
                for model in ('direct_non_neural','distilled_non_neural'):
                    key=row['id']+'/'+condition+'/'+model;record=normal[key];assert record['status']=='completed'
                    tests.append({'id':key,'text':row['text'],'model':model,'requested':requested,'normal_wav':record['wav'],'normal_wav_sha256':record['wav_sha256']})
        assert len(tests)==32
        save(out/'contract.json',{'tests':tests,'planned_render_calls':32,'normal_runs_reused':True,
            'profile_sha256':digest(out/'profile.sb'),'bundle_manifest_sha256':digest(bundle/'manifest.json'),'quality_certified':False})
    with b.job('audit','教師・訓練記録・ニューラル推論・ネットワーク拒否を検査',1000000):
        process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(out/'profile.sb'),sys.executable,'-B','-I',str(out/'probe.py'),'--inputs',str(out/'probe-inputs.json')],text=True,capture_output=True,timeout=60)
        save(out/'probe-result.json',{'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr})
        process.check_returncode();assert json.loads(process.stdout)['passed']
    results=[]
    for i,test in enumerate(read(out/'contract.json')['tests']):
        with b.job('render','非ニューラル単独実行/'+test['id'],2000000):
            output=out/(f'isolated-{i:02d}.wav');cmd=['/usr/bin/sandbox-exec','-f',str(out/'profile.sb'),sys.executable,'-B','-I',str(bundle/'runtime.py'),
                '--text',test['text'],'--model',test['model'],'--pitch-reference',str(test['requested']['requested_f0']),
                '--speed',str(test['requested']['speed']),'--output',str(output)]
            with Storage().external(output,(REPO/test['normal_wav']).stat().st_size):
                process=subprocess.run(cmd,text=True,capture_output=True,timeout=120)
            result={'id':test['id'],'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr,
                'wav_sha256':digest(output) if output.exists() else None,'normal_wav_sha256':test['normal_wav_sha256']}
            save(out/(f'isolated-{i:02d}.json'),result);process.check_returncode()
            metadata=json.loads(process.stdout);assert metadata['E0_pass'] and not metadata['forbidden_imports'] and metadata['synthesis_calls']==1
            assert result['wav_sha256']==test['normal_wav_sha256']==digest(REPO/test['normal_wav'])
            results.append({**result,'same_wav_sha256':True,'metadata':metadata})
        print('単独照合',i+1,'/32',flush=True)
    save(RESULT/'runtime-audit.json',{'passed':len(results)==32,'rows':results,'new_render_calls':32,
        'bundle_manifest_sha256':digest(bundle/'manifest.json'),'quality_certified':False,'content_evaluated':False})

if __name__=='__main__':main()
