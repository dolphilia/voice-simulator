"""共有HMM全体の比較を構築する。非因子は固定し、モデル固有時計を明示する。"""
import ast
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

POOL=dict(candidate_pool_short=['灰の粒を拾う。','村の橋を渡る。','坂の石を避ける。','竿の糸を結ぶ。','門の鍵を探す。','松の影を歩く。','麦の穂を揺らす。','蝉の声を聞く。','沼の縁を回る。','島の丘へ登る。','鯛の骨を抜く。','谷の霜を踏む。'],
 candidate_pool_long=['客が帰った後、母は玄関の花瓶を拭いて棚へ戻した。','畑の脇に立った兄は、伸びた豆の茎を支柱に結びつけた。','暗くなる前に、祖父は庭の隅に積んだ薪を家へ運んだ。','川沿いを歩く姉は、水面に映った雲を見ながら足を止めた。','市場の帰りに寄った店で、叔父は小さな鈴を一つ買った。','道の角で落ち葉を集める父は、風が弱まるのを待っていた。','箱を開けた弟は、中に入っていた絵を机の上に広げた。','昼過ぎに駅へ着いた友人は、窓口で地図を受け取った。','庭の門を閉めた叔母は、台所の窓から雲の様子を眺めた。','川の向こうへ渡る船に乗る前、妹は鞄の紐を結び直した。','廊下に置かれた椅子を運ぶ兄は、壁にぶつからないよう気をつけた。','夕飯の支度を始めた祖母は、畑で採れた芋を洗って鍋に入れた。'])

PROFILE_PATCH=r'''        physical=[p.resolve() for p in (HERE/'runtime-bundle').rglob('*') if p.is_file() and p.is_symlink()]
        text += '(allow file-read-data ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\n'
        text += '(allow file-read-metadata ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\n'
'''

MODEL_PAIR=r'''                if native_meta:
                    for key in ['settings','output_gain']:
                        assert meta[key]==native_meta[key],key
                    assert meta['shared_acoustic_model']=='tohoku' and native_meta['shared_acoustic_model']=='mei'
                    assert meta['voice_sha256']!=native_meta['voice_sha256']
                    assert len(meta['duration'])==len(native_meta['duration'])==len(row['full_context_labels'])*5
                    assert meta['model_original_states_and_parameters_preserved_except_uniform_LF0']
                    assert meta['output_parameter_hashes'][0]!=native_meta['output_parameter_hashes'][0]
                else:
                    native_meta=meta
'''

PAIR_AUDIT=r'''"""全32対で各モデル固有の状態長・列・校正と固定音素支持を確認する。"""
import sys,json,hashlib
from pathlib import Path
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text())
import numpy as np
def ah(v):return hashlib.sha256(np.asarray(v,dtype='<f8').tobytes()).hexdigest()
rows=[]
for row in p['rows']:
 for condition,cfg in p['conditions'].items():
  base=here/'render'/row['id']/condition;items={}
  for method in ('native','tohoku'):
   with np.load(base/(method+'.npz'),allow_pickle=False) as z:a={k:z[k].copy() for k in ('mcp','lf0','lpf','duration')}
   r=json.loads((base/(method+'.json')).read_text());meta=r['meta'];n=len(a['mcp'])
   assert a['mcp'].shape==(n,35) and a['lf0'].shape==(n,1) and a['lpf'].shape==(n,31)
   assert all(np.isfinite(a[k]).all() for k in a) and a['duration'].shape==(len(row['full_context_labels'])*5,)
   assert np.all(a['duration']>=1) and np.all(a['duration']==np.floor(a['duration'])) and int(a['duration'].sum())==n
   assert a['duration'].tolist()==meta['duration'] and [ah(a[k]) for k in ('mcp','lf0','lpf')]==meta['output_parameter_hashes']
   voiced=a['lf0'][:,0]>0;assert voiced.any() and np.all(a['lf0'][~voiced,0]==-1e10)
   median=float(np.exp(np.median(a['lf0'][voiced,0])));assert abs(median-cfg['requested_f0'])<=1e-9
   assert meta['native_parameter_hashes'][0]==meta['output_parameter_hashes'][0] and meta['native_parameter_hashes'][2]==meta['output_parameter_hashes'][2]
   assert meta['model_original_states_and_parameters_preserved_except_uniform_LF0'] and meta['invariants_pass']
   assert meta['conversion']['original_excitation_sha256']==meta['conversion']['processed_excitation_sha256']
   items[method]=(a,r)
  a,ra=items['native'];z,rz=items['tohoku'];assert ra['measurement']['support']==rz['measurement']['support']
  assert all(0<=index<len(row['full_context_labels']) for index in ra['measurement']['support'])
  assert ra['meta']['voice_sha256']!=rz['meta']['voice_sha256'] and not np.array_equal(a['mcp'],z['mcp'])
  rows.append(dict(id=row['id']+'/'+condition,frames_checked_native=len(a['mcp']),frames_checked_candidate=len(z['mcp']),frames_checked=len(a['mcp'])+len(z['mcp']),excluded_frames=0,
   each_model_duration_and_parameter_hashes_exact=True,each_model_MCP_LPF_and_voicing_control_preserved=True,fixed_phoneme_index_support_exact=True,
   model_specific_time_and_acoustics_are_intended_factor=True,source_clock_equality_between_models_claimed=False,passed=True))
assert len(rows)==32
print(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v['frames_checked'] for v in rows),saved_arrays_only=True,no_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))
'''

