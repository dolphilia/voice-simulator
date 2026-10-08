"""共有MCP分布の比較を、既存ゲート・全費用を継承して生成前に構築する。"""
import ast
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

POOL=dict(candidate_pool_short=['樽の蓋を叩く。','山の霧を眺める。','鴨の羽を数える。','棚の瓶を並べる。','馬の背を撫でる。','笛の音を聞く。','盆の豆を運ぶ。','庭の塀を直す。'],
 candidate_pool_long=['夕方の倉庫で荷物を探す父は、古い木箱の中を順番に調べた。','駅前の公園で待つ姉は、木陰の長椅子に座って本を読み始めた。','野菜を並べた店先で、祖母は大きな大根を手に取って重さを確かめた。','昼休みの教室に戻った弟は、机の上の紙を丁寧に重ねた。','遠くの山が赤く染まる頃、兄は道具を片付けて家へ向かった。','窓辺で小さな鉢を眺める叔母は、土が乾いていることに気づいた。','海沿いの道を走る友人は、白い波の向こうに船を見つけた。','朝食の後に庭へ出た祖父は、折れた竹を集めて隅に置いた。'])

PAIR_AUDIT=r'''"""保存全32対の非因子列保持とMCP変化を確認する。波形再生成なし。"""
import sys,json
from pathlib import Path
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text())
import numpy as np
rows=[]
for row in p['rows']:
 for condition in p['conditions']:
  base=here/'render'/row['id']/condition
  with np.load(base/'native.npz',allow_pickle=False) as z:a={k:z[k].copy() for k in ('mcp','lf0','lpf','duration')}
  with np.load(base/'happy_mcp.npz',allow_pickle=False) as z:b={k:z[k].copy() for k in a}
  assert all(np.array_equal(a[k],b[k]) for k in ('lf0','lpf','duration'))
  assert a['mcp'].shape==b['mcp'].shape and np.isfinite(b['mcp']).all() and not np.array_equal(a['mcp'],b['mcp'])
  rows.append(dict(id=row['id']+'/'+condition,LF0_LPF_duration_exact=True,MCP_intentionally_changed=True,frames_checked=len(a['mcp']),excluded_frames=0,
   finite_MCP_all_frames=True,changed_MCP_frames=int(np.any(a['mcp']!=b['mcp'],axis=1).sum()),passed=True))
assert len(rows)==32
print(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v['frames_checked'] for v in rows),saved_arrays_only=True,no_wave_resynthesis=True,render=0,dsp=96,quality_certified=False)))
'''

