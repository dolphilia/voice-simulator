"""LF0輪郭の振幅だけを変え、全体ACF診断と内容保護への効果を分離する。"""
import ast
from pathlib import Path
from budget import ROOT,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

CONTOUR=r'''"""校正済みLF0の中央値周りを固定倍率にする。語ごとのlookupはない。"""
import numpy as np
from hts_arrays import ah
SCALE={'native':1.,'half_contour':.5,'flat_contour':0.}
def apply_contour(params,pitch,method):
    if method not in SCALE:raise ValueError('未登録のLF0輪郭倍率')
    x=[np.ascontiguousarray(v,dtype=np.float64) for v in params];before=[ah(v) for v in x]
    y=[v.copy() for v in x];voiced=x[1][:,0]>0;scale=SCALE[method];center=np.log(pitch)
    if not np.any(voiced):raise ValueError('校正する有声LF0がない')
    if scale!=1.:y[1][voiced,0]=center+scale*(x[1][voiced,0]-center)
    expected=x[1][voiced,0] if scale==1. else center+scale*(x[1][voiced,0]-center)
    error=float(np.max(np.abs(y[1][voiced,0]-expected)))
    passed=bool(error<=2e-15 and np.array_equal(y[1][:,0]>0,voiced)
        and np.array_equal(y[1][~voiced],x[1][~voiced]) and ah(y[0])==before[0] and ah(y[2])==before[2]
        and np.all((np.exp(y[1][voiced,0])>=70)&(np.exp(y[1][voiced,0])<=800)))
    assert [ah(v) for v in x]==before and passed
    return y,dict(scale=scale,center_hz=pitch,target_max_abs_error=error,passed=passed,
        MCP_LPF_and_unvoiced_sentinel_exact=True,voicing_mask_exact=True,original_relative_LF0_preserved=scale==1.,
        flattened_is_mechanism_diagnostic_not_naturalness_candidate=scale==0.,
        input_LF0_log_range=float(np.ptp(x[1][voiced,0])),output_LF0_log_range=float(np.ptp(y[1][voiced,0])))
'''

FIXTURE=r'''"""輪郭の固定倍率・原波形一致・無周期経路不変を生成前検証する。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original,ah
from shape_arrays import raw,synthesize
from contour import apply_contour
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
  for dynamic in (False,True):
    mcp=np.zeros((100,35));mcp[:,0]=7.;mcp[:,1]=.35;mcp[:,2]=.15;mcp[:,6]=.12
    lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    if dynamic:lf0[20:80,0]+=.2*np.sin(np.linspace(-np.pi,np.pi,60))
    params=[mcp,lf0,np.full((100,1),coefficient)]
    native_params,ct=apply_contour(params,hz,'native');assert all(np.array_equal(a,z) for a,z in zip(params,native_params))
    baseline,_=original(params,settings);native,_=synthesize(native_params,settings,'native');assert np.array_equal(baseline,native)
    a,ta=raw(native_params,settings,'native')
    for method in ('half_contour','flat_contour'):
        changed,meta=apply_contour(params,hz,method);z,tz=raw(changed,settings,method)
        assert meta['passed'] and np.isfinite(z).all()
        assert np.array_equal(ta['period']==0,tz['period']==0)
        if coefficient==0.:assert np.array_equal(a,z)
        if dynamic and coefficient==1.:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,dynamic=dynamic,legacy_audio_exact=True,voicing_mask_exact=True,
        MCP_LPF_sentinel_exact=True,noise_only_wave_exact=coefficient==0.,dynamic_periodic_changed=dynamic and coefficient==1.))
control_checks=[]
for hz in (110.,220.,280.,400.):
 for swing in (0.,.1,.3):
  lf0=np.r_[-1e10,np.log(hz)-swing,np.log(hz),np.log(hz)+swing,-1e10].reshape(-1,1)
  p=[np.zeros((5,35)),lf0,np.ones((5,1))]
  for method,scale in [('native',1.),('half_contour',.5),('flat_contour',0.)]:
    z,m=apply_contour(p,hz,method);assert m['passed'] and np.array_equal(z[1][[0,4]],lf0[[0,4]])
    assert abs(float(np.median(z[1][1:4,0]))-np.log(hz))<1e-14
    assert abs(float(np.ptp(z[1][1:4,0]))-2*swing*scale)<2e-15
    control_checks.append(dict(hz=hz,swing=swing,method=method,scale=scale,passed=True))
print(json.dumps(dict(passed=True,checks=checks,contour_control_checks=control_checks,render=40,dsp=600,fixture_only=True,
    original_native_wave_exact=True,relative_contour_intentionally_changed=True,flat_is_not_naturalness_target=True,quality_certified=False)))
'''

