"""HMM版を二段生成として計数し、ニューラル・参照を遮断して未知文を検証する。"""
import argparse
import json
import subprocess
import sys
from budget import Budget,ROOT,RESULT,save,digest

TESTS=['赤い傘を閉じる。','朝の窓を開ける。']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();out=RESULT/'hts-runtime-audit-v2';budget=Budget()
    if args.prepare_only:
        with budget.job('setup','HMM隔離検証の契約固定',1_000_000):
            out.mkdir(exist_ok=False)
            used={r['text'] for r in json.loads((RESULT/'splits.json').read_text())['rows']}
            used.update(r['text'] for r in json.loads((RESULT/'hts-transfer/protocol.json').read_text())['rows'])
            if used.intersection(TESTS):raise ValueError('未知文が重複しています')
            profile=(RESULT/'runtime-audit/profile.sb').read_text()
            extra=[RESULT/name for name in ('hts-transfer','natural-comparison','world','fitted','comparisons')]
            profile+='\n(deny file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in extra)+')\n'
            (out/'profile.sb').write_text(profile)
            save(out/'contract.json',{'tests':TESTS,'models':['direct_non_neural','distilled_non_neural'],
                'synthesis_calls_per_run':2,'planned_synthesis_calls':16,
                'profile_sha256':digest(out/'profile.sb'),'unknown_before_generation':True,
                'quality_qualification':False,
                'prior_failed_test':'最初の文はv1の工学不通過を検出済み。同じ文での修正検証であり、新しい独立品質確認ではない'})
        return
    contract=json.loads((out/'contract.json').read_text());profile=out/'profile.sb'
    if digest(profile)!=contract['profile_sha256']:raise ValueError('隔離設定の不一致')
    with budget.job('audit','HMM隔離probe',1_000_000):
        result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),sys.executable,'-I',
            str(ROOT/'runtime_probe.py'),'--inputs',str(RESULT/'runtime-audit/probe-inputs.json')],capture_output=True,text=True,timeout=60)
        save(out/'probe.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        result.check_returncode()
        if not json.loads(result.stdout)['passed']:raise RuntimeError('隔離拒否を確認できません')
    rows=[]
    for model in contract['models']:
        for i,text in enumerate(contract['tests']):
            pair=[]
            for isolated in (False,True):
                label=f'{model}-{i}-'+('isolated' if isolated else 'normal')
                with budget.job('render','HMM未知文/'+label,2_000_000,count=2):
                    command=[sys.executable,'-I',str(RESULT/'hts-bundle-v2/hts_runtime.py'),'--text',text,
                             '--model',model,'--output',str(out/(label+'.wav'))]
                    if isolated:command=['/usr/bin/sandbox-exec','-f',str(profile),*command]
                    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
                    save(out/(label+'.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                    result.check_returncode();pair.append(json.loads(result.stdout))
            rows.append({'model':model,'text':text,'same_float64':pair[0]['sha256_float64']==pair[1]['sha256_float64'],'runs':pair})
    passed=all(r['same_float64'] and all(x['E0_pass'] and not x['forbidden_imports'] and x['synthesis_calls']==2 for x in r['runs']) for r in rows)
    save(RESULT/'hts-runtime-audit-v2.json',{'passed':passed,'rows':rows,
        'manifest_sha256':digest(RESULT/'hts-bundle-v2/manifest.json'),'quality_qualification':False})
    if not passed:raise RuntimeError('HMMの隔離実行に不一致があります')
    print(json.dumps({'passed':passed,'pairs':len(rows),'synthesis_calls':16}))


if __name__=='__main__':main()
