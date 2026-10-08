"""原HTSの有声LPF入力だけを固定LFで変更し、未知日本語64波形を比較する。"""
import ast,hashlib,json,os,subprocess,importlib.util,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-lf-comparison-20261008-v1'
NAME='hts-lf-comparison-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1'
MECHANISM=ROOT/'campaigns/nas-hts-lf-coupling-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL={'candidate_pool_short': ['砂の瓶を振る。', '梅の実を漬ける。', '窓の網を張る。', '襟の糸を抜く。', '庭の杭を打つ。', '池の鯉を数える。', '畑の豆を蒸す。', '丘の鐘を鳴らす。', '櫓の板を削る。', '舟の帆を畳む。', '皿の胡麻を撒く。', '柿の枝を束ねる。'], 'candidate_pool_long': ['風が静まった頃、祖母は裏庭に干した布を取り込んだ。', '朝の支度を終えた姉は、机の端に置いた帳面を鞄に入れた。', '道に残った水を避けながら、父は市場へ向かって歩いた。', '小屋の扉を開けた兄は、壁に掛けられた縄を手に取った。', '畑で集めた豆を広げると、叔母は傷んだ粒を一つずつ除いた。', '窓辺に座った友人は、遠くから聞こえる鐘に耳を傾けた。', '雨雲が去った後、妹は門の前に落ちた葉を掃き集めた。', '昼の休みに戻った叔父は、台所で冷たい水を一杯飲んだ。', '灯りを点けた祖父は、棚から取り出した地図を広げた。', '港から歩いて帰る母は、路地の角で近所の人と話した。', '木陰で一息ついた弟は、靴に入った砂を静かに払った。', '村を出る前に、友人は橋の上から川の流れを眺めた。']}
PROFILE_PATCH="        physical=[p.resolve() for p in (HERE/'runtime-bundle').rglob('*') if p.is_file() and p.is_symlink()]\n        text += '(allow file-read-data ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'\n        text += '(allow file-read-metadata ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'\n"
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
    reg=dict(campaign=NAME,status='registered_before_output',question='固定LFを有声LPF入力へ結合した候補が、新日本語で原nativeの内容/旧工学/固定支持を保持できるか。',
        variants=['native','lf'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor='元sqrt(period) impulseだけを、Tp=.4/Te=.6/Ta=.05/Ee=1の連続周期RMS=1固定LF derivativeへ置換。noise/RNG/LPF ring/元counter/period/全三stream/MLSAは保持。',
        phase='元counter更新後、period補間前のfmod(counter/period,1)。有限/動的な周期面積0・antialiasing・自然声最適性を主張しない。LF0列縮小とは別。',
        fixed_control='同共有Mei/labels/duration/MSD/state/variance/MCP/LF0/LPF・相対LF0と校正中央値・alpha.55/beta0/volume1・24k resample/12msfade/gain.25。波形別gain/係数/phase探索なし。',
        input='全履歴非衝突の新16文(8短8長)×2条件×2方式64。出力前pool固定し最初のvalid非衝突を選ぶ。P5本文を読まない。',
        support='nativeで一度固定した全音素支持を候補へ保持、欠測を分母から除かない。旧31方式/31,601支持/249欠測/二ASR各33群を保持。',
        gates=dict(engineering='全件E0、旧DIO/全体ACF±1半音/confidence≥.6/固定支持3以上/不変量。',content='二ASR各33群がnative以下、悪化相殺なし。',
            independence='全64通常/隔離・CLI4・論理/物理資料/通信の実拒否。外部bundleは封印した個別実体だけ許可。',
            physical='保存全32対の全frame MCP/LF0/LPF/duration完全一致、源時計/元励振/noise/phase hash完全一致、固定支持一致。処理励振だけ意図した因子。',
            measurement_scope='旧工学操作的条件だけ。LF面積・周期観測・人工結合資格を未知日本語知覚/境界truthへ移さない。'),
        estimates=dict(comparison_render=96,comparison_dsp=192,isolation_render=192,isolation_dsp=128,CLI_render=6,CLI_dsp=4,physical_dsp=96,two_ASR_ai=128,
            internal_MLSA_helpers=98,total_without_retry=dict(render=294,dsp=420,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        source=dict(mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),LF_primitive_seal_sha256=digest(ROOT/'campaigns/nas-lf-source-mechanism-20261008-v1/artifact-seal.json'),coupled_binary_sha256=digest(MECHANISM/'runtime-bundle/shape.dylib')),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,coefficient_search_after_output=False,
        controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_lf_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),old_failed_routes_kept=True,
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','固定LF結合の新入力・全比較費・対照を生成前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-allpass-comparison','hts-lf-comparison').replace('allpass-fresh','lf-fresh')
            if n=='controller.py':
                assert text.count('from paths import *')==1;text=text.replace('from paths import *','from paths import *\nfrom paths import job as managed_job',1)
                text=text.replace('new_render_calls=64, internal_MLSA_helpers=0','new_render_calls=96, internal_MLSA_helpers=32').replace('    count=64\n','    count=96\n')
                text=text.replace("'通常/隔離batch64 ' + mode, count=64","'通常/隔離batch64 ' + mode, count=96")
                text=text.replace("for r in manifest['records']) == 64","for r in manifest['records']) == 96")
                text=text.replace("'CLI ' + mode + '/' + request['id'], count=1","'CLI ' + mode + '/' + request['id'], count=1 if request['method']=='native' else 2")
                text=text.replace('new_render_calls=132, new_DSP_calls=132, internal_MLSA_helpers=0','new_render_calls=198, new_DSP_calls=132, internal_MLSA_helpers=66')
                needle="                    assert meta['conversion']['original_excitation_sha256'] == native_meta['conversion']['original_excitation_sha256']"
                assert text.count(needle)==1;text=text.replace(needle,needle+"\n                    assert meta['conversion']['noise_sha256']==native_meta['conversion']['noise_sha256']\n                    assert meta['conversion']['LF_phase_sha256']==native_meta['conversion']['LF_phase_sha256']")
                line=next(line for line in text.splitlines() if 'identity.json' in line);assert text.count(line)==1;text=text.replace(line,line+'\n'+PROFILE_PATCH)
            if n=='runtime.py':text=text.replace("METHODS=['native','allpass']","METHODS=['native','lf']")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        for n in ('shape.c','shape_arrays.py','HTS-BSD-NOTICE.txt','lf_source.c'):b.write(HERE/n,(MECHANISM/n).read_bytes(),j)
        b.write_data(HERE/'shape.dylib',(MECHANISM/'runtime-bundle/shape.dylib').read_bytes(),j)
        for n in ('HTS_hidden.h','HTS_engine.h','HTS_vocoder_shaped.c'):b.write(HERE/'vendor'/n,(MECHANISM/'vendor'/n).read_bytes(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(dict(registered=True,new_scientific_outputs=0),flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json')
    assert digest(Path(__file__))==reg['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','同一原HTSと固定LF結合の閉じた共有bundle',size=16000000) as j:
        assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib')
        bundle=HERE/'runtime-bundle';mapping={n:PARENT/'runtime-bundle'/n for n in read(PARENT/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
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
    b.save(ROOT/'progress-0107.json',dict(active_campaign=NAME,next='登録push→機構hash継承→比較64→通常隔離/CLI→二ASR→全件物理照合/終了',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(prepared=True,new_scientific_outputs=0),flush=True)
def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256']
    if stage=='fixture':
        with job(b,'audit','固定LF結合機構の全hash継承',size=2000000) as j:
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
