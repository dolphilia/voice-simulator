"""固定文脈韻律を新16文へ展開し、旧操作的ゲートと二ASRで全分母を比較する。"""
import ast
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

POOL=dict(candidate_pool_short=['櫛の歯を洗う。','柚子の皮を干す。','瓶の蓋を回す。','靴の紐を結ぶ。','藁の束を運ぶ。','鉢の土を均す。','絹の帯を巻く。','雲の影を追う。','坂の石を拾う。','笛の音を聞く。','杉の葉を集める。','杖の先を拭く。'],
 candidate_pool_long=['霧が晴れた朝、祖父は坂の途中にある畑へ道具を運んだ。','仕事を終えた母は、店の前で待っていた友人に手を振った。','船が岸を離れると、弟は鞄から取り出した地図を広げた。','庭に置いた鉢の土を確かめて、姉は小さな苗に水を注いだ。','駅から帰った兄は、窓辺の椅子に座って靴の紐を解いた。','日が傾く頃、叔母は台所に並べた瓶の蓋を一つずつ閉めた。','川から吹く風を感じながら、父は橋の近くで友人を待った。','門の外から声がすると、妹は手に持った布を棚へ戻した。','村の祭りが終わった後、叔父は広場に残された箱を運んだ。','雨音が弱くなると、祖母は窓を開けて庭の木を眺めた。','海辺を歩いていた友人は、波が運んできた貝を拾い上げた。','本を読み終えた姉は、机の灯りを消して廊下へ出た。'])

REG=r'''    reg=dict(campaign=NAME,status='registered_before_output',question='ラベルからの固定句/アクセント応答は、新日本語でnativeの工学・固定支持・内容を保持できるか。',
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
'''

PAIR=r'''"""保存全32対の保持因子と候補LF0の独立scalar式を全frame照合。波形再生成なし。"""
import sys,json,math
from pathlib import Path
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text())
import numpy as np
rows=[]
for row in p['rows']:
 for condition,q in p['conditions'].items():
  base=here/'render'/row['id']/condition
  with np.load(base/'native.npz',allow_pickle=False) as z:n={k:z[k].copy() for k in ('mcp','lf0','lpf','duration')}
  with np.load(base/'fujisaki.npz',allow_pickle=False) as z:c={k:z[k].copy() for k in n}
  assert all(np.array_equal(n[k],c[k]) for k in ('mcp','lpf','duration'));mask=n['lf0'][:,0]>0
  assert np.array_equal(mask,c['lf0'][:,0]>0) and n['lf0'][~mask].tobytes()==c['lf0'][~mask].tobytes()
  nm=json.loads((base/'native.json').read_text());cm=json.loads((base/'fujisaki.json').read_text());detail=cm['meta']['control'];cmd=detail['commands']
  assert detail['parameters']==dict(alpha=3.,beta=20.,gamma=.9,Ap_seconds=.15,Aa=.25,phrase_lead_seconds=.2)
  def gp(t):return 9.*t*math.exp(-3.*t) if t>=0 else 0.
  def ga(t):return min(1.-(1.+20.*t)*math.exp(-20.*t),.9) if t>=0 else 0.
  shape=np.array([sum(.15*gp(i*.005-u) for u in cmd['phrase_times'])+sum(.25*(ga(i*.005-u)-ga(i*.005-v)) for u,v in cmd['accent_times']) for i in range(len(n['lf0']))])
  expected=shape[mask]+detail['log_offset'];error=float(np.max(np.abs(expected-c['lf0'][mask,0])))
  assert error<=1e-12 and abs(np.median(c['lf0'][mask,0])-math.log(q['requested_f0']))<=2e-15
  assert not np.array_equal(n['lf0'][mask],c['lf0'][mask]) and not detail['native_LF0_values_used_for_shape']
  assert nm['measurement']['support']==cm['measurement']['support']
  for key in ('duration','msd','settings','state_sha256','variance_sha256','native_parameter_hashes'):assert nm['meta'][key]==cm['meta'][key]
  rows.append(dict(id=row['id']+'/'+condition,all_saved_retained_parameters_exact=True,LF0_intentionally_changed=True,independent_scalar_LF0_max_error=error,
                   frames_checked=len(n['mcp']),excluded_frames=0,voiced_mask_and_sentinel_exact=True,fixed_support_exact=True,passed=True))
assert len(rows)==32
print(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v['frames_checked'] for v in rows),saved_arrays_and_metadata_only=True,no_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))
'''

def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)

