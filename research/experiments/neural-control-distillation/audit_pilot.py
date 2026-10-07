"""来歴・台帳・旧成果保全と、実施完了/品質未達を区別して監査する。"""
import ast
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from collections import Counter,defaultdict
from budget import Budget,ROOT,RESULT,save,digest
from quality_gate import decide


def main():
    budget=Budget()
    with budget.job('audit','pilotの来歴と実装検証',10000000):
        old=ROOT.parent/'autonomous-speech-synthesis'
        repo=ROOT.parents[2]
        seal=json.loads((old/'results/cycles/ans-extension-20261002-v1/artifact-seal.json').read_text())
        differences=[]
        for name,sha in seal['files'].items():
            p=repo/name
            if not p.is_file() or digest(p)!=sha:differences.append(name)
        save(RESULT/'old-preservation-audit.json',{'checked':len(seal['files']),'differences':differences,
            'passed':not differences,'old_confirmation_used':False,
            'scope':'旧追加サイクルの封印ファイルをハッシュ照合。新研究の自然参照は旧開発群3件のみ'})
        if differences:raise ValueError('旧成果が変更されています')
        for p in ROOT.glob('*.py'):ast.parse(p.read_text())
        test=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],capture_output=True,text=True)
        save(RESULT/'tests.json',{'returncode':test.returncode,'stdout':test.stdout,'stderr':test.stderr,'source_sha256':{p.name:digest(p) for p in (ROOT/'tests').glob('*.py')}})
        test.check_returncode()
        bundles={}
        for name in ('bundle','hts-bundle-v2'):
            p=RESULT/name;m=json.loads((p/'manifest.json').read_text())
            bad=[f for f,sha in m['files'].items() if digest(p/f)!=sha]
            bundles[name]={'manifest_sha256':digest(p/'manifest.json'),'files':len(m['files']),
                'bytes':sum((p/f).stat().st_size for f in m['files']),'mismatched':bad,
                'neural_weights_or_audio':[f for f in m['files'] if Path(f).suffix in ('.pt','.pth','.onnx','.wav','.mp3','.npz')]}
            if bad or bundles[name]['neural_weights_or_audio']:raise ValueError('最終bundleの不正な内容')
        save(RESULT/'bundle-audit.json',bundles)
        cache_files={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'.cache').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
        save(RESULT/'dependency-manifest.json',{'python':sys.version,'platform':platform.platform(),
            'existing_environment':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
            'new_dependency_files':cache_files,'pip_changed_existing_environment':False})
    events=budget.events();starts=[r for r in events if r['event']=='start'];ends={r['id']:r for r in events if r['event']=='finish'}
    counts=Counter();timings=defaultdict(float)
    for r in starts:
        counts[r['kind']]+=r.get('count',1)
        if r['id'] in ends:timings[r['kind']]+=ends[r['id']]['seconds']
    pending=[r['id'] for r in starts if r['id'] not in ends]
    failures=[{'kind':r['kind'],'label':r['label'],'count':r.get('count',1),'details':ends[r['id']]['details']}
        for r in starts if r['id'] in ends and ends[r['id']]['status']=='failed']
    contract=json.loads((RESULT/'contract.json').read_text());inventory=budget.inventory()
    elapsed=time.time()-contract['started_epoch']
    cost={'counts':dict(counts),'job_seconds':dict(timings),'wall_seconds':elapsed,'inventory':inventory,
          'failures':failures,'pending':pending,'limits':contract['limits'],
          'within_limits':elapsed<contract['limits']['seconds'] and inventory['bytes']<contract['limits']['bytes'] and all(counts[k]<=contract['limits'][k] for k in ('teacher','render','ai')),
          'accounting':'countを持たない過去予約は1回。二段HMM実行は2回を開始前に予約し失敗しても返却しない',
          'timing_scope':'job_secondsは読込/管理を含む予約処理。wallとの差は実装・調査・記録を含み、純粋な演算時間ではない'}
    save(RESULT/'cost-audit.json',cost)
    if pending or not cost['within_limits']:raise ValueError('費用監査に不通過')
    evidence={key:(RESULT/path).is_file() for key,path in {
        'teacher_provenance':'teacher-provenance.json','split':'splits.json','control_schema':'control-schema.json',
        'real_renderer_comparison':'main-comparison-summary.json','direct_neural_distilled_models':'model-selection.json',
        'supplementary_comparison':'extended-comparison-summary-v2.json','vtl_independence':'runtime-audit.json',
        'hts_independence':'hts-runtime-audit-v2.json','failure_and_cost':'cost-audit.json','old_preservation':'old-preservation-audit.json',
        'quality_gate_tests':'tests.json'}.items()}
    save(RESULT/'completion-audit.json',{'pilot_artifacts_complete':all(evidence.values()),'evidence':evidence,
        'final_quality_goal_met':False,'goal_completion_not_claimed':True,
        'vtl_candidate_adoption':'rejected-content-protection',
        'hts_research_candidate':'低費用の直接非ニューラル回帰を第一候補、蒸留版を対照として保持。小標本の研究版',
        'missing':['日本語の対象方式に資格のある知覚評価と非劣性幅','独立な最終品質確認',
                   'VOT・局所遷移の信頼性を確認した計測','複数声・速度・長文への品質一般化'],
        'next':'今の監査データで再調整しない。評価器の適用範囲と音素別の生成/制御不足を次の契約へ分ける。規定比較を自動延長しない'})
    print(json.dumps({'counts':dict(counts),'bytes':inventory['bytes'],'wall_seconds':elapsed,'old_files_preserved':len(seal['files']),'pilot_artifacts_complete':all(evidence.values()),'quality_goal_met':False},ensure_ascii=False))


if __name__=='__main__':main()
