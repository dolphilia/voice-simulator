"""固定オールパス源の人工資格を保持し、未使用日本語64波形へ別版で展開する。"""
import ast
import re
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

MECHANISM=ROOT/'campaigns/nas-hts-allpass-mechanism-20261008-v1'
POOL=dict(candidate_pool_short=['緑の豆を煮込む。','革の鞄を拭く。','櫛で髪を梳かす。','鍵穴の砂を除く。','葦の茎を折る。','蝋燭の芯を切る。','青い襟を縫う。','豆腐の水を切る。'],
 candidate_pool_long=['石畳の角を曲がると、隣人が花に水をやっている姿が見えた。','昼過ぎに届いた小包を、兄は机の上でゆっくり開いた。','山道の途中で休んでいると、森の奥から涼しい風が吹いてきた。','夕暮れの河原を歩いた後、姉と私は橋のそばで少し話をした。','家の前に積もった雪を除けながら、父は空の様子を何度も確かめた。','売り場で野菜を選び終えると、祖母は籠を持って出口へ向かった。','雨が強くなる前に、弟は庭の椅子を屋根の下へ運び込んだ。','古い地図を広げた叔母は、指で道をなぞりながら旅の話を続けた。'])

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='原MCP/LPF/LF0と励振時計を固定し、LPF後の振幅1位相処理が新日本語の原native保護に与える因果効果を検証する。',
        variants=['native','allpass'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='原HTSの純観測・完全一致対照',allpass='元get_excitationを一度だけ呼び、LPF後の全periodic/noiseにpole.95オールパスを適用。発話頭状態0。'),
        source_rule='y[n]=.95*y[n-1]+x[n-1]-.95*x[n]。原励振/period/counter/eventはbyte保護し、実処理励振は意図して変更。振幅1はLTI解析式の性質で、非定常MLSA後の振幅/有限音声エネルギー保存とは呼ばない。',
        fixed_control='全三stream/duration/MSD/state/variance・相対LF0輪郭と校正中央値・alpha.55/beta0/volume1・元RNG/LPF/sqrt(period)を保持。gain.25/resample24k/12ms fade固定。波形別正規化なし。',
        input='未使用16文×2条件×2方式=64。全履歴文章/ラベル非衝突を出力前照合。P5本文は読まない。',
        source=dict(url='https://ccrma.stanford.edu/~jos/filters/Allpass_Filters.html',mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),scope='安定LTIの解析性質と登録人工機構。自然glottalモデルの再現や日本語知覚資格ではない。'),
        support='nativeで一度固定した全支持を候補へ保持。欠測除外なし。旧支持31,601/欠測249/判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF中央値±1半音、ACF confidence≥.6、固定支持3以上を全件。',content='二ASR各33群を原native以下、悪化相殺なし。',independence='全64通常/隔離・CLI4・資料/通信の実拒否。',mechanism='同一機構bundleの封印hash一致、保存全32対のMCP/LF0/LPF/durationを物理照合。',measurement_scope='旧工学ゲート不変。YIN人工40ms資格を未知HTS/境界/知覚へ移さない。'),
        estimates=dict(comparison_render=64,comparison_dsp=192,isolation_render=128,isolation_dsp=128,CLI_render=4,CLI_dsp=4,fixture_render=0,inherited_fixture=True,physical_pairs_dsp=64,two_ASR_ai=128,total_without_retry=dict(render=196,dsp=388,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_allpass_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        phase_pole=.95,coefficient_search_after_output=False,old_failed_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

PAIR_AUDIT=r'''"""保存した全32対の四列を直接照合する。新波形の再生成なし。"""
import sys,json
from pathlib import Path
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text())
import numpy as np
rows=[]
for row in p['rows']:
 for condition in p['conditions']:
    base=here/'render'/row['id']/condition
    with np.load(base/'native.npz',allow_pickle=False) as z:native={k:z[k].copy() for k in ('mcp','lf0','lpf','duration')}
    with np.load(base/'allpass.npz',allow_pickle=False) as z:assert all(np.array_equal(z[k],v) for k,v in native.items())
    rows.append(dict(id=row['id']+'/'+condition,all_saved_parameters_exact=True,frames_checked=len(native['mcp']),excluded_frames=0,passed=True))
assert len(rows)==32
print(json.dumps(dict(rows=rows,passed=True,pairs_checked=32,all_frames_checked=sum(v['frames_checked'] for v in rows),saved_arrays_only=True,no_wave_resynthesis=True,render=0,dsp=64,quality_certified=False)))
'''

def main():
    b=Budget();assert not b.snapshot()['jobs'] and not b.review_due()['due'];assert read(MECHANISM/'aggregate-summary.json')['mechanical_fixture_passed']
    parent=ROOT/'hts_glottal_shape_20261008.py';text=parent.read_text()
    text=constant(text,'C_SOURCE',repr((MECHANISM/'shape.c').read_text()));text=constant(text,'WRAPPER',repr((MECHANISM/'shape_arrays.py').read_text()));text=constant(text,'FIXTURE',repr('# 先行機構の全fixtureをhash照合で引き継ぐ。追加生成なし。\n'));text=constant(text,'POOL',repr(POOL))
    text=text.replace('from budget import ROOT,read,digest,encode','from budget import ROOT,read,digest,encode')
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call))
    # 前のcampaign参照を持たない登録式なので全体のcampaign名変更で自己参照へ変わらない。
    text=text.replace(ast.get_source_segment(text,node),REGISTRATION)
    text=text.replace('hts-glottal-shape','hts-allpass-comparison').replace('glottal-fresh','allpass-fresh').replace('progress-0049.json','progress-0083.json').replace("METHODS=['native','rosenberg']","METHODS=['native','allpass']")
    text=text.replace("@contextmanager\ndef job(b,kind", "MECHANISM=ROOT/'campaigns/nas-hts-allpass-mechanism-20261008-v1'\n\n@contextmanager\ndef job(b,kind",1)
    start=text.index("        controller=(BASE/'controller.py')");end=text.index("        b.write(HERE/'controller.py'",start)
    controller=(ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1/controller.py').read_text().replace('fft-fir-fresh','allpass-fresh')
    controller=re.sub(r'(?<![A-Za-z0-9_])(?:96|198|32|66)(?![A-Za-z0-9_])',lambda m:str({96:64,198:132,32:0,66:0}[int(m[0])]),controller)
    controller=controller.replace("count=1 if request['method']=='native' else 2",'count=1')
    needle="                    assert meta['conversion']['source_clock_hashes'] == native_meta['conversion']['source_clock_hashes']"
    assert controller.count(needle)==1;controller=controller.replace(needle,needle+"\n                    assert meta['conversion']['original_excitation_sha256'] == native_meta['conversion']['original_excitation_sha256']")
    ast.parse(controller);text=text[:start]+'        controller='+repr(controller)+'\n'+text[end:]
    start=text.index("    with job(b,'setup','新source build");end=text.index("    with job(b,'setup','全履歴",start)
    prepare='''    with job(b,'setup','機構通過した同一binaryと共有bundleを固定',size=16000000) as j:
        assert read(MECHANISM/'fixture-audit.json')['passed']
        assert digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')
        for n in ('HTS_hidden.h','HTS_engine.h','HTS_vocoder_shaped.c'):assert digest(HERE/'vendor'/n)==digest(MECHANISM/'vendor'/n)
        b.write(HERE/'shape.dylib',(MECHANISM/'shape.dylib').read_bytes(),j)
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(HERE/'shape.dylib'),source_sha256=digest(HERE/'shape.c'),inherited_binary_exact=True,new_compilation=False,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json')),j)
        bundle=HERE/'runtime-bundle';mapping={}
        for n in read(BASE/'runtime-bundle/manifest.json')['files']:
            if n.startswith('packages-v2/') or n in ('world_renderer2.py','LICENSE-WORLD.txt','runtime.py','runtime_batch.py'):continue
            mapping[n]=BASE/'runtime-bundle'/n
        mapping.update({n:MECHANISM/'runtime-bundle'/n for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib')})
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib')})
        for n,source in mapping.items():b.write(bundle/n,source.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
'''
    text=text[:start]+prepare+text[end:]
    start=text.index("    if stage=='fixture':");end=text.index('    else:\n        assert read',start)
    text=text[:start]+'''    if stage=='fixture':
        with job(b,'audit','先行オールパス機構の全hashを継承',size=2000000) as j:
            for n,h in read(MECHANISM/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
            assert digest(HERE/'shape.dylib')==digest(MECHANISM/'shape.dylib')
            b.save(HERE/'fixture-audit.json',dict(read(MECHANISM/'fixture-audit.json'),inherited=True,original_sha256=digest(MECHANISM/'fixture-audit.json'),new_render=0,new_dsp=0),j)
'''+text[end:]
    ast.parse(text);path=ROOT/'hts_allpass_comparison_20261008.py';b.write(path,text.encode())
    close=(ROOT/'hts_fft_fir_closeout_20261008.py').read_text().replace('hts_fft_fir_comparison_20261008','hts_allpass_comparison_20261008').replace('progress-0073.json','progress-0084.json').replace('hts-fft-fir-comparison-completed','hts-allpass-comparison-completed')
    close=constant(close,'ALL_FRAMES',repr(PAIR_AUDIT));close=close.replace('fft_fir','allpass')
    close=close.replace("manifest['new_render_calls']==96 and runtime['new_render_calls']==198", "manifest['new_render_calls']==64 and runtime['new_render_calls']==132")
    close=close.replace("digest(MECHANISM/'runtime-bundle/shape.dylib')","digest(MECHANISM/'shape.dylib')").replace("digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/shape.c')","digest(MECHANISM/'shape.c')")
    close=close.replace('全実MCP frameの解析応答・finite IR tailと保存列照合','保存全32対のMCP/LF0/LPF/duration物理照合').replace('全frame FIR検証の科学ライブラリ初期化','全保存パラメータ対の科学ライブラリ初期化')
    close=close.replace("and z['meta']['conversion']['periodic_source_delay_samples']==0", "and z['meta']['conversion']['source_allpass_pole']==.95")
    close=close.replace("z['meta']['conversion']['render_calls_including_internal_MLSA']==2","z['meta']['conversion']['render_calls_including_internal_MLSA']==1")
    needle="                assert a['meta']['conversion']['source_clock_hashes']==z['meta']['conversion']['source_clock_hashes'] and a['measurement']['support']==z['measurement']['support']"
    assert close.count(needle)==1;close=close.replace(needle,needle+"\n                assert a['meta']['conversion']['original_excitation_sha256']==z['meta']['conversion']['original_excitation_sha256']\n                assert z['meta']['conversion']['processed_excitation_intentionally_changed']")
    close=close.replace('excitation_and_cycle_clock_exact=True','original_excitation_and_cycle_clock_exact=True,processed_excitation_is_intended_factor=True')
    close=close.replace('real_MCP_grid_audit=physical','physical_parameter_audit=physical').replace('filter_factor_pairs=pairs','source_factor_pairs=pairs')
    close=close.replace("methodological_limits='固定DIO/全体ACF診断と有限grid応答。短窓/動的/瞬時F0/知覚/連続全周波数への資格ではない。'", "methodological_limits='原工学DIO/全体ACFと人工オールパスLTI資格。人工YIN40ms資格をHTSや知覚へ拡張しない。'")
    close=close.replace("next='FIRの全実MCP応答と音声の工学/二ASR保護を区別し、不通過は全件で保持する。有効な範囲から時間表現または共有生成制御の別要因へ進む。'", "next='源の位相因子と振幅/内容保護を全件で保持する。不通過を同コホートのpole調整で救済せず、別の共有生成制御または独立測定へ進む。'")
    start=close.index("        lines=['# 原HTS");end=close.index("        b.write(HERE/'report.md'",start)
    report='''        lines=['# 原HTSとLPF後オールパス励振の比較','','新16文×2条件×2方式の64波形。原MCP/LF0/LPF/duration、原励振と源時計を保持し、候補の処理励振だけpole.95の周波数依存位相を変更した。全32対の保存列、全64通常/隔離、CLI4と実読取/通信拒否を照合した。','','|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['',f'保存した全{physical["all_frames_checked"]}frameの三streamとdurationを照合した。源時計・原励振一致は処理後音響pitchや自然さのtruthではない。','',
            '振幅1は安定LTIの解析性質であり、非定常MLSA出力や有限音声のエネルギー保存を保証しない。固定poleの調整で不通過を救済しない。YINの人工40ms資格もこの未知HTSへ移さない。',
            '', '旧31方式・支持31,601・欠測249・二ASR各33群の判定、FIRなどの封印経路を保持する。日本語知覚資格なし・P5未開封・品質未達。候補は最終採択しない。',
            '', '一次資料: [Julius O. Smith, Allpass Filters](https://ccrma.stanford.edu/~jos/filters/Allpass_Filters.html)。', '', '全件研究保護: '+str(research_gates),summary['next'],'']
'''
    close=close[:start]+report+close[end:]
    close=close.replace("dict(all_MCP_frames=physical['all_frames_checked'],grid_passed=physical['passed'],research_protection_gates=research_gates)","dict(parameter_pairs=physical['pairs_checked'],research_protection_gates=research_gates)")
    ast.parse(close);closepath=ROOT/'hts_allpass_closeout_20261008.py';b.write(closepath,close.encode())
    b.save(ROOT/'allpass-comparison-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),source_sha256=digest(path),closeout_sha256=digest(closepath),mechanism_source_sha256=digest(MECHANISM/'shape.c'),mechanism_wrapper_sha256=digest(MECHANISM/'shape_arrays.py'),output_waves=64,total_without_retry=dict(render=196,dsp=388,ai=128),actual_processed_source_intentionally_changed=True,original_excitation_and_clock_protected=True,old_results_unchanged=True))
    print('固定オールパス励振の新日本語64波形と全件終了監査を構築',flush=True)

if __name__=='__main__':main()
