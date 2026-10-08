"""旧封印・対応一次実装・全依存を固定し、観測入口だけを構築する。"""
from paths import *
import ast,subprocess
def main():
    b=Budget();b.recover()
    with b.job(NAME,'setup','一次HTSの純粋観測変更と既存依存の同梱',reserve_bytes=20_000_000) as j:
        original=(SOURCE/'upstream/HTS_vocoder.c').read_text()
        assert digest(SOURCE/'upstream/HTS_vocoder.c')=='f5b97b331639af246dea3871a74bca512f40d96618702f6512d8e0fbed86cdd9'
        needle='x = HTS_Vocoder_get_excitation(v, lpf);';assert original.count(needle)==1
        observed=original.replace(needle,'x = tr_observe(v, lpf);')
        b.write(HERE/'HTS_vocoder_observed.c',observed.encode(),j)
        b.save(HERE/'source-change-audit.json',dict(primary_sha256=digest(SOURCE/'upstream/HTS_vocoder.c'),
            source_commit='214e26dfb7f728ff9db39c14a59db709abcc121d',
            replaced_call_site_count=1,old_call=needle,new_call='x = tr_observe(v, lpf);',
            all_other_primary_source_bytes_unchanged=True,observer_no_vocoder_state_writes=True,
            no_new_synthesis_rule=True,excitation_truth_only=True,perceived_pitch_truth=False),j)
        names=['local_renderer.py','local_hts-v2.dylib','hts_arrays.py','hts_arrays.dylib','acoustics.py',
               'postfilter_v2.py','postfilter_v2.dylib','HTS-BSD-NOTICE.txt','LICENSE-WORLD.txt']
        previous=read(PREVIOUS/'artifact-seal.json')['files'];bundle=HERE/'runtime-bundle'
        for n in names:
            p=PREVIOUS/'runtime-bundle'/n;assert digest(p)==previous[str(p.relative_to(REPO))]
            b.write(bundle/n,p.read_bytes(),j)
        package=LATEST/'runtime-bundle/packages-v2'
        latest=read(LATEST/'artifact-seal.json')['files']
        for p in package.rglob('*'):
            if p.is_file():
                assert digest(p)==latest[str(p.relative_to(REPO))]
                b.write(bundle/'packages-v2'/p.relative_to(package),p.read_bytes(),j)
        b.write(bundle/'period_measurement.py',(HERE/'period_measurement.py').read_bytes(),j)
        b.write(bundle/'observer.py',(HERE/'observer.py').read_bytes(),j)
        # pyworldのパスを、ライブラリimport前に子が指定する。
    tool=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    assert tool.is_file() and sdk.is_dir()
    cmd=[str(tool),'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),
        '-I'+str(HERE/'vendor'),'-I'+str(HERE),str(HERE/'observer.c'),'-o',str(HERE/'runtime-bundle/observer.dylib')]
    with b.job(NAME,'setup','観測Cのbuildと専用一時物の削除',reserve_bytes=20_000_000) as j:
        with b.workspace(j,'clang中間物とcache',16_000_000,32_000_000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'runtime-bundle/observer.dylib',100_000,j):
                result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=result.stderr,returncode=result.returncode,
            source_sha256=digest(HERE/'observer.c'),binary_sha256=digest(HERE/'runtime-bundle/observer.dylib'),
            all_temporary_removed=True,new_download=0),j)
    with b.job(NAME,'setup','観測前の全ソース・旧128入力契約を固定',reserve_bytes=400_000) as j:
        p=read(PREVIOUS/'protocol.json');records=[]
        for row in p['rows']:
            for condition in p['conditions']:
                for method in ['hts_native','hts_postfilter','hts_voicing','hts_voicing_postfilter']:
                    base=PREVIOUS/'render'/row['id']/condition/method;x=read(base.with_suffix('.json'))
                    assert x['status']=='completed' and digest(REPO/x['wav'])==x['wav_sha256']
                    assert digest(base.with_suffix('.json'))==read(PREVIOUS/'artifact-seal.json')['files'][str(base.with_suffix('.json').relative_to(REPO))]
                    records.append(dict(id=row['id']+'/'+condition+'/'+method,row=row,condition=condition,method=method,
                        old_record=str(base.with_suffix('.json').relative_to(REPO)),old_record_sha256=digest(base.with_suffix('.json')),
                        parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),
                        native_initial=str(base.with_name('native').with_suffix('.npz').relative_to(REPO)),
                        native_initial_sha256=digest(base.with_name('native').with_suffix('.npz'))))
        assert len(records)==128
        b.save(HERE/'protocol.json',dict(records=records,conditions=p['conditions'],registration_sha256=digest(HERE/'registration.json'),
            inputs_are_existing_audit_only=True,no_prospective_quality_claim=True,protected_confirmation_opened=False),j)
        bundle=HERE/'runtime-bundle'
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},
            observer_only=True,diagnostic_from_saved_parameters=True,final_generator_qualification=False),j)
        for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
        b.save(HERE/'execution-contract.json',dict(registration_sha256=digest(HERE/'registration.json'),
            protocol_sha256=digest(HERE/'protocol.json'),source_hashes={p.name:digest(p) for p in HERE.glob('*.py')},
            C_source_sha256=digest(HERE/'observer.c'),observed_primary_sha256=digest(HERE/'HTS_vocoder_observed.c'),
            runtime_manifest_sha256=digest(bundle/'manifest.json'),all_conditions_fixed_before_output=True,
            observer_only=True,old_gates_unchanged=True,quality_goal_completed=False),j)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