def controller(text):
    text=replace_once(text,'from paths import *','from paths import *\nfrom paths import job as managed_job')
    for line in ("                    assert meta['output_parameter_hashes'] == native_meta['output_parameter_hashes']",
                 "                    assert meta['conversion']['source_clock_hashes'] == native_meta['conversion']['source_clock_hashes']",
                 "                    assert meta['conversion']['original_excitation_sha256'] == native_meta['conversion']['original_excitation_sha256']"):
        text=replace_once(text,line+'\n','')
    needle="                    assert meta['output_parameter_hashes'][0] == native_meta['output_parameter_hashes'][0]"
    text=replace_once(text,needle,needle+"\n                    assert meta['output_parameter_hashes'][2]==native_meta['output_parameter_hashes'][2]\n                    assert meta['control']['MCP_LPF_duration_and_MSD_unchanged']\n                    assert not meta['control']['native_LF0_values_used_for_shape']\n                    assert abs(meta['generated_lf0_median_hz']/q['requested_f0']-1.)<=1e-14")
    text=replace_once(text,"               (HERE / 'runtime-archives/normal.zip').resolve()]","               (HERE / 'runtime-archives/normal.zip').resolve(), logical.with_suffix('.npz'), logical.with_suffix('.npz').resolve()]")
    text=replace_once(text,"open(p,'rb').close();a.append(False)","open(p,'rb').read(1);a.append(False)")
    return text

