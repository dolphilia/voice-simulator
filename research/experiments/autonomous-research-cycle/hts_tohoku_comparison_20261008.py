"""別の共有HMM全モデルを対比し、未知日本語64波形を比較する。"""
import ast,hashlib,json,os,subprocess,importlib.util,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-tohoku-comparison-20261008-v1'
NAME='hts-tohoku-comparison-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
MECHANISM=ROOT/'campaigns/nas-hts-tohoku-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL={'candidate_pool_short': ['灰の粒を拾う。', '村の橋を渡る。', '坂の石を避ける。', '竿の糸を結ぶ。', '門の鍵を探す。', '松の影を歩く。', '麦の穂を揺らす。', '蝉の声を聞く。', '沼の縁を回る。', '島の丘へ登る。', '鯛の骨を抜く。', '谷の霜を踏む。'], 'candidate_pool_long': ['客が帰った後、母は玄関の花瓶を拭いて棚へ戻した。', '畑の脇に立った兄は、伸びた豆の茎を支柱に結びつけた。', '暗くなる前に、祖父は庭の隅に積んだ薪を家へ運んだ。', '川沿いを歩く姉は、水面に映った雲を見ながら足を止めた。', '市場の帰りに寄った店で、叔父は小さな鈴を一つ買った。', '道の角で落ち葉を集める父は、風が弱まるのを待っていた。', '箱を開けた弟は、中に入っていた絵を机の上に広げた。', '昼過ぎに駅へ着いた友人は、窓口で地図を受け取った。', '庭の門を閉めた叔母は、台所の窓から雲の様子を眺めた。', '川の向こうへ渡る船に乗る前、妹は鞄の紐を結び直した。', '廊下に置かれた椅子を運ぶ兄は、壁にぶつからないよう気をつけた。', '夕飯の支度を始めた祖母は、畑で採れた芋を洗って鍋に入れた。']}
PROFILE_PATCH="        physical=[p.resolve() for p in (HERE/'runtime-bundle').rglob('*') if p.is_file() and p.is_symlink()]\n        text += '(allow file-read-data ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'\n        text += '(allow file-read-metadata ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'\n"
MODEL_PAIR="                if native_meta:\n                    for key in ['settings','output_gain']:\n                        assert meta[key]==native_meta[key],key\n                    assert meta['shared_acoustic_model']=='tohoku' and native_meta['shared_acoustic_model']=='mei'\n                    assert meta['voice_sha256']!=native_meta['voice_sha256']\n                    assert len(meta['duration'])==len(native_meta['duration'])==len(row['full_context_labels'])*5\n                    assert meta['model_original_states_and_parameters_preserved_except_uniform_LF0']\n                    assert meta['output_parameter_hashes'][0]!=native_meta['output_parameter_hashes'][0]\n                else:\n                    native_meta=meta\n"
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
    reg=dict(campaign=NAME,status='registered_before_output',question='別の公開共有HMM全モデルは未知日本語の内容/工学保護を改善し、固定支持の欠測を増やさず独立生成できるか。',
        variants=['native','tohoku'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor='Mei normalと公式Tohoku-F01 neutralの全共有HMM対比。MCP/LF0/LPF/duration/MSD/GVはモデル固有。源時計/列がモデル間で一致するとは扱わない。',
        fixed_control='辞書/同labels、速度/指定F0中央値、各モデル内のMCP/LPF/有声mask・相対LF0保持、MLPG/原HTS/alpha.55/beta0/48k/240/24k resample/12msfade/gain.25。',
        input='全履歴に非衝突の新16文×2条件×2モデル64。候補poolは出力前固定、最初の非衝突/valid8短8長を選ぶ。保護資料本文を読まない。',
        support='nativeの音素index支持を一度固定してcandidate固有の状態時間軸へ適用。candidateの有声/測定による再選別なし。欠測は不通過、旧31方式/31,601支持/249欠測/二ASR33群を保持。',
        gates=dict(engineering='全件E0、旧DIO/全体ACF±1半音/confidence≥.6/固定音素支持3以上/不変量。',content='二ASR各33群がnative以下、悪化相殺なし。',
            independence='全64通常/隔離・CLI4・論理/物理資料/通信の実拒否。bundle共有資産だけ許可。',
            physical='全32対・各モデル全frameの有限/形状/状態長合計/保存hash/指定LF0中央値、各モデル内MCP/LPF保持、固定音素支持一致。HMM全体の時間・音響差は意図的。',
            measurement_scope='旧工学の操作的資格のみ。モデルの有声時刻は別々で同標本対比ではない。源周期の観測を知覚pitch/自然さへ拡張しない。'),
        estimates=dict(comparison_render=64,comparison_dsp=192,isolation_render=128,isolation_dsp=128,CLI_render=4,CLI_dsp=4,physical_dsp=96,two_ASR_ai=128,
            total_without_retry=dict(render=196,dsp=420,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        source=dict(mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),original_HTS_binary_sha256=digest(MECHANISM/'runtime-bundle/shape.dylib'),
            candidate_model_sha256=digest(MECHANISM/'runtime-bundle/tohoku-f01-neutral.htsvoice'),native_model_sha256=digest(MECHANISM/'runtime-bundle/mei_normal.htsvoice')),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,coefficient_search_after_output=False,
        controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_tohoku_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,old_failed_routes_kept=True)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','全共有HMM比較の新入力・全比較費・対照を生成前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-output-bound-comparison','hts-tohoku-comparison').replace('bound-fresh','tohoku-fresh')
            if n=='controller.py':
                a=text.index('                if native_meta:');z=text.index("                if method.startswith('hts_'):",a);text=text[:a]+MODEL_PAIR+text[z:]
                line=next(line for line in text.splitlines() if 'identity.json' in line);assert text.count(line)==1
                text=text.replace(line,line+'\n'+PROFILE_PATCH)
            if n=='runtime.py':
                text=text.replace('from bounded_output import synthesize as shape_synthesize','from shape_arrays import synthesize as shape_synthesize').replace("METHODS=['native','soft_bound']","METHODS=['native','tohoku']")
                text=text.replace("    with Engine(row, ROOT / 'mei_normal.htsvoice', speed=speed,","    voice='mei_normal.htsvoice' if method=='native' else 'tohoku-f01-neutral.htsvoice'\n    model='mei' if method=='native' else 'tohoku'\n    with Engine(row, ROOT / voice, speed=speed,")
                text=text.replace('raw,conversion=shape_synthesize(params,settings,method)',"raw,conversion=shape_synthesize(params,settings,'native')\n        conversion.update(renderer='原HTS-MLSA',source_phase_rule='変更なし',phase_is_frequency_dependent=False,shared_HMM_model=model,model_specific_time_and_streams=True)")
                text=text.replace('output_gain=.25, conversion=conversion,',"output_gain=.25, conversion=conversion, shared_acoustic_model=model, voice_sha256=hashlib.sha256((ROOT/voice).read_bytes()).hexdigest(), model_original_states_and_parameters_preserved_except_uniform_LF0=bool(invariants),")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(dict(registered=True,new_scientific_outputs=0),flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json')
    assert digest(Path(__file__))==reg['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','同一原HTSと全共有HMM比較の閉じた共有bundle',size=16000000) as j:
        bundle=HERE/'runtime-bundle';mapping={n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:PARENT/'runtime-bundle'/n for n in ('acoustics.py',)})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():
            if n=='tohoku-f01-neutral.htsvoice':b.write_data(bundle/n,p.read_bytes(),j)
            else:b.write(bundle/n,p.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(bundle/'shape.dylib'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
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
    b.save(ROOT/'progress-0100.json',dict(active_campaign=NAME,next='登録push→機構hash継承→比較64→通常隔離/CLI→二ASR→全件物理照合/終了',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(prepared=True,new_scientific_outputs=0),flush=True)
def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs'];reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256']
    if stage=='fixture':
        with job(b,'audit','全共有HMM機構の全hash継承',size=2000000) as j:
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
