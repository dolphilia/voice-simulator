"""利得分離の機構資格を固定し、新16文の三方式比較と全件終了監査を構築する。"""
import ast
import re
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

MECHANISM=ROOT/'campaigns/nas-hts-fir-gain-mechanism-20261008-v1'
PREVIOUS=ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1'
POOL=dict(candidate_pool_short=['青磁の皿を洗う。','銀杏の殻を割る。','絹糸の端を結ぶ。','暖炉の薪を足す。','葡萄の房を持つ。','書棚の埃を払う。','木靴の底を直す。','麦茶の瓶を冷やす。'],
 candidate_pool_long=['木の橋を渡った先で、叔父は荷物を下ろして川の流れを眺めた。','夕方の台所から香りが漂い、妹は窓を閉めて食卓の椅子を並べた。','海辺の道を進んでいると、友人が白い貝殻を拾って私に見せた。','畑の隅で作業を終えた祖父は、手袋を外して井戸の水で手を洗った。','曇り空の下を歩きながら、姉は明日の予定を一つずつ話してくれた。','倉庫の奥から道具を運び出し、父は壊れた扉の蝶番を取り替えた。','坂道を登った少年は、花の咲く庭を見つけて足を止めた。','夕食の片付けが済むと、母は机に向かって短い手紙を書き始めた。'])

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='全体IRの算術補間と対数利得分離補間を新日本語で切り分け、原nativeの内容/固定支持/工学制御を守れるか。',
        variants=['native','fft_fir','fft_loggain'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='原HTS Pade-MLSA alpha=.55完全一致対照',fft_fir='解析IR2048の全利得込み算術出力crossfade j/240',fft_loggain='IR/exp(b0)形状の算術補間×exp(線形補間b0)。b0=polyval(-.55,MCP)。'),
        effective_alpha=dict(native=.55,fft_fir=.55,fft_loggain=.55),IR_length=2048,FFT_length=16384,
        fixed_control='校正LF0・全MCP/LPF/duration/state/MSD/variance・源period/counter/event/実励振をbyte固定。sqrt(period)、gain.25、resample24k、12ms fade、volume1、因果参照・ゼロ追加遅延を保持。MLSA状態/全b補間との同一性は主張しない。',
        normalization='入力MCPと励振を保持。解析式b0のみを使い、波形別gain救済なし。',
        input='未使用16文×2条件×3方式=96。全履歴文章/ラベル非衝突を出力前確認。P5本文は読まない。',
        source=dict(url='https://sp-nitech.github.io/sptk/latest/main/mc2b.html',related_url='https://sp-nitech.github.io/sptk/latest/main/mglsadf.html',mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),previous_speech_seal_sha256=digest(ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1/artifact-seal.json')),
        support='原nativeから一度固定し、欠測を除外せず二候補全件へ保持。旧249欠測/旧判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上を全件。短窓/動的/知覚資格へ一般化しない。',content='二固定ASR各33群で原native以下。群間/方式間の悪化相殺なし。',independence='全96通常/隔離・CLI4と実読取/通信拒否。',FIR_mechanism='全32nativeの全MCP frameで16384gridの複素応答相対誤差≤1e-3、参考IR2048以降tail energy割合≤1e-6。保存三方式列の全64対を物理照合。'),
        CPU_limits='生成/測定/隔離子のBLAS/VECLIB/OMP=1。二ASRの明示threads4/2と環境は既存契約を引継ぐ。',
        estimates=dict(comparison_render=160,comparison_output_waves=96,internal_MLSA_helpers=64,comparison_dsp=288,isolation_render=320,isolation_dsp=192,CLI_render=6,CLI_dsp=4,fixture_render=0,inherited_fixture=True,all_frame_FIR_dsp=96,two_ASR_ai=192,total_without_retry=dict(render=486,dsp=580,ai=192),maximum_seconds=11000,external_peak=800000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_fir_gain_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        stop_rule='FIR経路は1024/2048の既不通過を引継ぐ。この三回目でも全件保護不通過なら同補間・係数救済は封印し、別測定資格へ進む。',
        old_FIR_failures_kept=True,new_route_does_not_qualify_perception=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

def numbers(text,mapping):
    return re.sub(r'(?<![A-Za-z0-9_])(?:'+ '|'.join(str(v) for v in mapping)+r')(?![A-Za-z0-9_])',lambda m:str(mapping[int(m[0])]),text)

def main():
    b=Budget();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert read(MECHANISM/'aggregate-summary.json')['mechanical_fixture_passed']
    parent=ROOT/'hts_fft_fir_comparison_20261008.py';text=parent.read_text()
    text=constant(text,'MINPHASE',repr((MECHANISM/'fft_fir.py').read_text()));text=constant(text,'POOL',repr(POOL))
    text=constant(text,'MECHANISM',"ROOT/'campaigns/nas-hts-fir-gain-mechanism-20261008-v1'")
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call))
    text=text.replace(ast.get_source_segment(text,node),REGISTRATION)
    text=text.replace('hts-fft-fir-comparison','hts-fir-gain-comparison').replace('fft-fir-fresh','fir-gain-fresh').replace('progress-0072.json','progress-0076.json')
    text=text.replace("METHODS=['native','fft_fir']","METHODS=['native','fft_fir','fft_loggain']")
    start=text.index("        controller=(BASE/'controller.py')");end=text.index("        b.write(HERE/'controller.py'",start)
    controller=(PREVIOUS/'controller.py').read_text().replace('fft-fir-fresh','fir-gain-fresh')
    controller=numbers(controller,{64:96,96:160,192:288,198:326,132:196,129:193,32:64,66:130}).replace('batch64','batch96').replace('ASR64','ASR96').replace('隔離64組','隔離96組')
    ast.parse(controller);text=text[:start]+'        controller='+repr(controller)+'\n'+text[end:]
    # 検査済み別版を使い、base64等の識別子は置換しない。
    text=text.replace("text=(BASE/name).read_text().replace('192','64')", "text=(ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1'/name).read_text()\n            if name in ('asr_worker.py','runtime_batch.py'):text=re.sub(r'(?<![A-Za-z0-9_])64(?![A-Za-z0-9_])','96',text)")
    text=text.replace('import ast\n','import ast\nimport re\n',1)
    text=text.replace('expected_records=64','expected_records=96').replace('→64波形比較','→96波形三方式比較')
    ast.parse(text);path=ROOT/'hts_fir_gain_comparison_20261008.py';b.write(path,text.encode())
    close=(ROOT/'hts_fft_fir_closeout_20261008.py').read_text().replace('hts_fft_fir_comparison_20261008','hts_fir_gain_comparison_20261008').replace('progress-0073.json','progress-0077.json').replace('hts-fft-fir-comparison-completed','hts-fir-gain-comparison-completed')
    close=close.replace("with np.load(base/'fft_fir.npz',allow_pickle=False) as z:\n        assert all(np.array_equal(z[k],v) for k,v in native.items())", "for method in ('fft_fir','fft_loggain'):\n        with np.load(base/(method+'.npz'),allow_pickle=False) as z:\n            assert all(np.array_equal(z[k],v) for k,v in native.items())")
    close=close.replace('render=0,dsp=64','render=0,dsp=96').replace("64,20000000,600)","96,20000000,600)")
    close=close.replace("len(manifest['rows'])==64 and len(runtime['pairs'])==64", "len(manifest['rows'])==96 and len(runtime['pairs'])==96")
    close=close.replace("manifest['new_render_calls']==96 and runtime['new_render_calls']==198", "manifest['new_render_calls']==160 and runtime['new_render_calls']==326")
    close=close.replace("asr_manifest['new_ai']==64", "asr_manifest['new_ai']==96")
    start=close.index("                key=row['id']+'/'+condition+'/';a=records[key+'native'];z=records[key+'fft_fir']")
    end=close.index('        assert len(pairs)==32',start)
    block=close[start:end].replace(";z=records[key+'fft_fir']", "\n                for method in ('fft_fir','fft_loggain'):\n                    z=records[key+method]")
    lines=block.splitlines();lines=[line if i<3 else '    '+line for i,line in enumerate(lines)]
    block='\n'.join(lines)+'\n';block=block.replace("key+'fft_fir'",'key+method')
    close=close[:start]+block+close[end:]
    close=close.replace('assert len(pairs)==32','assert len(pairs)==64').replace('summary=dict(total=64','summary=dict(total=96')
    close=close.replace("next='FIRの全実MCP応答と音声の工学/二ASR保護を区別し、不通過は全件で保持する。有効な範囲から時間表現または共有生成制御の別要因へ進む。'", "next='FIR三回目の全件保護不通過を保持し同補間/係数救済を封印。6件レビュー後、YIN型の短窓/動的/境界測定を別契約で資格検証する。' if not any(research_gates[m] for m in ('fft_fir','fft_loggain')) else '全件保護を満たす範囲から独立した知覚資格の取得へ進む。'")
    close=close.replace("lines=['# 原HTSと最小位相因果FIRの比較'", "lines=['# 原HTSと二つのFIR利得補間の比較'")
    close=close.replace('新16日本語文×2条件×2方式の64波形。全32対','新16日本語文×2条件×3方式の96波形。全64対').replace('原nativeとの全64通常/隔離','原nativeとの全96通常/隔離')
    close=close.replace('FIRは2048点の因果IRと出力時刻のIR補間を使い','FIRは2048点の因果IRで全体利得込み算術補間と対数利得分離補間を比較し')
    close=close.replace('源の時計と原励振の一致は','対数利得分離は波形からの利得推定ではなくMCPのb0式を使う。源の時計と原励振の一致は')
    ast.parse(close);closepath=ROOT/'hts_fir_gain_closeout_20261008.py';b.write(closepath,close.encode())
    b.save(ROOT/'fir-gain-comparison-source-derivation.json',dict(parent_sha256=digest(parent),previous_controller_sha256=digest(PREVIOUS/'controller.py'),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),closeout_sha256=digest(closepath),module_sha256=digest(MECHANISM/'fft_fir.py'),methods=3,output_waves=96,total_without_retry=dict(render=486,dsp=580,ai=192),physical_parameter_pairs=64,old_results_unchanged=True))
    print('利得二表現と原HTSの96波形・全件終了判定を構築',flush=True)

if __name__=='__main__':main()
