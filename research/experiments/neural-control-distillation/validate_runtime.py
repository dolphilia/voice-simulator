"""未知文章を通常/OS隔離で再生成し、参照からの独立性を検証する。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from budget import Budget,ROOT,RESULT,save,digest

OLD=ROOT.parent/'autonomous-speech-synthesis'
TESTS=[{'text':'遠くの鐘が鳴る。','f0':180.,'speed':.85},
       {'text':'夕焼けの庭を眺める。','f0':260.,'speed':1.15}]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    out=RESULT/'runtime-audit'
    bundle=RESULT/'bundle'
    budget=Budget()
    if args.prepare_only:
        with budget.job('setup','OS隔離の契約と拒否対象を固定',2_000_000):
            out.mkdir(exist_ok=True)
            forbidden=[ROOT/'.cache',RESULT/'teacher',RESULT/'teacher-corrected',RESULT/'models',
                       OLD/'.cache',OLD/'results',ROOT.parents[1]/'data',Path.home()/'.cache']
            site=Path(sys.executable).parent.parent/'lib/python3.11/site-packages'
            forbidden.extend(site/name for name in ('torch','transformers','faster_whisper','ctranslate2',
                                                    'onnxruntime','tensorflow'))
            profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+''.join(
                '(subpath '+json.dumps(str(p))+') ' for p in forbidden)+')\n'
            (out/'profile.sb').write_text(profile)
            split=json.loads((OLD/'results/ans-pilot-v1/splits.json').read_text())
            natural=ROOT.parents[2]/split['groups']['development']['records'][0]['wav']
            files=[ROOT/'.cache/teacher/kokoro-v1_0.pth',RESULT/'teacher/development-00.wav',
                   RESULT/'models/neural_control.pt',natural,site/'torch/__init__.py']
            if not all(p.is_file() for p in files):
                raise ValueError('拒否probeの対象ファイルが実在しません')
            save(out/'probe-inputs.json',{'files':[str(p) for p in files]})
            save(out/'contract.json',{'tests':TESTS,'models':['direct_non_neural','distilled_non_neural'],
                 'independence':'未使用の文章とF0/速度組合せ。内容認識の認定とは別',
                 'profile_sha256':digest(out/'profile.sb'),'source_sha256':digest(__file__)})
        return
    profile=out/'profile.sb'
    contract=json.loads((out/'contract.json').read_text())
    if digest(profile)!=contract['profile_sha256']:
        raise ValueError('隔離設定が変わりました')
    with budget.job('audit','隔離probe',1_000_000):
        result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),sys.executable,'-I',
                              str(ROOT/'runtime_probe.py'),'--inputs',str(out/'probe-inputs.json')],
                              capture_output=True,text=True,timeout=60)
        save(out/'probe.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        result.check_returncode()
        if not json.loads(result.stdout)['passed']:
            raise RuntimeError('隔離拒否の検査に不通過です')
    rows=[]
    for model in contract['models']:
        for i,test in enumerate(contract['tests']):
            pair=[]
            for isolated in (False,True):
                label=f'{model}-{i}-'+('isolated' if isolated else 'normal')
                with budget.job('render','未知文/'+label,5_000_000):
                    command=[sys.executable,'-I',str(bundle/'runtime.py'),'--text',test['text'],
                             '--model',model,'--f0',str(test['f0']),'--speed',str(test['speed']),
                             '--output',str(out/(label+'.wav'))]
                    if isolated:
                        command=['/usr/bin/sandbox-exec','-f',str(profile),*command]
                    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
                    save(out/(label+'.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                    result.check_returncode()
                    pair.append(json.loads(result.stdout))
            rows.append({'model':model,**test,'same_float64':pair[0]['sha256_float64']==pair[1]['sha256_float64'],
                         'runs':pair})
    passed=all(r['same_float64'] and all(not x['forbidden_imports'] for x in r['runs']) for r in rows)
    save(RESULT/'runtime-audit.json',{'passed':passed,'rows':rows,'probe':str((out/'probe.json').relative_to(ROOT)),
         'manifest_sha256':digest(bundle/'manifest.json'),'quality_qualification':False})
    if not passed:
        raise RuntimeError('未知文の隔離再生成が一致しません')
    print(json.dumps({'passed':passed,'pairs':len(rows)},ensure_ascii=False))


if __name__=='__main__':
    main()
