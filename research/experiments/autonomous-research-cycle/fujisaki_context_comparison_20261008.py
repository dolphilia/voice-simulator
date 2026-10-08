"""原HTSの有声LF0輪郭だけを固定指令応答で変更し、未知日本語64波形を比較する。"""
import ast,hashlib,json,os,subprocess,importlib.util,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1'
NAME='fujisaki-context-comparison-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1'
MECHANISM=ROOT/'campaigns/nas-fujisaki-context-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL={'candidate_pool_short': ['櫛の歯を洗う。', '柚子の皮を干す。', '瓶の蓋を回す。', '靴の紐を結ぶ。', '藁の束を運ぶ。', '鉢の土を均す。', '絹の帯を巻く。', '雲の影を追う。', '坂の石を拾う。', '笛の音を聞く。', '杉の葉を集める。', '杖の先を拭く。'], 'candidate_pool_long': ['霧が晴れた朝、祖父は坂の途中にある畑へ道具を運んだ。', '仕事を終えた母は、店の前で待っていた友人に手を振った。', '船が岸を離れると、弟は鞄から取り出した地図を広げた。', '庭に置いた鉢の土を確かめて、姉は小さな苗に水を注いだ。', '駅から帰った兄は、窓辺の椅子に座って靴の紐を解いた。', '日が傾く頃、叔母は台所に並べた瓶の蓋を一つずつ閉めた。', '川から吹く風を感じながら、父は橋の近くで友人を待った。', '門の外から声がすると、妹は手に持った布を棚へ戻した。', '村の祭りが終わった後、叔父は広場に残された箱を運んだ。', '雨音が弱くなると、祖母は窓を開けて庭の木を眺めた。', '海辺を歩いていた友人は、波が運んできた貝を拾い上げた。', '本を読み終えた姉は、机の灯りを消して廊下へ出た。']}
from prepare_fujisaki_comparison_20261008 import controller as make_controller
@contextmanager
def job(b,kind,label,count=1,size=0,seconds=180):
    token=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield token
    except BaseException as exc:b.finish(token,repr(exc));raise
    else:b.finish(token)
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert read(MECHANISM/'aggregate-summary.json')['mechanical_fixture_passed']
    limits=dict(seconds=14400,bytes=1800000000,write_bytes=2800000000,setup=30,audit=40,render=650,dsp=1800,ai=384,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,status='registered_before_output',question='ラベルからの固定句/アクセント応答は、新日本語でnativeの工学・固定支持・内容を保持できるか。',
        variants=['native','fujisaki'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor='原有声LF0輪郭を固定Fujisaki応答へ置換。alpha3/beta20/gamma.9/Ap.15秒/Aa.25/句先行.2秒とA/F/I時刻規則は機構登録のまま。',
        fixed_control='同一共有Mei/labels/状態長/MSD/state/variance/MCP/LPF、原pulse/noise/MLSA/alpha.55/beta0/volume1/resample/12msfade/gain.25。源時計と原励振の方式間同一性は主張しない。',
        semantics='同じ有声中央値220/280Hzへ校正するが、相対LF0輪郭は意図して異なる。句/アクセント応答は因果的、全発話median校正はstreaming因果ではない。末尾核/無アクセントのF2同値化を保持。',
        input='全履歴非衝突の新16文(8短8長)×2条件×2方式64。出力前poolから最初のvalid非衝突を選ぶ。P5本文を読まない。',
        support='nativeで一度固定した全支持を候補へ保持。欠測を分母から除かず、旧31方式/31,601支持/249欠測/二ASR各33群を保持。',
        gates=dict(engineering='全件E0、旧DIO/全体ACF±1半音/confidence≥.6/固定支持3以上/全不変量。',content='二ASR各33群がnative以下、悪化相殺なし。',
            independence='全64通常/隔離・CLI4・論理/物理の波形/配列/契約/旧入力/archivesと通信の実拒否。空のallow clauseを生成しない。',
            physical='保存全32対の全frame MCP/LPF/duration/mask/sentinel完全一致。候補LF0は保存指令時刻と固定一次式から独立scalarで全frame照合。固定支持一致。',
            measurement_scope='旧工学操作的条件だけ。二次応答やラベル生成の機構資格を日本語知覚/音韻正解へ移さない。'),
        estimates=dict(comparison_render=64,comparison_dsp=192,isolation_render=128,isolation_dsp=128,CLI_render=4,CLI_dsp=4,physical_dsp=96,two_ASR_ai=128,
            internal_MLSA_helpers=0,total_without_retry=dict(render=196,dsp=420,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        source=dict(mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),mechanism_runtime_sha256=digest(MECHANISM/'runtime-bundle/runtime.py'),fixed_prosody_module_sha256=digest(MECHANISM/'runtime-bundle/fujisaki_context.py'),source_derivation_generator_sha256=digest(ROOT/'prepare_fujisaki_comparison_20261008.py')),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,coefficient_or_command_search_after_output=False,
        controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'fujisaki_context_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),old_failed_routes_kept=True,
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','固定文脈韻律の新入力・全比較費・対照を生成前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py'):
            text=(PARENT/n).read_text().replace('hts-allpass-comparison','fujisaki-context-comparison').replace('allpass-fresh','fujisaki-fresh')
            if n=='controller.py':text=make_controller(text)
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.write(HERE/'runtime.py',(MECHANISM/'runtime-bundle/runtime.py').read_bytes(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(dict(registered=True,new_scientific_outputs=0),flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json')
    assert digest(Path(__file__))==reg['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','同一原HTSと固定文脈韻律の閉じた共有bundle',size=16000000) as j:
        bundle=HERE/'runtime-bundle';mapping={n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():b.write(bundle/n,p.read_bytes(),j)
        assert all(not (bundle/n).is_symlink() for n in mapping), '今回の共有bundleは内蔵実体だけに限定する'
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(inherited_shared_assets_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
    with job(b,'setup','全履歴非衝突と入力条件の波形前固定',size=16000000) as j:
        with b.workspace(j,'辞書と入力照合') as (_,env):
            result=subprocess.run([str(PYTHON),'-B',str(HERE/'prepare_inputs.py')],env=env,check=True,timeout=120,capture_output=True,text=True)
        value=json.loads(result.stdout);assert len(value['rows'])==16
        b.save(HERE/'novelty-audit.json',value['audit'],j)
        b.save(HERE/'protocol.json',dict(rows=value['rows'],variants=reg['variants'],conditions=reg['conditions'],expected_records=64,protected_confirmation_opened=False,no_optimization_after_first_audio=True,quality_certified=False),j)
        b.save(HERE/'measurement-package-contract.json',read(PARENT/'measurement-package-contract.json'),j)
        b.save(HERE/'execution-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),registration_sha256=digest(HERE/'registration.json'),runtime_manifest_sha256=digest(bundle/'manifest.json'),source_hashes={p.name:digest(p) for p in HERE.glob('*.py')},engine_contract_sha256=digest(HERE/'engine-contract.json'),controller_sha256=digest(Path(__file__)),fixed_before_first_wave=True,quality_certified=False),j)
        sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('_output_bound_controller',HERE/'controller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.verify();assert callable(m.managed_job)
        b.save(HERE/'controller-binding-audit.json',dict(reservation_alias_callable=True,source_contract_verified=True,new_scientific_outputs=0),j)
        with b.workspace(j,'隔離profileの出力前実拒否') as (work,env):
            sb=m.profile(b,work,True);assert '(allow file-read-data )' not in sb and '(allow file-read-metadata )' not in sb
            blocked=[HERE/'protocol.json',HERE/'registration.json',BASE/'protocol.json']
            code='import json,socket; paths='+repr([str(p) for p in blocked])+'; a=[]\n'
            code+="for p in paths:\n try:open(p,'rb').read(1);a.append(False)\n except PermissionError:a.append(True)\n"
            code+="s=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps(dict(read_denied=a,network_denied=net)))"
            proof=json.loads(m.execute([str(PYTHON),'-I','-B','-c',code],env,sb,timeout=45))
            assert all(proof['read_denied']) and proof['network_denied']
        b.save(HERE/'isolation-preflight.json',dict(proof,paths=[str(p) for p in blocked],empty_allow_clause_absent=True,scientific_outputs=0),j)
    b.save(ROOT/'progress-0113.json',dict(active_campaign=NAME,next='登録push→機構hash継承→比較64→通常隔離/CLI→二ASR→全件物理照合/終了',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(prepared=True,new_scientific_outputs=0),flush=True)
def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256']
    if stage=='fixture':
        with job(b,'audit','固定文脈韻律機構の全hash継承',size=2000000) as j:
            for n,h in read(MECHANISM/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
            b.save(HERE/'fixture-audit.json',dict(read(MECHANISM/'fixture-audit.json'),inherited=True,original_sha256=digest(MECHANISM/'fixture-audit.json'),new_render=0,new_dsp=0),j)
    else:
        assert read(HERE/'fixture-audit.json')['passed']
        env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(BASE/'runtime-bundle/packages-v2')
        args=[str(PYTHON),'-B',str(HERE/'controller.py'),stage]
        if engine:args+=['--engine',engine]
        try:result=subprocess.run(args,env=env,check=True,capture_output=True,text=True,timeout=4000)
        except subprocess.CalledProcessError as exc:
            with job(b,'audit','子比較の失敗出力保持 '+stage+(engine or ''),size=2000000) as j:b.save(HERE/('child-failure-'+stage+(engine or '')+'.json'),dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),j)
            raise
        print(result.stdout,flush=True)
        if result.stderr:print(result.stderr,flush=True)
    print(b.reconcile(),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture','comparison','isolate','asr']);p.add_argument('--engine');a=p.parse_args()
    register() if a.stage=='register' else prepare() if a.stage=='prepare' else run(a.stage,a.engine)
