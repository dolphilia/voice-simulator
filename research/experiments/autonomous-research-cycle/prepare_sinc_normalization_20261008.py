"""sinc形状・位相を揃え、周期源のL2とDC正規化を独立因子にする。"""
import ast
from pathlib import Path
from budget import ROOT,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

FIXTURE=r'''"""位相と形状の一致、DC/二乗和の別条件、元波形/clockの工程検証。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original
from shape_arrays import raw,synthesize,kernel
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((100,35));mcp[:,0]=7.;lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    params=[mcp,lf0,np.full((100,1),coefficient)]
    baseline,_=original(params,settings);native,_=synthesize(params,settings,'native')
    assert np.array_equal(baseline,native)
    a,ta=raw(params,settings,'native')
    for method in ('sinc','sinc_dc'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        if coefficient==0.:assert np.array_equal(a,z)
        else:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,legacy_audio_exact=True,all_clock_and_phase_exact=True,zero_LPF_exact=coefficient==0.))
normalization_checks=[]
for hz in (80.,110.,220.,280.,400.,800.):
 for remainder in np.linspace(0,1,11):
    p=48000/hz;w=2*np.pi*hz/48000;target=4-remainder
    a=kernel(p,float(remainder),'sinc');z=kernel(p,float(remainder),'sinc_dc')
    assert np.isfinite(a).all() and np.isfinite(z).all()
    assert abs(float(np.sum(a*a))-p)<1e-10 and abs(float(z.sum())-np.sqrt(p))<1e-10
    assert np.allclose(z,a*(np.sqrt(p)/a.sum()),rtol=0,atol=1e-12)
    Ha=np.dot(a,np.exp(-1j*w*np.arange(9)));Hz=np.dot(z,np.exp(-1j*w*np.arange(9)))
    assert abs(float(np.angle(Hz/Ha)))<1e-12
    normalization_checks.append(dict(hz=hz,remainder=float(remainder),phase_error_samples=float(abs(np.angle(Ha*np.exp(1j*w*target))/w)),
        L2_DC_gain=float(a.sum()/np.sqrt(p)),DC_DC_gain=float(z.sum()/np.sqrt(p)),DC_energy_ratio=float(np.sum(z*z)/p),shape_and_phase_equal=True))
print(json.dumps(dict(passed=True,checks=checks,normalization_checks=normalization_checks,render=20,dsp=800,fixture_only=True,
    L2_energy_and_DC_gain_are_different_constraints=True,mechanical_truth_not_perceptual_truth=True,quality_certified=False)))
'''

POOL=dict(candidate_pool_short=['胡麻を軽く煎る。','布団を棚にしまう。','穏やかな波が寄せる。','庭石に露が光る。','柿の皮を剥く。','小さな笛を吹く。','白い糸を通す。','南の窓を閉める。'],
    candidate_pool_long=['静かな夕方に、猫が廊下の端で丸くなって眠っていた。','祖父の話を聞きながら、机に広げた地図を指でなぞった。','青い空の下で、妹は花壇の周りに小さな石を並べた。','温かい汁を器によそってから、家族を呼ぶために戸を開けた。','長い旅から戻った友人が、港で見た景色を楽しそうに話した。','柔らかな日差しが差す部屋で、母は古い写真を一枚ずつ眺めた。','道端に落ちていた小さな葉を拾い、手帳の間に挟んでおいた。','遠くの町へ向かう列車を見送り、二人はゆっくり歩き始めた。'])