def main():
 b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
 mechanism=ROOT/'campaigns/nas-hts-acoustic-model-mechanism-20261008-v1'
 assert read(mechanism/'aggregate-summary.json')['mechanical_fixture_passed']
 driver=(ROOT/'hts_output_bound_comparison_20261008.py').read_text()
 driver=driver.replace('hts_output_bound','hts_acoustic_model').replace('hts-output-bound','hts-acoustic-model').replace('progress-0087.json','progress-0096.json')
 driver=driver.replace("PARENT=ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1'","PARENT=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'")
 driver=constant(driver,'POOL',repr(POOL))
 start=driver.index('    reg=dict(');end=driver.index('    b.start_campaign',start)
 driver=driver[:start]+'''    reg=dict(campaign=NAME,status='registered_before_output',question='共有happy HMMのMCP状態平均/分散だけを交換した生成は、未知日本語で内容と工学支持をnative以下に保護できるか。',
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
''' +driver[end:]
 start=driver.index("        for n in ('paths.py'");end=driver.index('    print(dict(registered=True',start)
 driver=driver[:start]+'''        for n in ('paths.py','controller.py','asr_worker.py','runtime_batch.py','measurement.py','prepare_inputs.py','runtime.py'):
            text=(PARENT/n).read_text().replace('hts-output-bound-comparison','hts-acoustic-model-comparison').replace('bound-fresh','model-fresh')
            if n=='controller.py':
                needle="                    for key in ['duration', 'msd', 'settings', 'state_sha256', 'variance_sha256', 'native_parameter_hashes']:"
                assert text.count(needle)==1;text=text.replace(needle,"                    for key in ['duration', 'msd', 'settings', 'state_sha256', 'variance_sha256', 'GV_sha256']:")
                needle="                    assert meta['output_parameter_hashes'][0] == native_meta['output_parameter_hashes'][0]"
                text=text.replace(needle,"                    assert meta['output_parameter_hashes'][0] != native_meta['output_parameter_hashes'][0]")
                needle="                    assert meta['output_parameter_hashes'] == native_meta['output_parameter_hashes']"
                text=text.replace(needle,"                    assert meta['output_parameter_hashes'][1:] == native_meta['output_parameter_hashes'][1:]\\n                    assert meta['native_parameter_hashes'][1:] == native_meta['native_parameter_hashes'][1:]")
                text=text.replace('new_DSP_calls=192','new_DSP_calls=256').replace('    dsp=192','    dsp=256')
                text=text.replace("count=64, reserve_bytes=100_000):","count=128, reserve_bytes=100_000):")
                text=text.replace("'CLI E0 ' + mode + '/' + request['id'], reserve_bytes=100_000):","'CLI E0 ' + mode + '/' + request['id'], count=1 if request['method']=='native' else 3, reserve_bytes=100_000):")
                text=text.replace('new_DSP_calls=132','new_DSP_calls=264')
                # bundleに許可した共有資産の物理実体だけを追加し、外部root全体は拒否する。
                needle="        text += '(allow file-read-data (literal ' + json.dumps(str(b.guard.root / 'identity.json')) + '))\\n'"
                assert text.count(needle)==1
                text=text.replace(needle,needle+"\\n        physical=[p.resolve() for p in (HERE/'runtime-bundle').rglob('*') if p.is_file() and p.is_symlink()]\\n        text += '(allow file-read-data ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'\\n        text += '(allow file-read-metadata ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'")
            if n=='runtime.py':
                text=text.replace('from timing_engine import Engine','from acoustic_model import Engine,gv').replace('from bounded_output import synthesize as shape_synthesize','from shape_arrays import synthesize as shape_synthesize').replace("METHODS=['native','soft_bound']","METHODS=['native','happy_mcp']")
                needle='        settings = engine.get_settings()'
                assert text.count(needle)==1
                text=text.replace(needle,needle+"\\n        before_GV=gv(engine)\\n        transfer=None\\n        if method=='happy_mcp':\\n            with Engine(row,ROOT/'mei_happy.htsvoice',speed=speed,half_tone=12*math.log2(pitch/220)) as donor:transfer=engine.transfer_mcp(donor)\\n        after=engine.snapshot();after_variance=engine.variance()")
                text=text.replace('raw,conversion=shape_synthesize(params,settings,method)',"raw,conversion=shape_synthesize(params,settings,'native')\\n        conversion.update(renderer='原HTS-MLSA',source_method='native',source_phase_rule='変更なし',MCP_state_distribution_source=method,MCP_transfer=transfer)")
                text=text.replace('assert engine.snapshot() == before and np.array_equal(engine.variance(), variance)','assert engine.snapshot() == after and np.array_equal(engine.variance(), after_variance) and np.array_equal(gv(engine),before_GV)')
                text=text.replace('variance_sha256=ah(variance), native_parameter_hashes=',"variance_sha256=ah(variance), GV_sha256=ah(before_GV), state_after_sha256=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest(), variance_after_sha256=ah(after_variance), native_parameter_hashes=")
            ast.parse(text);b.write(HERE/n,text.encode(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
''' +driver[end:]
 start=driver.index("        assert digest(HERE/'shape.dylib')");end=driver.index("    with job(b,'setup','全履歴",start)
 driver=driver[:start]+'''        bundle=HERE/'runtime-bundle';mapping={n:MECHANISM/'runtime-bundle'/n for n in read(MECHANISM/'runtime-bundle/manifest.json')['files']}
        mapping.update({n:PARENT/'runtime-bundle'/n for n in ('acoustics.py',)})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py')})
        for n,p in mapping.items():
            if n=='mei_happy.htsvoice':b.write_data(bundle/n,p.read_bytes(),j)
            else:b.write(bundle/n,p.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(bundle/'mcp_model.dylib'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
''' +driver[end:]
 driver=driver.replace("assert digest(MECHANISM/'runtime-bundle/shape.dylib')", "assert digest(MECHANISM/'runtime-bundle/shape.dylib')")
 driver=driver.replace('固定出力','共有MCP分布').replace('原HTSの最終振幅だけを固定解析式で変更','共有文脈HMMのMCP状態分布だけを交換')
 ast.parse(driver)
 close=(ROOT/'hts_output_bound_closeout_20261008.py').read_text().replace('hts_output_bound_comparison','hts_acoustic_model_comparison').replace('hts-output-bound-comparison','hts-acoustic-model-comparison').replace('progress-0088.json','progress-0097.json')
 close=constant(close,'ALL_FRAMES',repr(PAIR_AUDIT));close=close.replace("'soft_bound'","'happy_mcp'")
 needle="    assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib') and digest(HERE/'shape.c')==digest(ROOT/'campaigns/nas-hts-allpass-comparison-20261008-v1/shape.c')"
 assert close.count(needle)==1;close=close.replace(needle,"    for name,h in read(MECHANISM/'runtime-bundle/manifest.json')['files'].items():assert digest(HERE/'runtime-bundle'/name)==h,name")
 close=close.replace('保存全32対の列・出力式・上限と恒等域の物理照合','保存全32対の非因子列・全MCP変化・有限性の物理照合')
 close=close.replace("assert a['meta']['output_parameter_hashes']==z['meta']['output_parameter_hashes']","assert a['meta']['output_parameter_hashes'][1:]==z['meta']['output_parameter_hashes'][1:] and a['meta']['output_parameter_hashes'][0]!=z['meta']['output_parameter_hashes'][0]")
 close=close.replace("                assert z['meta']['conversion']['output_bound_intentionally_changes_large_samples']","                transfer=z['meta']['conversion']['MCP_transfer']\\n                assert all(transfer[k] for k in ('state_MCP_donor_exact','other_state_distributions_exact','duration_MSD_windows_exact','GV_and_settings_exact','donor_unmodified'))\\n                assert a['meta']['GV_sha256']==z['meta']['GV_sha256']".replace('\\n','\n'))
 close=close.replace("assert z['meta']['conversion']['effective_filter_alpha']==.55 and z['meta']['conversion']['output_knee']==.5 and z['meta']['conversion']['output_ceiling']==.98","assert z['meta']['conversion']['effective_filter_alpha']==.55 and z['meta']['conversion']['MCP_state_distribution_source']=='happy_mcp'")
 close=close.replace('all_parameters_exact=True','LF0_LPF_duration_GV_exact=True').replace('output_bound_is_intended_factor=True','MCP_state_emissions_is_intended_factor=True').replace('output_factor_pairs=pairs','MCP_factor_pairs=pairs')
 close=close.replace("methodological_limits='旧DIO/全体ACFの操作的条件と固定振幅上限。独立式のfloat32誤差はbyte一致ではない。自然さ/動的pitch/境界のtruthではない。'","methodological_limits='旧DIO/全体ACFの操作的条件。共有MCP交換機構は自然さ/動的pitch/境界のtruthではない。全happyモデルの発声ではなくnormal時間・源・GVのMCP分布交換。'")
 close=close.replace("next='出力上限のE0と内容/ピッチ保護を区別して全件保持する。係数の同コホート救済を行わず、別の声道表現または測定資格へ進む。'","next='共有MCP状態分布の内容/工学保護を全件保持する。同コホートの別style/補間/gain探索は封印し、別の文脈または調音制御を事前登録する。'")
 start=close.index("        lines=['# 原HTS");end=close.index("        b.write(HERE/'report.md'",start)
 close=close[:start]+'''        lines=['# 原HTSと共有HMMのMCP分布交換比較','','新16文×2条件×2方式64波形。公式Mei1.4 happyの文脈別MCP状態平均/分散だけをnormalへ交換した。原時間配分・LF0/LPF・GV・励振と源時計、MLPG/vocoder/gain.25は保持。通常/隔離64組・CLI4・実拒否を確認した。','','|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'保存全{physical["all_frames_checked"]}frameでLF0/LPF/durationの完全一致とMCPの有限性を確認した。全32対でMCPだけ意図的に変わった。全happyモデルではなく、normalの時間・源・GVを保持した共有emission分布交換である。','',
            'HTS Voice Mei v1.4、MMDAgent Project Team / Nagoya Institute of Technology Department of Computer Science、Copyright 2009–2013。[公式配布](https://github.com/mmdagent-ex/example/tree/main/voice/mei)・[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)。元配布モデルは不改変。状態MCP平均/分散交換が派生処理であり、提供者の推奨を主張しない。','',
            '旧31方式・支持31,601・欠測249・二ASR33群と凍結経路を保持。日本語知覚資格なし・P5未開封・品質未達。最終採択なし。','',
            '全件研究保護: '+str(research_gates),summary['next'],'']
''' +close[end:]
 close=close.replace('固定出力制御','共有MCP分布');ast.parse(close)
 dp=ROOT/'hts_acoustic_model_comparison_20261008.py';cp=ROOT/'hts_acoustic_model_closeout_20261008.py'
 b.write(dp,driver.encode());b.write(cp,close.encode())
 b.save(ROOT/'acoustic-model-comparison-source-derivation.json',dict(generator_sha256=digest(Path(__file__)),source_sha256=digest(dp),closeout_sha256=digest(cp),parent_controller_source_sha256=digest(ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1/controller.py'),
  MCP_invariant_intentionally_changed=True,donor_state_and_transfer_DSP_counted=True,total_without_retry=dict(render=196,dsp=616,ai=128),old_results_unchanged=True))
 print('共有MCP分布の64比較・固定ゲート・全件物理終了監査を構築',flush=True)

if __name__=='__main__':main()
