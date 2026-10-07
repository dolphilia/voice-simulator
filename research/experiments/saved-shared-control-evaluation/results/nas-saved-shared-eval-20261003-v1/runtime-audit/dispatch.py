"""OS隔離の適用拒否後、未起動の検査本体を適用可能な環境で実行する。"""
import sys
import json
import subprocess
from pathlib import Path
sys.path.insert(0,'/Users/dolphilia/github/voice-simulator/research/experiments/saved-shared-control-evaluation')
from campaign import *
def main():
    b=LocalBudget();bundle=RESULT/"bundle";out=RESULT/"runtime-audit"
    with b.job('audit','教師・訓練記録・ニューラル推論・ネットワーク拒否を検査',1000000):
        process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(out/'profile.sb'),sys.executable,'-B','-I',str(out/'probe.py'),'--inputs',str(out/'probe-inputs.json')],text=True,capture_output=True,timeout=60)
        save(out/'probe-first-executed-result.json',{'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr})
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