def main():
    b=Budget();assert not b.snapshot()['jobs'];parent=ROOT/'hts_fractional_pulse_20261008.py';text=parent.read_text()
    source=ast.parse(text)
    c=ast.literal_eval(next(n.value for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='C_SOURCE' for t in n.targets)))
    c=c.replace('selected>3','selected>4')
    a='double scale=sqrt(p/energy);for(size_t i=0;i<n;i++)out[i]*=scale;'
    z='double sum=0.;for(size_t i=0;i<n;i++)sum+=out[i];\n    if(selected==4 && sum<=1e-12)return 0;\n    double scale=selected==4?sqrt(p)/sum:sqrt(p/energy);for(size_t i=0;i<n;i++)out[i]*=scale;'
    assert c.count(a)==1;c=c.replace(a,z)
    wrapper=ast.literal_eval(next(n.value for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='WRAPPER' for t in n.targets)))
    wrapper=wrapper.replace("'sinc':3}","'sinc':3,'sinc_dc':4}").replace("('latency','linear','sinc')","('latency','linear','sinc','sinc_dc')")
    wrapper=wrapper.replace("energy_per_cycle='period:LPF前kernelの二乗和。出力/雑音/LPFは固定。'", "source_normalization='DC sum=sqrt(period)' if method=='sinc_dc' else 'L2 sumsq=period',output_noise_LPF_gain_fixed=True")
    text=constant(text,'C_SOURCE',"r'''"+c+"'''");text=constant(text,'WRAPPER',"r'''"+wrapper+"'''");text=constant(text,'FIXTURE',"r'''"+FIXTURE+"'''");text=constant(text,'POOL',repr(POOL))
    text=text.replace('hts-fractional-pulse','hts-sinc-normalization').replace('fractional-fresh','normalization-fresh')
    text=text.replace('render=1400,dsp=6000,ai=768','render=1000,dsp=4000,ai=576')
    text=text.replace("variants=['native','latency','linear','sinc']", "variants=['native','sinc','sinc_dc']")
    text=text.replace("METHODS=['native','latency','linear','sinc']", "METHODS=['native','sinc','sinc_dc']")
    text=text.replace(".replace('192','128').replace('576','384').replace('385','257').replace('388','260')", ".replace('192','96').replace('576','288').replace('385','193').replace('388','196')")
    text=text.replace("text=(BASE/name).read_text().replace('192','128')", "text=(BASE/name).read_text().replace('192','96')")
    text=text.replace('expected_records=128','expected_records=96').replace('progress-0054.json','progress-0056.json')
    text=text.replace("job(b,'render','pulse補間の数値対照fixture',24", "job(b,'render','sinc正規化の数値対照fixture',20")
    text=text.replace("job(b,'dsp','kernelエネルギー・位相・直接応答・旧波形fixture',900", "job(b,'dsp','sinc形状/位相・L2/DC条件・旧波形fixture',800")
    text=text.replace('元pulseを対照に、周期内位置の整数丸めと共通遅延/線形/窓付きsincを分離して、位置誤差・固定支持・内容保護への因果効果を検証する','原nativeを対照に、同じ9tap sinc形状・fractional phase・4sample遅延下のL2正規化とDC利得保存を比較し、源の周期ごとの振幅変動が固定支持/内容保護に与える因果効果を検証する')
    text=text.replace("latency='周期pulseだけ4sample遅延、noiseと全時計不変',linear='同遅延下でcell端数を2tap線形補間',sinc='同遅延下で9tap raised-cosine窓sinc補間'", "sinc='9tap raised-cosine窓sinc、二乗和period',sinc_dc='同形状/位相/遅延、和sqrt(period)。周期二乗和は保存しない。'")
    text=text.replace('各周期kernel二乗和period。出力gain.25、noise、MCP、LPF、全clock不変。出力後の音量調整なし。','native/sincは周期kernel二乗和period。sinc_dcは和sqrt(period)。出力gain.25、noise、MCP、LPF、全clock不変。波形ごとの正規化/出力後調整なし。')
    text=text.replace('新16文×2条件×4方式=128。','新16文×2条件×3方式=96。').replace('全128通常/隔離','全96通常/隔離')
    text=text.replace('comparison_render=128,comparison_dsp=384,isolation_render=256,isolation_dsp=256','comparison_render=96,comparison_dsp=288,isolation_render=192,isolation_dsp=192')
    text=text.replace('fixture_render=24,fixture_dsp=900,two_ASR_ai=256,total_without_retry=dict(render=412,dsp=1544,ai=256)','fixture_render=20,fixture_dsp=800,two_ASR_ai=192,total_without_retry=dict(render=312,dsp=1284,ai=192)')
    path=ROOT/'hts_sinc_normalization_20261008.py';ast.parse(text);b.write(path,text.encode())
    b.save(ROOT/'sinc-normalization-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),
        native_primary_control=True,phase_shape_delay_equal_between_candidates=True,normalization_only_factor=True,old_outputs_preserved=True,quality_goal_completed=False))
    print('sinc形状/位相を揃えた正規化三方式96件を生成前構築',flush=True)

if __name__=='__main__':main()
