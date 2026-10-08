"""原HTSの最終振幅だけを固定解析式で変更し、未知日本語64波形を比較する。"""
import ast,hashlib,json,os,subprocess,importlib.util,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
NAME='hts-output-bound-comparison-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1'
MECHANISM=ROOT/'campaigns/nas-hts-output-bound-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL={'candidate_pool_short': ['籠の梨を剥く。', '鍋の底を磨く。', '布の端を裂く。', '犬の鈴を外す。', '爪の砂を洗う。', '桃の種を拾う。', '花の枝を切る。', '猫の皿を拭く。'], 'candidate_pool_long': ['庭の隅で芽を出した草を見つけて、祖父は静かに笑った。', '帰り道で買った小さな箱を、姉は玄関の棚に置いた。', '日差しが弱まった頃、弟は窓を開けて部屋の空気を入れ替えた。', '橋を渡る途中で振り返ると、遠くの丘に白い雲が浮かんでいた。', '店の奥で見つけた布を広げて、母は手触りを確かめた。', '雨上がりの畑を歩く兄は、濡れた葉の様子を注意深く見ていた。', '夕食を終えた叔父は、台所の灯りを消して廊下へ出た。', '朝の港を眺めながら、友人は前日の出来事をゆっくり話した。']}
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
    reg=dict(campaign=NAME,status='registered_before_output',question='固定出力上限は未知日本語の過大ピークを抑え、旧pitch/固定支持/二ASRを原native以下に保護できるか。',
        variants=['native','soft_bound'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor='共通gain.25後でabs(x)<=.5は恒等、外側sign(x)*(.5+.48*tanh((abs(x)-.5)/.48))。knee.5/ceiling.98を固定。',
        fixed_control='原MCP/LF0/LPF/duration/MSD/state/variance、原励振と源時計、alpha.55/beta0/volume1、24k resample/12msfade/gain.25不変。オールパス不使用。波形別係数/利得/教師/保存lookupなし。',
        input='未使用16文×2条件×2方式64。全履歴の文章・full-contextラベル非衝突を出力前照合。保護資料本文は読まない。',
        support='新nativeで一度固定した全支持を保持。欠測は不通過で分母に残す。旧31方式/支持31,601/欠測249/各ASR33群の判定を変えない。',
        gates=dict(engineering='全件E0、DIO/全体ACF±1半音、confidence≥.6、固定支持3以上、全件不変量。',content='二ASR各33群をnative以下、悪化相殺なし。',independence='全64通常/隔離・CLI4・保存資料/外部実体/通信の実拒否。',
            physical='保存全32対のMCP/LF0/LPF/duration完全一致、float32恒等域完全一致とpeak<.99、保存native float32からの独立式最大誤差≤1.5e-7。元double→float32丸め差を含む許容誤差でbyte一致と呼ばない。',
            measurement_scope='旧工学の操作的資格のみ。人工上限・YIN40msを未知HTSピッチ/境界/知覚へ拡張しない。'),
        estimates=dict(comparison_render=64,comparison_dsp=192,isolation_render=128,isolation_dsp=128,CLI_render=4,CLI_dsp=4,fixture_render=0,inherited_fixture=True,physical_dsp=96,two_ASR_ai=128,
            total_without_retry=dict(render=196,dsp=420,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        nonlinear_harmonics_alias_or_DC_changes_possible=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
        source=dict(mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),original_HTS_binary_sha256=digest(MECHANISM/'runtime-bundle/shape.dylib')),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,coefficient_search_after_output=False,
        controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_output_bound_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),old_failed_routes_kept=True)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','固定出力制御の新入力・全比較費・対照を生成前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-allpass-comparison','hts-output-bound-comparison').replace('allpass-fresh','bound-fresh')
            if n=='controller.py':
                assert text.count('from paths import *')==1;text=text.replace('from paths import *','from paths import *\nfrom paths import job as managed_job',1)
                needle="                    assert meta['conversion']['original_excitation_sha256'] == native_meta['conversion']['original_excitation_sha256']"
                assert text.count(needle)==1;text=text.replace(needle,needle+"\n                    assert meta['conversion']['processed_excitation_sha256'] == native_meta['conversion']['processed_excitation_sha256']")
            if n=='runtime.py':
                text=text.replace('from shape_arrays import synthesize as shape_synthesize','from bounded_output import synthesize as shape_synthesize').replace("METHODS=['native','allpass']","METHODS=['native','soft_bound']")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.write(HERE/'bounded_output.py',(MECHANISM/'bounded_output.py').read_bytes(),j)
        for n in ('shape.c','shape.dylib','shape_arrays.py','HTS-BSD-NOTICE.txt'):b.write(HERE/n,(PARENT/n).read_bytes(),j)
        for n in ('HTS_hidden.h','HTS_engine.h','HTS_vocoder_shaped.c'):b.write(HERE/'vendor'/n,(PARENT/'vendor'/n).read_bytes(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(dict(registered=True,new_scientific_outputs=0),flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json')
    assert digest(Path(__file__))==reg['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','同一原HTSと固定出力制御の閉じた共有bundle',size=16000000) as j:
        assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib')
        bundle=HERE/'runtime-bundle';mapping={n:PARENT/'runtime-bundle'/n for n in read(PARENT/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py','bounded_output.py')})
        for n,p in mapping.items():b.write(bundle/n,p.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(HERE/'shape.dylib'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
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
    b.save(ROOT/'progress-0087.json',dict(active_campaign=NAME,next='登録push→機構hash継承→比較64→通常隔離/CLI→二ASR→全件物理照合/終了',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(prepared=True,new_scientific_outputs=0),flush=True)
def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256']
    if stage=='fixture':
        with job(b,'audit','固定出力上限機構の全hash継承',size=2000000) as j:
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
