"""18固定条件・DSP計測・C接続を生成前に検査する。"""
import json,subprocess,sys
from pathlib import Path
from campaign import *

def main():
    b=LocalBudget()
    with b.job('setup','既存clangで対応版C wrapperを構築',1_000_000):
        command=['/usr/bin/clang','-dynamiclib','-O2','-undefined','dynamic_lookup','-I'+str(ROOT/'vendor'),str(ROOT/'counter.c'),'-o',str(ROOT/'counter.dylib')]
        with Storage().external(ROOT/'counter.dylib',500000):
            p=subprocess.run(command,text=True,capture_output=True,timeout=60)
        save(RESULT/'build.json',{'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,
            'source_sha256':digest(ROOT/'counter.c'),'binary_sha256':digest(ROOT/'counter.dylib') if (ROOT/'counter.dylib').exists() else None,
            'source_download_bytes':0})
        p.check_returncode()
    with b.job('setup','18列・固定支持域・対照条件・依存を固定',2_000_000):
        from renderer import tests
        save(RESULT/'negative-tests.json',tests())
        import pyopenjtalk.htsengine,numpy as np,scipy
        sys.path.insert(0,str(PILOT/'.cache/packages'));import pyworld
        proof=read(ERES/'next-proposal-preparation.json')
        assert len(proof['rows'])==18 and sum(r['phase']=='development' for r in proof['rows'])==10
        old=read(SRES/'protocol.json');texts={r['id']:r for r in old['selection_rows']+old['rows']}
        contracts={};rows=[]
        for r in proof['rows']:
            for n,h in [('source_record','source_record_sha256'),('wav','wav_sha256'),('parameter_lf0_source_npz','parameter_lf0_source_npz_sha256')]:assert digest(REPO/r[n])==r[h]
            record=read(REPO/r['source_record']);source=REPO/r['source_record'];support=source.parent/'support-contract.json'
            assert record['status']=='completed' and record['E0_pass'] and record['internal_unchanged']
            row=texts[r['id'].split('/')[0]]
            rows.append({**r,'full_context_labels':row['full_context_labels'],'settings':record['settings'],
                'support_contract':str(support.relative_to(REPO)),'support_contract_sha256':digest(support),
                'focus_indices':sorted({d['index'] for d in read(ERES/'support-cause-audit.json')['rows'] if d['id'].rsplit('/',1)[0]==r['id'].rsplit('/',1)[0]})})
            contracts[str(support.relative_to(REPO))]=digest(support)
        assert len(contracts)==7
        libs={str(Path(pyopenjtalk.htsengine.__file__).relative_to(REPO)):digest(pyopenjtalk.htsengine.__file__),
            str(Path(pyworld.__file__).relative_to(REPO)):digest(pyworld.__file__)}
        for p in Path(pyworld.__file__).parent.glob('*.so'):libs[str(p.relative_to(REPO))]=digest(p)
        assert libs[str(Path(pyopenjtalk.htsengine.__file__).relative_to(REPO))]==proof['binary_sha256']
        save(RESULT/'protocol.json',{'rows':rows,'planned_render_calls':54,'modes':['baseline','flat_spectrum','simple_excitation'],
            'baseline_gate_before_contrasts':18,'teacher_ai_fit_inverse_download_calls':0,
            'proposal_sha256':digest(REPO/'docs/plans/source-filter-counterfactual-proposal-2026-10-03.md'),
            'schedule_source_sha256':digest(ERES/'next-proposal-preparation.json'),'support_contracts':contracts,
            'measurements':{'dio':{'f0_floor':70.,'f0_ceil':800.,'frame_period':5.,'refinement':'StoneMask'},
                'missing_rule':{'minimum_frames':3,'minimum_fraction':.5},'lf0_reference':'保存MLPG列。日本語の音響正解ではない。',
                'lf0_comparison':'同一5ms時刻の内部LF0とDIOの検出点を比較。欠損・偽有声を別記。'},
            'dependencies':libs,'versions':{'numpy':np.__version__,'scipy':scipy.__version__,'pyworld':pyworld.__version__,'pyopenjtalk':'0.4.1'},
            'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and 'results' not in p.parts},
            'no_retries':True,'quality_certified':False,'confirmation_is_mechanism_diagnostic_only':True})
        denied=[]
        site=OLD/'.venv-eval/lib/python3.11/site-packages'
        for name in ('torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'):
            if (site/name).exists():denied.append(site/name)
        denied += [SRES/'models',PILOT/'results/nas-pilot-20261002-v1/teacher',PILOT/'.cache/reazonspeech',OLD/'.cache',REPO/'research/data']
        profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in denied)+')\n'
        write_checked(RESULT/'profile.sb',profile.encode('utf8'))
        save(RESULT/'entry-audit.json',{'passed':True,'source_rows':18,'source_supports':7,'new_render_calls':0,'source_and_parameters_frozen':True,
            'no_neural_inference_required':True,'network_deny_profile_sha256':digest(RESULT/'profile.sb'),'quality_certified':False})
    print({'rows':18,'supports':7,'entry_passed':True},flush=True)

if __name__=='__main__':main()
