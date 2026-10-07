"""登録済みvocoder×LF0比較の実装だけを生成前に保存する。"""
from pathlib import Path
import sys,re,ast
ROOT=Path(__file__).resolve().parent
PREV=ROOT/'campaigns/nas-voicing-ap-20261008-v1'
sys.path.insert(0,str(PREV))
from paths import Budget,SOURCE,REPO
from budget import read,digest,encode
HERE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1';NAME='vocoder-f0-v1'
b=Budget();b.recover()
assert read(HERE/'registration.json')['variants']==['native','calibrated','voicing','hts_native','hts_calibrated','hts_voicing']
files={}
files['paths.py']=(PREV/'paths.py').read_text().replace("NAME = 'voicing-ap-v1'","NAME = 'vocoder-f0-v1'").replace("PREVIOUS = ROOT / 'campaigns/nas-absolute-f0-20261008-v1'","PREVIOUS = ROOT / 'campaigns/nas-voicing-ap-20261008-v1'").replace('有声補完・非周期成分実験','vocoder・LF0実験')
files['temporary_storage.py']=(PREV/'temporary_storage.py').read_text().replace("owner = 'voicing-ap-'","owner = 'vocoder-f0-'")
files['measurement.py']=(PREV/'measurement.py').read_text()
files['controls_v2.py']=(PREV/'controls_v2.py').read_text()
files['asr_worker.py']=re.sub(r'\b160\b','192',(PREV/'asr_worker.py').read_text()).replace('160音声','192音声').replace('160件','192件')
p=(PREV/'prepare.py').read_text().replace('voicing-ap-candidate-pool-0001','vocoder-f0-candidate-pool-0001').replace("('runtime.py', 'runtime_batch.py', 'controls.py', 'voicing_world.py')","('runtime.py', 'runtime_batch.py', 'controls_v2.py', 'hts_arrays.py', 'hts_arrays.c', 'hts_arrays.dylib')")
p=p.replace("        mapping['calibration.py']","        mapping['HTS-BSD-NOTICE.txt']=HERE/'HTS-BSD-NOTICE.txt'\n        mapping['calibration.py']")
p=p.replace("expected_records=160","expected_records=192").replace("'vap-fresh-'","'voc-fresh-'").replace("fill_rule=reg['voicing_rule'], AP_rule=reg['AP_rule'],","fill_rule=reg['fill_rule'], renderer_rule=reg['factor_rules'], AP_noise_power_factor=1.,").replace("source_AP_commit=reg['AP_source_commit']","renderer=['WORLD','HTS-pulse-noise-MLSA']")
files['prepare.py']=p
c=(PREV/'controller_v4.py').read_text();start=c.index('def verify():');end=c.index('\n\ndef requests():',start)
c=c[:start]+"""def verify():
    contract=read(HERE/'execution-contract.json')
    assert digest(HERE/'protocol.json')==contract['protocol_sha256']
    assert digest(HERE/'registration.json')==contract['registration_sha256']
    assert digest(HERE/'runtime-bundle/manifest.json')==contract['runtime_manifest_sha256']
    for name,expected in contract['source_hashes'].items(): assert digest(HERE/name)==expected,name
    return contract
"""+c[end:]
c=c.replace('runtime-bundle-v2','runtime-bundle').replace('runtime_batch_v4.py','runtime_batch.py').replace('controller_v4.py','controller.py').replace('vap-fresh-00','voc-fresh-00')
for old,new in [('160','192'),('480','576'),('321','385'),('324','388')]:c=re.sub(r'\b'+old+r'\b',new,c)
c=c.replace('batch160','batch192').replace('ASR160','ASR192').replace('160件','192件').replace('隔離160組','隔離192組')
start=c.index("                if method in ['aperiodicity', 'combined']:");end=c.index("                by_method[method]=meta",start)
c=c[:start]+"""                if method.startswith('hts_'):
                    reference=by_method[method[4:]]
                    assert meta['output_parameter_hashes']==reference['output_parameter_hashes']
                    assert meta['generated_lf0_median_hz']==reference['generated_lf0_median_hz']
                    assert meta['conversion']['input_streams_unchanged']
"""+c[end:]
c=c.replace("choices=['test', 'fixture', 'comparison', 'isolate', 'asr',\n        'fixture-worker', 'comparison-worker']","choices=['comparison', 'isolate', 'asr', 'comparison-worker']").replace("    if args.stage != 'test':\n        verify()","    verify()")
start=c.index('def test():');end=c.index('def comparison_worker(',start)
c=c[:start]+c[end:]
c=c.replace("    if args.stage == 'test':\n        test()\n    elif args.stage in ['fixture', 'comparison']:\n        computation(args.stage)","    if args.stage == 'comparison':\n        computation(args.stage)")
c=c.replace("    count = 2 if stage == 'fixture' else 192\n    dsp = 4 if stage == 'fixture' else 576","    count=192\n    dsp=576")
files['controller.py']=c
r=(PREV/'runtime-bundle-v2/runtime.py').read_text().replace("from voicing_world import synthesize","from world_renderer2 import synthesize as world_synthesize\nfrom hts_arrays import synthesize as hts_synthesize").replace("from controls_v2 import transform, METHODS","from controls_v2 import transform\nMETHODS=['native','calibrated','voicing','hts_native','hts_calibrated','hts_voicing']")
r=r.replace("transform(method,native","transform(method[4:] if method.startswith('hts_') else method,native")
r=r.replace("        raw,conversion=synthesize(params,settings,control['AP_noise_power_factor'])","""        assert control['AP_noise_power_factor']==1.
        if method.startswith('hts_'):
            raw,conversion=hts_synthesize(params,settings)
        else:
            raw,conversion=world_synthesize(params,settings)
            conversion.update(renderer='WORLD',AP_noise_power_factor=1.,input_streams_unchanged=True)""")
