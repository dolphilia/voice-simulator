"""固定入力/実行契約を再利用し、予約不足だった隔離事前probeだけを再開する。"""
import importlib.util,json,os,subprocess,sys
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1'
NAME='fujisaki-context-comparison-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

def main():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json')
    assert digest(ROOT/'fujisaki_context_comparison_20261008.py')==reg['controller_sha256']
    assert digest(ROOT/'prepare_fujisaki_comparison_20261008.py')==reg['source']['source_derivation_generator_sha256']
    assert not (HERE/'render-manifest.json').exists() and len(read(HERE/'protocol.json')['rows'])==16
    sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('_fujisaki_fixed_controller',HERE/'controller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.verify()
    assert read(HERE/'controller-binding-audit.json')['reservation_alias_callable']
    token=b.reserve(NAME,'audit','固定Fujisaki入力の隔離事前probeだけを再開',1,20000000,expected_seconds=180)
    try:
        b.save(HERE/'preparation-technical-resume-v2.json',dict(reason='原prepareの入力固定setup後半で一時領域予約が不足。生成0、固定済み入力/bundle/契約は再作成せず、probeだけ別audit予約へ移す。',
                   source_sha256=digest(Path(__file__)),original_registration_sha256=digest(HERE/'registration.json'),execution_contract_sha256=digest(HERE/'execution-contract.json'),
                   original_controller_sha256=digest(HERE/'controller.py'),original_failed_setup_retained=True,all_original_caps_preserved=True,factor_or_gate_change=False,new_render=0,new_DSP=0),token)
        with b.workspace(token,'固定文脈韻律の出力前実拒否probe専用',8000000,16000000) as (work,env):
            sb=m.profile(b,work,True);assert '(allow file-read-data )' not in sb and '(allow file-read-metadata )' not in sb
            assert not any(p.is_symlink() for p in (HERE/'runtime-bundle').rglob('*') if p.is_file())
            blocked=[HERE/'protocol.json',HERE/'registration.json',ROOT/'campaigns/nas-vocoder-f0-20261008-v1/protocol.json']
            code='import json,socket; paths='+repr([str(p) for p in blocked])+'; a=[]\n'
            code+="for p in paths:\n try:open(p,'rb').read(1);a.append(False)\n except PermissionError:a.append(True)\n"
            code+="s=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps(dict(read_denied=a,network_denied=net)))"
            out=subprocess.run(['/usr/bin/sandbox-exec','-p',sb,str(PYTHON),'-I','-B','-c',code],env=env,check=True,capture_output=True,text=True,timeout=45)
            proof=json.loads(out.stdout);assert all(proof['read_denied']) and proof['network_denied']
        m.verify();b.save(HERE/'isolation-preflight.json',dict(proof,paths=[str(p) for p in blocked],empty_allow_clause_absent=True,scientific_outputs=0,temporary_removed=True,technical_resume_sha256=digest(HERE/'preparation-technical-resume-v2.json')),token)
    except BaseException as exc:
        if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'preparation-probe-failure-v2.json',dict(stdout=exc.stdout,stderr=exc.stderr,returncode=exc.returncode),token)
        b.finish(token,repr(exc));raise
    else:b.finish(token)
    assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in b.snapshot()['temporary_work'].values() if x['campaign']==NAME)
    b.save(ROOT/'progress-0113.json',dict(active_campaign=NAME,next='固定準備結果push→機構hash継承→新64比較/通常隔離CLI/二ASR/保存LF0独立式',preparation_completed=True,technical_setup_failure_retained=True,new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(prepared=True,all_three_reads_denied=True,network_denied=True,new_scientific_outputs=0),flush=True)

if __name__=='__main__':main()
