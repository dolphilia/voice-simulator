"""限定LF結合を新日本語へ展開し、元native/全支持/二ASRを別登録する。"""
import ast
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant
from prepare_tohoku_comparison_20261008 import PROFILE_PATCH

POOL=dict(candidate_pool_short=['砂の瓶を振る。','梅の実を漬ける。','窓の網を張る。','襟の糸を抜く。','庭の杭を打つ。','池の鯉を数える。','畑の豆を蒸す。','丘の鐘を鳴らす。','櫓の板を削る。','舟の帆を畳む。','皿の胡麻を撒く。','柿の枝を束ねる。'],
 candidate_pool_long=['風が静まった頃、祖母は裏庭に干した布を取り込んだ。','朝の支度を終えた姉は、机の端に置いた帳面を鞄に入れた。','道に残った水を避けながら、父は市場へ向かって歩いた。','小屋の扉を開けた兄は、壁に掛けられた縄を手に取った。','畑で集めた豆を広げると、叔母は傷んだ粒を一つずつ除いた。','窓辺に座った友人は、遠くから聞こえる鐘に耳を傾けた。','雨雲が去った後、妹は門の前に落ちた葉を掃き集めた。','昼の休みに戻った叔父は、台所で冷たい水を一杯飲んだ。','灯りを点けた祖父は、棚から取り出した地図を広げた。','港から歩いて帰る母は、路地の角で近所の人と話した。','木陰で一息ついた弟は、靴に入った砂を静かに払った。','村を出る前に、友人は橋の上から川の流れを眺めた。'])

REG=r'''    reg=dict(campaign=NAME,status='registered_before_output',question='固定LFを有声LPF入力へ結合した候補が、新日本語で原nativeの内容/旧工学/固定支持を保持できるか。',
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
'''

PAIR=r'''"""保存全32対の四列と源clock/noise/phase/固定支持を物理照合する。再生成なし。"""
import sys,json
from pathlib import Path
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text())
import numpy as np
rows=[]
for row in p['rows']:
 for condition in p['conditions']:
  base=here/'render'/row['id']/condition
  with np.load(base/'native.npz',allow_pickle=False) as z:a={k:z[k].copy() for k in ('mcp','lf0','lpf','duration')}
  with np.load(base/'lf.npz',allow_pickle=False) as z:assert all(np.array_equal(z[k],v) for k,v in a.items())
  n=json.loads((base/'native.json').read_text());c=json.loads((base/'lf.json').read_text());tn=n['meta']['conversion'];tc=c['meta']['conversion']
  for key in ('source_clock_hashes','original_excitation_sha256','noise_sha256','LF_phase_sha256'):assert tn[key]==tc[key],key
  assert tn['original_excitation_sha256']==tn['processed_excitation_sha256'] and tc['processed_excitation_intentionally_changed']
  assert tn['render_calls_including_internal_MLSA']==1 and tc['render_calls_including_internal_MLSA']==2
  assert n['measurement']['support']==c['measurement']['support'] and tc['LF_fixed_time_ratios']==[.4,.6,.05]
  rows.append(dict(id=row['id']+'/'+condition,all_saved_parameters_exact=True,frames_checked=len(a['mcp']),excluded_frames=0,original_excitation_clock_noise_phase_exact=True,
   fixed_support_exact=True,processed_excitation_changed=tn['processed_excitation_sha256']!=tc['processed_excitation_sha256'],passed=True))
assert len(rows)==32
print(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v['frames_checked'] for v in rows),saved_arrays_and_metadata_only=True,no_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))
'''

