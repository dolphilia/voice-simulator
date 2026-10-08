"""共有文脈HMMのMCP状態分布だけを交換し、未知日本語64波形を比較する。"""
import ast,hashlib,json,os,subprocess,importlib.util,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-acoustic-model-comparison-20261008-v1'
NAME='hts-acoustic-model-comparison-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
MECHANISM=ROOT/'campaigns/nas-hts-acoustic-model-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL={'candidate_pool_short': ['樽の蓋を叩く。', '山の霧を眺める。', '鴨の羽を数える。', '棚の瓶を並べる。', '馬の背を撫でる。', '笛の音を聞く。', '盆の豆を運ぶ。', '庭の塀を直す。'], 'candidate_pool_long': ['夕方の倉庫で荷物を探す父は、古い木箱の中を順番に調べた。', '駅前の公園で待つ姉は、木陰の長椅子に座って本を読み始めた。', '野菜を並べた店先で、祖母は大きな大根を手に取って重さを確かめた。', '昼休みの教室に戻った弟は、机の上の紙を丁寧に重ねた。', '遠くの山が赤く染まる頃、兄は道具を片付けて家へ向かった。', '窓辺で小さな鉢を眺める叔母は、土が乾いていることに気づいた。', '海沿いの道を走る友人は、白い波の向こうに船を見つけた。', '朝食の後に庭へ出た祖父は、折れた竹を集めて隅に置いた。']}
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
    reg=dict(campaign=NAME,status='registered_before_output',question='共有happy HMMのMCP状態平均/分散だけを交換した生成は、未知日本語で内容と工学支持をnative以下に保護できるか。',
        variants=['native','happy_mcp'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor='同full-contextラベルのMei1.4 happy MCP state平均/分散105列をnormalへ交換。共有HMM一つ、係数探索なし。',
        fixed_control='原duration/MSD/LF0/LPF/GV/window/settings/MLPG/vocoder、原励振と時計、alpha.55/beta0/volume1、24k resample/12msfade/gain.25を保持。MCP平均/分散と出力MCPだけ意図的に変える。',
        input='未使用16文×2条件×2方式64。全履歴の文章・full-context非衝突を出力前照合。保護資料本文は読まない。',
        support='新nativeの全支持を一度固定し、candidateの欠測を分母に残す。旧31方式/31,601支持/249欠測/二ASR33群を保持。',
        gates=dict(engineering='全件E0、旧DIO/全体ACF±1半音/confidence≥.6/支持3以上/不変量。',content='二ASR各33群がnative以下、悪化相殺なし。',
            independence='全64通常/隔離・CLI4・保存/外部実体/通信の実拒否。許可はbundle共有資産に限定。',
            physical='保存全32対のLF0/LPF/duration完全一致、MCP全frame有限/形一致/各対非恒等。共有モデルhash/状態MCP donor完全一致/GV・時計・励振完全保持。',
            measurement_scope='旧工学の操作的条件のみ。MCP交換機構を未知HTS動的pitch/境界/知覚へ拡張しない。'),
        estimates=dict(comparison_render=64,comparison_dsp=256,isolation_render=128,isolation_dsp=256,CLI_render=4,CLI_dsp=8,physical_dsp=96,two_ASR_ai=128,
            total_without_retry=dict(render=196,dsp=616,ai=128),additional_DSP='candidate生成ごとにdonor状態照会/状態分布交換照合2単位。64比較32×2、隔離64×2、candidate CLI2×2を追加。',
            maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        source=dict(mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),original_HTS_binary_sha256=digest(MECHANISM/'runtime-bundle/shape.dylib'),
            happy_model_sha256=digest(MECHANISM/'runtime-bundle/mei_happy.htsvoice'),MCP_transfer_binary_sha256=digest(MECHANISM/'runtime-bundle/mcp_model.dylib')),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,coefficient_search_after_output=False,
        controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_acoustic_model_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,old_failed_routes_kept=True)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','共有MCP分布制御の新入力・全比較費・対照を生成前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-output-bound-comparison','hts-acoustic-model-comparison').replace('bound-fresh','model-fresh')
            if n=='controller.py':
                needle="                    for key in ['duration', 'msd', 'settings', 'state_sha256', 'variance_sha256', 'native_parameter_hashes']:"
                assert text.count(needle)==1;text=text.replace(needle,"                    for key in ['duration', 'msd', 'settings', 'state_sha256', 'variance_sha256', 'GV_sha256']:")
                needle="                    assert meta['output_parameter_hashes'][0] == native_meta['output_parameter_hashes'][0]"
                text=text.replace(needle,"                    assert meta['output_parameter_hashes'][0] != native_meta['output_parameter_hashes'][0]")
                needle="                    assert meta['output_parameter_hashes'] == native_meta['output_parameter_hashes']"
                text=text.replace(needle,"                    assert meta['output_parameter_hashes'][1:] == native_meta['output_parameter_hashes'][1:]\n                    assert meta['native_parameter_hashes'][1:] == native_meta['native_parameter_hashes'][1:]")
                text=text.replace('new_DSP_calls=192','new_DSP_calls=256').replace('    dsp=192','    dsp=256')
                text=text.replace("count=64, reserve_bytes=100_000):","count=128, reserve_bytes=100_000):")
                text=text.replace("'CLI E0 ' + mode + '/' + request['id'], reserve_bytes=100_000):","'CLI E0 ' + mode + '/' + request['id'], count=1 if request['method']=='native' else 3, reserve_bytes=100_000):")
                text=text.replace('new_DSP_calls=132','new_DSP_calls=264')
                # bundleに許可した共有資産の物理実体だけを追加し、外部root全体は拒否する。
                needle="        text += '(allow file-read-data (literal ' + json.dumps(str(b.guard.root / 'identity.json')) + '))\n'"
                assert text.count(needle)==1
                text=text.replace(needle,needle+"\n        physical=[p.resolve() for p in (HERE/'runtime-bundle').rglob('*') if p.is_file() and p.is_symlink()]\n        text += '(allow file-read-data ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\n'\n        text += '(allow file-read-metadata ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\n'")
            if n=='runtime.py':
                text=text.replace('from timing_engine import Engine','from acoustic_model import Engine,gv').replace('from bounded_output import synthesize as shape_synthesize','from shape_arrays import synthesize as shape_synthesize').replace("METHODS=['native','soft_bound']","METHODS=['native','happy_mcp']")
                needle='        settings = engine.get_settings()'
                assert text.count(needle)==1
                text=text.replace(needle,needle+"\n        before_GV=gv(engine)\n        transfer=None\n        if method=='happy_mcp':\n            with Engine(row,ROOT/'mei_happy.htsvoice',speed=speed,half_tone=12*math.log2(pitch/220)) as donor:transfer=engine.transfer_mcp(donor)\n        after=engine.snapshot();after_variance=engine.variance()")
                text=text.replace('raw,conversion=shape_synthesize(params,settings,method)',"raw,conversion=shape_synthesize(params,settings,'native')\n        conversion.update(renderer='原HTS-MLSA',source_method='native',source_phase_rule='変更なし',MCP_state_distribution_source=method,MCP_transfer=transfer)")
                text=text.replace('assert engine.snapshot() == before and np.array_equal(engine.variance(), variance)','assert engine.snapshot() == after and np.array_equal(engine.variance(), after_variance) and np.array_equal(gv(engine),before_GV)')
                text=text.replace('variance_sha256=ah(variance), native_parameter_hashes=',"variance_sha256=ah(variance), GV_sha256=ah(before_GV), state_after_sha256=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest(), variance_after_sha256=ah(after_variance), native_parameter_hashes=")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(dict(registered=True,new_scientific_outputs=0),flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json')
    assert digest(Path(__file__))==reg['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','同一原HTSと共有MCP分布制御の閉じた共有bundle',size=16000000) as j:
        bundle=HERE/'runtime-bundle';mapping={n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:PARENT/'runtime-bundle'/n for n in ('acoustics.py',)})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():
            if n=='mei_happy.htsvoice':b.write_data(bundle/n,p.read_bytes(),j)
            else:b.write(bundle/n,p.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(bundle/'mcp_model.dylib'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
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
    b.save(ROOT/'progress-0096.json',dict(active_campaign=NAME,next='登録push→機構hash継承→比較64→通常隔離/CLI→二ASR→全件物理照合/終了',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(prepared=True,new_scientific_outputs=0),flush=True)
def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256']
    if stage=='fixture':
        with job(b,'audit','共有MCP分布上限機構の全hash継承',size=2000000) as j:
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