r=r.replace('生成LF0補完と有声APの2要因を固定制御する','同じ生成LF0制御をWORLDとHTSに渡す')
files['runtime.py']=r
files['runtime_batch.py']=(PREV/'runtime-bundle-v2/runtime_batch_v4.py').read_text().replace('assert len(rows) == 160','assert len(rows) == 192')
files['hts_arrays.c']=r'''/* 対応版HTSヘッダと既存vocoderを使う全フレーム配列入口。BSD通知を同梱。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stddef.h>
#include <string.h>
int hts_arrays_render(const double *mcp,const double *lf0,const double *lpf,
                      size_t frames,size_t nmcp,size_t nlpf,double *out,size_t samples) {
    if (!mcp || !lf0 || !lpf || !out || frames<1 || frames>6000 ||
        nmcp!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240) return 0;
    for (size_t f=0;f<frames;f++) {
        if (!isfinite(lf0[f]) || (lf0[f]!=LZERO && (exp(lf0[f])<70 || exp(lf0[f])>800))) return 0;
        for (size_t j=0;j<nmcp;j++) if (!isfinite(mcp[f*nmcp+j])) return 0;
        for (size_t j=0;j<nlpf;j++) if (!isfinite(lpf[f*nlpf+j])) return 0;
    }
    HTS_Vocoder v;
    HTS_Vocoder_initialize(&v,nmcp-1,0,FALSE,48000,240);
    for (size_t f=0;f<frames;f++) {
        double mc[35],lp[63];
        memcpy(mc,mcp+f*nmcp,nmcp*sizeof(double));
        memcpy(lp,lpf+f*nlpf,nlpf*sizeof(double));
        HTS_Vocoder_synthesize(&v,nmcp-1,lf0[f],mc,nlpf,lp,.55,0.,1.,out+f*240,NULL);
    }
    HTS_Vocoder_clear(&v);
    for (size_t i=0;i<samples;i++) if (!isfinite(out[i])) return 0;
    return 1;
}
'''
files['hts_arrays.py']='''"""生成3streamをHTS pulse/noise MLSAへ直接渡す非ニューラル配列入口。"""
import ctypes as C
from pathlib import Path
import hashlib
import numpy as np
from scipy import signal
import local_renderer  # 対応版pyopenjtalk HTS symbolsをRTLD_GLOBALで初期化
_lib=C.CDLL(str(Path(__file__).resolve().parent/'hts_arrays.dylib'))
_fn=_lib.hts_arrays_render
P=C.POINTER(C.c_double);S=C.c_size_t
_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,P,S]
def ah(x): return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def validated(params,settings):
    if len(params)!=3: raise ValueError('生成3stream必須')
    x=[np.ascontiguousarray(v,dtype=np.float64) for v in params]
    if any(v.ndim!=2 or not v.size or not np.isfinite(v).all() for v in x):
        raise ValueError('有限非空の2D配列を要求')
    if len({len(v) for v in x})!=1 or not 1<=len(x[0])<=6000 or x[0].shape[1]!=35 or x[1].shape[1]!=1 or not 1<=x[2].shape[1]<=63 or x[2].shape[1]%2!=1:
        raise ValueError('固定Meiの同フレームMCP35/LF01/奇数LPFを要求')
    voiced=x[1][:,0]>0
    if np.any(x[1][~voiced]!=-1e10) or np.any((np.exp(x[1][voiced,0])<70)|(np.exp(x[1][voiced,0])>800)):
        raise ValueError('LF0 sentinelまたは有声F0範囲が不正')
    expected=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
    if settings!=expected: raise ValueError('固定Mei設定だけを許可')
    return x
def synthesize(params,settings):
    x=validated(params,settings);before=[ah(v) for v in x]
    raw=np.empty(len(x[0])*240,dtype=np.float64)
    if not _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],raw.ctypes.data_as(P),len(raw)):
        raise RuntimeError('HTS配列vocoderの入力/有限性検査に不通過')
    assert [ah(v) for v in x]==before
    audio=signal.resample_poly(raw/32768.,1,2)
    n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=env;audio[-n:]*=env[::-1]
    assert len(audio)==len(x[0])*120 and np.isfinite(audio).all()
    return audio,dict(renderer='HTS-pulse-noise-MLSA',input_parameter_hashes=before,input_streams_unchanged=True,
        frames_original=len(x[0]),fs=48000,output_fs=24000,sample_count_24k=len(audio),alpha=.55,beta=0.,volume=1.,stage=0,use_log_gain=False,
        clock='native全フレームを順次生成。先頭複製/末尾frame切りなし。',
        source='対応版HTS_Vocoder_initialize/synthesize/clear',saved_waveform_analysis_used=False,
        neural_model=False,utterance_lookup=False)
'''
files['build.py']='''"""外部の所有一時領域を使い、対応版C入口だけを構築する。"""
from paths import *
import subprocess
def main():
    b=Budget();b.recover()
    tool=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    assert tool.is_file() and sdk.is_dir()
    cmd=[str(tool),'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),'-I'+str(HERE/'vendor'),str(HERE/'hts_arrays.c'),'-o',str(HERE/'hts_arrays.dylib')]
    with b.job(NAME,'setup','HTS全frame配列入口のC build',reserve_bytes=20000000) as job:
        with b.workspace(job,'clang中間物とcache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'hts_arrays.dylib',100000,job):
                result=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,source_sha256=digest(HERE/'hts_arrays.c'),binary_sha256=digest(HERE/'hts_arrays.dylib'),temporary_removed=True,new_download=0),job)
    print(b.reconcile(),flush=True)
if __name__=='__main__': main()
'''
s=(PREV/'summarize_v5.py').read_text().replace('from controller_v4 import verify','from controller import verify')
s=s.replace("    fix=read(HERE/'summary-routing-amendment-04.json')\n    assert digest(Path(__file__))==fix['source_sha256']\n",'')
s=re.sub(r'\b160\b','192',s).replace('voicing_AP_research_only=True','vocoder_LF0_research_only=True')
start=s.index('        factorial={}');end=s.index('        summary=dict(',start)
s=s[:start]+'''        factorial={}
        for metric in ['missing_support','DIO_error','ACF_error','whisper_errors','reazon_errors']:
            values={}
            for method in p['variants']:
                if metric.endswith('_errors'):
                    pairs=content[method][metric.split('_')[0]]['pairs']
                    values[method]=sum(r['errors'] for r in pairs) if all(r['status']=='completed' for r in pairs) else None
                else:
                    pairs=engineering[method]['pairs']
                    if metric=='missing_support':
                        values[method]=sum(len(r['measurement']['missing_support']) for r in pairs) if all('measurement' in r for r in pairs) else None
                    else:
                        key='dio_error_semitones' if metric=='DIO_error' else 'acf_error_semitones'
                        points=[r.get('pitch_gate',{}).get(key) for r in pairs]
                        values[method]=sum(points)/len(points) if all(x is not None for x in points) else None
            complete=all(x is not None for x in values.values())
            delta={m:values['hts_'+m]-values[m] for m in ['native','calibrated','voicing']} if complete else {}
            factorial[metric]=dict(values=values,complete=complete,lower_is_better=True,renderer_delta_at_each_LF0=delta,
                renderer_main=sum(delta.values())/3 if complete else None,
                calibration_main=((values['calibrated']-values['native'])+(values['hts_calibrated']-values['hts_native']))/2 if complete else None,
                voicing_addition_main=((values['voicing']-values['calibrated'])+(values['hts_voicing']-values['hts_calibrated']))/2 if complete else None,
                renderer_calibration_interaction=delta['calibrated']-delta['native'] if complete else None,
                renderer_voicing_interaction=delta['voicing']-delta['calibrated'] if complete else None)
'''+s[end:];files['summarize.py']=s
files['closeout.py']=(PREV/'closeout_v4.py').read_text().replace('from controller_v4 import verify','from controller import verify').replace('160','192').replace('320','384').replace('progress-0016','progress-0018').replace('# 有声補完・非周期成分2×2の比較結果','# 同一3streamのvocoder×LF0比較結果').replace('×5方式','×6方式')
files['test_controls.py']=(PREV/'test_controls_v2.py').read_text().replace('runtime-bundle-v2','runtime-bundle')
with b.job(NAME,'setup','言語別検査後に同一パラメータvocoder実装を保存',reserve_bytes=8000000) as job:
    for n,s in files.items():
        if n.endswith('.py'): ast.parse(s,filename=n)
        b.write(HERE/n,s.encode(),job)
    for path in (SOURCE/'vendor').glob('*.h'):b.write(HERE/'vendor'/path.name,path.read_bytes(),job)
    b.write(HERE/'HTS-BSD-NOTICE.txt',(SOURCE/'vendor/HTS_hidden.h').read_bytes(),job)
    b.save(HERE/'implementation-audit.json',dict(source_hashes={n:digest(HERE/n) for n in files},Python_AST_pass=True,C_validation='build.pyのclangで実施',shared_rules_unchanged=True,old_frozen_results_unchanged=True,not_generated=True),job)
print('実装保存',len(files),flush=True);print(b.reconcile(),flush=True)
