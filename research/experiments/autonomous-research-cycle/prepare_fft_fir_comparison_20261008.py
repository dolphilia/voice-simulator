"""機構資格を固定し、選別未使用の新日本語64波形へFFT FIRを展開する。"""
import ast
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

MECHANISM=ROOT/'campaigns/nas-hts-fft-fir-mechanism-20261008-v1'
POOL=dict(candidate_pool_short=['檸檬の皮を剥く。','箒の柄を握る。','毛糸を丸く巻く。','柵の内側を歩く。','雨粒を指で払う。','鏡の縁を磨く。','小瓶の蓋を開ける。','橙色の紐を探す。'],
 candidate_pool_long=['夜の廊下に灯りがつくと、祖父は本を閉じて部屋へ戻った。','昼休みの公園で、姉は木陰に座って温かい茶を飲んでいた。','配達の人が門を叩いたので、弟は靴を履いて外へ出た。','駅前の喫茶店に入り、母は窓から見える街をしばらく眺めた。','遠くで鳥の声が聞こえた時、兄は手を止めて空を見上げた。','北へ向かう船を見送りながら、少年は港の柵に静かにもたれた。','箱の底に古い写真を見つけた父が、その日の話を私に教えた。','庭に落ちた枯れ葉を拾い集めて、祖母は木の根元へ運んでいった。'])

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='固定長2048のFFT生成IRと直接因果畳み込みは、新日本語MCPで応答範囲・原nativeの内容/固定支持/工学制御を保てるか。',
        variants=['native','fft_fir'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='原HTS Pade-MLSA alpha=.55の完全一致対照',fft_fir='16384gridの解析MCP複素応答→IR2048。過去だけの直接内積と前/current IRの出力crossfade j/240。'),
        effective_alpha=dict(native=.55,fft_fir=.55),IR_length=2048,FFT_length=16384,
        fixed_control='校正LF0・全MCP/LPF/duration/state/MSD/variance・源period/counter/event/実励振をbyte固定。元sqrt(period)、gain.25、resample24k、12ms fade、volume1を保持。FIRのIR補間はMLSA b補間と別表現。',
        normalization='MCP c0と全励振を保護。帯域/波形別gain救済なし。',
        input='新16文×2条件×2方式=64。全履歴文章/ラベル非衝突を出力前確認。P5本文は読まない。',
        source=dict(url=PAPER,related_url='https://sp-nitech.github.io/sptk/latest/main/c2mpir.html',mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),cutoff_seal_sha256=digest(ROOT/'campaigns/nas-hts-fir-cutoff-qualification-20261008-v1/artifact-seal.json'),scope='前の全MCPによる長さ選択は選別資料。今回は新入力で再度全frameを検査し、独立最終品質の確認とは区別。'),
        support='原nativeから一度固定し、欠測を除外せず候補全件へ保持。旧249欠測/旧判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上を全件。短窓/動的/知覚資格へ一般化しない。',content='二固定ASR各33群で原native以下。悪化相殺なし。',independence='全64通常/隔離・CLI4と実読取/通信拒否。',FIR_mechanism='全32nativeの全MCP frameで16384gridの複素応答相対誤差≤1e-3、参考IR2048以降のtail energy割合≤1e-6。全frame検査、連続全域/知覚truthとはしない。'),
        CPU_limits='生成/測定/隔離子はBLAS/VECLIB/OMPを1に固定。二ASRの明示threads4/2と環境は既存契約を引き継ぐ。',
        estimates=dict(comparison_render=96,comparison_output_waves=64,internal_MLSA_helpers=32,comparison_dsp=192,isolation_render=192,isolation_dsp=128,CLI_render=6,CLI_dsp=4,fixture_render=0,inherited_fixture=True,all_frame_FIR_dsp=64,two_ASR_ai=128,total_without_retry=dict(render=294,dsp=388,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_fft_fir_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        old_FIR1024_failures_kept=True,new_route_does_not_qualify_perception=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

def main():
    b=Budget();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert read(MECHANISM/'aggregate-summary.json')['mechanical_fixture_passed']
    parent=ROOT/'hts_minphase_comparison_20261008.py';text=parent.read_text()
    text=constant(text,'MINPHASE',repr((MECHANISM/'fft_fir.py').read_text()))
    text=constant(text,'FIXTURE',repr('# 同一機構fixtureをhash照合で引継ぐ。新波形生成なし。\n'))
    text=constant(text,'POOL',repr(POOL))
    text=constant(text,'MECHANISM',"ROOT/'campaigns/nas-hts-fft-fir-mechanism-20261008-v1'")
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call))
    text=text.replace(ast.get_source_segment(text,node),REGISTRATION)
    text=text.replace('hts-minphase-comparison','hts-fft-fir-comparison').replace('minphase-fresh','fft-fir-fresh').replace('progress-0066.json','progress-0072.json')
    text=text.replace("METHODS=['native','fir1024']","METHODS=['native','fft_fir']")
    text=text.replace("HERE/'minphase.py'","HERE/'fft_fir.py'").replace("'shape.dylib','minphase.py'","'shape.dylib','fft_fir.py'").replace('from minphase import synthesize as shape_synthesize','from fft_fir import synthesize as shape_synthesize')
    text=text.replace("MECHANISM/'shape.dylib'","MECHANISM/'runtime-bundle/shape.dylib'")
    text=text.replace("digest(MECHANISM/'shape.c')","digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/shape.c')")
    needle="        b.write(HERE/'controller.py',controller.encode(),j)"
    changes='''        controller=controller.replace("    state=Budget().snapshot();c=state['campaigns'][NAME]", "    env=dict(env)\\n    if '--engine' not in command:env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')\\n    state=Budget().snapshot();c=state['campaigns'][NAME]")
'''
    assert text.count(needle)==1;text=text.replace(needle,changes+needle)
    text=text.replace('原HTSと最小位相FIRの表現を比較し、','原HTSと固定長FFT FIRの表現を比較し、')
    ast.parse(text);path=ROOT/'hts_fft_fir_comparison_20261008.py';b.write(path,text.encode())
    b.save(ROOT/'fft-fir-comparison-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),FFT_module_sha256=digest(MECHANISM/'fft_fir.py'),IR_length=2048,output_waves=64,render_including_helpers=294,old_results_unchanged=True,quality_goal_completed=False))
    close=(ROOT/'hts_minphase_closeout_20261008.py').read_text()
    close=close.replace('hts_minphase_comparison_20261008','hts_fft_fir_comparison_20261008').replace('progress-0067.json','progress-0073.json').replace('hts-minphase-comparison-completed','hts-fft-fir-comparison-completed')
    close=close.replace('fir1024','fft_fir').replace('from minphase import kernel','from fft_fir import kernel').replace('N=8192','N=16384').replace('reference[1024:]','reference[2048:]').replace('IR_length=1024','IR_length=2048')
    close=close.replace("digest(MECHANISM/'shape.dylib')","digest(MECHANISM/'runtime-bundle/shape.dylib')").replace("digest(MECHANISM/'shape.c')","digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/shape.c')")
    close=close.replace("with b.workspace(j,'全frame FIR検証の科学ライブラリ初期化') as (_,env):", "with b.workspace(j,'全frame FIR検証の科学ライブラリ初期化') as (_,env):\n            env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')")
    close=close.replace('有限8192grid','有限16384grid').replace('FIRは1024点','FIRは2048点').replace('MCP-FFT-causal-FIR1024','MCP-FFT-causal-FIR2048')
    close=close.replace("'有限grid応答と参考IR tail'", "'有限16384grid応答と参考2048IR tail'")
    ast.parse(close);closepath=ROOT/'hts_fft_fir_closeout_20261008.py';b.write(closepath,close.encode())
    b.save(ROOT/'fft-fir-closeout-source-derivation.json',dict(parent_sha256=digest(ROOT/'hts_minphase_closeout_20261008.py'),controller_sha256=digest(closepath),all_MCP_frames_checked=True,IR_length=2048,FFT_grid=16384,old_33_group_function_unchanged=True,old_results_unchanged=True))
    print('2048点FFT FIRの二方式64波形と全frame終了判定を構築',flush=True)

if __name__=='__main__':
    main()
