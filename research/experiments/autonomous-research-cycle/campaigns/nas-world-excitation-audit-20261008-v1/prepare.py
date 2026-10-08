"""固定commitの必要header取得と純粋観測build。初出力前に契約固定。"""
from paths import *
import ast,re,subprocess,urllib.request
COMMIT='8d79b88b7dd92e8a132996cf74080b2d6f881b98'
def main():
    b=Budget();b.recover()
    assert digest(PRIMARY/'synthesis.cpp')=='9888973e28f2194a0eb9807e18e36680f3d912bef3ddf174dc640fedc4e08b4c'
    with b.job(NAME,'download','固定WORLD commit必要headerのみ取得',count=200000,reserve_bytes=250000) as j:
        pending=['synthesis.h','common.h','constantnumbers.h','matlabfunctions.h'];seen={};total=0
        while pending:
            name=pending.pop(0)
            if name in seen:continue
            assert re.fullmatch(r'[a-z_]+\.h',name)
            path=HERE/'vendor/world'/name;url=f'https://raw.githubusercontent.com/mmorise/World/{COMMIT}/src/world/{name}'
            assert not path.exists()
            with urllib.request.urlopen(url,timeout=30) as response:
                body=response.read(60001);assert len(body)<=60000
            total+=len(body);assert total<=200000
            b.write(path,body,j);seen[name]=dict(url=url,sha256=digest(path),bytes=len(body))
            pending.extend(re.findall(r'#include\s+"world/([^"]+)"',body.decode()))
        b.save(HERE/'header-provenance.json',dict(commit=COMMIT,headers=seen,actual_bytes=total,charged_bytes=200000,maximum_response_bytes=60000),j)
    with b.job(NAME,'setup','一次sourceを2つの観測読取hookのみで固定',reserve_bytes=500000) as j:
        original=(PRIMARY/'synthesis.cpp').read_text()
        n1='      pulse_locations_time_shift, interpolated_vuv);'
        n2='  double sqrt_noise_size = sqrt(static_cast<double>(noise_size));'
        h1=n1+'\n  ObsTime(number_of_pulses,y_length,pulse_locations_index,pulse_locations_time_shift,interpolated_vuv);'
        h2='  ObsResponse(fft_size,noise_size,current_vuv,aperiodic_ratio[0],periodic_response,aperiodic_response);\n'+n2
        assert original.count(n1)==1 and original.count(n2)==1
        observed=original.replace(n1,h1).replace(n2,h2)
        assert observed.replace(h1,n1).replace(h2,n2)==original
        b.write(HERE/'synthesis_observed.cpp',observed.encode(),j)
        b.write(HERE/'LICENSE-WORLD.txt',(CONVERT/'LICENSE-WORLD.txt').read_bytes(),j)
        b.save(HERE/'source-change-audit.json',dict(primary_sha256=digest(PRIMARY/'synthesis.cpp'),commit=COMMIT,
            hooks=2,reverse_patch_byte_exact=True,observer_only_writes_own_buffers=True,
            original_state_coefficients_random_filter_unchanged=True,installed_binary_direct_trace=False,
            recompilation_compatibility_required_for_every_old_wave=True),j)
    tool=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    assert tool.is_file() and sdk.is_dir()
    cmd=[str(tool),'-dynamiclib','-O2','-std=c++11','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),'-I'+str(HERE/'vendor'),'-I'+str(HERE),str(HERE/'observer.cpp'),'-o',str(HERE/'observer.dylib')]
    with b.job(NAME,'setup','観測Cの固定ABI build/外部一時後始末',reserve_bytes=20000000) as j:
        with b.workspace(j,'clang中間物とcache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            with b.external_output(HERE/'observer.dylib',200000,j):
                result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,returncode=result.returncode,stderr=result.stderr,binary_sha256=digest(HERE/'observer.dylib'),all_temporary_removed=True),j)
    with b.job(NAME,'setup','全768件観測前のコード/依存/入力hashを固定',reserve_bytes=300000) as j:
        for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
        inputs={str(p.relative_to(REPO)):digest(p) for p in [PRIMARY/'synthesis.cpp',CONVERT/'world_renderer2.py',PERIOD/'runtime-bundle/manifest.json',ROOT/'campaign-allocation-approval-20261008-0001.json']}
        b.save(HERE/'execution-contract.json',dict(registration_sha256=digest(HERE/'registration.json'),protocol_sha256=digest(HERE/'protocol.json'),
            source_hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.suffix in ['.py','.cpp','.h','.dylib']},inputs=inputs,
            gates_unchanged=True,quality_goal_completed=False),j)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