def main():
 b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
 mechanism=ROOT/'campaigns/nas-hts-tohoku-mechanism-20261008-v1';assert read(mechanism/'aggregate-summary.json')['mechanical_fixture_passed']
 driver=(ROOT/'hts_output_bound_comparison_20261008.py').read_text().replace('hts_output_bound','hts_tohoku').replace('hts-output-bound','hts-tohoku').replace('progress-0087.json','progress-0100.json')
 driver=driver.replace("PARENT=ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1'","PARENT=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'")
 driver=constant(driver,'POOL',repr(POOL));driver=constant(driver,'PROFILE_PATCH',repr(PROFILE_PATCH)) if 'PROFILE_PATCH=' in driver else driver.replace('@contextmanager', 'PROFILE_PATCH='+repr(PROFILE_PATCH)+'\nMODEL_PAIR='+repr(MODEL_PAIR)+'\n@contextmanager',1)
 start=driver.index('    reg=dict(');end=driver.index('    b.start_campaign',start)
 driver=driver[:start]+'''    reg=dict(campaign=NAME,status='registered_before_output',question='別の公開共有HMM全モデルは未知日本語の内容/工学保護を改善し、固定支持の欠測を増やさず独立生成できるか。',
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
''' +driver[end:]
 start=driver.index("        for n in ('paths.py'");end=driver.index('    print(dict(registered=True',start)
 driver=driver[:start]+'''        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-output-bound-comparison','hts-tohoku-comparison').replace('bound-fresh','tohoku-fresh')
            if n=='controller.py':
                a=text.index('                if native_meta:');z=text.index("                if method.startswith('hts_'):",a);text=text[:a]+MODEL_PAIR+text[z:]
                line=next(line for line in text.splitlines() if 'identity.json' in line);assert text.count(line)==1
                text=text.replace(line,line+'\\n'+PROFILE_PATCH)
            if n=='runtime.py':
                text=text.replace('from bounded_output import synthesize as shape_synthesize','from shape_arrays import synthesize as shape_synthesize').replace("METHODS=['native','soft_bound']","METHODS=['native','tohoku']")
                text=text.replace("    with Engine(row, ROOT / 'mei_normal.htsvoice', speed=speed,","    voice='mei_normal.htsvoice' if method=='native' else 'tohoku-f01-neutral.htsvoice'\\n    model='mei' if method=='native' else 'tohoku'\\n    with Engine(row, ROOT / voice, speed=speed,")
                text=text.replace('raw,conversion=shape_synthesize(params,settings,method)',"raw,conversion=shape_synthesize(params,settings,'native')\\n        conversion.update(renderer='原HTS-MLSA',source_phase_rule='変更なし',phase_is_frequency_dependent=False,shared_HMM_model=model,model_specific_time_and_streams=True)")
                text=text.replace('output_gain=.25, conversion=conversion,',"output_gain=.25, conversion=conversion, shared_acoustic_model=model, voice_sha256=hashlib.sha256((ROOT/voice).read_bytes()).hexdigest(), model_original_states_and_parameters_preserved_except_uniform_LF0=bool(invariants),")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
''' +driver[end:]
 start=driver.index("        assert digest(HERE/'shape.dylib')");end=driver.index("    with job(b,'setup','全履歴",start)
 driver=driver[:start]+'''        bundle=HERE/'runtime-bundle';mapping={n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:PARENT/'runtime-bundle'/n for n in ('acoustics.py',)})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():
            if n=='tohoku-f01-neutral.htsvoice':b.write_data(bundle/n,p.read_bytes(),j)
            else:b.write(bundle/n,p.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(bundle/'shape.dylib'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
''' +driver[end:]
 driver=driver.replace('固定出力制御','全共有HMM比較').replace('固定出力上限','全共有HMM').replace('固定出力','全共有HMM').replace('原HTSの最終振幅だけを固定解析式で変更','別の共有HMM全モデルを対比')
 ast.parse(driver)
 close=(ROOT/'hts_output_bound_closeout_20261008.py').read_text().replace('hts_output_bound_comparison','hts_tohoku_comparison').replace('hts-output-bound-comparison','hts-tohoku-comparison').replace('progress-0088.json','progress-0101.json')
 close=constant(close,'ALL_FRAMES',repr(PAIR_AUDIT));close=close.replace("'soft_bound'","'tohoku'")
 needle="    assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib') and digest(HERE/'shape.c')==digest(ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1/shape.c')"
 assert close.count(needle)==1;close=close.replace(needle,"    for name,h in read(MECHANISM/'runtime-bundle/manifest.json')['files'].items():assert digest(HERE/'runtime-bundle'/name)==h,name")
 close=close.replace('保存全32対の列・出力式・上限と恒等域の物理照合','保存全32対の各モデル状態長・全列・校正・音素支持の物理照合')
 start=close.index("                assert a['meta']['output_parameter_hashes']");end=close.index('        assert len(pairs)==32',start)
 close=close[:start]+'''                assert a['measurement']['support']==z['measurement']['support']
                assert a['meta']['settings']==z['meta']['settings'] and a['meta']['output_gain']==z['meta']['output_gain']==.25
                assert a['meta']['shared_acoustic_model']=='mei' and z['meta']['shared_acoustic_model']=='tohoku'
                assert a['meta']['voice_sha256']!=z['meta']['voice_sha256']
                for r in (a,z):
                    assert r['meta']['model_original_states_and_parameters_preserved_except_uniform_LF0'] and r['meta']['conversion']['source_method']=='native'
                    assert r['meta']['conversion']['original_excitation_sha256']==r['meta']['conversion']['processed_excitation_sha256']
                    assert r['meta']['conversion']['render_calls_including_internal_MLSA']==1
                pairs.append(dict(id=key+'tohoku',each_model_internal_controls_preserved=True,model_specific_time_and_streams_intentionally_changed=True,fixed_phoneme_index_support_exact=True,
                    native_duration_frames=sum(a['meta']['duration']),candidate_duration_frames=sum(z['meta']['duration']),source_clock_equality_between_models_claimed=False,output_changed=a['wav_sha256']!=z['wav_sha256']))
''' +close[end:]
 close=close.replace('output_factor_pairs=pairs','full_model_factor_pairs=pairs')
 close=close.replace("methodological_limits='旧DIO/全体ACFの操作的条件と固定振幅上限。独立式のfloat32誤差はbyte一致ではない。自然さ/動的pitch/境界のtruthではない。'","methodological_limits='旧DIO/全体ACFの操作的条件。全HMM対比でモデル固有の時間/有声/源が違う。native音素index支持を候補の時間軸に適用する。自然さ/動的pitch/境界のtruthではない。'")
 close=close.replace("next='出力上限のE0と内容/ピッチ保護を区別して全件保持する。係数の同コホート救済を行わず、別の声道表現または測定資格へ進む。'","next='全モデルの工学/二ASR結果を全分母で保持。全件保護と改善が確認できれば独立新入力へ別登録し、未通過を同コホートのstyle/補間/係数/gainで救済しない。資格不足の知覚を採択根拠にしない。'")
 start=close.index("        lines=['# 原HTS");end=close.index("        b.write(HERE/'report.md'",start)
 close=close[:start]+'''        lines=['# 原Meiと公開Tohoku共有HMM全モデルの比較','','新16文×2条件×2モデル64波形。全HMMを交換するため、MCP/LF0/LPF/duration/MSD/GVはモデル固有。辞書・labels・速度/指定中央値・MLPG/HTS・resample/fade/gain.25を共通化した。nativeの音素index支持を固定し、candidate固有の時間軸へ適用。通常/隔離64組・CLI4・実拒否を確認した。','','|モデル|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'二モデルの保存全{physical["all_frames_checked"]}frameで各モデル固有の状態長合計・列/hash・有限性・指定LF0中央値と固定音素支持を照合した。二モデル間の源時計/列一致や同標本の対比は主張しない。','',
            'HTS voice tohoku-f01、Copyright 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University。[公式配布](https://github.com/icn-lab/htsvoice-tohoku-f01)・[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。モデルは不改変、生成時の一様LF0制御と共通resample/fade/gainを変更として表示。Meiの元CC BY 3.0表示もbundleに保持する。提供者の推奨を主張しない。','',
            '旧31方式・支持31,601・欠測249・二ASR33群と凍結経路を保持。日本語知覚資格なし・P5未開封・品質未達。最終採択なし。','',
            '全件研究保護: '+str(research_gates),summary['next'],'']
''' +close[end:]
 close=close.replace('固定出力制御','全共有HMM比較');ast.parse(close)
 dp=ROOT/'hts_tohoku_comparison_20261008.py';cp=ROOT/'hts_tohoku_closeout_20261008.py';b.write(dp,driver.encode());b.write(cp,close.encode())
 b.save(ROOT/'tohoku-comparison-source-derivation.json',dict(generator_sha256=digest(Path(__file__)),source_sha256=digest(dp),closeout_sha256=digest(cp),parent_controller_source_sha256=digest(ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1/controller.py'),
     full_model_time_and_streams_intentionally_changed=True,native_phoneme_index_support_frozen=True,total_without_retry=dict(render=196,dsp=420,ai=128),old_results_unchanged=True))
 print('全共有HMMの64比較・固定音素支持・全件物理終了監査を構築',flush=True)

if __name__=='__main__':main()
