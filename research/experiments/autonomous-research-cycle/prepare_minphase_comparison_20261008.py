"""機構資格済みのFIRを、原HTSと新日本語64波形で比較する独立契約へ展開する。"""
import ast
from pathlib import Path
from budget import ROOT,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

MECHANISM=ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1'
POOL=dict(candidate_pool_short=['小箱に石を並べる。','階段の端に座る。','布を机に広げる。','椅子の脚を拭く。','畑で豆を摘む。','鍵を紐に通す。','池に雲が映る。','窓の外で鈴が鳴る。'],
 candidate_pool_long=['午後の授業が終わると、少年は鞄を持って図書室へ向かった。','風が止んだ頃、祖母は庭に干していた布を丁寧に畳んだ。','坂の途中にある店で、兄は夕食に使う野菜を選んでいた。','雨の降る朝、母は玄関に置いた長靴の泥を洗い落とした。','森の入口で道を確かめてから、父は山頂を目指して歩き出した。','川沿いの道を走っていた弟が、橋の手前で友人を見つけた。','夕日が海に沈むまで、姉は砂浜に残った貝殻を集めていた。','駅に着いた旅人は、壁に掛かった時計を見てほっと息をついた。'])

SYNTHESIS=r'''
def synthesize(params,settings,method):
    import hashlib
    from scipy import signal
    if method=='native':out,tr=raw(params,settings,'native');calls=1
    elif method=='fir1024':out,tr,unused_native=fir_raw(params,settings);calls=2
    else:raise ValueError('未登録の最小位相比較方式')
    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA' if method=='native' else 'MCP-minimum-phase-causal-FIR1024',filter_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,original_excitation_noise_LPF_unchanged=True,
        periodic_source_delay_samples=0,render_calls_including_internal_MLSA=calls,
        FIR_length=1024 if method=='fir1024' else None,
        interpolation='前frame/current IRの出力時刻crossfade j/240。MLSA b補間とは別表現。' if method=='fir1024' else 'HTS原b係数補間',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
'''

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='同じMCP/LF0/LPFと原HTS実励振を使う1024点最小位相FIRは、Pade-MLSA原nativeの内容/固定支持/工学制御を新日本語入力で保てるか。有限IRとIR補間を含む経路変更を比較する。',
        variants=['native','fir1024'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='原HTS Pade-MLSA alpha=.55の完全一致対照',fir1024='MCP35→freqt(-.55)の通常cepstrum1024→c2ir1024。前frame/current IRをj/240補間し、過去の原HTS励振へ因果畳み込み。'),
        effective_alpha=dict(native=.55,fir1024=.55),
        fixed_control='全方式の校正LF0・MCP/LPF/duration/state/MSD/variance・源period/counter/event/全sample励振をbyte固定。波形gain.25・24k resample・12ms fade・alpha.55・volume1も固定。FIRはb補間と同一とは呼ばない。',
        normalization='c0を含むMCPと原sqrt(period)源を保護。周波数帯/波形別の利得救済なし。',
        input='新16文×2条件×2方式=64。全履歴文章/ラベル非衝突を出力前確認。P5本文を読まない。',
        source=dict(url=PAPER,related_url='https://sp-nitech.github.io/sptk/latest/main/c2mpir.html',mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),scope='人工MCPの機構資格を同じC binary/kernel/filterで引き継ぐ。実MCP/音声/知覚の資格は別に調べる。'),
        support='原nativeから一度固定。欠測を除外せず全候補で保持。旧支持/欠測249/旧判定は不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上を全件。短窓/動的/知覚の資格にはしない。',content='固定二ASR各33群で原native以下。群ごとの悪化を相殺しない。',independence='全64通常/隔離・CLI4と実読取/通信拒否。',FIR_mechanism='全32nativeの全保存MCP frameで8192FFTの解析複素応答に対する1024IRの最大相対誤差≤1e-3、8192点参考IRの1024以降tailエネルギー割合≤1e-6。全frame検査。有限grid/tailであり連続全域や知覚truthではない。'),
        estimates=dict(comparison_render=96,comparison_output_waves=64,internal_MLSA_helpers=32,comparison_dsp=192,isolation_render=192,isolation_dsp=128,CLI_render=6,CLI_dsp=4,fixture_render=0,inherited_fixture=True,all_frame_FIR_dsp=64,two_ASR_ai=128,total_without_retry=dict(render=294,dsp=388,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_minphase_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        new_route_not_alpha_or_pulse_coefficient_rescue=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

def main():
    b=Budget();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    parent=ROOT/'hts_filter_warp_20261008.py';text=parent.read_text()
    for name,v in [('C_SOURCE',(MECHANISM/'shape.c').read_text()),('WRAPPER',(MECHANISM/'shape_arrays.py').read_text()),('FIXTURE','機構fixtureは同一C binaryで終了済み。別音声生成を再試行せずhashで引き継ぐ。')]:text=constant(text,name,"r'''"+v+"'''")
    text=constant(text,'POOL',repr(POOL))
    tree=ast.parse(text);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call))
    text=text.replace(ast.get_source_segment(text,node),REGISTRATION)
    text=text.replace('hts-filter-warp','hts-minphase-comparison').replace('filter-warp-fresh','minphase-fresh').replace('progress-0058.json','progress-0066.json')
    text=constant(text,'PAPER',repr('https://sp-nitech.github.io/sptk/latest/main/freqt.html'))
    text=text.replace('共有HTSのフィルタ周波数軸だけを変更し、','原HTSと最小位相FIRの表現を比較し、')
    text=text.replace("METHODS=['native','alpha_low','alpha_high']","METHODS=['native','fir1024']")
    a="\n@contextmanager\ndef job(";text=text.replace(a,"\nMECHANISM=ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1'\nMINPHASE="+repr((MECHANISM/'minphase.py').read_text()+SYNTHESIS)+a)
    text=text.replace("b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j)","b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j);b.write(HERE/'minphase.py',MINPHASE.encode(),j)")
    text=text.replace(".replace('192','96').replace('576','288').replace('385','193').replace('388','196')",".replace('192','64').replace('576','192').replace('385','129').replace('388','132')")
    text=text.replace(".replace('192','96')",".replace('192','64')")
    needle="        b.write(HERE/'controller.py',controller.encode(),j)"
    changes='''        controller=controller.replace('    count=64\\n    dsp=192','    count=96\\n    dsp=192')
        controller=controller.replace("'通常/隔離batch64 ' + mode, count=64", "'通常/隔離batch64 ' + mode, count=96")
        controller=controller.replace("'CLI ' + mode + '/' + request['id'], reserve_bytes=", "'CLI ' + mode + '/' + request['id'], count=1 if request['method']=='native' else 2, reserve_bytes=")
        controller=controller.replace('new_render_calls=64,\\n        new_DSP_calls=192', 'new_render_calls=96, internal_MLSA_helpers=32, output_waves=64,\\n        new_DSP_calls=192')
        controller=controller.replace('new_render_calls=132, new_DSP_calls=132','new_render_calls=198, new_DSP_calls=132, internal_MLSA_helpers=66')
        controller=controller.replace("                    records = {}", "                    assert sum(r['conversion']['render_calls_including_internal_MLSA'] for r in manifest['records']) == 96\\n                    records = {}")
'''
    assert text.count(needle)==1;text=text.replace(needle,changes+needle)
    text=text.replace('from shape_arrays import synthesize as shape_synthesize','from minphase import synthesize as shape_synthesize')
    text=text.replace("('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib')","('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib','minphase.py')")
    text=text.replace("expected_records=96","expected_records=64")
    start=text.index("        with b.workspace(j,'clang専用cacheと中間物'")
    end=text.index("        bundle=HERE/'runtime-bundle'",start)
    replacement='''        assert read(MECHANISM/'fixture-audit.json')['passed']
        b.write(HERE/'shape.dylib',(MECHANISM/'shape.dylib').read_bytes(),j)
        assert digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(HERE/'shape.dylib'),source_sha256=digest(HERE/'shape.c'),inherited_binary_exact=True,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),new_compilation=False),j)
'''
    text=text[:start]+replacement+text[end:]
    start=text.index("    if stage=='fixture':",text.index('def run('));end=text.index('    else:',start)
    text=text[:start]+'''    if stage=='fixture':
        with job(b,'audit','同一C機構資格のhash照合と追補',size=1000000) as j:
            assert digest(HERE/'shape.dylib')==digest(MECHANISM/'shape.dylib')
            assert digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')
            b.save(HERE/'fixture-audit.json',dict(read(MECHANISM/'fixture-audit.json'),inherited=True,original_sha256=digest(MECHANISM/'fixture-audit.json'),new_render=0,new_dsp=0),j)
'''+text[end:]
    text=text.replace('登録commit/push→fixture→96新入力比較→通常/隔離/CLI→二ASR→全件集計/封印','登録commit/push→機構hash照合→64波形比較（内部helper別計数）→通常/隔離/CLI→二ASR→全MCP応答監査/封印')
    text=text.replace('render=1000,dsp=4000,ai=576','render=1000,dsp=4000,ai=384')
    text=text.replace('原励振固定・フィルタ周波数軸・全比較費','原励振固定・最小位相FIR・全比較費')
    ast.parse(text);path=ROOT/'hts_minphase_comparison_20261008.py';b.write(path,text.encode())
    b.save(ROOT/'minphase-comparison-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),C_binary_reused_exact=True,methods=2,output_waves=64,render_including_helpers=294,old_results_unchanged=True,quality_goal_completed=False))
    print('原HTS/最小位相FIRの二方式64波形の初出力前ソースを構築',flush=True)

if __name__=='__main__':main()
