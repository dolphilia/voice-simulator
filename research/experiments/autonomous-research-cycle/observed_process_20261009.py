"""所有workspaceにログを置き、子process groupのRSS/壁時計/出力上限を観測。"""
import os,signal,subprocess,time,resource
from pathlib import Path

def run_observed(cmd,env,work,*,label,timeout=1500,memory_bytes=8_000_000_000,maximum_log_bytes=2_000_000):
    work=Path(work).resolve()
    if work!=Path(env['TMPDIR']).resolve() or not work.is_dir():raise ValueError('所有一時領域が必要')
    if not label or any(x not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for x in label):raise ValueError('ログ名不正')
    out=work/(label+'-stdout.txt');err=work/(label+'-stderr.txt')
    started=time.monotonic();peak=0;largest_group=0;samples=0;measurement_failures=0;reason=None
    with out.open('xb') as fo,err.open('xb') as fe:
        child=subprocess.Popen(cmd,env=env,stdout=fo,stderr=fe,start_new_session=True)
        while True:
            try:
                ps=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,rss='],capture_output=True,text=True,env=env,timeout=3,check=True)
                rows=[list(map(int,x.split())) for x in ps.stdout.splitlines() if len(x.split())==4]
                members=[x for x in rows if x[2]==child.pid];amount=sum(x[3]*1024 for x in members)
                peak=max(peak,amount);largest_group=max(largest_group,len(members));samples+=1
            except (OSError,ValueError,subprocess.SubprocessError):measurement_failures+=1
            elapsed=time.monotonic()-started;own=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            own_bytes=int(own if sys_platform_is_darwin() else own*1024)
            if peak+own_bytes>memory_bytes:reason='observed-memory-target'
            elif elapsed>timeout:reason='wall-timeout'
            elif out.stat().st_size+err.stat().st_size>maximum_log_bytes:reason='log-output-cap'
            if reason:
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait()
                break
            if child.poll() is not None:break
            time.sleep(.05)
        code=child.wait()
    stdout=out.read_text();stderr=err.read_text()
    record=dict(returncode=code,wall_seconds=time.monotonic()-started,sampled_process_group_peak_RSS_bytes=peak,controller_ru_maxrss_bytes=own_bytes,combined_observed_RSS_upper_bytes=peak+own_bytes,group_max_processes=largest_group,ps_samples=samples,ps_measurement_failures=measurement_failures,sampling_seconds=.05,continuous_exact_peak=False,shared_pages_may_be_double_counted=True,detached_process_groups_not_tracked=True,termination_reason=reason,stdout_bytes=out.stat().st_size,stderr_bytes=err.stat().st_size,log_paths_owned=True)
    return stdout,stderr,record

def sys_platform_is_darwin():
    import sys
    return sys.platform=='darwin'