def main():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    mechanism=ROOT/'campaigns/nas-hts-lf-coupling-20261008-v1';assert read(mechanism/'aggregate-summary.json')['mechanical_fixture_passed']
    driver=(ROOT/'hts_output_bound_comparison_20261008.py').read_text().replace('hts_output_bound','hts_lf').replace('hts-output-bound','hts-lf').replace('progress-0087.json','progress-0107.json')
    driver=driver.replace("MECHANISM=ROOT/'campaigns/nas-hts-lf-mechanism-20261008-v1'","MECHANISM=ROOT/'campaigns/nas-hts-lf-coupling-20261008-v1'")
    driver=constant(driver,'POOL',repr(POOL));driver=driver.replace('@contextmanager','PROFILE_PATCH='+repr(PROFILE_PATCH)+'\n@contextmanager',1)
    start=driver.index('    reg=dict(');end=driver.index('    b.start_campaign',start);driver=driver[:start]+REG+driver[end:]
    start=driver.index("        for n in ('paths.py'");end=driver.index('    print(dict(registered=True',start)
    driver=driver[:start]+'''        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-allpass-comparison','hts-lf-comparison').replace('allpass-fresh','lf-fresh')
            if n=='controller.py':
                assert text.count('from paths import *')==1;text=text.replace('from paths import *','from paths import *\\nfrom paths import job as managed_job',1)
                text=text.replace('new_render_calls=64, internal_MLSA_helpers=0','new_render_calls=96, internal_MLSA_helpers=32').replace('    count=64\\n','    count=96\\n')
                text=text.replace("'通常/隔離batch64 ' + mode, count=64","'通常/隔離batch64 ' + mode, count=96")
                text=text.replace("for r in manifest['records']) == 64","for r in manifest['records']) == 96")
                text=text.replace("'CLI ' + mode + '/' + request['id'], count=1","'CLI ' + mode + '/' + request['id'], count=1 if request['method']=='native' else 2")
                text=text.replace('new_render_calls=132, new_DSP_calls=132, internal_MLSA_helpers=0','new_render_calls=198, new_DSP_calls=132, internal_MLSA_helpers=66')
                needle="                    assert meta['conversion']['original_excitation_sha256'] == native_meta['conversion']['original_excitation_sha256']"
                assert text.count(needle)==1;text=text.replace(needle,needle+"\\n                    assert meta['conversion']['noise_sha256']==native_meta['conversion']['noise_sha256']\\n                    assert meta['conversion']['LF_phase_sha256']==native_meta['conversion']['LF_phase_sha256']")
                line=next(line for line in text.splitlines() if 'identity.json' in line);assert text.count(line)==1;text=text.replace(line,line+'\\n'+PROFILE_PATCH)
            if n=='runtime.py':text=text.replace("METHODS=['native','allpass']","METHODS=['native','lf']")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        for n in ('shape.c','shape_arrays.py','HTS-BSD-NOTICE.txt','lf_source.c'):b.write(HERE/n,(MECHANISM/n).read_bytes(),j)
        b.write_data(HERE/'shape.dylib',(MECHANISM/'runtime-bundle/shape.dylib').read_bytes(),j)
        for n in ('HTS_hidden.h','HTS_engine.h','HTS_vocoder_shaped.c'):b.write(HERE/'vendor'/n,(MECHANISM/'vendor'/n).read_bytes(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
''' +driver[end:]
    start=driver.index("        assert digest(HERE/'shape.dylib')");end=driver.index("    with job(b,'setup','全履歴",start)
    driver=driver[:start]+'''        assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib')
        bundle=HERE/'runtime-bundle';mapping={n:PARENT/'runtime-bundle'/n for n in read(PARENT/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():b.write(bundle/n,p.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(HERE/'shape.dylib'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
''' +driver[end:]
    driver=driver.replace('固定出力制御','固定LF結合').replace('固定出力上限','固定LF結合').replace('固定出力','固定LF結合').replace('原HTSの最終振幅だけを固定解析式で変更','原HTSの有声LPF入力だけを固定LFで変更')
    ast.parse(driver)
    close=(ROOT/'hts_allpass_closeout_20261008.py').read_text().replace('hts_allpass_comparison','hts_lf_comparison').replace('hts-allpass-comparison','hts-lf-comparison').replace('progress-0084.json','progress-0108.json')
    close=constant(close,'ALL_FRAMES',repr(PAIR));close=close.replace("'allpass'","'lf'")
    close=close.replace("manifest['new_render_calls']==64 and runtime['new_render_calls']==132","manifest['new_render_calls']==96 and runtime['new_render_calls']==198")
    close=close.replace("digest(MECHANISM/'shape.dylib')","digest(MECHANISM/'runtime-bundle/shape.dylib')")
    close=close.replace("'保存全32対のMCP/LF0/LPF/duration物理照合',64","'保存全32対の四列/源時計/noise/phase/支持の物理照合',96")
    close=close.replace("and z['meta']['conversion']['source_allpass_pole']==.95","and z['meta']['conversion']['LF_fixed_time_ratios']==[.4,.6,.05]")
    close=close.replace("z['meta']['conversion']['render_calls_including_internal_MLSA']==1","z['meta']['conversion']['render_calls_including_internal_MLSA']==2")
    needle="                assert a['meta']['conversion']['original_excitation_sha256']==z['meta']['conversion']['original_excitation_sha256']"
    assert close.count(needle)==1;close=close.replace(needle,needle+"\n                assert a['meta']['conversion']['noise_sha256']==z['meta']['conversion']['noise_sha256'] and a['meta']['conversion']['LF_phase_sha256']==z['meta']['conversion']['LF_phase_sha256']")
    close=close.replace('processed_excitation_is_intended_factor=True','processed_LF_excitation_is_intended_factor=True,noise_and_phase_exact=True')
    close=close.replace("methodological_limits='原工学DIO/全体ACFと人工オールパスLTI資格。人工YIN40ms資格をHTSや知覚へ拡張しない。'","methodological_limits='旧工学DIO/全体ACFの操作的条件と人工LF結合資格だけ。有限/動的周期面積0、aliasing、日本語知覚/境界truthの資格はない。'")
    close=close.replace("next='源の位相因子と振幅/内容保護を全件で保持する。不通過を同コホートのpole調整で救済せず、別の共有生成制御または独立測定へ進む。'","next='LFの工学/固定支持/二ASRを全分母で保持。不通過を同コホートの係数/phase/LPF/gainで救済しない。第5回分岐に従い独立な調音source-tract制御か異なる共有文脈/韻律表現へ進む。'")
    start=close.index("        lines=['# 原HTS");end=close.index("        b.write(HERE/'report.md'",start)
    close=close[:start]+'''        lines=['# 原HTSとLPF前の固定LF声門流微分の比較','','新16文×2条件×2方式64波形。元有声impulseだけを固定LFへ置換し、MCP/LF0/LPF/duration、元clock/noise/phase、MLSA/gain.25を保持した。候補は比較用native観測を内部で一度生成し、その費用も数える。全64通常/隔離・CLI4・実読取/通信拒否を照合した。','','|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'保存全{physical["all_frames_checked"]}frameの三stream/durationと全32対の源clock/原励振/noise/phase/固定支持を確認した。周期関数の面積0・clock一致を処理後のpitchや自然さへ読み替えない。','',
            'Tp=.4/Te=.6/Ta=.05/Ee=1と連続周期RMS尺度を固定。有限/時間変動の面積0、aliasing、日本語知覚の資格は未確認。出力後の係数/phase/LPF/gain探索なし。','',
            '旧31方式・支持31,601/欠測249・二ASR33群と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達・最終採択なし。','',
            '一次資料: [Fant, Liljencrants & Lin (1985), LF model](https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf)。独自LF式と変更したHTS-BSD励振を明示する。','', '全件研究保護: '+str(research_gates),summary['next'],'']
''' +close[end:]
    close=close.replace('FIR経路の内容保護','LF源の内容保護');ast.parse(close)
    dp=ROOT/'hts_lf_comparison_20261008.py';cp=ROOT/'hts_lf_closeout_20261008.py';b.write(dp,driver.encode());b.write(cp,close.encode())
    b.save(ROOT/'lf-comparison-source-derivation.json',dict(generator_sha256=digest(Path(__file__)),source_sha256=digest(dp),closeout_sha256=digest(cp),parent_controller_source_sha256=digest(ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1/controller.py'),
        reservation_alias_bound_in_initial_source=True,output_waves=64,total_without_retry=dict(render=294,dsp=420,ai=128),internal_MLSA_helpers_counted=True,LF_coefficients_and_phase_frozen=True,old_results_unchanged=True))
    print('固定LF源の64比較と源clock/noise/phase/全保存列の終了監査を構築',flush=True)
if __name__=='__main__':main()
