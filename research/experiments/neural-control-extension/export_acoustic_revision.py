"""ニューラルを含まない実行bundleを作り、未知文の隔離実行を検証する。"""
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path
from campaign import ROOT,PILOT,PRIOR,RESULT,digest,save
from revision_budget import RevisionBudget,REVISION


def main():
    budget=RevisionBudget();bundle=REVISION/'bundle';out=REVISION/'runtime-audit'
    if not (bundle/'manifest.json').exists():
        with budget.job('setup','音響量制御の非ニューラルbundleを作成',3000000):
            bundle.mkdir(exist_ok=False)
            old=PRIOR/'hts-bundle-v2'
            for name in ['acoustics.py','japanese_frontend.py','mei_normal.htsvoice','LICENSE-HTSVOICE','HTS-PROVENANCE.json']:
                shutil.copyfile(old/name,bundle/name)
            shutil.copyfile(ROOT/'acoustic_control.py',bundle/'acoustic_control.py')
            shutil.copyfile(ROOT/'acoustic_runtime.py',bundle/'runtime.py')
            for name in ['direct_non_neural','distilled_non_neural']:
                shutil.copyfile(REVISION/'models'/(name+'.json'),bundle/(name+'.json'))
            source=(old/'hts_core.py').read_text();tree=ast.parse(source)
            render=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_hts')
            (bundle/'hts_core.py').write_text('"""固定HMMの生成部分だけを抽出した非ニューラル実装。"""\nimport numpy as np\nfrom scipy import signal\n\n'+ast.get_source_segment(source,render)+'\n')
            (bundle/'README.md').write_text('# 音響量制御の研究版\n\n固定回帰とHMMのみで生成する。教師音声、ニューラル重み、発話ごとの軌跡は含めない。\n\n`runtime.py --text TEXT --model direct_non_neural --output output.wav`で生成する。`--pitch-reference`は学習した既定F0に対する220基準の相対指定で、指定値そのものの絶対F0は保証しない。`--speed`は相対速度。1〜120音素、F0参照140〜320、速度0.75〜1.3の研究用範囲。校正・初回生成・一回補正の3生成を実行する。\n\n内容と自然さは未検証。品質認定版として使用しない。Python、NumPy、SciPy、pyopenjtalkと辞書が必要。Mei音源の出典とCC BY 3.0は同梱文書参照。\n')
            save(bundle/'PROVENANCE.json',{'model_selection_sha256':digest(REVISION/'model-selection.json'),
                'targets_sha256':digest(REVISION/'targets.json'),'copied_renderer_sha256':digest(old/'hts_core.py'),
                'quantity':'acoustic-active-duration-and-f0','runtime_neural':False,'control_coefficients_per_model':20,
                'training_data_included':False,'quality_certified':False})
            files={p.name:digest(p) for p in bundle.iterdir() if p.is_file()}
            save(bundle/'manifest.json',{'files':files,'bytes':sum((bundle/n).stat().st_size for n in files),'quality_certified':False})
    if not (out/'contract.json').exists():
        with budget.job('setup','改訂bundleの依存遮断と未知文を固定',1000000):
            out.mkdir(exist_ok=False)
            texts=['風が止む。','買い物の帰りに川の向こうの公園へ寄りました。']
            known=set()
            for path in [PRIOR/'splits.json',PRIOR/'hts-transfer/protocol.json',RESULT/'protocol.json',RESULT/'relative-protocol.json',RESULT/'bounded-protocol.json',REVISION/'render-protocol.json']:
                known.update(r['text'] for r in json.loads(path.read_text())['rows'])
            for name in ['runtime-audit/contract.json','hts-runtime-audit-v2/contract.json']:
                known.update(t if isinstance(t,str) else t['text'] for t in json.loads((PRIOR/name).read_text())['tests'])
            if set(texts)&known:raise ValueError('単独検査文の重複')
            profile=(PRIOR/'hts-runtime-audit-v2/profile.sb').read_text()
            denied=[PILOT,ROOT/'.cache',REVISION/'models',REVISION/'render',REVISION/'refined',REVISION/'targets.json']
            denied.extend(p for p in RESULT.iterdir() if p!=REVISION)
            denied.extend(ROOT.glob('*.py'))
            profile+='\n(deny file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in denied)+')\n'
            (out/'profile.sb').write_text(profile)
            shutil.copyfile(PILOT/'runtime_probe.py',out/'probe.py')
            forbidden_files=[PRIOR/'teacher/development-00.wav',REVISION/'models/neural_control.pt',RESULT/'post-analysis/teacher-targets-v3.json',ROOT/'acoustic_control.py']
            if not all(p.is_file() for p in forbidden_files):raise ValueError('probe対象が実在しない')
            save(out/'probe-inputs.json',{'files':[str(p) for p in forbidden_files]})
            save(out/'contract.json',{'tests':[{'text':texts[0],'pitch_reference':180.,'speed':.85},{'text':texts[1],'pitch_reference':260.,'speed':1.15}],
                'models':['direct_non_neural','distilled_non_neural'],'synthesis_calls_per_run':3,'planned_synthesis_calls':24,
                'profile_sha256':digest(out/'profile.sb'),'quality_certified':False})
    contract=json.loads((out/'contract.json').read_text());profile=out/'profile.sb'
    if digest(profile)!=contract['profile_sha256']:raise ValueError('隔離設定の変更')
    probes=[json.loads(p.read_text()) for p in out.glob('probe*.json') if p.name!='probe-inputs.json']
    probe_passed=any(p.get('returncode')==0 and json.loads(p['stdout']).get('passed') for p in probes)
    if not probe_passed:
        with budget.job('audit','ニューラル・教師・開発コード・ネットワーク拒否を実検査',1000000):
            process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),sys.executable,'-I',str(out/'probe.py'),'--inputs',str(out/'probe-inputs.json')],capture_output=True,text=True,timeout=60)
            save(out/f'probe-attempt-{len(probes)+1}.json',{'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr})
            process.check_returncode()
            if not json.loads(process.stdout)['passed']:raise ValueError('隔離の拒否検査に不通過')
    rows=[]
    for model in contract['models']:
        for i,test in enumerate(contract['tests']):
            pair=[]
            for isolated in [False,True]:
                label=f"{model}-{i}-"+('isolated' if isolated else 'normal');target=out/(label+'.json')
                if target.exists():
                    record=json.loads(target.read_text());pair.append(json.loads(record['stdout']));continue
                with budget.job('render','改訂bundle単独実行/'+label,2000000,count=3):
                    command=[sys.executable,'-I',str(bundle/'runtime.py'),'--text',test['text'],'--model',model,
                        '--pitch-reference',str(test['pitch_reference']),'--speed',str(test['speed']),'--output',str(out/(label+'.wav'))]
                    if isolated:command=['/usr/bin/sandbox-exec','-f',str(profile),*command]
                    process=subprocess.run(command,capture_output=True,text=True,timeout=120)
                    save(target,{'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr})
                    process.check_returncode();pair.append(json.loads(process.stdout))
            rows.append({'model':model,'text':test['text'],'same_float32':pair[0]['sha256_float32']==pair[1]['sha256_float32'],'runs':pair})
    passed=all(r['same_float32'] and all(x['E0_pass'] and not x['forbidden_imports'] and x['synthesis_calls']==3 for x in r['runs']) for r in rows)
    save(REVISION/'runtime-audit.json',{'passed':passed,'rows':rows,'quality_certified':False,'bundle_manifest_sha256':digest(bundle/'manifest.json')})
    if not passed:raise ValueError('単独実行の一致検査に不通過')
    print(json.dumps({'passed':passed,'pairs':len(rows)},ensure_ascii=False))


if __name__=='__main__':main()