POOL=dict(candidate_pool_short=['庭に小さな芽が出る。','折り紙を袋に入れる。','橋の下で魚が泳ぐ。','棚から皿を下ろす。','麦茶を少し注ぐ。','糸巻きを箱へ戻す。','草原を馬が歩く。','帽子の紐を結ぶ。'],
 candidate_pool_long=['明るい台所で、兄は鍋の中の湯を静かにかき混ぜた。','川の向こうの村まで、二人は荷物を背負って歩いていった。','朝の光が床に広がると、猫が伸びをして窓へ近づいた。','門の前に立った友人が、昨日の出来事を短く話してくれた。','夕暮れの風に吹かれながら、祖父は畑の道具を小屋へ運んだ。','母から届いた手紙を読み終えて、姉は引き出しに大切にしまった。','道の曲がり角で雨を避けていた子供に、父が傘を貸してあげた。','広い庭の真ん中で、弟が新しい靴の紐を何度も結び直していた。'])

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='指定F0周りのLF0輪郭幅を1/.5/0にしたとき、原HTSフィルタ下の全体ACF/DIO診断・固定支持・二ASR内容保護はどう変わるか。輪郭変動と源/フィルタ変更を別因子にする。',
        variants=['native','half_contour','flat_contour'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='従来校正LF0の全輪郭をbyte保持',half_contour='log(指定Hz)+.5*(校正LF0-log(指定Hz))',flat_contour='有声LF0をlog(指定Hz)。単調源の機構診断であり自然さ候補としない。'),
        contour_scale=dict(native=1.,half_contour=.5,flat_contour=0.),
        fixed_control='MCP/LPF・duration/state/MSD/variance・有声mask/無声sentinel・HTS原pulse/noise算法・alpha=.55・beta0・全frame時計を保持。LF0輪郭が意図した因子。周期/counter/励振列の候補間一致は要求しない。',
        normalization='LF0だけの事前固定倍率。原HTSのsqrt(period)源振幅も変更したLF0へ従う。volume1、gain.25、12ms fade、24k resample固定。波形別音量調整なし。',
        input='新16文×2条件×3方式=96。全履歴の文章/ラベル非衝突を波形前確認。P5未開封。',
        source=dict(local='共有校正コード・HTS原実装を固定し、式を独立fixtureで検証。新しい教師/録音/ニューラル推論なし。',url=PAPER,scope='原MLSAフィルタの一次資料。今回alphaは全方式.55。輪郭倍率の自然さ先例としては引用しない。'),
        support='nativeから一度固定し全候補へ引継ぎ。欠測を除外せず、旧249欠測/旧判定を保持。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上で全件確認。輪郭倍率とMCP/LPF/MSD/無声sentinel/時計の不変量。短窓/動的/知覚へ資格を拡張しない。',content='二固定ASR各33群が原native以下。別コホートの悪化を相殺しない。',independence='全96通常/隔離、CLI4、禁止資料/通信の実拒否。'),
        estimates=dict(comparison_render=96,comparison_dsp=288,isolation_render=192,isolation_dsp=192,CLI_render=4,CLI_dsp=4,fixture_render=40,fixture_dsp=600,two_ASR_ai=192,total_without_retry=dict(render=332,dsp=1084,ai=192),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,
        controller_sha256=digest(Path(__file__)),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        contour_change_is_not_gate_relaxation=True,flat_pass_is_not_naturalness_qualification=True,
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

def main():
    b=Budget();assert not b.snapshot()['jobs'];parent=ROOT/'hts_filter_warp_20261008.py';text=parent.read_text();tree=ast.parse(text)
    def value(name):return ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)))
    c=value('C_SOURCE');a=c.index('int shape_mc2b(');z=c.index('int shape_render(',a);c=c[:a]+c[z:]
    c=c.replace('(selected<0||selected>2)','selected!=0').replace('double alpha=selected==1?.50:selected==2?.60:.55;','double alpha=.55;')
    wrapper=value('WRAPPER');a=wrapper.index('_mc2b=');z=wrapper.index('def raw(',a)
    wrapper=wrapper[:a]+"MODES={'native':0,'half_contour':0,'flat_contour':0}\n"+wrapper[z:]
    wrapper=wrapper.replace("filter_method=method,effective_filter_alpha=ALPHA[method]","filter_method=method,effective_filter_alpha=.55")
    wrapper=wrapper.replace('周波数軸の独立因子','LF0輪郭の独立因子').replace('周期/雑音/LPF/励振列','原HTS励振算法')
    wrapper=wrapper.replace('共有MCPと原励振を保ち、実フィルタalphaだけを変更する入口。','与えたLF0を原HTSのalpha=.55フィルタへ渡す入口。').replace('未登録の周波数軸設定','未登録のLF0輪郭設定')
    wrapper=wrapper.replace("original_excitation_noise_LPF_and_gain_unchanged=True", "original_HTS_excitation_algorithm_LPF_filter_gain_unchanged=True")
    wrapper=wrapper.replace('MCP35を変換せず、同じalphaをmc2bとMLSAへ渡す。周波数一様倍率/物理声道長ではない。','全方式alpha=.55固定。LF0輪郭だけが別因子。')
    assert 'ALPHA' not in wrapper
    for name,v in [('C_SOURCE',c),('WRAPPER',wrapper),('FIXTURE',FIXTURE)]:text=constant(text,name,"r'''"+v+"'''")
    text=constant(text,'POOL',repr(POOL))
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call));text=text.replace(ast.get_source_segment(text,node),REGISTRATION)
    text=text.replace('hts-filter-warp','hts-lf0-contour').replace('filter-warp-fresh','contour-fresh').replace('progress-0058.json','progress-0061.json')
    text=text.replace("METHODS=['native','alpha_low','alpha_high']","METHODS=['native','half_contour','flat_contour']")
    a="\n@contextmanager\ndef job(";assert text.count(a)==1;text=text.replace(a,"\nCONTOUR="+repr(CONTOUR)+a)
    a="b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j)";text=text.replace(a,a+";b.write(HERE/'contour.py',CONTOUR.encode(),j)")
    text=text.replace("('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib')","('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib','contour.py')")
    text=text.replace("assert meta['output_parameter_hashes'] == native_meta['output_parameter_hashes']\\n                    assert meta['conversion']['source_clock_hashes'] == native_meta['conversion']['source_clock_hashes']", "assert meta['output_parameter_hashes'][2] == native_meta['output_parameter_hashes'][2]\\n                    assert meta['contour']['passed'] and meta['contour_target_max_abs_error'] <= 2e-15")
    needle="        b.write(HERE/'runtime.py',runtime.encode(),j)";assert text.count(needle)==1
    changes='''        runtime=runtime.replace('from calibration import calibrated_lf0','from contour import apply_contour\\nfrom calibration import calibrated_lf0')
        runtime=runtime.replace('        voiced=params[1][:,0]>0','        params,contour=apply_contour(params,pitch,method)\\n        voiced=params[1][:,0]>0')
        runtime=runtime.replace('invariants_pass=bool(invariants)',"invariants_pass=bool(invariants and contour['passed'])")
        runtime=runtime.replace('relative_LF0_max_abs_error=relative_error, control=control,',"relative_LF0_max_abs_error=contour['target_max_abs_error'], calibration_relative_LF0_max_abs_error=relative_error, contour_target_max_abs_error=contour['target_max_abs_error'], contour=contour, control=control,")
'''
    text=text.replace(needle,changes+needle)
    text=text.replace('フィルタ周波数軸の原波形対照fixture','LF0輪郭の固定倍率と原波形対照fixture').replace('全励振一致・MLSA係数/伝達関数恒等式fixture','輪郭倍率・固定median・MCP/LPF/MSD/原波形fixture')
    text=text.replace('原励振固定・フィルタ周波数軸・全比較費','LF0輪郭の固定倍率・対照・全比較費').replace('共有HTSのフィルタ周波数軸だけを変更し、','共有HTSのLF0輪郭幅だけを変更し、')
    path=ROOT/'hts_lf0_contour_20261008.py';ast.parse(text);b.write(path,text.encode())
    b.save(ROOT/'lf0-contour-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),
        original_native_is_primary=True,LF0_contour_only_factor=True,original_filter_alpha_55_for_all=True,flat_is_diagnostic_only=True,old_source_and_249_missing_preserved=True,quality_goal_completed=False))
    print('LF0輪郭幅1/.5/0の三方式96件を初出力前構築',flush=True)

if __name__=='__main__':main()