def main():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    mechanism=ROOT/'campaigns/nas-fujisaki-context-mechanism-20261008-v1'
    assert read(mechanism/'aggregate-summary.json')['mechanical_fixture_passed']
    driver=(ROOT/'hts_output_bound_comparison_20261008.py').read_text().replace('hts_output_bound','fujisaki_context').replace('hts-output-bound','fujisaki-context').replace('progress-0087.json','progress-0113.json')
    driver=constant(driver,'POOL',repr(POOL))
    start=driver.index('    reg=dict(');end=driver.index('    b.start_campaign',start);driver=driver[:start]+REG+driver[end:]
    start=driver.index("        for n in ('paths.py'");end=driver.index('    print(dict(registered=True',start)
    assemble='''        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py'):
            text=(PARENT/n).read_text().replace('hts-allpass-comparison','fujisaki-context-comparison').replace('allpass-fresh','fujisaki-fresh')
            if n=='controller.py':text=make_controller(text)
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.write(HERE/'runtime.py',(MECHANISM/'runtime-bundle/runtime.py').read_bytes(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
'''
    driver=driver[:start]+assemble+driver[end:]
    driver=driver.replace('@contextmanager','from prepare_fujisaki_comparison_20261008 import controller as make_controller\n@contextmanager',1)
    start=driver.index("        assert digest(HERE/'shape.dylib')");end=driver.index("    with job(b,'setup','全履歴",start)
    prepare='''        bundle=HERE/'runtime-bundle';mapping={n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():b.write(bundle/n,p.read_bytes(),j)
        assert all(not (bundle/n).is_symlink() for n in mapping), '今回の共有bundleは内蔵実体だけに限定する'
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(inherited_shared_assets_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
'''
    driver=driver[:start]+prepare+driver[end:]
    needle="        b.save(HERE/'controller-binding-audit.json',dict(reservation_alias_callable=True,source_contract_verified=True,new_scientific_outputs=0),j)"
    extra=needle+'''
        with b.workspace(j,'隔離profileの出力前実拒否') as (work,env):
            sb=m.profile(b,work,True);assert '(allow file-read-data )' not in sb and '(allow file-read-metadata )' not in sb
            blocked=[HERE/'protocol.json',HERE/'registration.json',BASE/'protocol.json']
            code='import json,socket; paths='+repr([str(p) for p in blocked])+'; a=[]\\n'
            code+="for p in paths:\\n try:open(p,'rb').read(1);a.append(False)\\n except PermissionError:a.append(True)\\n"
            code+="s=socket.socket()\\ntry:s.bind(('127.0.0.1',0));net=False\\nexcept PermissionError:net=True\\nprint(json.dumps(dict(read_denied=a,network_denied=net)))"
            proof=json.loads(m.execute([str(PYTHON),'-I','-B','-c',code],env,sb,timeout=45))
            assert all(proof['read_denied']) and proof['network_denied']
        b.save(HERE/'isolation-preflight.json',dict(proof,paths=[str(p) for p in blocked],empty_allow_clause_absent=True,scientific_outputs=0),j)'''
    driver=replace_once(driver,needle,extra)
    driver=driver.replace('固定出力制御','固定文脈韻律').replace('固定出力上限','固定文脈韻律').replace('原HTSの最終振幅だけを固定解析式で変更','原HTSの有声LF0輪郭だけを固定指令応答で変更')
    ast.parse(driver)
    close=(ROOT/'hts_allpass_closeout_20261008.py').read_text().replace('hts_allpass_comparison','fujisaki_context_comparison').replace('hts-allpass-comparison','fujisaki-context-comparison').replace('progress-0084.json','progress-0114.json')
    close=constant(close,'ALL_FRAMES',repr(PAIR));close=close.replace("'allpass'","'fujisaki'")
    close=replace_once(close,"    assert digest(HERE/'shape.dylib')==digest(MECHANISM/'shape.dylib') and digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')","    assert digest(HERE/'runtime-bundle/fujisaki_context.py')==digest(MECHANISM/'runtime-bundle/fujisaki_context.py')\n    assert digest(HERE/'runtime-bundle/hts_arrays.dylib')==digest(MECHANISM/'runtime-bundle/hts_arrays.dylib')")
    close=close.replace("'保存全32対のMCP/LF0/LPF/duration物理照合',64","'保存全32対の保持列と独立LF0式の全frame物理照合',96")
    start=close.index("                assert a['meta']['output_parameter_hashes']");end=close.index('        assert len(pairs)',start)
    close=close[:start]+'''                assert a['meta']['output_parameter_hashes'][0]==z['meta']['output_parameter_hashes'][0] and a['meta']['output_parameter_hashes'][2]==z['meta']['output_parameter_hashes'][2]
                assert a['meta']['output_parameter_hashes'][1]!=z['meta']['output_parameter_hashes'][1] and a['measurement']['support']==z['measurement']['support']
                assert z['meta']['control']['MCP_LPF_duration_and_MSD_unchanged'] and not z['meta']['control']['native_LF0_values_used_for_shape']
                assert z['meta']['conversion']['alpha']==.55 and z['meta']['conversion']['source_method']=='native-pulse-noise'
                assert a['meta']['conversion']['render_calls_including_internal_MLSA']==z['meta']['conversion']['render_calls_including_internal_MLSA']==1
                pairs.append(dict(id=key+'fujisaki',MCP_LPF_duration_mask_exact=True,LF0_is_intended_factor=True,between_method_source_clock_identity_claimed=False,fixed_support_exact=True,output_changed=a['wav_sha256']!=z['wav_sha256']))
''' +close[end:]
    close=close.replace("methodological_limits='原工学DIO/全体ACFと人工オールパスLTI資格。人工YIN40ms資格をHTSや知覚へ拡張しない。'","methodological_limits='旧工学DIO/全体ACFの操作的条件だけ。句/アクセント機構資格を音韻正解・自然さ・動的/境界truthへ拡張しない。全発話中央値はstreaming因果でない。'")
    close=close.replace("next='源の位相因子と振幅/内容保護を全件で保持する。不通過を同コホートのpole調整で救済せず、別の共有生成制御または独立測定へ進む。'","next='固定Fujisaki文脈韻律の全分母結果を保持。不改善時は同応答係数/指令時刻/median/gainを同コホートで救済せず、独立な調音source-tract機構または異なる生成表現へ進む。'")
    start=close.index("        lines=['# 原HTS");end=close.index("        b.write(HERE/'report.md'",start)
    close=close[:start]+'''        lines=['# 原HTSと固定句アクセント指令応答の日本語比較','','新16文×2条件×2方式64波形。LF0輪郭をラベル指令から計算し、MCP/LPF/duration/MSD/state/variance・原pulse/noise/MLSA・共通gain.25を保持した。係数/時刻規則の出力後探索なし。全64通常/隔離・CLI4・9論理/物理資料と通信の実拒否を照合した。','','|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'保存全{physical["all_frames_checked"]}frameの保持列/mask/sentinelと候補LF0の固定独立scalar式を照合した。LF0/源時計の方式間一致を主張しない。','',
            'alpha3/beta20/gamma.9/Ap.15秒/Aa.25/句先行.2秒は出力前固定。元LF0値の輪郭/教師/録音/lookupを使わない。全有声median校正はstreaming因果でなく、F2末尾核/無アクセント同値化は未知を保持する。','',
            '旧31方式・支持31,601/欠測249・二ASR33群と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達・最終採択なし。','',
            '一次資料: [Fujisaki and Hirose (1984)](https://www.jstage.jst.go.jp/article/ast1980/5/4/5_4_233/_pdf)。式とラベル規則の独自実装。','', '全件研究保護: '+str(research_gates),summary['next'],'']
''' +close[end:]
    close=close.replace('FIR経路の内容保護','固定文脈韻律の内容保護');ast.parse(close)
    dp=ROOT/'fujisaki_context_comparison_20261008.py';cp=ROOT/'fujisaki_context_closeout_20261008.py';b.write(dp,driver.encode());b.write(cp,close.encode())
    b.save(ROOT/'fujisaki-comparison-source-derivation.json',dict(generator_sha256=digest(Path(__file__)),source_sha256=digest(dp),closeout_sha256=digest(cp),fixed_mechanism_seal_sha256=digest(mechanism/'artifact-seal.json'),
               reservation_alias_bound=True,profile_does_not_emit_empty_allow=True,LF0_factor_intentionally_changed=True,no_source_clock_identity_claim=True,output_waves=64,total_without_retry=dict(render=196,dsp=420,ai=128),old_results_unchanged=True))
    print('固定文脈韻律の新64比較と保存全LF0式/保持因子の終了監査を構築',flush=True)

if __name__=='__main__':main()
